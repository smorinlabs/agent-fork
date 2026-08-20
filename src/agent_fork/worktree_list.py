"""Shared parsing for ``git worktree list --porcelain`` output."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorktreeRecord:
    path: Path
    branch: str | None


def parse_worktree_list(output: bytes) -> tuple[WorktreeRecord, ...]:
    """Parse porcelain records, flushing the final open record.

    Paths are always resolved. Every caller compares them against resolved
    paths, and the one historical unresolved comparison — in ``verify_fork``,
    which matched a resolved ``creation.path`` against a raw porcelain string —
    was a defect rather than a supported mode.
    """
    records: list[WorktreeRecord] = []
    path: str | None = None
    branch: str | None = None
    for line in output.decode(errors="surrogateescape").splitlines() + [""]:
        if line.startswith("worktree "):
            if path is not None:
                records.append(WorktreeRecord(Path(path).resolve(), branch))
            path = line.removeprefix("worktree ")
            branch = None
        elif line.startswith("branch refs/heads/"):
            branch = line.removeprefix("branch refs/heads/")
        elif not line and path is not None:
            records.append(WorktreeRecord(Path(path).resolve(), branch))
            path = None
            branch = None
    return tuple(records)
