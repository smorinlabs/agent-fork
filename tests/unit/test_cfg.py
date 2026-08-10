"""G-CFG — Config resolution (U-tier rows only; F/C rows land in Task 8).

Matrix: docs/testing/TEST-MATRIX.md §G-CFG.
"""

import pytest


@pytest.mark.matrix("T-CFG-01")
def test_with_state_unset_defaults_true(repo_scenario):
    """T-CFG-01 — with_state unset resolves to True.

    Given:  no config file, no flags
    Expect: resolved plan carries state (exact)
    Source: REQ-13; RESEARCH §1.1 tri-state accessors
    """
    from agent_fork.config import resolve_config

    resolved = resolve_config()
    assert resolved.with_state is True
    assert resolved.with_ignored is False


@pytest.mark.matrix("T-CFG-02")
def test_explicit_with_state_false_is_honored(repo_scenario):
    """T-CFG-02 — explicit with_state=false is honored, not coerced back to default.

    Given:  with_state=false set in a single config source
    Expect: resolved plan honors with_state=false, not the tri-state default
    Source: REQ-13; RESEARCH §1.1
    """
    from agent_fork.config import resolve_config

    resolved = resolve_config(sources=({"with_state": False},))
    assert resolved.with_state is False
    assert resolved.mode == "no-state"


@pytest.mark.matrix("T-CFG-03")
def test_within_source_implication_resolves_exact_ignored(repo_scenario):
    """T-CFG-03 — within-source implication resolves conflicting flags to exact+ignored.

    Given:  --no-with-state --with-ignored typed together on one source
    Expect: resolved mode is exact+ignored
    Source: REQ-13; RESEARCH §1.1
    """
    from agent_fork.config import resolve_config

    resolved = resolve_config(flags={"with_state": False, "with_ignored": True})
    assert resolved.with_state is True
    assert resolved.with_ignored is True
    assert resolved.mode == "exact+ignored"

    truth_table = {
        (None, None): "exact",
        (True, False): "exact",
        (False, False): "no-state",
        (None, True): "exact+ignored",
        (False, True): "exact+ignored",
        (True, True): "exact+ignored",
    }
    for (with_state, with_ignored), expected in truth_table.items():
        source = {
            key: value
            for key, value in {
                "with_state": with_state,
                "with_ignored": with_ignored,
            }.items()
            if value is not None
        }
        assert resolve_config(flags=source).mode == expected


@pytest.mark.matrix("T-CFG-04")
def test_a12_cross_source_config_false_plus_flag_ignored_true(repo_scenario):
    """T-CFG-04 — A12 cross-source: config with_state=false + --with-ignored resolves
    exact+ignored.

    Given:  config sets with_state=false; --with-ignored flag passed
    Expect: resolved mode is exact+ignored (the flag's implication forces state back on)
    Source: REQ-13 (A12); spec §4
    """
    from agent_fork.config import resolve_config

    resolved = resolve_config(
        sources=({"with_state": False},), flags={"with_ignored": True}
    )
    assert resolved.mode == "exact+ignored"


@pytest.mark.matrix("T-CFG-05")
def test_a12_cross_source_config_ignored_true_plus_flag_no_with_state(repo_scenario):
    """T-CFG-05 — A12 cross-source: config with_ignored=true + --no-with-state resolves
    no-state.

    Given:  config sets with_ignored=true; --no-with-state flag passed
    Expect: resolved mode is no-state (flag wins; config's with_ignored suppressed)
    Source: REQ-13 (A12); spec §4
    """
    from agent_fork.config import resolve_config

    resolved = resolve_config(
        sources=({"with_ignored": True},), flags={"with_state": False}
    )
    assert resolved.with_state is False
    assert resolved.with_ignored is False
    assert resolved.mode == "no-state"


@pytest.mark.matrix("T-CFG-06")
def test_a12_cross_source_all_sources_unset_resolves_exact(repo_scenario):
    """T-CFG-06 — A12 cross-source: all sources unset resolves to exact.

    Given:  no config, no env, no flags set
    Expect: resolved mode is exact
    Source: REQ-13 (A12); spec §4
    """
    from agent_fork.config import resolve_config

    assert resolve_config().mode == "exact"


@pytest.mark.matrix("T-CFG-07")
def test_precedence_chain_flags_beat_env_beat_config_file(repo_scenario):
    """T-CFG-07 — precedence chain: flags beat env beat config-file order.

    Given:  flags, env, and config-file each set to conflicting values
    Expect: resolved value follows flags > env > config-file order
    Source: REQ-12; RESEARCH §1.1
    """
    from agent_fork.config import resolve_config

    sources = (
        {"branch_prefix": "system/", "output": "system"},
        {"branch_prefix": "user/", "output": "user"},
        {"branch_prefix": "project/", "output": "project"},
    )
    env = {"AGENT_FORK_OUTPUT": "env"}
    resolved = resolve_config(sources=sources, env=env, flags={"output": "flag"})
    assert resolved.branch_prefix == "project/"
    assert resolved.output == "flag"
    assert resolve_config(sources=sources, env=env).output == "env"


@pytest.mark.matrix("T-CFG-08")
def test_branch_prefix_whitespace_only_resolves_to_default(repo_scenario):
    """T-CFG-08 — a whitespace-only branch_prefix resolves to the default fork/.

    Given:  branch_prefix set to a whitespace-only string
    Expect: resolved branch_prefix is the default fork/
    Source: REQ-13
    """
    from agent_fork.config import resolve_config

    assert resolve_config(sources=({"branch_prefix": " \t "},)).branch_prefix == "fork/"


@pytest.mark.matrix("T-CFG-09")
def test_env_vars_applied_to_config_path_and_output_format(repo_scenario):
    """T-CFG-09 — AGENT_FORK_CONFIG and AGENT_FORK_OUTPUT env vars are read and applied.

    Given:  AGENT_FORK_CONFIG and AGENT_FORK_OUTPUT env vars set
    Expect: config-path and output-format resolution reflect them respectively
    Source: REQ-14
    """
    from agent_fork.config import resolve_config

    world = repo_scenario("plain@main")
    path = world.parent_path / "explicit.toml"
    resolved = resolve_config(
        env={"AGENT_FORK_CONFIG": str(path), "AGENT_FORK_OUTPUT": "json"}
    )
    assert resolved.config_path == path.resolve()
    assert resolved.output == "json"
