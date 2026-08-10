"""G-EMT — byte-exact locked templates and shell-boundary proofs."""

import json
import os
import subprocess

import pytest


def _context(agent):
    from agent_fork.agents import AgentContext

    parent = (
        "11111111-1111-1111-1111-111111111111"
        if agent == "claude"
        else "22222222-2222-2222-2222-222222222222"
    )
    return AgentContext(agent, parent)


@pytest.mark.matrix("T-EMT-01")
def test_claude_fixed_prefix_byte_exact(repo_scenario):
    from agent_fork.agents import build_launch_command

    world = repo_scenario()
    built = build_launch_command(
        _context("claude"),
        worktree=world.parent_path,
        name="review",
        child_session_id="33333333-3333-3333-3333-333333333333",
    )
    assert built.command == (
        f"cd {world.parent_path} && claude --session-id "
        "33333333-3333-3333-3333-333333333333 --resume "
        "11111111-1111-1111-1111-111111111111 --fork-session -n review"
    )
    assert built.child_session_id == "33333333-3333-3333-3333-333333333333"


@pytest.mark.matrix("T-EMT-02")
def test_codex_fixed_prefix_byte_exact(repo_scenario):
    from agent_fork.agents import build_launch_command

    world = repo_scenario()
    built = build_launch_command(
        _context("codex"), worktree=world.parent_path, name="ignored-by-codex"
    )
    assert built.command == (
        f"codex fork 22222222-2222-2222-2222-222222222222 -C {world.parent_path}"
    )
    assert built.child_session_id is None


def _fake_binary(directory, name):
    log = directory / "argv.json"
    script = directory / name
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "Path(os.environ['ARGV_LOG']).write_text(json.dumps(sys.argv[1:]))\n"
    )
    script.chmod(0o755)
    return log


@pytest.mark.matrix("T-EMT-03")
def test_uniform_quoting_of_special_chars_in_worktree_path(repo_scenario):
    from agent_fork.agents import build_launch_command

    world = repo_scenario()
    hostile = world.parent_path.parent / "space ' quote $HOME; touch INJECTED"
    hostile.mkdir()
    binary = world.parent_path.parent / "bin"
    binary.mkdir()
    log = _fake_binary(binary, "claude")
    command = build_launch_command(
        _context("claude"),
        worktree=hostile,
        name="safe",
        child_session_id="33333333-3333-3333-3333-333333333333",
    ).command
    completed = subprocess.run(
        ["/bin/sh", "-c", command],
        env={
            **world.env,
            "PATH": f"{binary}{os.pathsep}{world.env['PATH']}",
            "ARGV_LOG": str(log),
        },
        capture_output=True,
    )
    assert completed.returncode == 0
    assert not (world.parent_path / "INJECTED").exists()
    assert hostile == hostile.resolve()
    assert json.loads(log.read_text())[-2:] == ["-n", "safe"]


@pytest.mark.matrix("T-EMT-04")
def test_extra_args_shell_quoted_at_emission(repo_scenario):
    from agent_fork.agents import build_launch_command

    world = repo_scenario()
    binary = world.parent_path.parent / "bin"
    binary.mkdir()
    log = _fake_binary(binary, "codex")
    hostile = ("two words", "single'quote", "$HOME", "; touch INJECTED")
    built = build_launch_command(
        _context("codex"), worktree=world.parent_path, name="review", extra_args=hostile
    )
    completed = subprocess.run(
        ["/bin/sh", "-c", built.command],
        cwd=world.parent_path,
        env={
            **world.env,
            "PATH": f"{binary}{os.pathsep}{world.env['PATH']}",
            "ARGV_LOG": str(log),
        },
        capture_output=True,
    )
    assert completed.returncode == 0
    assert json.loads(log.read_text())[-4:] == list(hostile)
    assert not (world.parent_path / "INJECTED").exists()


@pytest.mark.matrix("T-EMT-05")
def test_extra_args_visible_in_dry_run_output(repo_scenario):
    from agent_fork.agents import build_launch_command

    world = repo_scenario()
    built = build_launch_command(
        _context("claude"),
        worktree=world.parent_path,
        name="review",
        extra_args=("--model", "gpt future"),
        child_session_id="33333333-3333-3333-3333-333333333333",
    )
    output = built.dry_run_text()
    assert "--model" in output and "gpt future" in output
    assert built.command in output and "local-only" in output


@pytest.mark.matrix("T-EMT-06")
def test_extra_args_visible_in_json_command_field(repo_scenario):
    from agent_fork.agents import build_launch_command

    world = repo_scenario()
    built = build_launch_command(
        _context("codex"),
        worktree=world.parent_path,
        name="review",
        extra_args=("--model", "claude future"),
    )
    fields = built.json_fields()
    assert fields["extra_args"] == ["--model", "claude future"]
    command = fields["command"]
    assert isinstance(command, str)
    assert "--model 'claude future'" in command
