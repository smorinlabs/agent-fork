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


class CollectionError(RuntimeError):
    """Raised when the pytest collection subprocess fails or produces no dump.

    Any nonzero exit (including pytest's own exit code 5, "no tests
    collected") is treated as fatal — an empty tier tree is drift, not
    cleanliness, and collect_items must never silently return [] for a
    broken tree.
    """


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
        result = subprocess.run(
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
        if result.returncode != 0 or not dump_path.exists():
            stderr_tail = "\n".join(result.stderr.strip().splitlines()[-20:])
            raise CollectionError(
                f"pytest collection failed under {repo_root} "
                f"(exit {result.returncode}, dump "
                f"{'missing' if not dump_path.exists() else 'present'}):\n{stderr_tail}"
            )
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


TIER_DIRS: dict[str, str] = {
    "tests/unit": "U",
    "tests/pipeline": "F",
    "tests/cli": "C",
    "tests/live": "R",
    "tests/fixtures": "F",
}

# Spec §7.4 check (3): E1-E6 must all be accounted for at these exact statuses.
_EXPERIMENT_STATUS: dict[str, str] = {
    "T-EXP-01": "live",
    "T-EXP-02": "live",
    "T-EXP-03": "live",
    "T-EXP-04": "retired",
    "T-EXP-05": "n/a",
    "T-EXP-06": "tombstone",
}


def _tier_for_path(path: str, tier_dirs: dict[str, str]) -> str | None:
    """Map a repo-relative item path to a tier via tier_dirs, None if out of scope."""
    for prefix, tier in tier_dirs.items():
        if path == prefix or path.startswith(prefix + "/"):
            return tier
    return None


def run_checks(
    groups: dict[str, Group], items: list[Item], tier_dirs: dict[str, str]
) -> list[str]:
    """Cross-check TEST-MATRIX.md groups/rows against collected pytest items.

    Implements spec §7.4's five checks and returns one finding string per
    violation, formatted "CHECK<n>: <message>". Empty list means clean.
    """
    findings: list[str] = []

    row_index: dict[str, Row] = {}
    for group in groups.values():
        row_index.update(group.rows)

    items_by_id: dict[str, list[Item]] = {}
    for item in items:
        if item.matrix_id:
            items_by_id.setdefault(item.matrix_id, []).append(item)

    # CHECK1 direction 1: every live (or blocked) row has exactly one item.
    for row_id, row in row_index.items():
        if row.row_status in ("live", "blocked"):
            count = len(items_by_id.get(row_id, []))
            if count != 1:
                findings.append(
                    f"CHECK1: {row_id} has {count} collected items, expected exactly 1"
                )

    # CHECK1 direction 2 / CHECK4 / CHECK5: every in-scope collected item.
    for item in items:
        tier = _tier_for_path(item.path, tier_dirs)
        if tier is None:
            continue  # out of scope, e.g. tests/test_package.py
        if not item.matrix_id or item.matrix_id not in row_index:
            findings.append(
                f"CHECK1: {item.nodeid} cites unknown matrix ID {item.matrix_id!r}"
            )
            continue
        row = row_index[item.matrix_id]
        if row.row_status in ("tombstone", "n/a"):
            findings.append(
                f"CHECK4: {item.nodeid} cites {row.row_status} row {item.matrix_id}"
            )
            continue
        if row.tier != tier:
            findings.append(
                f"CHECK5: {item.nodeid} under tier {tier!r} cites {item.matrix_id} "
                f"whose row tier is {row.tier!r}"
            )

    # CHECK2: lifecycle invariants (spec §7.2), live rows only.
    for group in groups.values():
        for row_id, row in group.rows.items():
            if row.row_status != "live":
                continue
            for item in items_by_id.get(row_id, []):
                reason = item.skip_reason or ""
                if group.status == "pending":
                    if not (
                        reason.startswith("pending:") or reason.startswith("retired:")
                    ):
                        findings.append(
                            f"CHECK2: {row_id} in pending group has non-pending skip "
                            f"reason {item.skip_reason!r}"
                        )
                elif group.status in ("tdd", "done"):
                    if reason.startswith("pending:"):
                        findings.append(
                            f"CHECK2: {row_id} in {group.status} group still has "
                            f"lifecycle skip {item.skip_reason!r}"
                        )

    # CHECK3: experiment accounting (E1-E6). Drift-check runs unconditionally
    # on whichever canonical IDs are present; "missing" only fires once at
    # least two canonical IDs are present, so a synthetic test declaring a
    # single unrelated experiment row (see
    # test_check2_retired_and_requires_real_cli_skips_are_exempt) doesn't
    # spuriously report the other five as missing.
    present_experiments = [eid for eid in _EXPERIMENT_STATUS if eid in row_index]
    for exp_id, expected_status in _EXPERIMENT_STATUS.items():
        row = row_index.get(exp_id)
        if row is None:
            if len(present_experiments) >= 2:
                findings.append(
                    f"CHECK3: {exp_id} missing from TEST-MATRIX.md "
                    f"(expected status {expected_status!r})"
                )
            continue
        if row.row_status != expected_status:
            findings.append(
                f"CHECK3: {exp_id} status drifted (expected {expected_status!r}, "
                f"got {row.row_status!r})"
            )

    return findings


def main(argv: list[str] | None = None) -> int:
    """Entry point: cross-check TEST-MATRIX.md against the collected stub tree."""
    matrix_path = _CHECKER_ROOT / "docs" / "testing" / "TEST-MATRIX.md"
    groups = parse_matrix(matrix_path.read_text())

    try:
        items = collect_items(_CHECKER_ROOT)
    except CollectionError as exc:
        print(exc)
        return 1

    relative_items = [
        Item(
            nodeid=item.nodeid,
            path=str(Path(item.path).resolve().relative_to(_CHECKER_ROOT)),
            matrix_id=item.matrix_id,
            skip_reason=item.skip_reason,
        )
        for item in items
    ]

    findings = run_checks(groups, relative_items, TIER_DIRS)
    for finding in findings:
        print(finding)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
