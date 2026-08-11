"""G-SES — installed CLI inspection and assertion contract."""

import json

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
    assert not path.exists()
