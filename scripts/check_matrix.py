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

GROUP_STATUSES = {"pending", "tdd", "done"}
ROW_STATUSES = {"live", "n/a", "tombstone", "retired", "blocked"}


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
    """One collected pytest item.

    `marker_count` is the number of `matrix` markers found on the item
    (exactly 1 expected for any in-scope item); `matrix_id` is populated
    only when there's exactly one marker with exactly one string arg.
    `param_id` is the pytest callspec param id, None when unparametrized.
    """

    nodeid: str
    path: str
    matrix_id: str | None
    skip_reason: str | None
    marker_count: int = 1
    param_id: str | None = None


class CollectionError(RuntimeError):
    """Raised when the pytest collection subprocess fails or produces no dump.

    Any nonzero exit (including pytest's own exit code 5, "no tests
    collected") is treated as fatal — an empty tier tree is drift, not
    cleanliness, and collect_items must never silently return [] for a
    broken tree.
    """


def parse_matrix(text: str) -> tuple[dict[str, Group], list[str]]:
    """Parse TEST-MATRIX.md text into ({group_id: Group}, schema_errors).

    Stdlib regex only: `## G-XXX` headings start a group, the following
    `Status:` line sets its status, and `| T-XXX-NN | ... |` table rows
    (6 columns: ID, Scenario, Axes, Tier, row_status, Source) populate it.

    Schema errors (duplicate group headings, duplicate row IDs within or
    across groups, and unrecognized group/row statuses) are collected and
    returned rather than silently overwriting prior data — callers must
    treat any non-empty error list as fatal before running cross-checks.
    """
    groups: dict[str, Group] = {}
    errors: list[str] = []
    seen_row_ids: dict[str, str] = {}

    current_group_id: str | None = None
    current_status: str | None = None
    current_rows: dict[str, Row] = {}

    def flush() -> None:
        if current_group_id is None:
            return
        if current_group_id in groups:
            errors.append(f"SCHEMA: duplicate group heading {current_group_id!r}")
            return
        status = current_status or ""
        if status not in GROUP_STATUSES:
            errors.append(
                f"SCHEMA: group {current_group_id} has unrecognized status {status!r}"
            )
        groups[current_group_id] = Group(status=status, rows=current_rows)

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
            row_status = row_match.group("row_status").strip()
            if row_status not in ROW_STATUSES:
                errors.append(
                    f"SCHEMA: {row_id} has unrecognized row_status {row_status!r}"
                )
            if row_id in current_rows:
                errors.append(
                    f"SCHEMA: duplicate row ID {row_id} within group {current_group_id}"
                )
            elif row_id in seen_row_ids:
                errors.append(
                    f"SCHEMA: duplicate row ID {row_id} across groups "
                    f"({seen_row_ids[row_id]} and {current_group_id})"
                )
            else:
                seen_row_ids[row_id] = current_group_id
            current_rows[row_id] = Row(
                row_id=row_id,
                row_status=row_status,
                tier=row_match.group("tier").strip(),
            )

    flush()
    return groups, errors


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
            matrix_ids: list[str | None] = record.get("matrix") or []
            items.append(
                Item(
                    nodeid=record["nodeid"],
                    path=record["path"],
                    matrix_id=matrix_ids[0] if len(matrix_ids) == 1 else None,
                    skip_reason=record.get("skip_reason"),
                    marker_count=len(matrix_ids),
                    param_id=record.get("param_id"),
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
    groups: dict[str, Group],
    items: list[Item],
    tier_dirs: dict[str, str],
    *,
    enforce_experiments: bool = True,
) -> list[str]:
    """Cross-check TEST-MATRIX.md groups/rows against collected pytest items.

    Implements spec §7.4's five checks and returns one finding string per
    violation, formatted "CHECK<n>: <message>". Empty list means clean.

    ``enforce_experiments`` gates only CHECK3's missing-experiment check:
    it is True in production (all six canonical E-rows must be mapped, with
    no count-based carve-outs); synthetic unit tests that deliberately build
    partial experiment sets pass False. Status-drift detection on rows that
    ARE present is never gated.
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

    # CHECK8: every retired row has exactly one collected item, skip-marked
    # with a reason starting "retired:" (the exempt-skip contract, spec §7.3).
    for row_id, row in row_index.items():
        if row.row_status != "retired":
            continue
        matched = items_by_id.get(row_id, [])
        if len(matched) != 1:
            findings.append(
                f"CHECK8: retired row {row_id} has {len(matched)} collected "
                f"items, expected exactly 1"
            )
            continue
        reason = matched[0].skip_reason or ""
        if not reason.startswith("retired:"):
            findings.append(
                f"CHECK8: retired row {row_id} stub has skip reason "
                f"{matched[0].skip_reason!r}, expected prefix 'retired:'"
            )

    # CHECK1 direction 2 / CHECK4 / CHECK5 / CHECK6 / CHECK7: every in-scope
    # collected item.
    for item in items:
        tier = _tier_for_path(item.path, tier_dirs)
        if tier is None:
            continue  # out of scope, e.g. tests/test_package.py
        if item.marker_count != 1:
            findings.append(
                f"CHECK6: {item.nodeid} has {item.marker_count} matrix markers, "
                f"expected exactly 1"
            )
            continue
        if item.param_id is not None and item.matrix_id != item.param_id:
            findings.append(
                f"CHECK7: {item.nodeid} matrix marker {item.matrix_id!r} does "
                f"not match param id {item.param_id!r}"
            )
            continue
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
                    if not reason.startswith("pending:"):
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
    # on whichever canonical IDs are present. "Missing" fires at 0 canonical
    # The missing-experiment check has NO count-based carve-outs: any absent
    # canonical E-row is a finding whenever enforce_experiments is on (the
    # production default). Synthetic unit tests building deliberate partial
    # sets opt out explicitly via enforce_experiments=False.
    for exp_id, expected_status in _EXPERIMENT_STATUS.items():
        row = row_index.get(exp_id)
        if row is None:
            if enforce_experiments:
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
    groups, schema_errors = parse_matrix(matrix_path.read_text())
    if schema_errors:
        # Schema errors (duplicate headings/IDs, unrecognized statuses) make
        # the parsed groups untrustworthy — never proceed to collection/
        # cross-checks on top of drifted data.
        for error in schema_errors:
            print(error)
        return 1

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
            marker_count=item.marker_count,
            param_id=item.param_id,
        )
        for item in items
    ]

    findings = run_checks(groups, relative_items, TIER_DIRS)
    for finding in findings:
        print(finding)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
