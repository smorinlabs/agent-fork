"""G-CFG — Config resolution (tier F rows only; U rows in tests/unit/, C rows in
tests/cli/).

Matrix: docs/testing/TEST-MATRIX.md §G-CFG.
"""

import pytest


@pytest.mark.matrix("T-CFG-10")
@pytest.mark.skip(reason="pending: T-CFG-10")
def test_project_config_walkup_stops_at_repo_boundary(repo_scenario):
    """T-CFG-10 — project-config walk-up stops at the repo boundary and never escalates
    above it.

    Given:  a project config walk-up search from within the repo
    Expect: the walk-up stops at the repo boundary; never escalates above it
    Source: REQ-12
    """
    raise NotImplementedError


@pytest.mark.matrix("T-CFG-11")
@pytest.mark.skip(reason="pending: T-CFG-11")
def test_a6_linked_worktree_walkup_boundary_is_own_root(repo_scenario):
    """T-CFG-11 — A6 — in a linked worktree, the project-config walk-up boundary is the
    worktree's own root.

    Given:  a linked-worktree topology
    Expect: the walk-up boundary is the worktree's own root, not the main checkout's
    Source: REQ-12 (A6); spec §8 A6
    """
    raise NotImplementedError


@pytest.mark.matrix("T-CFG-13")
@pytest.mark.skip(reason="pending: T-CFG-13")
def test_explicit_config_flag_replaces_discovery_entirely(repo_scenario):
    """T-CFG-13 — --config <path> replaces config discovery entirely.

    Given:  `--config <path>` passed explicitly
    Expect: the walk-up/XDG/system chain is not consulted
    Source: REQ-12
    """
    raise NotImplementedError
