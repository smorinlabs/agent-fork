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
    """A13(B) — the effective output is text or JSON, with flags winning.

    A11 amendment: the enum-rejection message now names the key, the
    offending value, the allowed forms, and the winning source (owner
    decision 3), generated by the shared `validate_values()` registry rather
    than a standalone inline check (F1/F2). The message shape changed; the
    rejection itself, and the override-precedence rule, did not.
    """
    from agent_fork.config import ConfigError, resolve_config

    assert resolve_config().output == "text"
    assert resolve_config(env={"AGENT_FORK_OUTPUT": "text"}).output == "text"
    assert resolve_config(env={"AGENT_FORK_OUTPUT": "json"}).output == "json"

    for invalid in ("table", "yaml", ""):
        with pytest.raises(ConfigError) as caught:
            resolve_config(env={"AGENT_FORK_OUTPUT": invalid})
        message = str(caught.value)
        assert "fork.output" in message
        assert invalid in message
        assert "text, json" in message
        assert "AGENT_FORK_OUTPUT" in message

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
def test_fork_output_key_accepted_by_loader(repo_scenario):
    """T-CFG-24 — `[fork].output` is accepted and resolves through precedence
    (owner decision 4, ratified ACCEPT 2026-08-20)."""
    from agent_fork.config import load_config, resolve_config

    world = repo_scenario()
    path = world.parent_path / "out.toml"
    path.write_text('[fork]\noutput = "json"\n')
    loaded = load_config(path)
    assert resolve_config(sources=(loaded,)).output == "json"
    assert (
        resolve_config(sources=(loaded,), env={"AGENT_FORK_OUTPUT": "text"}).output
        == "text"
    )


@pytest.mark.matrix("T-CFG-25")
def test_validate_values_finding_names_key_value_allowed_and_source(repo_scenario):
    """T-CFG-25 — a rejection names the key, the value, the allowed forms,
    and the winning source (owner decision 3)."""
    from agent_fork.config import ConfigFinding, ResolvedConfig, validate_values

    resolved = ResolvedConfig(
        with_state=True,
        with_ignored=False,
        with_submodules=True,
        branch_prefix="fork/",
        worktree_location="sibling",
        worktree_location_explicit=False,
        agent_mode="auto",
        verify=True,
        copy=False,
        output="bogus",
        config_path=None,
        claude_extra_args=(),
        codex_extra_args=(),
        codex_session_name_resolution=True,
        setup_hook_policy="tracked",
        setup_hook_timeout=300,
    )
    findings = validate_values(resolved, provenance={"output": "AGENT_FORK_OUTPUT"})
    assert len(findings) == 1
    finding = findings[0]
    assert finding == ConfigFinding(
        key="fork.output",
        value="bogus",
        reason="not one of the allowed values",
        allowed="text, json",
        source="AGENT_FORK_OUTPUT",
    )
    rendered = finding.render()
    assert "fork.output" in rendered
    assert "bogus" in rendered
    assert "text, json" in rendered
    assert "AGENT_FORK_OUTPUT" in rendered


@pytest.mark.matrix("T-CFG-26")
def test_validate_values_returns_every_finding_not_just_the_first(repo_scenario):
    """T-CFG-26 — a multi-bad-key configuration reports every finding."""
    from agent_fork.config import ResolvedConfig, validate_values

    resolved = ResolvedConfig(
        with_state=True,
        with_ignored=False,
        with_submodules=True,
        branch_prefix="-bad/",
        worktree_location="{bogus}/x",
        worktree_location_explicit=True,
        agent_mode="auto",
        verify=True,
        copy=False,
        output="bogus",
        config_path=None,
        claude_extra_args=(),
        codex_extra_args=(),
        codex_session_name_resolution=True,
        setup_hook_policy="tracked",
        setup_hook_timeout=300,
    )
    findings = validate_values(resolved, provenance={})
    keys = {finding.key for finding in findings}
    assert keys == {"fork.branch_prefix", "fork.worktree_location", "fork.output"}


@pytest.mark.matrix("T-CFG-27")
def test_branch_prefix_composed_sample_corpus_rejected(repo_scenario):
    """T-CFG-27 — an invalid composed-sample corpus is rejected.

    Validates the *composed* branch (prefix + a representative suffix), not
    the bare prefix — a prefix's legality is a property of the branch it
    composes into (A11 Gate-4 finding F7).
    """
    from agent_fork.config import ConfigError, resolve_config

    for invalid_prefix in ("-bad/", "a..b/", "a@{b/", "a~b/", "/abs/", "a//b/"):
        with pytest.raises(ConfigError):
            resolve_config(sources=({"branch_prefix": invalid_prefix},))


