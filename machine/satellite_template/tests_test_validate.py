"""Generated smoke tests: a well-formed record passes, broken ones do not."""

from __future__ import annotations

import json
from pathlib import Path

from app.validate import validate

GOOD = {"slug": "example-record", "name": "Example", "verified": False,
        "source_urls": ["https://example.org/record"]}


def _write(tmp_path: Path, rec: dict, name: str | None = None) -> Path:
    folder = tmp_path / "{{category}}" / "ex"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name or rec['slug']}.json").write_text(json.dumps(rec), encoding="utf-8")
    return tmp_path / "{{category}}"


def test_good_record_passes(tmp_path):
    assert validate(_write(tmp_path, GOOD)) == []


def test_empty_catalog_is_an_error(tmp_path):
    (tmp_path / "{{category}}").mkdir()
    assert validate(tmp_path / "{{category}}")


def test_missing_source_urls(tmp_path):
    rec = {k: v for k, v in GOOD.items() if k != "source_urls"}
    assert validate(_write(tmp_path, rec))


def test_filename_must_match_slug(tmp_path):
    assert any("filename" in e for e in validate(_write(tmp_path, GOOD, "other")))
