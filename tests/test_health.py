"""The checks that matter: silent failures surface, stale failures do not."""

from __future__ import annotations

from machine.health import endpoint_finding, latest_runs, render, run_findings


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


def test_endpoint_without_expected_field_is_a_problem():
    assert endpoint_finding("summary", "https://x", "count", {"other": 1})
    assert endpoint_finding("summary", "https://x", "count", "<html>404</html>")
    assert endpoint_finding("summary", "https://x", "count", {"count": 147}) is None


def test_render_all_clear_and_problem_table():
    config = {"repos": [{"name": "org/repo"}], "endpoints": [{}]}
    assert "all clear" in render([], config)
    problems = render(run_findings("org/repo", "main", [_run("deploy", "cancelled")]), config)
    assert "1 problem" in problems and "| cancelled |" in problems
