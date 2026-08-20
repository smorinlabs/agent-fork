"""Shared enumeration and parsing of ``git worktree list --porcelain``.

POSIX permits a newline inside a directory name, so the newline-delimited
porcelain format cannot distinguish a record separator from path content: a
worktree at ``wt\\nname`` parses as ``wt``. The truncated path then fails
``verify_fork``'s worktree-list check, and rollback destroys a valid fork.

Before ``-z`` was requested, this reproduced through the public CLI::

    $ agent-fork fork safe --no-agent --worktree-name $'wt\\nname'
    verify_failed: verification failed: worktree-list

Git's ``-z`` switches the separator to NUL, which cannot appear in a path, so
the ambiguity disappears. It arrived in Git 2.36, above this project's
``PRODUCT_GIT_MIN`` of 2.19, so it is requested rather than assumed.

The fallback is safe because an older Git *rejects* the unknown option rather
than ignoring it::

    $ git worktree list --porcelain --bogus-flag
    error: unknown option `bogus-flag'
    usage: git worktree list [-v | --porcelain [-z]]
    exit=129

That distinction is load-bearing. A silently-ignored flag would have left
newline-delimited bytes to be parsed as NUL-delimited, which is worse than the
original defect: confident nonsense rather than a truncated path.

When ``PRODUCT_GIT_MIN`` reaches 2.36, the retry in ``list_worktrees`` and the
legacy branch in ``parse_worktree_list`` can both be deleted. Tracked in #46.
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
    # `check=False` because a non-zero exit here is an expected answer, not a
    # failure: Git below 2.36 reports the unknown `-z` as exit 129. Any other
    # non-zero exit (a genuine Git error) also falls through to the retry,
    # which then runs with `check=True` and raises the real diagnostic.
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
        # `-z` form: fields are NUL-separated and a record ends with an empty
        # field (Git emits a second NUL), so a newline inside a path is
        # ordinary content rather than a separator.
        fields = text.split("\0")
    else:
        # Legacy form: fields are lines and a record ends with a blank line.
        # A path containing a newline is indistinguishable from two fields
        # here — the defect this function cannot fix without `-z`.
        fields = text.splitlines()
    records: list[WorktreeRecord] = []
    path: str | None = None
    branch: str | None = None
    # The trailing "" is a sentinel that flushes a record left open by output
    # with no final separator, so both forms end the same way.
    for field in [*fields, ""]:
        if field.startswith("worktree "):
            if path is not None:
                records.append(WorktreeRecord(Path(path).resolve(), branch))
            path = field.removeprefix("worktree ")
            branch = None
        elif field.startswith("branch refs/heads/"):
            branch = field.removeprefix("branch refs/heads/")
        elif not field and path is not None:
            # Empty field ends the record in both forms: a blank line in the
            # legacy output, the doubled NUL in the `-z` output.
            records.append(WorktreeRecord(Path(path).resolve(), branch))
            path = None
            branch = None
    return tuple(records)
