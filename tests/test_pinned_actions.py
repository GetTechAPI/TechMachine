"""Every action is GitHub-owned and pinned by full commit SHA.

The organisation only runs such actions, in this repository's workflows and
in the ones the satellite template generates. A tag (`@v7`) can be moved to
other code; a SHA cannot.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_DIRS = (
    ROOT / ".github" / "workflows",
    ROOT / "machine" / "satellite_template" / ".github" / "workflows",
)
USES = re.compile(r"^\s*(?:-\s*)?uses:\s*(\S+)", re.MULTILINE)
PINNED = re.compile(r"actions/[a-z0-9-]+@[0-9a-f]{40}\Z")


def unpinned(workflow_text: str) -> list[str]:
    """The `uses:` references that are not `actions/<name>@<40-hex-sha>`."""
    return [ref.strip("'\"") for ref in USES.findall(workflow_text)
            if not PINNED.match(ref.strip("'\""))]


def workflow_files() -> list[Path]:
    return sorted(path for folder in WORKFLOW_DIRS
                  for pattern in ("*.yml", "*.yaml") for path in folder.glob(pattern))


def test_both_workflow_directories_are_scanned():
    folders = {path.parent for path in workflow_files()}
    assert folders == set(WORKFLOW_DIRS)


@pytest.mark.parametrize("path", workflow_files(), ids=lambda p: p.relative_to(ROOT).as_posix())
def test_actions_are_github_owned_and_pinned_by_sha(path: Path):
    text = path.read_text(encoding="utf-8")
    assert USES.search(text), f"{path} uses no action; is the pattern still right?"
    assert unpinned(text) == []


def test_the_rule_rejects_tags_branches_and_other_owners():
    sha = "3d3c42e5aac5ba805825da76410c181273ba90b1"
    assert unpinned(f"      - uses: actions/checkout@{sha} # v7.0.1\n") == []
    assert unpinned(f"        uses: actions/deploy-pages@{sha}\n") == []
    assert unpinned("      - uses: actions/checkout@v7\n") == ["actions/checkout@v7"]
    assert unpinned("      - uses: actions/checkout@main\n") == ["actions/checkout@main"]
    assert unpinned(f"      - uses: someone/checkout@{sha}\n") == [f"someone/checkout@{sha}"]
    assert unpinned(f"      - uses: actions/checkout@{sha[:12]}\n") == [f"actions/checkout@{sha[:12]}"]
