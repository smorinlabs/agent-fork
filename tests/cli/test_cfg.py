"""G-CFG — Config resolution (tier C rows only; U rows in tests/unit/, F rows in
tests/pipeline/).

Matrix: docs/testing/TEST-MATRIX.md §G-CFG.
"""

from pathlib import Path

import pytest


@pytest.mark.matrix("T-CFG-12")
def test_config_set_then_validate_round_trips(repo_scenario):
    """T-CFG-12 — `config set` followed by `config validate` round-trips a written
    value.

    Given:  `config set <key> <value>` followed by `config validate`
    Expect: the written value round-trips through the CLI
    Source: REQUIREMENTS §3.2
    """
    from conftest import run_cli

    world = repo_scenario("plain@main")
    config_path = (
        Path(world.env["XDG_CONFIG_HOME"]) / "agent-fork/agent-fork_config.toml"
    )
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        '[agents.claude]\nextra_args = ["--model", "claude future"]\n'
    )
    written = run_cli(
        ["config", "set", "branch_prefix", "team/"],
        world.env,
        world.parent_path,
    )
    assert written.returncode == 0, written.stderr.decode()
    validated = run_cli(["config", "validate"], world.env, world.parent_path)
    assert validated.returncode == 0, validated.stderr.decode()
    assert validated.stdout == b"config valid\n"

    viewed = run_cli(["config", "get", "branch_prefix"], world.env, world.parent_path)
    assert viewed.returncode == 0
    assert viewed.stdout == b"team/\n"
    assert 'extra_args = ["--model", "claude future"]' in config_path.read_text()


@pytest.mark.matrix("T-CFG-35")
def test_config_set_output_round_trips(repo_scenario):
    """T-CFG-35 — `config set output` round-trips through `config
    validate`/`config get` (decision 4, ratified ACCEPT — A13 explicitly
    reserved this exact round trip for A11)."""
    from conftest import run_cli

    world = repo_scenario("plain@main")
    written = run_cli(["config", "set", "output", "json"], world.env, world.parent_path)
    assert written.returncode == 0, written.stderr.decode()
    validated = run_cli(["config", "validate"], world.env, world.parent_path)
    assert validated.returncode == 0, validated.stderr.decode()
    read = run_cli(["config", "get", "output"], world.env, world.parent_path)
    assert read.returncode == 0
    assert read.stdout == b"json\n"


HOOK_CONFIG_PATH = "agent-fork/agent-fork_config.toml"


@pytest.mark.matrix("T-CFG-38")
def test_setup_hook_keys_round_trip_through_the_config_cli(repo_scenario):
    """T-CFG-38 — A12 keys are first-class in `config set` / `config get`.

    Given:  `config set` for both A12 keys, then `config validate` and
            `config get`
    Expect: the enum round-trips as a quoted string, the timeout round-trips as
            an unquoted integer (not a string TOML would reject on reload), and
            an existing unrelated key survives the rewrite
    Source: P02 A12; REQUIREMENTS §3.2
    """
    from conftest import run_cli

    world = repo_scenario("plain@main")
    config_path = Path(world.env["XDG_CONFIG_HOME"]) / HOOK_CONFIG_PATH
    config_path.parent.mkdir(parents=True)
    config_path.write_text('[fork]\nbranch_prefix = "team/"\n')

    for key, value in (("setup_hook_policy", "any"), ("setup_hook_timeout", "45")):
        written = run_cli(["config", "set", key, value], world.env, world.parent_path)
        assert written.returncode == 0, written.stderr.decode()

    assert "setup_hook_timeout = 45" in config_path.read_text()
    assert 'setup_hook_policy = "any"' in config_path.read_text()
    assert 'branch_prefix = "team/"' in config_path.read_text()

    validated = run_cli(["config", "validate"], world.env, world.parent_path)
    assert validated.returncode == 0, validated.stderr.decode()
    assert validated.stdout == b"config valid\n"

    for key, expected in (
        ("setup_hook_policy", b"any\n"),
        ("setup_hook_timeout", b"45\n"),
    ):
        viewed = run_cli(["config", "get", key], world.env, world.parent_path)
        assert viewed.returncode == 0, viewed.stderr.decode()
        assert viewed.stdout == expected

    # `config view` builds its document independently of `config get` — a
    # configured value taking effect while `view` still omitted it went
    # unnoticed until CodeRabbit's review of PR #65.
    document = run_cli(["config", "view"], world.env, world.parent_path)
    assert document.returncode == 0, document.stderr.decode()
    view_text = document.stdout.decode()
    assert "setup_hook_policy = any" in view_text
    assert "setup_hook_timeout = 45" in view_text


