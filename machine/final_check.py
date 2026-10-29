"""Final check on an important pull request, posted as TechEngineBot.

TechEngineBot is a real account and was suspended once for spam, so it keeps
its standing by speaking rarely: only on PRs a person marks with the
`final-check` label, as one comment per PR that later runs edit in place, plus
one commit status. A status can be made a required check; neither edits nor
statuses notify anyone.

The verdict only reads what GitHub already knows — it never checks out or
runs the PR's code, so it is safe under `pull_request_target`.

Run with: python -m machine.final_check --repo OWNER/NAME --pr N [--publish]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from machine.health import API, HEALTHY, _get, _get_text, foreign_secrets

MARKER = "<!-- techenginebot:final-check -->"
CONTEXT = "final-check"
# git-flow: main only moves through a release from develop, or a hotfix.
RELEASE_SOURCES = ("develop", "hotfix/")


@dataclass
class Verdict:
    problems: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    passed: list[str] = field(default_factory=list)

    @property
    def state(self) -> str:
        if self.problems:
            return "failure"
        return "pending" if self.pending else "success"


def evaluate(pr: dict[str, Any], check_runs: list[dict[str, Any]], statuses: list[dict[str, Any]],
             workflow_texts: dict[str, str], allowed: set[str] = frozenset()) -> Verdict:
    v = Verdict()

    if pr.get("draft"):
        v.problems.append("the PR is still a draft")

    base, head = pr["base"]["ref"], pr["head"]["ref"]
    if base == "main" and not head.startswith(RELEASE_SOURCES):
        v.problems.append(f"`{head}` → `main`: main only takes a release from develop or a hotfix")
    else:
        v.passed.append(f"`{head}` → `{base}` follows git-flow")

    if pr.get("mergeable") is False:
        v.problems.append("merge conflicts with the base branch")

    # Our own job and status would otherwise wait on themselves.
    runs = [r for r in check_runs if CONTEXT not in r.get("name", "")]
    others = [s for s in statuses if s.get("context") != CONTEXT]
    unsettled = len(v.problems) + len(v.pending)
    for run in runs:
        if run.get("status") != "completed":
            v.pending.append(f"check `{run['name']}` is still running")
        elif run.get("conclusion") not in HEALTHY:
            v.problems.append(f"check `{run['name']}`: {run.get('conclusion')}")
    for status in others:
        if status.get("state") == "pending":
            v.pending.append(f"status `{status['context']}` is pending")
        elif status.get("state") != "success":
            v.problems.append(f"status `{status['context']}`: {status.get('state')}")
    if not runs and not others:
        # Passing a commit nothing has looked at would be a silent failure of its own.
        v.problems.append("no other check ran on this commit — nothing to confirm")
    elif len(v.problems) + len(v.pending) == unsettled:
        v.passed.append(f"{len(runs) + len(others)} other check(s) passed")

    for path, text in sorted(workflow_texts.items()):
        names = foreign_secrets(text, allowed)
        if names:
            v.problems.append(f"`{path}` uses {', '.join(names)} — automation must not run as a person")
    if workflow_texts and not any("automation must not" in p for p in v.problems):
        v.passed.append("changed workflows use only GITHUB_TOKEN")
    return v


def render(v: Verdict, sha: str) -> str:
    title = {"success": "passed", "failure": "not ready", "pending": "waiting on checks"}[v.state]
    lines = [MARKER, f"### Final check: {title}", "", f"Checked `{sha[:7]}`.", ""]
    lines += [f"- ❌ {p}" for p in v.problems]
    lines += [f"- ⏳ {p}" for p in v.pending]
    lines += [f"- ✅ {p}" for p in v.passed]
    lines += ["", "<sub>Runs when the `final-check` label is on the PR; this comment is updated, not repeated.</sub>"]
    return "\n".join(lines) + "\n"


def _call(method: str, path: str, token: str, payload: dict[str, Any]) -> Any:
    request = urllib.request.Request(f"{API}{path}", data=json.dumps(payload).encode("utf-8"),
                                     method=method, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8") or "null")


def _paged(url: str, token: str | None, key: str | None = None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for page in range(1, 11):
        data = _get(f"{url}{'&' if '?' in url else '?'}per_page=100&page={page}", token)
        batch = data[key] if key else data
        items.extend(batch)
        if len(batch) < 100:
            break
    return items


def gather(repo: str, number: int, token: str | None, allowed: set[str]) -> tuple[dict[str, Any], Verdict]:
    pr = _get(f"{API}/repos/{repo}/pulls/{number}", token)
    sha = pr["head"]["sha"]
    runs = _paged(f"{API}/repos/{repo}/commits/{sha}/check-runs", token, "check_runs")
    statuses = _get(f"{API}/repos/{repo}/commits/{sha}/status", token).get("statuses", [])
    files = _paged(f"{API}/repos/{repo}/pulls/{number}/files", token)
    workflows = {
        f["filename"]: _get_text(f"{API}/repos/{repo}/contents/{f['filename']}?ref={sha}", token)
        for f in files
        if f["filename"].startswith(".github/workflows/") and f.get("status") != "removed"
    }
    return pr, evaluate(pr, runs, statuses, workflows, allowed)


def publish(repo: str, number: int, sha: str, body: str, state: str, token: str) -> None:
    """One comment per PR, edited in place, and one commit status."""
    comments = _paged(f"{API}/repos/{repo}/issues/{number}/comments", token)
    existing = next((c for c in comments if MARKER in (c.get("body") or "")), None)
    if existing:
        comment = _call("PATCH", f"/repos/{repo}/issues/comments/{existing['id']}", token, {"body": body})
    else:
        comment = _call("POST", f"/repos/{repo}/issues/{number}/comments", token, {"body": body})
    description = {"success": "Ready to merge", "failure": "Not ready — see the comment",
                   "pending": "Waiting on other checks"}[state]
    _call("POST", f"/repos/{repo}/statuses/{sha}", token, {
        "state": state, "context": CONTEXT, "description": description,
        "target_url": comment.get("html_url", ""),
    })


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", required=True, help="OWNER/NAME")
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--publish", action="store_true", help="comment and set the status")
    parser.add_argument("--wait-minutes", type=int, default=0,
                        help="poll this long for other checks to finish before judging")
    parser.add_argument("--allowed-secret", action="append", default=[])
    args = parser.parse_args(argv)

    token = os.environ.get("GITHUB_TOKEN")
    allowed = set(args.allowed_secret)
    deadline = time.monotonic() + args.wait_minutes * 60
    pr, verdict = gather(args.repo, args.pr, token, allowed)
    # Waiting here instead of posting "pending" keeps it to one meaningful update.
    while verdict.state == "pending" and time.monotonic() < deadline:
        time.sleep(60)
        pr, verdict = gather(args.repo, args.pr, token, allowed)

    body = render(verdict, pr["head"]["sha"])
    print(body)
    if args.publish:
        if not token:
            raise SystemExit("--publish needs GITHUB_TOKEN (TechEngineBot's token)")
        publish(args.repo, args.pr, pr["head"]["sha"], body, verdict.state, token)
    # The status is the gate; a red job would only repeat it.
    return 0


if __name__ == "__main__":
    sys.exit(main())
