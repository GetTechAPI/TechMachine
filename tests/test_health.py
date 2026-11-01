"""The checks that matter: silent failures surface, stale failures do not."""

from __future__ import annotations

import urllib.error

from machine import health

from machine.health import endpoint_finding, latest_runs, leftover_workflow, render, run_findings


def _run(name: str, conclusion: str | None, status: str = "completed") -> dict:
    return {"name": name, "status": status, "conclusion": conclusion, "html_url": f"https://x/{name}"}


def test_cancelled_is_a_problem():
    # A job killed at GitHub's 6-hour limit reports `cancelled`, not `failure`.
    findings = run_findings("org/repo", "main", [_run("dump-refresh", "cancelled")])
    assert [f.what for f in findings] == ["cancelled"]


def test_timed_out_is_a_problem():
    assert run_findings("org/repo", "main", [_run("deploy", "timed_out")])


def test_success_and_skipped_are_healthy():
    runs = [_run("a", "success"), _run("b", "skipped")]
    assert run_findings("org/repo", "main", runs) == []


def test_only_the_newest_run_per_workflow_counts():
    # Newest first, as the API returns them: a fixed failure is not reported.
    runs = [_run("deploy", "success"), _run("deploy", "failure")]
    assert run_findings("org/repo", "main", runs) == []


def test_a_new_failure_after_a_success_is_reported():
    runs = [_run("deploy", "failure"), _run("deploy", "success")]
    assert len(run_findings("org/repo", "main", runs)) == 1


def test_in_progress_runs_are_ignored():
    runs = [_run("dump", None, status="in_progress"), _run("dump", "success")]
    assert latest_runs(runs)["dump"]["conclusion"] == "success"


def test_dependabot_workflow_without_config_is_a_leftover():
    # TechAPI removed dependabot.yml; GitHub keeps the workflow and its old runs.
    dependabot = {"name": "Dependabot Updates", "path": "dynamic/dependabot/dependabot-updates"}
    assert leftover_workflow(dependabot, has_dependabot_config=False)
    assert not leftover_workflow(dependabot, has_dependabot_config=True)


def _contents(present: set[str]):
    """A stand-in for `_get` where only the named .github files exist."""
    def get(url: str, token: str | None) -> dict:
        if url.rsplit("/", 1)[1] not in present:
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
        return {}
    return get


def test_either_dependabot_file_counts_as_configured(monkeypatch):
    monkeypatch.setattr(health, "_get", _contents({"dependabot.yml"}))
    assert health.dependabot_configured("org/repo", None)
    monkeypatch.setattr(health, "_get", _contents({"dependabot.yaml"}))
    assert health.dependabot_configured("org/repo", None)
    monkeypatch.setattr(health, "_get", _contents(set()))
    assert not health.dependabot_configured("org/repo", None)


def test_a_failed_lookup_keeps_dependabot_checked(monkeypatch):
    def forbidden(url: str, token: str | None) -> dict:
        raise urllib.error.HTTPError(url, 403, "Forbidden", None, None)
    monkeypatch.setattr(health, "_get", forbidden)
    assert health.dependabot_configured("org/repo", None)


def test_other_workflows_are_never_leftovers():
    pages = {"name": "pages-build-deployment", "path": "dynamic/pages/pages-build-deployment"}
    ci = {"name": "test", "path": ".github/workflows/test.yml"}
    assert not leftover_workflow(pages, has_dependabot_config=False)
    assert not leftover_workflow(ci, has_dependabot_config=False)


def test_endpoint_without_expected_field_is_a_problem():
    assert endpoint_finding("summary", "https://x", "count", {"other": 1})
    assert endpoint_finding("summary", "https://x", "count", "<html>404</html>")
    assert endpoint_finding("summary", "https://x", "count", {"count": 147}) is None


def test_render_all_clear_and_problem_table():
    config = {"repos": [{"name": "org/repo"}], "endpoints": [{}]}
    assert "all clear" in render([], config)
    problems = render(run_findings("org/repo", "main", [_run("deploy", "cancelled")]), config)
    assert "1 problem" in problems and "| cancelled |" in problems


# --- automation must not run as a person -----------------------------------

from pathlib import Path  # noqa: E402

from machine.health import foreign_secrets, token_finding  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def test_personal_token_is_a_problem():
    text = "token: ${{ secrets.TECHENGINEBOT_TOKEN || secrets.TECHAPI_TOKEN }}"
    finding = token_finding("org/repo@main · weekly-ingest", text, "https://x")
    assert finding and "TECHAPI_TOKEN" in finding.what and "TECHENGINEBOT_TOKEN" in finding.what


def test_builtin_token_is_fine():
    assert token_finding("w", "GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}", "https://x") is None


def test_allowed_secret_is_fine():
    assert foreign_secrets("${{ secrets.SOME_API_KEY }}", {"SOME_API_KEY"}) == []


# TechEngineBot's token is allowed in one place: the label-triggered final check.
BOT_SECRET = {"final-check.yml": {"TECHENGINEBOT_TOKEN"}}


def test_techmachine_itself_uses_only_the_builtin_token():
    for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        allowed = BOT_SECRET.get(path.name, set())
        assert foreign_secrets(path.read_text(encoding="utf-8"), allowed) == [], path
