"""TechEngineBot's verdict: block what is broken, wait on what is running."""

from __future__ import annotations

from machine.final_check import MARKER, evaluate, render


def _pr(base: str = "develop", head: str = "feat/x", **extra) -> dict:
    return {"base": {"ref": base}, "head": {"ref": head, "sha": "abcdef1234"}, "draft": False,
            "mergeable": True, **extra}


def _run(name: str, conclusion: str | None, status: str = "completed") -> dict:
    return {"name": name, "status": status, "conclusion": conclusion}


def test_green_pr_passes():
    v = evaluate(_pr(), [_run("test", "success")], [], {})
    assert v.state == "success" and v.problems == []


def test_failed_or_cancelled_check_blocks():
    assert evaluate(_pr(), [_run("test", "failure")], [], {}).state == "failure"
    assert evaluate(_pr(), [_run("validate", "cancelled")], [], {}).state == "failure"


def test_running_check_waits():
    assert evaluate(_pr(), [_run("test", None, status="in_progress")], [], {}).state == "pending"


def test_its_own_check_and_status_are_ignored():
    runs = [_run("final-check / final-check", None, status="in_progress")]
    statuses = [{"context": "final-check", "state": "pending"}]
    assert evaluate(_pr(), runs + [_run("test", "success")], statuses, {}).state == "success"


def test_main_only_takes_a_release_or_hotfix():
    assert evaluate(_pr("main", "feat/x"), [_run("test", "success")], [], {}).state == "failure"
    assert evaluate(_pr("main", "develop"), [_run("test", "success")], [], {}).state == "success"
    assert evaluate(_pr("main", "hotfix/pages"), [_run("test", "success")], [], {}).state == "success"


def test_nothing_checked_is_not_a_pass():
    # TechAPI's release PR after its workflows were removed: no evidence at all.
    v = evaluate(_pr("main", "develop"), [], [], {})
    assert v.state == "failure" and "nothing to confirm" in v.problems[0]


def test_draft_and_conflicts_block():
    assert evaluate(_pr(draft=True), [], [], {}).state == "failure"
    assert evaluate(_pr(mergeable=False), [], [], {}).state == "failure"


def test_workflow_with_personal_token_blocks():
    text = "token: ${{ secrets.TECHAPI_TOKEN }}"
    v = evaluate(_pr(), [_run("test", "success")], [], {".github/workflows/sync.yml": text})
    assert v.state == "failure" and "TECHAPI_TOKEN" in v.problems[0]


def test_comment_carries_the_marker_so_it_is_edited_not_repeated():
    body = render(evaluate(_pr(), [_run("test", "success")], [], {}), "abcdef1234")
    assert body.startswith(MARKER) and "abcdef1" in body and "passed" in body
