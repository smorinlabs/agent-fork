"""P09 — OpenCode on the CLI surfaces Claude and Codex already have (tier C).

Matrix: docs/testing/TEST-MATRIX.md §G-CLI.
"""

import json
from pathlib import Path

import pytest


def _opencode_cli(repo_scenario, fake_opencode, **build):
    world = repo_scenario()
    fake = fake_opencode(
        {"ses_parent1": {"title": "Parent", "directory": str(world.parent_path)}},
        **build,
    )
    env = {
        **fake.path_env(world.env),
        "OPENCODE": "1",
        "OPENCODE_SESSION_ID": "ses_parent1",
    }
    return world, fake, env


@pytest.mark.matrix("T-CLI-71")
def test_agent_choices_and_help_name_opencode(repo_scenario, fake_opencode):
    """T-CLI-71 — `fork --agent` and `session validate --agent` accept opencode."""
    from conftest import run_cli

    world, fake, env = _opencode_cli(repo_scenario, fake_opencode, service="stopped")
    fork_help = run_cli(["help", "fork"], env, world.parent_path).stdout
    assert b"{claude,codex,opencode}" in fork_help
    assert b"Host agent (claude, codex, or opencode); detected" in fork_help
    validated = run_cli(
        ["session", "validate", "--agent", "opencode", "--json"],
        env,
        world.parent_path,
    )
    assert validated.returncode == 0, validated.stderr
    assert json.loads(validated.stdout)["valid"] is True
    wrong = run_cli(
        ["session", "validate", "--agent", "codex", "--json"], env, world.parent_path
    )
    assert wrong.returncode == 3


@pytest.mark.matrix("T-CLI-72")
def test_opencode_dry_run_forks_nothing(repo_scenario, fake_opencode):
    """T-CLI-72 — a dry run confirms the parent but never forks it."""
    from conftest import run_cli

    world, fake, env = _opencode_cli(repo_scenario, fake_opencode)
    completed = run_cli(
        ["fork", "oc-dry", "--dry-run", "--json"], env, world.parent_path
    )
    assert completed.returncode == 0, completed.stderr
    document = json.loads(completed.stdout)
    assert document["mutation_performed"] is False
    assert document["command"].endswith("&& opencode --session <forked session ID>")
    assert fake.api_ops() == ["session.get"]

    # A stopped service is never started by a dry run: no `opencode api` call.
    fake.update(service="stopped")
    stopped = run_cli(
        ["fork", "oc-dry2", "--dry-run", "--json"], env, world.parent_path
    )
    assert stopped.returncode == 0, stopped.stderr
    notices = json.loads(stopped.stdout)["notices"]
    assert any("service is not running" in notice for notice in notices)
    assert fake.api_ops() == ["session.get"]


@pytest.mark.matrix("T-CLI-73")
def test_opencode_extra_args_come_from_their_own_config_table(
    repo_scenario, fake_opencode
):
    """T-CLI-73 — `[agents.opencode] extra_args` reach the paste command; the
    Codex table never does."""
    from conftest import run_cli

    world, fake, env = _opencode_cli(repo_scenario, fake_opencode)
    config = Path(world.env["XDG_CONFIG_HOME"]) / "agent-fork/agent-fork_config.toml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(
        '[agents.opencode]\nextra_args = ["--auto"]\n'
        '[agents.codex]\nextra_args = ["--codex-only"]\n'
    )
    shown = run_cli(["config", "view", "--json"], env, world.parent_path)
    assert shown.returncode == 0, shown.stderr
    assert json.loads(shown.stdout)["agents"]["opencode"] == {"extra_args": ["--auto"]}
    forked = run_cli(["fork", "oc-args", "--json"], env, world.parent_path)
    assert forked.returncode == 0, forked.stderr
    command = json.loads(forked.stdout)["command"]
    assert command.endswith("opencode --session ses_child1 --auto")
    assert "--codex-only" not in command
    # `config set` rewrites the file; the OpenCode table must survive it.
    updated = run_cli(["config", "set", "branch_prefix", "oc/"], env, world.parent_path)
    assert updated.returncode == 0, updated.stderr
    rewritten = config.read_text()
    assert "branch_prefix" in rewritten and "[agents.opencode]" in rewritten
    kept = run_cli(["config", "view", "--json"], env, world.parent_path)
    assert json.loads(kept.stdout)["agents"]["opencode"] == {"extra_args": ["--auto"]}


@pytest.mark.matrix("T-CLI-74")
def test_doctor_reports_opencode_version_and_recipe_flag(repo_scenario, fake_opencode):
    """T-CLI-74 — OpenCode gets a version row and a recipe-flag entry; it is
    optional unless OpenCode is the selected agent."""
    from conftest import run_cli

    world, fake, env = _opencode_cli(repo_scenario, fake_opencode)
    selected = run_cli(["doctor"], env, world.parent_path)
    output = selected.stdout.decode()
    assert "OpenCode CLI: 2.2.7 (no minimum)" in output
    assert "opencode: 1 documented" in output
    assert "selected=opencode" in output

    unselected_env = {
        key: value for key, value in env.items() if not key.startswith("OPENCODE")
    }
    unselected = run_cli(["doctor"], unselected_env, world.parent_path).stdout
    assert b"OpenCode CLI: 2.2.7 (no minimum) (optional)" in unselected

    missing_env = {
        **env,
        "PATH": world.env["PATH"].replace(
            str(Path.home() / ".opencode/bin"), "/nonexistent"
        ),
    }
    missing = run_cli(["doctor"], missing_env, world.parent_path)
    assert missing.returncode != 0
    assert b"FAIL OpenCode CLI: missing" in missing.stdout
