"""G-LOC — Worktree location (tier F rows only; U rows in tests/unit/).

Matrix: docs/testing/TEST-MATRIX.md §G-LOC.
"""

import pytest


@pytest.mark.matrix("T-LOC-06")
def test_mirror_parent_heuristic_for_linked_worktree_parent(repo_scenario):
    """T-LOC-06 — the mirror-parent heuristic places the fork like a linked-worktree
    parent.

    Given:  the parent is itself a linked worktree (topology=linked-worktree)
    Expect: the fork mirrors the parent's observed placement pattern
    Source: D5; RESEARCH §4
    """
    from agent_fork.location import derive_worktree_path

    world = repo_scenario("linked-worktree")
    path = derive_worktree_path(
        world.repo_root,
        "fork/fix-auth",
        "fix-auth",
        "sibling",
        parent_path=world.parent_path,
        parent_is_linked=True,
    )
    assert path.parent == world.parent_path.parent
    assert path.name == f"{world.repo_root.name}-fork-fix-auth"


@pytest.mark.matrix("T-LOC-07")
def test_bare_at_root_placement_override(repo_scenario):
    """T-LOC-07 — the bare-at-root override places the fork worktree as a child of the
    bare dir.

    Given:  the repo is bare, invoked at the bare root (topology=bare@bare)
    Expect: fork worktree placed as a child of the bare dir
    Source: D5; RESEARCH §2.4
    """
    from agent_fork.location import derive_worktree_path

    world = repo_scenario("bare@bare")
    path = derive_worktree_path(
        world.repo_root,
        "fork/fix-auth",
        "fix-auth",
        "sibling",
        bare_at_root=True,
    )
    assert path == world.repo_root / "fix-auth"
