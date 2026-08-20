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


@pytest.mark.matrix("T-EMT-08")
def test_claude_session_fork_command_is_byte_exact(repo_scenario):
    from agent_fork.agents import build_session_fork_command

    world = repo_scenario()
    built = build_session_fork_command(
        _context("claude"),
        directory=world.parent_path,
        child_session_id="33333333-3333-4333-8333-333333333333",
    )

    assert built.command == (
        f"cd {world.parent_path} && claude --session-id "
        "33333333-3333-4333-8333-333333333333 --resume "
        "11111111-1111-1111-1111-111111111111 --fork-session"
    )
    assert built.child_session_id == "33333333-3333-4333-8333-333333333333"
    assert built.extra_args == ()


@pytest.mark.matrix("T-EMT-09")
def test_codex_session_fork_command_is_byte_exact(repo_scenario):
    from agent_fork.agents import build_session_fork_command

    world = repo_scenario()
    built = build_session_fork_command(_context("codex"), directory=world.parent_path)

    assert built.command == (
        f"codex fork 22222222-2222-2222-2222-222222222222 -C {world.parent_path}"
    )
    assert built.child_session_id is None
    assert built.extra_args == ()


@pytest.mark.matrix("T-EMT-10")
def test_session_renderer_quotes_shell_values_and_rejects_terminal_controls(
    repo_scenario,
):
    from agent_fork.agents import (
        AgentContext,
        UnsafeCommandInputError,
        build_session_fork_command,
    )

    world = repo_scenario()
    hostile_directory = world.parent_path.parent / "space ' quote $HOME; safe"
    hostile_directory.mkdir()
    binary = world.parent_path.parent / "session-bin"
    binary.mkdir()
    log = _fake_binary(binary, "claude")
    parent = "parent ' $HOME; touch INJECTED"
    child = "33333333-3333-4333-8333-333333333333"
    built = build_session_fork_command(
        AgentContext("claude", parent),
        directory=hostile_directory,
        child_session_id=child,
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
    assert json.loads(log.read_text()) == [
        "--session-id",
        child,
        "--resume",
        parent,
        "--fork-session",
    ]
    assert not (world.parent_path / "INJECTED").exists()

    unsafe_values = (
        "line\nfeed",
        "escape\x1b]52;c;Zm9v\x07",
        "delete\x7f",
        "c1\x9b",
        "bidi\u202e",
    )
    for unsafe in unsafe_values:
        with pytest.raises(UnsafeCommandInputError):
            build_session_fork_command(
                AgentContext("claude", unsafe),
                directory=world.parent_path,
                child_session_id=child,
            )
        with pytest.raises(UnsafeCommandInputError):
            build_session_fork_command(
                _context("claude"),
                directory=world.parent_path / unsafe,
                child_session_id=child,
            )

    from agent_fork.pipeline import ForkRequest, fork

    destination = world.parent_path.parent / "unsafe-command-child"
    branch = "fork/unsafe-command-child"
    request = ForkRequest(
        parent=world.parent_path,
        destination=destination,
        name="unsafe-command-child",
        branch=branch,
        agent=_context("claude"),
        extra_args=("unsafe\x1b]52;c;Zm9v\x07",),
        agent_executable="/fake/claude",
        agent_version_output="Claude Code 2.1.220",
        git_version_output="git version 2.43.0",
        child_session_id=child,
    )

    with pytest.raises(UnsafeCommandInputError):
        fork(request, env=world.env)

    branch_probe = subprocess.run(
        [
            "git",
            "-C",
            str(world.parent_path),
            "show-ref",
            "--verify",
            "--quiet",
            f"refs/heads/{branch}",
        ],
        env=world.env,
    )
    assert branch_probe.returncode != 0
    assert not destination.exists()


@pytest.mark.matrix("T-EMT-11")
def test_claude_session_resume_command_is_byte_exact(repo_scenario):
    from agent_fork.agents import build_session_resume_command

    world = repo_scenario()
    built = build_session_resume_command(
        _context("claude"), directory=world.parent_path
    )

    assert built.command == (
        f"cd {world.parent_path} && claude --resume "
        "11111111-1111-1111-1111-111111111111"
    )
    assert built.child_session_id is None
    assert built.extra_args == ()


@pytest.mark.matrix("T-EMT-12")
def test_codex_session_resume_command_is_byte_exact(repo_scenario):
    from agent_fork.agents import build_session_resume_command

    world = repo_scenario()
    built = build_session_resume_command(_context("codex"), directory=world.parent_path)

    assert built.command == (
        f"codex resume 22222222-2222-2222-2222-222222222222 -C {world.parent_path}"
    )
    assert built.child_session_id is None
    assert built.extra_args == ()


@pytest.mark.matrix("T-EMT-13")
def test_session_resume_renderer_quotes_shell_values_and_rejects_terminal_controls(
    repo_scenario,
):
    from agent_fork.agents import (
        AgentContext,
        UnsafeCommandInputError,
        build_session_resume_command,
    )

    world = repo_scenario()
    hostile_directory = world.parent_path.parent / "space ' quote $HOME; safe"
    hostile_directory.mkdir()
    binary = world.parent_path.parent / "resume-bin"
    binary.mkdir()
    log = _fake_binary(binary, "claude")
    parent = "parent ' $HOME; touch INJECTED"
    built = build_session_resume_command(
        AgentContext("claude", parent), directory=hostile_directory
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
    assert json.loads(log.read_text()) == ["--resume", parent]
    assert not (world.parent_path / "INJECTED").exists()

    unsafe_values = (
        "line\nfeed",
        "escape\x1b]52;c;Zm9v\x07",
        "delete\x7f",
        "c1\x9b",
        "bidi\u202e",
    )
    for unsafe in unsafe_values:
        with pytest.raises(UnsafeCommandInputError):
            build_session_resume_command(
                AgentContext("claude", unsafe), directory=world.parent_path
            )
        with pytest.raises(UnsafeCommandInputError):
            build_session_resume_command(
                _context("claude"), directory=world.parent_path / unsafe
            )
