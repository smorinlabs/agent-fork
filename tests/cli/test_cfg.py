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
