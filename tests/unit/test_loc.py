"""G-LOC — Worktree location (U-tier rows only; F rows land in Task 8).

Matrix: docs/testing/TEST-MATRIX.md §G-LOC.
"""

from pathlib import Path

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
    from agent_fork.config import resolve_config
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

    resolved = resolve_config(sources=({"worktree_location": "sibling"},))
    assert resolved.worktree_location_explicit is True
    explicit_sibling = derive_worktree_path(
        world.repo_root,
        "fork/fix-auth",
        "fix-auth",
        resolved.worktree_location,
        parent_path=world.parent_path,
        parent_is_linked=True,
        location_explicit=resolved.worktree_location_explicit,
    )
    assert explicit_sibling.parent == world.repo_root.parent
    assert explicit_sibling.parent != world.parent_path.parent


@pytest.mark.parametrize(
    ("base", "leaf", "expected"),
    [
        pytest.param(
            "base",
            None,
            "base/derived",
            id="T-LOC-08",
            marks=pytest.mark.matrix("T-LOC-08"),
        ),
        pytest.param(
            None,
            "Exact Name",
            "original/Exact Name",
            id="T-LOC-09",
            marks=pytest.mark.matrix("T-LOC-09"),
        ),
        pytest.param(
            "base",
            "Exact Name",
            "base/Exact Name",
            id="T-LOC-10",
            marks=pytest.mark.matrix("T-LOC-10"),
        ),
    ],
)
def test_partial_destination_composition(repo_scenario, base, leaf, expected):
    from agent_fork.location import compose_worktree_destination

    root = repo_scenario().parent_path.parent
    (root / "base").mkdir()
    derived = root / "original/derived"
    value = compose_worktree_destination(
        derived,
        invocation_cwd=root,
        base_dir=Path(base) if base else None,
        worktree_name=leaf,
    )
    assert value == root / expected


@pytest.mark.matrix("T-LOC-11")
def test_invalid_explicit_worktree_leaf_inventory(repo_scenario):
    from agent_fork.errors import PreconditionError
    from agent_fork.location import validate_worktree_name

    for value in ("", "   ", ".", "..", "a/b", "a\\b", "a\0b", "/absolute"):
        with pytest.raises(PreconditionError) as caught:
            validate_worktree_name(value)
        assert caught.value.code == "invalid_worktree_name"


@pytest.mark.matrix("T-LOC-14")
def test_template_destination_can_replace_parent_and_leaf(repo_scenario):
    from agent_fork.location import compose_worktree_destination, derive_worktree_path

    root = repo_scenario().parent_path
    base = root.parent / "base"
    base.mkdir()
    derived = derive_worktree_path(
        root, "fork/topic", "topic", "{repo-root}/custom/{branch}"
    )
    assert (
        compose_worktree_destination(
            derived, invocation_cwd=root, base_dir=base, worktree_name="leaf"
        )
        == base / "leaf"
    )