@pytest.mark.matrix("T-CFG-39")
def test_invalid_setup_hook_values_are_rejected_at_validate_time(repo_scenario):
    """T-CFG-39 — the A11 guard: never validate clean and crash at use.

    A11 found a key that passed `config validate` and then crashed `fork`.
    Every rejection below therefore has to happen in `load_config()` /
    `resolve_config()`, which is what `config validate` runs, not later.

    Given:  `setup_hook_timeout` set to zero, a negative number, a string, or a
            boolean, and `setup_hook_policy` set outside {tracked, any, off}
    Expect: `ConfigError` from the library and exit 2 from the CLI in every case
    Source: P02 A12; P02 A11; REQ-12; R6.1
    """
    from agent_fork.config import ConfigError, load_config, resolve_config
    from conftest import run_cli

    world = repo_scenario("plain@main")
    config_path = Path(world.env["XDG_CONFIG_HOME"]) / HOOK_CONFIG_PATH
    config_path.parent.mkdir(parents=True)

    rejected = (
        ("setup_hook_timeout = 0", "greater than zero"),
        ("setup_hook_timeout = -1", "greater than zero"),
        ('setup_hook_timeout = "300"', "whole number of seconds"),
        ("setup_hook_timeout = true", "whole number of seconds"),
        ('setup_hook_policy = "nonsense"', "tracked, any, or off"),
        ("setup_hook_policy = 3", "must be a string"),
    )
    for line, message in rejected:
        config_path.write_text(f"[fork]\n{line}\n")
        with pytest.raises(ConfigError, match=message):
            load_config(config_path)
        completed = run_cli(["config", "validate"], world.env, world.parent_path)
        assert completed.returncode == 2, line
        assert message.encode() in completed.stderr, line

    config_path.unlink()

    # The flag path bypasses `load_config()`, so `resolve_config()` has to
    # reject the same values on its own — through A11's `validate_values()`
    # registry, whose `ConfigFinding.render()` names the key, the offending
    # value, the allowed forms, and the winning source.
    with pytest.raises(ConfigError) as rejected_timeout:
        resolve_config(flags={"setup_hook_timeout": 0})
    timeout_message = str(rejected_timeout.value)
    assert "greater than zero" in timeout_message
    # CodeRabbit, PR #65: resolve_config() never recorded provenance for
    # these two fields, so an invalid flag-set value rendered "(from
    # default)" instead of naming the flag that actually supplied it.
    assert "(from flag)" in timeout_message
    with pytest.raises(ConfigError) as rejected_policy:
        resolve_config(flags={"setup_hook_policy": "nonsense"})
    policy_message = str(rejected_policy.value)
    assert "fork.setup_hook_policy" in policy_message
    assert "'nonsense'" in policy_message
    assert "allowed: tracked, any, off" in policy_message
    assert "(from flag)" in policy_message

    flagged = run_cli(
        ["fork", "bad-timeout", "--dry-run", "--no-agent", "--setup-hook-timeout", "0"],
        world.env,
        world.parent_path,
    )
    assert flagged.returncode == 2
    assert b"greater than zero" in flagged.stderr

    # `config set` must refuse the same values rather than writing a file that
    # only fails on the next read.
    for key, value in (
        ("setup_hook_timeout", "0"),
        ("setup_hook_timeout", "never"),
        # Python's `int()` accepts digit-group underscores, so `1_000` used to
        # be written to the file as 1000 — a value the user never typed.
        ("setup_hook_timeout", "1_000"),
        ("setup_hook_policy", "nonsense"),
    ):
        refused = run_cli(["config", "set", key, value], world.env, world.parent_path)
        assert refused.returncode == 2, (key, value)
        assert not config_path.exists()
