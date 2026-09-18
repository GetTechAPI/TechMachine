"""Scaffold a satellite data repository from the proven game-catalog layout.

Writes the files only. Creating the GitHub repository is left to a person —
it is an org-level change — and the remaining one-off steps are printed at
the end, including the one that silently broke game-catalog's first deploys.

Example:
    python -m machine.new_satellite --repo game-catalog --category game \
        --title "Game catalog" --plural games --date-field release_date \
        --range rating:0:5 --range metacritic:0:100 --out ../game-catalog
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

TEMPLATE = Path(__file__).with_name("satellite_template")
PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")
# Template files stored under a name git or pytest would otherwise act on.
RENAMES = {"gitignore": ".gitignore", "tests_test_validate.py": "tests/test_validate.py"}


def parse_range(text: str) -> tuple[str, float, float]:
    field, low, high = text.split(":")
    return field, float(low), float(high)


def render(text: str, values: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            raise KeyError(f"template placeholder {{{{{key}}}}} has no value")
        return values[key]
    return PLACEHOLDER.sub(replace, text)


def values_from(args: argparse.Namespace) -> dict[str, str]:
    ranges = {field: (low, high) for field, low, high in args.range}
    return {
        "repo": args.repo,
        "category": args.category,
        "title": args.title,
        "plural": args.plural,
        "description": args.description,
        "date_fields": repr(tuple(args.date_field)),
        "ranges": repr({k: (int(a) if a.is_integer() else a, int(b) if b.is_integer() else b)
                        for k, (a, b) in ranges.items()}),
    }


def scaffold(out: Path, values: dict[str, str]) -> list[Path]:
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} is not empty; refusing to overwrite")
    written = []
    for source in sorted(TEMPLATE.rglob("*")):
        if source.is_dir():
            continue
        rel = source.relative_to(TEMPLATE).as_posix()
        target = out / RENAMES.get(rel, rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix in {".py", ".md", ".toml", ".yml", ".html", ""} or source.name == "gitignore":
            target.write_text(render(source.read_text(encoding="utf-8"), values),
                              encoding="utf-8", newline="\n")
        else:
            target.write_bytes(source.read_bytes())
        written.append(target)
    (out / "data" / values["category"]).mkdir(parents=True, exist_ok=True)
    (out / "README.md").write_text(readme(values), encoding="utf-8", newline="\n")
    written.append(out / "README.md")
    return written


def readme(v: dict[str, str]) -> str:
    return f"""# {v['repo']}

[![validate-data](https://github.com/GetTechAPI/{v['repo']}/actions/workflows/validate-data.yml/badge.svg)](https://github.com/GetTechAPI/{v['repo']}/actions/workflows/validate-data.yml)

{v['description']}

Code is MIT; the records under `data/` are CC BY-SA 4.0 ([DATA_LICENSE.md](DATA_LICENSE.md)).

## Layout

```
data/{v['category']}/<bucket>/<slug>.json   # bucket = first two slug characters
app/validate.py                             # schema / slug / date / range checks
site/build.py                               # summary.json + history.json
```

A record needs `slug`, `name`, `source_urls` and `verified`.

## Self-check

```bash
python -m app.validate
python -m pytest -q
```

## Site

`python site/build.py` writes `summary.json` (`{{"count": N}}`) and
`history.json` (one point per data commit). The TechAPI homepage reads these
to count this catalog; there is deliberately no listing of every record.

## Branching (git-flow)

`develop` is the default branch; `main` is the released state and deploys the
site. Pull requests target `develop`; a release is a PR from `develop` to `main`.
"""


def checklist(v: dict[str, str]) -> str:
    repo = f"GetTechAPI/{v['repo']}"
    return f"""
Next steps (not automated — each changes the org):

  1. gh repo create {repo} --public
  2. push the scaffold to develop, then develop:main
  3. gh api -X POST repos/{repo}/pages -f build_type=workflow
  4. gh api -X POST repos/{repo}/environments/github-pages/deployment-branch-policies -f name=main
     (skip this and every deploy fails with no log — game-catalog, 2026-09-17)
  5. add {{"name": "{repo}", "branches": ["develop", "main"]}} to TechMachine machine/repos.json
     and the summary.json URL to its endpoints
  6. add {{ key: "{v['plural']}", label: "{v['plural']}", base: "https://gettechapi.github.io/{v['repo']}/" }}
     to SATELLITES in TechAPI site/src/scripts/techapi.js
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", required=True, help="repository name, e.g. game-catalog")
    parser.add_argument("--category", required=True, help="data directory, e.g. game")
    parser.add_argument("--title", required=True, help='page title, e.g. "Game catalog"')
    parser.add_argument("--plural", required=True, help="count label, e.g. games")
    parser.add_argument("--description", default="Split out of TechAPI.")
    parser.add_argument("--date-field", action="append", default=[], help="YYYY-MM-DD field, repeatable")
    parser.add_argument("--range", action="append", default=[], type=parse_range,
                        help="field:low:high, repeatable")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    values = values_from(args)
    written = scaffold(args.out, values)
    print(f"wrote {len(written)} files to {args.out}")
    print(checklist(values))
    return 0


if __name__ == "__main__":
    sys.exit(main())
