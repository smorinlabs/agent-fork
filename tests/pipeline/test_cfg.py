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


@pytest.mark.matrix("T-CFG-29")
def test_branch_prefix_predicate_parity_with_real_git(repo_scenario):
    """T-CFG-29 — the pure `branch_prefix_reason()` predicate agrees with
    real `git check-ref-format --branch` on a composed-sample corpus.

    A11 Gate-4 finding F7: the oracle is `--branch` mode (matching the
    existing `cli.py` guard and `git worktree add -b`'s actual validation
    surface), not the fully-qualified `refs/heads/<name>` form — bare
    `check-ref-format` was empirically found *not* to enforce the
    leading-`-` rule that `--branch` mode does (`refs/heads/-bad/ok` is
    accepted; `--branch '-bad/ok'` is refused), so switching oracles would
    have silently dropped that rule's own verification. Entries containing
    `@{` are excluded from the git comparison — `--branch` mode resolves
    that sequence as reflog shorthand (non-deterministic across repo state),
    but such entries are already, and independently, rejected by this
    predicate's static `@{` rule, so no case needs the oracle to confirm it.
    """
    import subprocess

    from agent_fork.config import branch_prefix_reason

    world = repo_scenario("plain@main")
    corpus = (
        "fork/",
        "wt/",
        "user/name-",
        "topic.",
        "foolock",
        "",
        "-bad/",
        "a..b/",
        "a~b/",
        "a^b/",
        "a:b/",
        "a?b/",
        "a*b/",
        "a[b/",
        "a\\b/",
        "/abs/",
        "a//b/",
        ".hidden/",
        "a.lock/",
        "trailing.",
        "a b/",
    )
    for prefix in corpus:
        composed = f"{prefix}x"
        if "@{" in composed:
            continue
        predicate_reason = branch_prefix_reason(prefix)
        real = subprocess.run(
            ["git", "check-ref-format", "--branch", composed],
            cwd=world.parent_path,
            env=world.env,
            capture_output=True,
            text=True,
        )
        assert (predicate_reason is None) == (real.returncode == 0), (
            prefix,
            predicate_reason,
            real.returncode,
            real.stderr,
        )
