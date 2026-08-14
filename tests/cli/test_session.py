"""G-SES — installed CLI inspection and assertion contract."""

import json
from pathlib import Path

import pytest


@pytest.mark.matrix("T-SES-09")
def test_session_json_without_agent_is_success(repo_scenario):
    from conftest import run_cli

    world = repo_scenario()
    result = run_cli(["session", "-o", "json"], world.env, world.parent_path)
    assert result.returncode == 0 and result.stderr == b""
    assert json.loads(result.stdout)["lineage"]["status"] == "not_detected"


@pytest.mark.matrix("T-SES-10")
def test_plain_validate_requires_session(repo_scenario):
    from conftest import run_cli

    world = repo_scenario()
    result = run_cli(
        ["session", "validate", "-o", "json"], world.env, world.parent_path
    )
    assert result.returncode == 3 and result.stdout == b""
    assert json.loads(result.stderr)["error"]["code"] == "session_validation_failed"


@pytest.mark.matrix("T-SES-11")
def test_validate_agent_and_id(repo_scenario):
    from conftest import run_cli

    world = repo_scenario()
    env = {
        **world.env,
        "CLAUDECODE": "1",
        "CLAUDE_CODE_SESSION_ID": "child",
    }
    result = run_cli(
        [
            "session",
            "validate",
            "--agent",
            "claude",
            "--session-id",
            "child",
            "--no-parent",
            "-o",
            "json",
        ],
        env,
        world.parent_path,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout)["valid"] is True


@pytest.mark.matrix("T-SES-12")
def test_parent_id_conflicts_with_no_parent(repo_scenario):
    from conftest import run_cli

    world = repo_scenario()
    result = run_cli(
        ["session", "validate", "--parent-session-id", "parent", "--no-parent"],
        world.env,
        world.parent_path,
    )
    assert result.returncode == 2


@pytest.mark.matrix("T-SES-13")
def test_session_json_alias_matches_output(repo_scenario):
    from conftest import run_cli

    world = repo_scenario()
    explicit = run_cli(["session", "-o", "json"], world.env, world.parent_path)
    alias = run_cli(["session", "--json"], world.env, world.parent_path)
    assert alias.stdout == explicit.stdout and alias.stderr == explicit.stderr


@pytest.mark.matrix("T-SES-19")
def test_session_human_output_escapes_terminal_controls(repo_scenario):
    from conftest import run_cli

    world = repo_scenario()
    env = {
        **world.env,
        "CLAUDECODE": "1",
        "CLAUDE_CODE_SESSION_ID": "child\x1b[31m\nnext\u202e",
    }
    result = run_cli(["session"], env, world.parent_path)
    assert b"\x1b" not in result.stdout
    assert b"child\\u001b[31m\\nnext" in result.stdout
    assert b"\\u202e" in result.stdout


@pytest.mark.matrix("T-SES-22")
def test_session_does_not_require_git_or_write_state(repo_scenario):
    from agent_fork.lineage import lineage_path
    from conftest import run_cli

    world = repo_scenario()
    outside = world.parent_path.parent / "ordinary-terminal"
    outside.mkdir()
    path = lineage_path(world.env)
    assert not path.exists()
    result = run_cli(["session", "-o", "json"], world.env, outside)
    assert result.returncode == 0
    document = json.loads(result.stdout)
    assert document["directory"] == str(outside.resolve())
    assert document["repository"] is None
    assert not path.exists()


@pytest.mark.matrix("T-SES-27")
def test_human_session_always_labels_and_escapes_repository_context(repo_scenario):
    from conftest import run_cli

    world = repo_scenario("plain@branch")
    directory = world.parent_path / "unsafe-\x1b[31m-\u202e"
    directory.mkdir()
    environments = (
        world.env,
        {
            **world.env,
            "CLAUDECODE": "1",
            "CLAUDE_CODE_SESSION_ID": "claude",
            "CODEX_THREAD_ID": "codex",
        },
    )

    for env in environments:
        result = run_cli(["session"], env, directory)
        assert result.returncode == 0 and result.stderr == b""
        assert b"directory:" in result.stdout
        assert b"repository:" in result.stdout
        assert b"branch: feature" in result.stdout
        assert b"worktree: linked=no bare=no" in result.stdout
        assert b"status: clean" in result.stdout
        assert b"\x1b" not in result.stdout
        assert b"\\u001b[31m" in result.stdout
        assert b"\\u202e" in result.stdout


