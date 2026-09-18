"""Build the static site payload: summary.json and history.json.

Deliberately NOT a catalog.json of every record. TechAPI's homepage counts a
satellite by downloading its catalog and reading `.length`; at ~1M games that
would be hundreds of MB fetched twice on page load. It reads `summary.json`
instead, and the records themselves stay in `data/` and the API dump.

History is built in ONE git pass over add/delete name-status output, not one
`ls-tree` per commit (which is O(commits x records) — fine for 147 records,
hopeless for a million).

Run with: python site/build.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "{{category}}"
OUT = Path(__file__).resolve().parent
TRACKED = "data/{{category}}"


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout


def count_records() -> int:
    return sum(1 for _ in DATA.rglob("*.json"))


def build_history() -> list[dict[str, object]]:
    """Record count after every commit that touched the data, one git pass."""
    log = git(
        "log",
        "--reverse",
        "--no-renames",
        "--format=%x00%H %cI",
        "--name-status",
        "--diff-filter=AD",
        "--",
        TRACKED,
    )
    points: list[dict[str, object]] = []
    running = 0
    sha = date = ""
    for line in log.splitlines():
        if line.startswith("\x00"):
            if sha:
                points.append({"sha": sha, "date": date, "count": running})
            sha, date = line[1:].split(" ", 1)
            continue
        if not line.strip() or not line.endswith(".json"):
            continue
        running += 1 if line[0] == "A" else -1
    if sha:
        points.append({"sha": sha, "date": date, "count": running})
    return points


def main() -> int:
    count = count_records()
    summary = {
        "count": count,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"wrote summary.json ({count} {{category}} records)")

    history = build_history()
    (OUT / "history.json").write_text(
        json.dumps({"points": history}, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote history.json ({len(history)} points)")

    if history and history[-1]["count"] != count:
        # The working tree and the replayed history disagree — usually an
        # uncommitted change locally, but in CI it means the replay is wrong.
        print(f"WARNING: history ends at {history[-1]['count']}, tree has {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