@pytest.mark.matrix("T-CFG-28")
def test_branch_prefix_legal_once_composed_remains_valid(repo_scenario):
    """T-CFG-28 — prefixes that are only legal once composed with a suffix
    remain valid, including ones a bare-prefix rule would have rejected
    (F7): a trailing '.' and a prefix ending 'lock' without a slash.
    Whitespace-only still falls back to the default (T-CFG-08).
    """
    from agent_fork.config import resolve_config

    for valid_prefix in ("fork/", "wt/", "user/name-", "topic.", "foolock", " \t "):
        resolved = resolve_config(sources=({"branch_prefix": valid_prefix},))
        assert resolved.branch_prefix in (valid_prefix, "fork/")

    # F14 — set_user_value() normalizes identically to resolve_config()
    # before validating: a whitespace-only branch_prefix must not be
    # spuriously refused just because it isn't pre-stripped.
    import tomllib

    from agent_fork.config import set_user_value

    world = repo_scenario()
    target = world.parent_path / "agent-fork_config.toml"
    set_user_value(target, "branch_prefix", "  \t  ")
    assert tomllib.loads(target.read_text())["fork"]["branch_prefix"] == "  \t  "


@pytest.mark.matrix("T-CFG-30")
def test_config_get_dotted_addressing_including_arrays(repo_scenario):
    """T-CFG-30 — dotted `get` addresses both agents' `extra_args` and
    `session_name_resolution`; arrays render as round-trip-parseable TOML
    literals, including the empty case.

    F15: the round-trip is proved by actually parsing the rendered literal
    back with `tomllib`, not by matching a fixed string — a value containing
    a raw newline or other control character must still emit valid TOML.
    """
    import tomllib

    from agent_fork.config import ResolvedConfig, config_get

    base = ResolvedConfig(
        with_state=True,
        with_ignored=False,
        with_submodules=True,
        branch_prefix="fork/",
        worktree_location="sibling",
        worktree_location_explicit=False,
        agent_mode="auto",
        verify=True,
        copy=False,
        output="text",
        config_path=None,
        claude_extra_args=("--model", 'opus "max"\nwith a newline\tand a tab'),
        codex_extra_args=(),
        codex_session_name_resolution=False,
        setup_hook_policy="tracked",
        setup_hook_timeout=300,
    )
    rendered = config_get(base, "agents.claude.extra_args")
    parsed = tomllib.loads(f"extra_args = {rendered}\n")["extra_args"]
    assert tuple(parsed) == base.claude_extra_args
    assert config_get(base, "agents.codex.extra_args") == "[]"
    assert config_get(base, "agents.codex.session_name_resolution") == "false"
    assert config_get(base, "branch_prefix") == "fork/"
    assert config_get(base, "fork.branch_prefix") == "fork/"


@pytest.mark.matrix("T-CFG-31")
def test_config_get_rejects_every_internal_attribute(repo_scenario):
    """T-CFG-31 — every internal-only attribute the former `hasattr`
    fallback leaked is now rejected, not just the ones first documented
    (F13): `config_path`, `mode`, `worktree_location_explicit`,
    `claude_extra_args`, `codex_extra_args`, and the bare (undotted)
    `codex_session_name_resolution`."""
    from agent_fork.config import ConfigError, ResolvedConfig, config_get

    base = ResolvedConfig(
        with_state=True,
        with_ignored=False,
        with_submodules=True,
        branch_prefix="fork/",
        worktree_location="sibling",
        worktree_location_explicit=False,
        agent_mode="auto",
        verify=True,
        copy=False,
        output="text",
        config_path=None,
        claude_extra_args=(),
        codex_extra_args=(),
        codex_session_name_resolution=True,
        setup_hook_policy="tracked",
        setup_hook_timeout=300,
    )
    for leaked in (
        "config_path",
        "mode",
        "worktree_location_explicit",
        "claude_extra_args",
        "codex_extra_args",
        "codex_session_name_resolution",
        "agents.claude.extra_args_typo",
        "__class__",
    ):
        with pytest.raises(ConfigError, match="unknown config key"):
            config_get(base, leaked)


