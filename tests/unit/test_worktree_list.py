"""Unit tests for porcelain worktree enumeration and parsing."""

from pathlib import Path

import pytest

from agent_fork import worktree_list
from agent_fork.git import GitResult
from agent_fork.worktree_list import list_worktrees, parse_worktree_list

PORCELAIN = b"""worktree /tmp/wt-a
HEAD abc
branch refs/heads/fork/a

worktree /tmp/wt-b
HEAD def
branch refs/heads/fork/b

"""

NO_TRAILING_BLANK = b"""worktree /tmp/wt-a
HEAD abc
branch refs/heads/fork/a"""

DETACHED = b"""worktree /tmp/wt-a
HEAD abc
detached

"""

# The NUL-delimited form Git emits for `--porcelain -z`, carrying a path whose
# name contains a newline. This is the case the newline-delimited form cannot
# express unambiguously.
NUL_WITH_NEWLINE_PATH = (
    b"worktree /tmp/wt-a\x00HEAD abc\x00branch refs/heads/fork/a\x00\x00"
    b"worktree /tmp/wt\nname\x00HEAD def\x00branch refs/heads/fork/b\x00\x00"
)


@pytest.mark.matrix("T-ANC-09")
def test_parse_worktree_list_resolves_paths_and_flushes_final_record():
    records = parse_worktree_list(PORCELAIN)
    assert len(records) == 2
    assert records[0].branch == "fork/a"
    assert records[0].path == Path("/tmp/wt-a").resolve()
    assert records[1].branch == "fork/b"


@pytest.mark.matrix("T-ANC-10")
def test_parse_worktree_list_flushes_record_without_trailing_blank_line():
    records = parse_worktree_list(NO_TRAILING_BLANK)
    assert len(records) == 1
    assert records[0].branch == "fork/a"


@pytest.mark.matrix("T-ANC-11")
def test_parse_worktree_list_reports_detached_worktree_with_no_branch():
    records = parse_worktree_list(DETACHED)
    assert len(records) == 1
    assert records[0].branch is None
    assert records[0].path == Path("/tmp/wt-a").resolve()


@pytest.mark.matrix("T-ANC-12")
def test_nul_delimited_form_preserves_a_newline_bearing_path():
    """The whole point of requesting `-z`.

    In the newline-delimited form this same worktree parses as `/tmp/wt`,
    a different location, which is what made `verify_fork` reject its own
    worktree and roll a valid fork back.
    """
    records = parse_worktree_list(NUL_WITH_NEWLINE_PATH)
    assert len(records) == 2
    assert records[1].branch == "fork/b"
    assert records[1].path == Path("/tmp/wt\nname").resolve()
    assert "\n" in records[1].path.name


@pytest.mark.matrix("T-ANC-13")
def test_list_worktrees_falls_back_when_z_is_unsupported(monkeypatch):
    """Git older than 2.36 rejects `-z` with exit 129 rather than ignoring it.

    CI runs only modern Git, so the legacy branch is exercised here instead.
    A silently-ignored flag would be the dangerous case: newline-delimited
    bytes parsed as NUL-delimited. Rejection is what makes the retry safe.
    """
    calls: list[list[str]] = []

    def fake_run_git(cwd, args, *, env=None, check=True, **kwargs):
        calls.append(list(args))
        if "-z" in args:
            return GitResult(
                args=tuple(args),
                returncode=129,
                stdout=b"",
                stderr=b"error: unknown option `z'",
            )
        return GitResult(args=tuple(args), returncode=0, stdout=PORCELAIN, stderr=b"")

    monkeypatch.setattr(worktree_list, "run_git", fake_run_git)
    records = list_worktrees(Path("/tmp"))

    assert [("-z" in call) for call in calls] == [True, False], calls
    assert len(records) == 2
    assert records[0].branch == "fork/a"


@pytest.mark.matrix("T-ANC-14")
def test_list_worktrees_does_not_retry_when_z_is_supported(monkeypatch):
    calls: list[list[str]] = []

    def fake_run_git(cwd, args, *, env=None, check=True, **kwargs):
        calls.append(list(args))
        return GitResult(
            args=tuple(args),
            returncode=0,
            stdout=NUL_WITH_NEWLINE_PATH,
            stderr=b"",
        )

    monkeypatch.setattr(worktree_list, "run_git", fake_run_git)
    records = list_worktrees(Path("/tmp"))

    assert len(calls) == 1 and "-z" in calls[0]
    assert records[1].path == Path("/tmp/wt\nname").resolve()
