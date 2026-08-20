"""Shared enumeration and parsing of ``git worktree list --porcelain``.

POSIX permits a newline inside a directory name, so the newline-delimited
porcelain format cannot distinguish a record separator from path content: a
worktree at ``wt\\nname`` parses as ``wt``. The truncated path then fails
``verify_fork``'s worktree-list check, and rollback destroys a valid fork.

Git's ``-z`` switches the separator to NUL, which cannot appear in a path, so
the ambiguity disappears. It arrived in Git 2.36, above this project's
``PRODUCT_GIT_MIN`` of 2.19, so it is requested rather than assumed: an older
Git rejects the unknown option with exit 129 instead of silently ignoring it,
which makes the fallback reliable — a silently-ignored flag would have made
newline-delimited bytes get parsed as NUL-delimited.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from agent_fork.git import run_git

_PORCELAIN = ["worktree", "list", "--porcelain"]


@dataclass(frozen=True)
class WorktreeRecord:
    path: Path
    branch: str | None


def list_worktrees(
    cwd: Path, *, env: Mapping[str, str] | None = None
) -> tuple[WorktreeRecord, ...]:
    """Enumerate worktrees, preferring the newline-safe NUL-delimited format.

    Requesting ``-z`` costs one rejected invocation on a Git older than 2.36
    and nothing at all on a newer one. Support is not cached: ``run_git``
    resolves ``git`` by name on every call so a changed PATH stays observable,
    and caching the answer would quietly defeat that.
    """
    result = run_git(cwd, [*_PORCELAIN, "-z"], env=env, check=False)
    if result.returncode != 0:
        result = run_git(cwd, _PORCELAIN, env=env)
    return parse_worktree_list(result.stdout)


def parse_worktree_list(output: bytes) -> tuple[WorktreeRecord, ...]:
    """Parse porcelain records in either delimiter form, flushing the last one.

    The delimiter is detected rather than declared: NUL cannot occur in a path
    or a ref, so its presence identifies the ``-z`` form unambiguously.

    Paths are always resolved. Every caller compares them against resolved
    paths, and the one historical unresolved comparison — in ``verify_fork``,
    which matched a resolved ``creation.path`` against a raw porcelain string —
    was a defect rather than a supported mode.
    """
    text = output.decode(errors="surrogateescape")
    if "\0" in text:
        fields = text.split("\0")
    else:
        fields = text.splitlines()
    records: list[WorktreeRecord] = []
    path: str | None = None
    branch: str | None = None
    for field in [*fields, ""]:
        if field.startswith("worktree "):
            if path is not None:
                records.append(WorktreeRecord(Path(path).resolve(), branch))
            path = field.removeprefix("worktree ")
            branch = None
        elif field.startswith("branch refs/heads/"):
            branch = field.removeprefix("branch refs/heads/")
        elif not field and path is not None:
            records.append(WorktreeRecord(Path(path).resolve(), branch))
            path = None
            branch = None
    return tuple(records)
