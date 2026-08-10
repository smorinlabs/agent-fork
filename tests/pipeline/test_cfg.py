"""G-CFG — Config resolution (tier F rows only; U rows in tests/unit/, C rows in
tests/cli/).

Matrix: docs/testing/TEST-MATRIX.md §G-CFG.
"""

import pytest


@pytest.mark.matrix("T-CFG-10")
def test_project_config_walkup_stops_at_repo_boundary(repo_scenario):
    """T-CFG-10 — project-config walk-up stops at the repo boundary and never escalates
    above it.

    Given:  a project config walk-up search from within the repo
    Expect: the walk-up stops at the repo boundary; never escalates above it
    Source: REQ-12
    """
    from agent_fork.config import CONFIG_RELATIVE_PATH, find_project_config

    world = repo_scenario("plain@main")
    outside = world.parent_path.parent / CONFIG_RELATIVE_PATH
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_text('[fork]\nbranch_prefix = "outside/"\n')
    nested = world.parent_path / "a/b"
    nested.mkdir(parents=True)
    assert find_project_config(nested, world.env) is None

    inside = world.parent_path / CONFIG_RELATIVE_PATH
    inside.parent.mkdir(parents=True, exist_ok=True)
    inside.write_text('[fork]\nbranch_prefix = "inside/"\n')
    assert find_project_config(nested, world.env) == inside


@pytest.mark.matrix("T-CFG-11")
def test_a6_linked_worktree_walkup_boundary_is_own_root(repo_scenario):
    """T-CFG-11 — A6 — in a linked worktree, the project-config walk-up boundary is the
    worktree's own root.

    Given:  a linked-worktree topology
    Expect: the walk-up boundary is the worktree's own root, not the main checkout's
    Source: REQ-12 (A6); spec §8 A6
    """
    from agent_fork.config import CONFIG_RELATIVE_PATH, find_project_config

    world = repo_scenario("linked-worktree")
    assert world.main_path is not None
    main_config = world.main_path / CONFIG_RELATIVE_PATH
    main_config.parent.mkdir(parents=True, exist_ok=True)
    main_config.write_text('[fork]\nbranch_prefix = "main/"\n')
    linked_config = world.parent_path / CONFIG_RELATIVE_PATH
    linked_config.parent.mkdir(parents=True, exist_ok=True)
    linked_config.write_text('[fork]\nbranch_prefix = "linked/"\n')
    nested = world.parent_path / "nested"
    nested.mkdir()
    assert find_project_config(nested, world.env) == linked_config


@pytest.mark.matrix("T-CFG-13")
def test_explicit_config_flag_replaces_discovery_entirely(repo_scenario):
    """T-CFG-13 — --config <path> replaces config discovery entirely.

    Given:  `--config <path>` passed explicitly
    Expect: the walk-up/XDG/system chain is not consulted
    Source: REQ-12
    """
    from agent_fork.config import CONFIG_RELATIVE_PATH, resolve_discovered_config

    world = repo_scenario("plain@main")
    discovered = world.parent_path / CONFIG_RELATIVE_PATH
    discovered.parent.mkdir(parents=True, exist_ok=True)
    discovered.write_text("this is invalid TOML = [")
    explicit = world.parent_path / "chosen.toml"
    explicit.write_text('[fork]\nbranch_prefix = "chosen/"\n')
    resolved = resolve_discovered_config(
        world.parent_path, world.env, explicit_path=explicit
    )
    assert resolved.branch_prefix == "chosen/"
    assert resolved.config_path == explicit.resolve()

    from agent_fork.config import ConfigError

    invalid = world.parent_path / "invalid.toml"
    invalid.write_text('[fork]\nunknown = "do-not-echo-this-secret"\n')
    with pytest.raises(ConfigError) as caught:
        resolve_discovered_config(world.parent_path, world.env, explicit_path=invalid)
    assert "unknown key fork.unknown" in str(caught.value)
    assert "do-not-echo-this-secret" not in str(caught.value)
