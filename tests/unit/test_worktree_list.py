"""Unit tests for porcelain worktree list parsing."""

from pathlib import Path

import pytest

from agent_fork.worktree_list import parse_worktree_list

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