@pytest.mark.matrix("T-SES-30")
def test_session_outputs_fork_command_object_or_explicit_status(repo_scenario):
    import re

    from conftest import run_cli

    world = repo_scenario()
    env = {
        **world.env,
        "CLAUDECODE": "1",
        "CLAUDE_CODE_SESSION_ID": "claude-child",
    }
    machine = run_cli(["session", "--json"], env, world.parent_path)
    document = json.loads(machine.stdout)
    command = document["fork_command"]
    assert command["status"] == "available"
    assert re.fullmatch(
        rf"cd {re.escape(str(world.parent_path))} && claude --session-id "
        r"[0-9a-f-]{36} --resume claude-child --fork-session",
        command["command"],
    )

    human = run_cli(["session"], env, world.parent_path)
    assert re.search(
        rb"^fork command: cd .* && claude --session-id [0-9a-f-]{36} "
        rb"--resume claude-child --fork-session$",
        human.stdout,
        flags=re.MULTILINE,
    )

    absent = run_cli(["session"], world.env, world.parent_path)
    assert b"fork command: unavailable (not_detected)" in absent.stdout

    unsafe_env = {
        **world.env,
        "CLAUDECODE": "1",
        "CLAUDE_CODE_SESSION_ID": "unsafe\x1b]52;c;Zm9v\x07\nnext\u202e",
    }
    unsafe = run_cli(["session"], unsafe_env, world.parent_path)
    assert b"\x1b" not in unsafe.stdout and b"\x07" not in unsafe.stdout
    assert b"fork command: unavailable (unsafe_input)" in unsafe.stdout


@pytest.mark.matrix("T-SES-31")
def test_session_command_construction_has_no_mutating_side_effects(repo_scenario):
    from agent_fork.git import run_git
    from agent_fork.lineage import lineage_path
    from conftest import run_cli

    world = repo_scenario()
    spy_dir = world.parent_path.parent / "session-spies"
    spy_dir.mkdir()
    called = spy_dir / "called"
    for executable in ("claude", "codex", "pbcopy", "xclip"):
        script = spy_dir / executable
        script.write_text(f"#!/bin/sh\ntouch '{called}'\nexit 99\n")
        script.chmod(0o755)
    config = Path(world.env["XDG_CONFIG_HOME"]) / "agent-fork" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text("this is not valid toml = [")
    env = {
        **world.env,
        "PATH": f"{spy_dir}:{world.env['PATH']}",
        "CLAUDECODE": "1",
        "CLAUDE_CODE_SESSION_ID": "claude-child",
    }
    before = run_git(
        world.parent_path, ["status", "--porcelain=v1", "-z"], env=world.env
    ).stdout
    lineage = lineage_path(env)
    assert not lineage.exists()

    result = run_cli(["session", "--json"], env, world.parent_path)

    after = run_git(
        world.parent_path, ["status", "--porcelain=v1", "-z"], env=world.env
    ).stdout
    assert result.returncode == 0 and result.stderr == b""
    assert json.loads(result.stdout)["fork_command"]["status"] == "available"
    assert before == after
    assert not called.exists()
    assert not lineage.exists()


@pytest.mark.matrix("T-SES-32")
def test_session_help_discovers_constructible_fork_commands(repo_scenario):
    from conftest import run_cli

    world = repo_scenario()
    result = run_cli(["session", "--help"], world.env, world.parent_path)

    assert result.returncode == 0 and result.stderr == b""
    assert b"Examples:" in result.stdout
    assert b"agent-fork session" in result.stdout
    assert b"agent-fork session --json" in result.stdout
    assert b"constructible, not preflighted" in result.stdout
