"""check-matrix: parsers for TEST-MATRIX.md and the collected stub tree.

Reads docs/testing/TEST-MATRIX.md (groups/rows) and the pytest collection of
tests/ (items carrying `matrix` markers) and cross-checks them (Task 10).
This module holds the parsers; `main` wires the checks together.

Spec: docs/superpowers/specs/2026-08-08-test-architecture-design.md.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

GROUP_HEADING_RE = re.compile(r"^## (?P<group_id>G-[A-Z0-9]+)\b")
STATUS_RE = re.compile(r"^Status:\s*(?P<status>\S+)")
ROW_RE = re.compile(
    r"^\|\s*(?P<row_id>T-[A-Z0-9]+-\d+)\s*\|"
    r"(?P<scenario>[^|]*)\|"
    r"(?P<axes>[^|]*)\|"
    r"\s*(?P<tier>[^|]*?)\s*\|"
    r"\s*(?P<row_status>[^|]*?)\s*\|"
    r"(?P<source>[^|]*)\|?"
)


@dataclass(frozen=True)
class Row:
    """One TEST-MATRIX.md table row."""

    row_id: str
    row_status: str
    tier: str


@dataclass(frozen=True)
class Group:
    """One `## G-XXX` section of TEST-MATRIX.md."""

    status: str
    rows: dict[str, Row] = field(default_factory=dict)


@dataclass(frozen=True)
class Item:
    """One collected pytest item."""

    nodeid: str
    path: str
    matrix_id: str | None
    skip_reason: str | None


def parse_matrix(text: str) -> dict[str, Group]:
    """Parse TEST-MATRIX.md text into {group_id: Group}.

    Stdlib regex only: `## G-XXX` headings start a group, the following
    `Status:` line sets its status, and `| T-XXX-NN | ... |` table rows
    (6 columns: ID, Scenario, Axes, Tier, row_status, Source) populate it.
    """
    groups: dict[str, Group] = {}
    current_group_id: str | None = None
    current_status: str | None = None
    current_rows: dict[str, Row] = {}

    def flush() -> None:
        if current_group_id is not None:
            groups[current_group_id] = Group(
                status=current_status or "", rows=current_rows
            )

    for line in text.splitlines():
        heading_match = GROUP_HEADING_RE.match(line)
        if heading_match:
            flush()
            current_group_id = heading_match.group("group_id")
            current_status = None
            current_rows = {}
            continue

        status_match = STATUS_RE.match(line)
        if status_match and current_group_id is not None and current_status is None:
            current_status = status_match.group("status")
            continue

        row_match = ROW_RE.match(line)
        if row_match and current_group_id is not None:
            row_id = row_match.group("row_id")
            current_rows[row_id] = Row(
                row_id=row_id,
                row_status=row_match.group("row_status").strip(),
                tier=row_match.group("tier").strip(),
            )

    flush()
    return groups


_CHECKER_ROOT = Path(__file__).resolve().parent.parent


def collect_items(repo_root: Path) -> list[Item]:
    """Collect pytest items under repo_root via `collect_dump.py` and parse them.

    Runs pytest (via `sys.executable -m pytest`, so it always resolves to an
    interpreter with pytest installed, regardless of whether repo_root itself
    is a uv project) with `--collect-only -q -p scripts.collect_dump` as a
    subprocess, COLLECT_DUMP_OUT pointed at a temp file, then parses the
    JSON-lines dump into Item objects. PYTHONPATH is extended with this
    module's own repo root so `-p scripts.collect_dump` resolves even when
    repo_root is a bare synthetic tree with no scripts/ package of its own.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        dump_path = Path(tmpdir) / "collect_dump.jsonl"
        env = os.environ.copy()
        env["COLLECT_DUMP_OUT"] = str(dump_path)
        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = os.pathsep.join(
            p for p in (str(_CHECKER_ROOT), existing_pythonpath) if p
        )
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "--collect-only",
                "-q",
                "-p",
                "scripts.collect_dump",
            ],
            cwd=repo_root,
            env=env,
            capture_output=True,
            text=True,
        )
        if not dump_path.exists():
            return []
        items: list[Item] = []
        for line in dump_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            items.append(
                Item(
                    nodeid=record["nodeid"],
                    path=record["path"],
                    matrix_id=record.get("matrix"),
                    skip_reason=record.get("skip_reason"),
                )
            )
        return items


def main(argv: list[str] | None = None) -> int:
    """Entry point: cross-check TEST-MATRIX.md against the collected stub tree.

    Skeleton phase: parsers only, full cross-check logic lands in Task 10.
    """
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
