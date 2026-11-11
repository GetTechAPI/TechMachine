"""A generated satellite must pass its own checks, not just render."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from machine.new_satellite import PLACEHOLDER, main, render

ARGS = ["--repo", "demo-catalog", "--category", "demo", "--title", "Demo catalog",
        "--plural", "demos", "--date-field", "release_date", "--range", "rating:0:5"]


@pytest.fixture
def generated(tmp_path: Path) -> Path:
    out = tmp_path / "demo-catalog"
    assert main([*ARGS, "--out", str(out)]) == 0
    return out


# Everything a new satellite starts with. A template change shows up here, so
# adding, renaming or dropping a generated file is a deliberate edit.
EXPECTED_FILES = [
    ".github/CODEOWNERS",
    ".github/pull_request_template.md",
    ".github/workflows/deploy-pages.yml",
    ".github/workflows/final-check.yml",
    ".github/workflows/validate-data.yml",
    ".gitignore",
    "DATA_LICENSE.md",
    "LICENSE",
    "README.md",
    "app/__init__.py",
    "app/validate.py",
    "pyproject.toml",
    "site/.nojekyll",
    "site/build.py",
    "site/index.html",
    "tests/test_validate.py",
]


def test_generated_tree_is_the_expected_file_list(generated: Path):
    files = sorted(p.relative_to(generated).as_posix() for p in generated.rglob("*") if p.is_file())
    assert files == sorted(EXPECTED_FILES)
    assert (generated / "data" / "demo").is_dir()


def test_generated_metadata_is_filled_in(generated: Path):
    assert "* @Seungpyo1007" in (generated / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
    template = (generated / ".github" / "pull_request_template.md").read_text(encoding="utf-8")
    assert "data(demo):" in template and "{{" not in template


def test_no_placeholder_survives(generated: Path):
    for path in generated.rglob("*"):
        if path.is_file() and path.suffix in {".py", ".md", ".toml", ".yml", ".html"}:
            # Actions expressions (${{ ... }}) are legitimate; template ones are not.
            assert not PLACEHOLDER.search(path.read_text(encoding="utf-8")), path


def test_generated_repo_passes_its_own_tests(generated: Path, tmp_path: Path):
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         "--basetemp", str(tmp_path / "inner")],
        cwd=generated, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_generated_validator_enforces_configured_range(generated: Path):
    record = {"slug": "x", "name": "X", "verified": False,
              "source_urls": ["https://example.org"], "rating": 9, "release_date": "2020"}
    folder = generated / "data" / "demo" / "x_"
    folder.mkdir(parents=True)
    (folder / "x.json").write_text(json.dumps(record), encoding="utf-8")
    result = subprocess.run([sys.executable, "-m", "app.validate"], cwd=generated,
                            capture_output=True, text=True)
    assert result.returncode == 1
    assert "rating" in result.stdout and "release_date" in result.stdout


def test_refuses_to_overwrite(generated: Path):
    with pytest.raises(SystemExit):
        main([*ARGS, "--out", str(generated)])


def test_unknown_placeholder_is_an_error():
    with pytest.raises(KeyError):
        render("{{nope}}", {})


# TechEngineBot's token is allowed in one place: the label-triggered final check.
BOT_SECRET = {"final-check.yml": {"TECHENGINEBOT_TOKEN"}}


def test_generated_workflows_use_the_bot_token_only_in_final_check(generated: Path):
    from machine.health import foreign_secrets
    workflows = sorted((generated / ".github" / "workflows").glob("*.yml"))
    assert workflows
    for path in workflows:
        text = path.read_text(encoding="utf-8")
        assert foreign_secrets(text, BOT_SECRET.get(path.name, set())) == [], path
    final_check = (generated / ".github" / "workflows" / "final-check.yml").read_text(encoding="utf-8")
    assert foreign_secrets(final_check) == ["TECHENGINEBOT_TOKEN"]


def test_generated_final_check_is_named_after_the_repo(generated: Path):
    text = (generated / ".github" / "workflows" / "final-check.yml").read_text(encoding="utf-8")
    assert text.count("<!-- demo-catalog-final-check -->") == 2
    assert "data/demo " in text


def test_checklist_registers_the_repo_with_the_bot_secret():
    from machine.new_satellite import checklist
    text = checklist({"repo": "demo-catalog", "plural": "demos"})
    assert '"allowed_secrets": ["TECHENGINEBOT_TOKEN"]' in text
    assert "final-check" in text