@pytest.mark.matrix("T-CFG-36")
def test_unknown_key_is_escaped_in_get_and_set_error_messages(repo_scenario, tmp_path):
    """T-CFG-36 — PR #62 review finding: `key` is a raw CLI argument echoed
    verbatim into "unknown config key: {key}" by both `config_get()` and
    `set_user_value()`, unlike every other diagnostic in this codebase
    (`ConfigFinding.render()`). A bidi control character in the key must
    render as a printable escape in both call sites, not the raw control
    character, so a malicious key cannot reorder or hide terminal output.
    """
    from agent_fork.config import (
        ConfigError,
        ResolvedConfig,
        config_get,
        set_user_value,
    )

    base = ResolvedConfig(
        with_state=True,
        with_ignored=False,
        with_submodules=True,
        branch_prefix="fork/",
        worktree_location="sibling",
        worktree_location_explicit=False,
        agent_mode="auto",
        verify=True,
        copy=False,
        output="text",
        config_path=None,
        claude_extra_args=(),
        codex_extra_args=(),
        codex_session_name_resolution=True,
        setup_hook_policy="tracked",
        setup_hook_timeout=300,
    )
    evil_key = "evil‮name"

    with pytest.raises(ConfigError) as caught:
        config_get(base, evil_key)
    assert "‮" not in str(caught.value)
    assert "\\u202e" in str(caught.value)

    config_path = tmp_path / "agent-fork_config.toml"
    with pytest.raises(ConfigError) as caught:
        set_user_value(config_path, evil_key, "x")
    assert "‮" not in str(caught.value)
    assert "\\u202e" in str(caught.value)


@pytest.mark.matrix("T-CFG-32")
def test_config_set_array_key_refuses_naming_the_exact_file(repo_scenario, tmp_path):
    """T-CFG-32 — `config set` on an array key refuses, naming the exact
    resolved TOML file and table/key to hand-edit, distinct from an
    unknown-key refusal."""
    from agent_fork.config import ConfigError, set_user_value

    target = tmp_path / "agent-fork_config.toml"
    with pytest.raises(ConfigError) as caught:
        set_user_value(target, "agents.claude.extra_args", '["x"]')
    message = str(caught.value)
    assert "agents.claude.extra_args" in message
    assert str(target) in message
    assert "[agents.claude]" in message
    assert not target.exists()


@pytest.mark.matrix("T-CFG-33")
def test_config_set_invalid_value_leaves_file_and_directory_untouched(
    repo_scenario, tmp_path
):
    """T-CFG-33 — an invalid value refuses before `path.parent.mkdir()` runs
    (F12), not merely before the write — no directory is created, and an
    existing file is left byte-for-byte unchanged."""
    from agent_fork.config import ConfigError, set_user_value

    missing_parent_target = tmp_path / "nested" / "agent-fork_config.toml"
    with pytest.raises(ConfigError):
        set_user_value(missing_parent_target, "worktree_location", "{bogus}/x")
    assert not missing_parent_target.parent.exists()

    existing_target = tmp_path / "existing.toml"
    original = '[fork]\nbranch_prefix = "team/"\n'
    existing_target.write_text(original)
    with pytest.raises(ConfigError):
        set_user_value(existing_target, "branch_prefix", "-bad/")
    assert existing_target.read_text() == original


@pytest.mark.matrix("T-CFG-34")
def test_config_set_does_not_block_on_a_pre_existing_unrelated_invalid_key(
    repo_scenario, tmp_path
):
    """T-CFG-34 — a pre-existing invalid value elsewhere in the file does
    not block `set` on an unrelated, valid key (validates the key being set,
    not the whole re-emitted document)."""
    from agent_fork.config import set_user_value

    target = tmp_path / "agent-fork_config.toml"
    target.write_text('[fork]\nbranch_prefix = "-already-bad/"\n')
    set_user_value(target, "verify", "false")
    assert 'branch_prefix = "-already-bad/"' in target.read_text()
    assert "verify = false" in target.read_text()


