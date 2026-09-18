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
