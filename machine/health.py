"""Org health check: the newest run of every workflow, plus the public endpoints.

Why this exists: automations here fail quietly. A job that hits GitHub's 6-hour
ceiling is reported as *cancelled*, not failed; a workflow that does all its
work and dies at `git push` looks like nothing happened; a Pages deploy blocked
by an environment rule leaves no log at all. Each of those went unnoticed for
days. This treats anything other than success/skipped as a problem.

Run with: python -m machine.health [--issue]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

API = "https://api.github.com"
CONFIG = Path(__file__).with_name("repos.json")
ISSUE_TITLE = "Org health report"

# Conclusions that mean the run did its job. Everything else is surfaced —
# `cancelled` and `timed_out` included, because that is how silent failures look.
HEALTHY = {"success", "skipped", "neutral"}


@dataclass
class Finding:
    where: str
    what: str
    url: str = ""


def _get(url: str, token: str | None) -> Any:
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    if token and url.startswith(API):
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def latest_runs(runs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Newest completed run per workflow name. `runs` arrive newest first."""
    newest: dict[str, dict[str, Any]] = {}
    for run in runs:
        if run.get("status") != "completed":
            continue
        newest.setdefault(run["name"], run)
    return newest


def run_findings(repo: str, branch: str, runs: list[dict[str, Any]]) -> list[Finding]:
    return [
        Finding(f"{repo}@{branch} · {name}", run.get("conclusion") or "unknown", run.get("html_url", ""))
        for name, run in sorted(latest_runs(runs).items())
        if run.get("conclusion") not in HEALTHY
    ]


def endpoint_finding(name: str, url: str, expect: str, body: Any) -> Finding | None:
    if not isinstance(body, dict) or expect not in body:
        return Finding(name, f"response has no `{expect}` field", url)
    return None


def check(config: dict[str, Any], token: str | None) -> list[Finding]:
    findings: list[Finding] = []
    for repo in config["repos"]:
        name = repo["name"]
        try:
            workflows = _get(f"{API}/repos/{name}/actions/workflows?per_page=100", token)
        except urllib.error.URLError as exc:
            findings.append(Finding(name, f"could not list workflows: {exc}"))
            continue
        for branch in repo["branches"]:
            # One query per workflow, not "the last N runs": a weekly job would
            # scroll out of any fixed window behind the daily ones, and weekly
            # jobs are exactly the ones that fail unnoticed.
            runs: list[dict[str, Any]] = []
            for workflow in workflows.get("workflows", []):
                if workflow.get("state") != "active":
                    continue
                url = (f"{API}/repos/{name}/actions/workflows/{workflow['id']}/runs"
                       f"?branch={branch}&status=completed&per_page=1")
                try:
                    runs.extend(_get(url, token).get("workflow_runs", []))
                except urllib.error.URLError as exc:
                    findings.append(Finding(f"{name} · {workflow['name']}", f"could not read runs: {exc}"))
            findings.extend(run_findings(name, branch, runs))

    for endpoint in config["endpoints"]:
        try:
            body = _get(endpoint["url"], None)
        except (urllib.error.URLError, json.JSONDecodeError) as exc:
            findings.append(Finding(endpoint["name"], f"unreachable: {exc}", endpoint["url"]))
            continue
        finding = endpoint_finding(endpoint["name"], endpoint["url"], endpoint["expect"], body)
        if finding:
            findings.append(finding)
    return findings


def render(findings: list[Finding], config: dict[str, Any]) -> str:
    checked = ", ".join(repo["name"].split("/")[1] for repo in config["repos"])
    if not findings:
        return f"## Org health: all clear\n\nChecked {checked} and {len(config['endpoints'])} public endpoints.\n"
    lines = [
        f"## Org health: {len(findings)} problem(s)",
        "",
        f"Checked {checked} and {len(config['endpoints'])} public endpoints. "
        "`cancelled` and `timed_out` are listed on purpose: that is how a job "
        "killed at a time limit reports itself.",
        "",
        "| Where | Result |",
        "|---|---|",
    ]
    for f in findings:
        where = f"[{f.where}]({f.url})" if f.url else f.where
        lines.append(f"| {where} | {f.what} |")
    return "\n".join(lines) + "\n"


def publish(body: str, token: str, repo: str) -> None:
    """Keep one open issue up to date instead of opening one per run."""
    def call(method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(f"{API}{path}", data=data, method=method, headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        })
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8") or "null")

    issues = call("GET", f"/repos/{repo}/issues?state=open&per_page=100")
    existing = next((i for i in issues if i.get("title") == ISSUE_TITLE), None)
    if existing:
        call("PATCH", f"/repos/{repo}/issues/{existing['number']}", {"body": body})
    else:
        call("POST", f"/repos/{repo}/issues", {"title": ISSUE_TITLE, "body": body})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--issue", action="store_true", help="update the health issue")
    args = parser.parse_args()

    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    token = os.environ.get("GITHUB_TOKEN")
    findings = check(config, token)
    report = render(findings, config)
    print(report)

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        Path(summary).write_text(report, encoding="utf-8")
    if args.issue and token:
        publish(report, token, os.environ.get("GITHUB_REPOSITORY", "GetTechAPI/TechMachine"))
    # The report is the output; a red run would only add a second alert.
    return 0


if __name__ == "__main__":
    sys.exit(main())
