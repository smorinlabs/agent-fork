"""G-LOC — Worktree location (U-tier rows only; F rows land in Task 8).

Matrix: docs/testing/TEST-MATRIX.md §G-LOC.
"""

import pytest


@pytest.mark.matrix("T-LOC-01")
def test_sibling_default_path_derivation(repo_scenario):
    """T-LOC-01 — sibling default path places the worktree at <repo>-<branch>.

    Given:  worktree_location=sibling (default)
    Expect: worktree placed at <repo>-<branch>
    Source: D5; RESEARCH §2.4
    """
    from agent_fork.location import derive_worktree_path

    root = repo_scenario("plain@main").parent_path
    path = derive_worktree_path(root, "fork/fix-auth", "fix-auth", "sibling")
    assert path == root.parent / f"{root.name}-fork-fix-auth"


@pytest.mark.matrix("T-LOC-02")
def test_central_location_uses_xdg_data_path(repo_scenario):
    """T-LOC-02 — central location places the worktree under the XDG data path.

    Given:  worktree_location=central
    Expect: worktree placed at ~/.local/share/agent-fork/worktrees/<repo>/<slug>
    Source: D5
    """
    from agent_fork.location import derive_worktree_path

    world = repo_scenario("plain@main")
    data = world.parent_path.parent / "data"
    path = derive_worktree_path(
        world.parent_path,
        "fork/fix-auth",
        "fix-auth",
        "central",
        xdg_data_home=data,
    )
    assert path == data / "agent-fork/worktrees" / world.parent_path.name / "fix-auth"


@pytest.mark.matrix("T-LOC-03")
def test_subdirectory_location(repo_scenario):
    """T-LOC-03 — subdirectory location places the worktree at <root>/.worktrees/<slug>.

    Given:  worktree_location=subdirectory
    Expect: worktree placed at <root>/.worktrees/<slug>
    Source: D5
    """
    from agent_fork.location import derive_worktree_path

    root = repo_scenario("plain@main").parent_path
    assert derive_worktree_path(root, "fork/topic", "topic", "subdirectory") == (
        root / ".worktrees/topic"
    )


@pytest.mark.matrix("T-LOC-04")
def test_path_template_placeholders_resolved_individually(repo_scenario):
    """T-LOC-04 — the path template resolves each placeholder.

    Given:  one templated worktree_location value using {repo-name}, {repo-root},
            and {branch}
    Expect: {repo-name} -> repo basename, {repo-root} -> parent dir of root,
            {branch} -> fork branch slug, each asserted individually
    Source: D5; RESEARCH §2.4
    """
    from agent_fork.location import derive_worktree_path

    root = repo_scenario("plain@main").parent_path
    template = "{repo-root}/custom/{repo-name}/{branch}/{branch-escaped}/{session-id}"
    path = derive_worktree_path(
        root,
        "fork/fix-auth",
        "fix-auth",
        template,
        session_id="session-1",
    )
    assert path == (
        root.parent
        / "custom"
        / root.name
        / "fork/fix-auth"
        / "fork-fix-auth"
        / "session-1"
    )


@pytest.mark.matrix("T-LOC-05")
def test_explicit_worktree_location_suppresses_mirror_parent_heuristic(repo_scenario):
    """T-LOC-05 — an explicit worktree_location value suppresses the mirror-parent
    heuristic.

    Given:  worktree_location explicitly set in config
    Expect: the mirror-parent heuristic is suppressed
    Source: D5
    """
    from agent_fork.location import derive_worktree_path

    world = repo_scenario("linked-worktree")
    data = world.parent_path.parent / "explicit-data"
    path = derive_worktree_path(
        world.repo_root,
        "fork/fix-auth",
        "fix-auth",
        "central",
        xdg_data_home=data,
        parent_path=world.parent_path,
        parent_is_linked=True,
        location_explicit=True,
    )
    assert path == data / "agent-fork/worktrees" / world.repo_root.name / "fix-auth"
