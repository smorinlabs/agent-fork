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


@pytest.mark.matrix("T-SES-38")
def test_session_outputs_resume_command_object_or_explicit_status(repo_scenario):
    from conftest import run_cli

    world = repo_scenario()
    env = {
        **world.env,
        "CLAUDECODE": "1",
        "CLAUDE_CODE_SESSION_ID": "claude-child",
    }
    machine = run_cli(["session", "--json"], env, world.parent_path)
    document = json.loads(machine.stdout)
    command = document["resume_command"]
    assert command["status"] == "available"
    assert command["command"] == (
        f"cd {world.parent_path} && claude --resume claude-child"
    )

    human = run_cli(["session"], env, world.parent_path)
    assert (
        f"resume command: cd {world.parent_path} && claude --resume claude-child"
    ).encode() in human.stdout

    absent = run_cli(["session"], world.env, world.parent_path)
    assert b"resume command: unavailable (not_detected)" in absent.stdout

    unsafe_env = {
        **world.env,
        "CLAUDECODE": "1",
        "CLAUDE_CODE_SESSION_ID": "unsafe\x1b]52;c;Zm9v\x07\nnext\u202e",
    }
    unsafe = run_cli(["session"], unsafe_env, world.parent_path)
    assert b"\x1b" not in unsafe.stdout and b"\x07" not in unsafe.stdout
    assert b"resume command: unavailable (unsafe_input)" in unsafe.stdout


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


@pytest.mark.matrix("T-SES-34")
def test_session_machine_output_exposes_exact_agent_signal(repo_scenario):
    from agent_fork.git import run_git
    from agent_fork.lineage import lineage_path
    from agent_fork.lineage_inference_store import index_freshness_path, inference_path
    from conftest import run_cli

    cases = (
        (
            {},
            {"status": "absent", "present": [], "missing": []},
            "not_detected",
            "not_detected",
        ),
        (
            {"CLAUDECODE": "1"},
            {
                "status": "incomplete",
                "present": ["CLAUDECODE=1"],
                "missing": ["CLAUDE_CODE_SESSION_ID"],
            },
            "not_detected",
            "not_detected",
        ),
        (
            {
                "CLAUDECODE": "1",
                "CLAUDE_CODE_SESSION_ID": "claude-child",
            },
            {
                "status": "detected",
                "present": ["CLAUDECODE=1", "CLAUDE_CODE_SESSION_ID"],
                "missing": [],
            },
            "not_found",
            "available",
        ),
        (
            {"CLAUDECODE": "1", "CODEX_THREAD_ID": "codex-thread"},
            {
                "status": "ambiguous",
                "present": ["CLAUDECODE=1", "CODEX_THREAD_ID"],
                "missing": ["CLAUDE_CODE_SESSION_ID"],
            },
            "ambiguous",
            "ambiguous",
        ),
    )

    for signals, expected_signal, expected_lineage, expected_fork in cases:
        world = repo_scenario()
        env = {**world.env, **signals}
        markers = {}
        state_before = []
        cache_root = world.parent_path.parent / "cache"
        git_before = (
            run_git(
                world.parent_path,
                ["status", "--porcelain=v1", "-z"],
                env=world.env,
            ).stdout,
            run_git(
                world.parent_path,
                ["for-each-ref", "--format=%(refname) %(objectname)"],
                env=world.env,
            ).stdout,
            run_git(
                world.parent_path,
                ["worktree", "list", "--porcelain"],
                env=world.env,
            ).stdout,
        )
        if expected_signal["status"] == "incomplete":
            spy_dir = world.parent_path.parent / "incomplete-session-spies"
            spy_dir.mkdir()
            markers = {
                name: spy_dir / f"{name}.called"
                for name in ("claude", "codex", "pbcopy", "xclip")
            }
            for name, marker in markers.items():
                script = spy_dir / name
                script.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 99\n")
                script.chmod(0o755)
            env = {
                **env,
                "PATH": f"{spy_dir}:{world.env['PATH']}",
                "XDG_CACHE_HOME": str(cache_root),
            }
            state_root = Path(env["XDG_STATE_HOME"])
            state_before = sorted(
                (path.relative_to(state_root), path.read_bytes())
                for path in state_root.rglob("*")
                if path.is_file()
            )
        result = run_cli(
            ["session", "--json"],
            env,
            world.parent_path,
        )

        assert result.returncode == 0 and result.stderr == b""
        document = json.loads(result.stdout)
        assert document["agent_signal"] == expected_signal
        assert document["lineage"]["status"] == expected_lineage
        assert document["fork_command"]["status"] == expected_fork

        if expected_signal["status"] == "incomplete":
            assert document["agent"] is None
            assert document["current_session"] is None
            assert document["parent_session"] is None
            assert document["lineage"] == {
                "has_parent_evidence": False,
                "status": "not_detected",
            }
            assert document["fork_command"] == {
                "status": "not_detected",
                "command": None,
            }
            assert any(
                "incomplete" in notice and "CLAUDE_CODE_SESSION_ID" in notice
                for notice in document["notices"]
            )

            human = run_cli(["session"], env, world.parent_path)
            assert human.returncode == 0 and human.stderr == b""
            assert b"agent signal: incomplete" in human.stdout
            assert b"session: not_detected" in human.stdout
            assert b"notice:" in human.stdout
            assert b"CLAUDE_CODE_SESSION_ID" in human.stdout

            state_root = Path(env["XDG_STATE_HOME"])
            state_after = sorted(
                (path.relative_to(state_root), path.read_bytes())
                for path in state_root.rglob("*")
                if path.is_file()
            )
            assert state_after == state_before
            git_after = (
                run_git(
                    world.parent_path,
                    ["status", "--porcelain=v1", "-z"],
                    env=world.env,
                ).stdout,
                run_git(
                    world.parent_path,
                    ["for-each-ref", "--format=%(refname) %(objectname)"],
                    env=world.env,
                ).stdout,
                run_git(
                    world.parent_path,
                    ["worktree", "list", "--porcelain"],
                    env=world.env,
                ).stdout,
            )
            assert git_after == git_before
            assert not lineage_path(env).exists()
            assert not inference_path(env).exists()
            assert not index_freshness_path(env).exists()
            assert not cache_root.exists()
            assert all(not marker.exists() for marker in markers.values())

        if expected_signal["status"] == "detected":
            validated = run_cli(
                [
                    "session",
                    "validate",
                    "--agent",
                    "claude",
                    "--session-id",
                    "claude-child",
                    "--no-parent",
                    "--json",
                ],
                env,
                world.parent_path,
            )
            assert validated.returncode == 0 and validated.stderr == b""
            validation = json.loads(validated.stdout)
            assert validation["valid"] is True
            assert validation["session"]["agent_signal"] == expected_signal