@pytest.mark.matrix("T-CFG-37")
def test_setup_hook_keys_default_and_obey_precedence(repo_scenario):
    """T-CFG-37 — A12 policy resolution.

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


@pytest.mark.matrix("T-CFG-40")
def test_with_submodules_unset_defaults_true(repo_scenario):
    """A6b step 3 — with_submodules unset resolves to True (owner decision)."""
    from agent_fork.config import resolve_config

    assert resolve_config().with_submodules is True


@pytest.mark.matrix("T-CFG-41")
def test_no_with_state_forces_with_submodules_false_regardless_of_order(
    repo_scenario,
):
    """A6b step 3 — --no-with-state implies no submodule carry.

    Mirrors the existing with_state/with_ignored coupling (T-CFG-01..03), and
    is tested against *every* explicit and configured with_submodules value,
    per the implementation plan's own requirement — an implicit rule that only
    held for one ordering would be worse than no rule.
    """
    from agent_fork.config import resolve_config

    # with_submodules explicit True, with_state False in the SAME source.
    assert (
        resolve_config(
            sources=({"with_state": False, "with_submodules": True},)
        ).with_submodules
        is False
    )
    # with_state False first, with_submodules True in a LATER, higher-precedence
    # source -- with_submodules must not silently re-enable state transport.
    assert (
        resolve_config(
            sources=({"with_state": False},), flags={"with_submodules": True}
        ).with_submodules
        is False
    )
    # with_submodules True first, with_state False arriving later still wins.
    assert (
        resolve_config(
            sources=({"with_submodules": True},), flags={"with_state": False}
        ).with_submodules
        is False
    )
    # with_submodules explicitly False plus with_state False: still False,
    # for the ordinary reason (both agree), not just the implication.
    assert (
        resolve_config(
            sources=({"with_state": False, "with_submodules": False},)
        ).with_submodules
        is False
    )


@pytest.mark.matrix("T-CFG-42")
def test_with_submodules_true_does_not_imply_with_state(repo_scenario):
    """A6b step 3 — the coupling is deliberately one-directional.

    `--with-ignored` implies `--with-state` (T-CFG-03); `--with-submodules`
    must NOT — the design doc calls this out explicitly, because silently
    re-enabling state transport from a flag about submodules would be a
    surprising side effect on unrelated state.
    """
    from agent_fork.config import resolve_config

    resolved = resolve_config(sources=({"with_state": False, "with_submodules": True},))
    assert resolved.with_state is False
    assert resolved.with_submodules is False  # still forced off by with_state


@pytest.mark.matrix("T-CFG-43")
def test_with_submodules_flag_wins_over_config_source(repo_scenario):
    """A6b step 3 — explicit flags outrank configured sources, same as with_state."""
    from agent_fork.config import resolve_config

    resolved = resolve_config(
        sources=({"with_submodules": False},), flags={"with_submodules": True}
    )
    assert resolved.with_submodules is True


@pytest.mark.matrix("T-CFG-44")
def test_with_submodules_round_trips_through_config_file(repo_scenario):
    """A6b step 3 — `[fork] with_submodules` loads like the other bools."""
    from agent_fork.config import ConfigError, load_config, resolve_config

    world = repo_scenario()
    path = world.parent_path / "agent-fork_config.toml"
    path.write_text("[fork]\nwith_submodules = false\n")
    loaded = load_config(path)
    assert resolve_config(sources=(loaded,)).with_submodules is False

    bad = world.parent_path / "bad.toml"
    bad.write_text('[fork]\nwith_submodules = "yes"\n')
    with pytest.raises(ConfigError, match="must be boolean"):
        load_config(bad)


@pytest.mark.matrix("T-CFG-45")
def test_with_state_restored_by_a_later_source_restores_with_submodules_default(
    repo_scenario,
):
    """Gate-6 finding 4 -- a LOWER-precedence with_state=False must not
    permanently zero with_submodules once a HIGHER-precedence source
    re-enables with_state. The prior implementation destructively reset
    with_submodules to False inside the with_state branch, and nothing
    restored it when a later source only touched with_state -- an explicit
    `--with-state` meant to override a config file's with_state=false
    silently left submodule carrying off, contrary to the documented
    default.
    """
    from agent_fork.config import resolve_config

    resolved = resolve_config(
        sources=({"with_state": False},), flags={"with_state": True}
    )
    assert resolved.with_state is True
    assert resolved.with_submodules is True


@pytest.mark.matrix("T-CFG-46")
def test_with_submodules_is_a_registered_config_key(repo_scenario):
    """Gate-6 round 2 finding 3 -- A11 introduced `KEY_SPECS`, the registry
    `config_get`/`config_set` resolve every key through, but never gained an
    entry for `with_submodules` (it did not exist on `main` yet when A11
    shipped). Both the bare and dotted forms of a documented, effective
    config key must resolve, not raise `unknown config key`.
    """
    from agent_fork.config import (
        ConfigError,
        ResolvedConfig,
        config_get,
        set_user_value,
    )

    base = ResolvedConfig(
        with_state=True,
        with_ignored=False,
        with_submodules=True,
        branch_prefix="fork/",
        worktree_location="sibling",
        worktree_location_explicit=False,
        agent_mode="auto",
        verify=True,
        copy=False,
        output="text",
        config_path=None,
        claude_extra_args=(),
        codex_extra_args=(),
        codex_session_name_resolution=False,
        setup_hook_policy="tracked",
        setup_hook_timeout=300,
    )
    assert config_get(base, "with_submodules") == "true"
    assert config_get(base, "fork.with_submodules") == "true"

    path = repo_scenario().parent_path / "cfg.toml"
    set_user_value(path, "with_submodules", "false")
    assert path.read_text().strip() == "[fork]\nwith_submodules = false"
    set_user_value(path, "fork.with_submodules", "true")
    assert path.read_text().strip() == "[fork]\nwith_submodules = true"
    with pytest.raises(ConfigError):
        config_get(base, "with_submodule")
