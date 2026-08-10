"""G-CLN command consent and dry-run rows."""

import pytest


def _forked(repo_scenario, name):
    from agent_fork.agents import AgentContext
    from agent_fork.pipeline import ForkRequest, fork
    from conftest import origin

    world = repo_scenario("plain@main", remote=origin())
    result = fork(
        ForkRequest(
            parent=world.parent_path,
            destination=world.parent_path.parent / f"child-{name}",
            name=name,
            branch=f"fork/{name}",
            agent=AgentContext("claude", "11111111-1111-1111-1111-111111111111"),
            agent_executable="/fake/claude",
            agent_version_output="Claude Code 2.1.220",
            git_version_output="git version 2.43.0",
            child_session_id="33333333-3333-3333-3333-333333333333",
        ),
        env=world.env,
    )
    return world, result


@pytest.mark.matrix("T-CLN-09")
def test_yes_flag_bypasses_consent_prompt(repo_scenario):
    from conftest import run_cli

    world, result = _forked(repo_scenario, "yes")
    completed = run_cli(["cleanup", "yes", "--yes"], world.env, world.parent_path)
    assert completed.returncode == 0
    assert b"[y/N]" not in completed.stderr
    assert not result.creation.path.exists()


@pytest.mark.matrix("T-CLN-10")
def test_no_input_without_yes_fails_exit_2(repo_scenario):
    from conftest import run_cli

    world, result = _forked(repo_scenario, "no-input")
    completed = run_cli(
        ["cleanup", "no-input", "--no-input"], world.env, world.parent_path
    )
    assert completed.returncode == 2
    assert b"requires --yes" in completed.stderr
    assert result.creation.path.exists()


@pytest.mark.matrix("T-CLN-11")
def test_tty_consent_prompt_names_exact_removal_targets(repo_scenario):
    from conftest import pty_run

    world, result = _forked(repo_scenario, "prompt")
    completed = pty_run(["cleanup", "prompt"], world.env, 2)
    assert completed.returncode == 2
    prompt = completed.tty.decode()
    assert f"remove worktree {result.creation.path}" in prompt
    assert "delete fork/prompt" in prompt
    assert "registry: prompt" in prompt
    assert result.creation.path.exists()


@pytest.mark.matrix("T-CLN-13")
def test_dry_run_prints_removal_plan_without_mutating(repo_scenario):
    from agent_fork.registry import find_owned
    from conftest import run_cli

    world, result = _forked(repo_scenario, "dry")
    completed = run_cli(["cleanup", "dry", "--dry-run"], world.env, world.parent_path)
    assert completed.returncode == 0 and completed.stderr == b""
    assert b"would remove worktree" in completed.stdout
    assert str(result.creation.path).encode() in completed.stdout
    assert result.creation.path.exists()
    assert find_owned("dry", env=world.env) is not None


@pytest.mark.matrix("T-CLN-15")
def test_force_does_not_substitute_for_consent(repo_scenario):
    from conftest import run_cli

    world, result = _forked(repo_scenario, "force-consent")
    completed = run_cli(
        ["cleanup", "force-consent", "--force", "--no-input"],
        world.env,
        world.parent_path,
    )
    assert completed.returncode == 2
    assert b"requires --yes" in completed.stderr
    assert result.creation.path.exists()
