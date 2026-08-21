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
        {"branch_prefix": "system/", "output": "text"},
        {"branch_prefix": "user/", "output": "json"},
        {"branch_prefix": "project/", "output": "text"},
    )
    env = {"AGENT_FORK_OUTPUT": "json"}
    resolved = resolve_config(sources=sources, env=env, flags={"output": "text"})
    assert resolved.branch_prefix == "project/"
    assert resolved.output == "text"
    assert resolve_config(sources=sources, env=env).output == "json"


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


@pytest.mark.matrix("T-CFG-18")
def test_output_defaults_validates_final_value_and_honors_precedence():
    """A13(B) — the effective output is text or JSON, with flags winning."""
    from agent_fork.config import ConfigError, resolve_config

    assert resolve_config().output == "text"
    assert resolve_config(env={"AGENT_FORK_OUTPUT": "text"}).output == "text"
    assert resolve_config(env={"AGENT_FORK_OUTPUT": "json"}).output == "json"

    for invalid in ("table", "yaml", ""):
        with pytest.raises(ConfigError, match="output must be text or json"):
            resolve_config(env={"AGENT_FORK_OUTPUT": invalid})

    assert (
        resolve_config(
            env={"AGENT_FORK_OUTPUT": "table"}, flags={"output": "text"}
        ).output
        == "text"
    )
    assert (
        resolve_config(
            env={"AGENT_FORK_OUTPUT": "table"}, flags={"output": "json"}
        ).output
        == "json"
    )


@pytest.mark.matrix("T-CFG-14")
def test_agent_mode_defaults_to_auto(repo_scenario):
    from agent_fork.config import resolve_config

    assert resolve_config().agent_mode == "auto"


@pytest.mark.matrix("T-CFG-15")
def test_agent_mode_precedence(repo_scenario):
    from agent_fork.config import resolve_config

    resolved = resolve_config(
        sources=({"agent_mode": "git-only"},),
        env={"AGENT_FORK_AGENT_MODE": "strict"},
        flags={"agent_mode": "auto"},
    )
    assert resolved.agent_mode == "auto"
    assert (
        resolve_config(
            sources=({"agent_mode": "git-only"},),
            env={"AGENT_FORK_AGENT_MODE": "strict"},
        ).agent_mode
        == "strict"
    )


@pytest.mark.matrix("T-CFG-16")
def test_invalid_agent_mode_is_config_error(repo_scenario):
    from agent_fork.config import ConfigError, load_config

    world = repo_scenario()
    path = world.parent_path / "bad.toml"
    path.write_text('[fork]\nagent_mode = "sometimes"\n')
    with pytest.raises(ConfigError, match="auto, strict, or git-only"):
        load_config(path)


@pytest.mark.matrix("T-CFG-17")
def test_codex_session_name_resolution_config_and_flag_precedence(repo_scenario):
    from agent_fork.config import load_config, resolve_config

    world = repo_scenario()
    path = world.parent_path / "agent.toml"
    path.write_text("[agents.codex]\nsession_name_resolution = false\n")
    loaded = load_config(path)
    assert resolve_config().codex_session_name_resolution is True
    assert resolve_config(sources=(loaded,)).codex_session_name_resolution is False
    assert (
        resolve_config(
            sources=(loaded,), flags={"codex_session_name_resolution": True}
        ).codex_session_name_resolution
        is True
    )


@pytest.mark.matrix("T-CFG-24")
def test_setup_hook_keys_default_and_obey_precedence(repo_scenario):
    """T-CFG-24 — A12 policy resolution.

    Given:  no source, a config-file source, and an explicit flag
    Expect: `setup_hook_policy` defaults to `tracked` and `setup_hook_timeout`
            to 300 seconds; an explicit flag beats a config value; and
            `off` dominates whatever a lower-precedence source asked for
    Source: P02 A12; REQ-12; REQ-13
    """
    from agent_fork.config import load_config, resolve_config

    world = repo_scenario()
    default = resolve_config()
    assert default.setup_hook_policy == "tracked"
    assert default.setup_hook_timeout == 300

    path = world.parent_path / "hook.toml"
    path.write_text('[fork]\nsetup_hook_policy = "any"\nsetup_hook_timeout = 45\n')
    loaded = load_config(path)
    configured = resolve_config(sources=(loaded,))
    assert configured.setup_hook_policy == "any"
    assert configured.setup_hook_timeout == 45

    flagged = resolve_config(
        sources=(loaded,),
        flags={"setup_hook_policy": "tracked", "setup_hook_timeout": 10},
    )
    assert flagged.setup_hook_policy == "tracked"
    assert flagged.setup_hook_timeout == 10

    assert (
        resolve_config(
            sources=(loaded,), flags={"setup_hook_policy": "off"}
        ).setup_hook_policy
        == "off"
    )
