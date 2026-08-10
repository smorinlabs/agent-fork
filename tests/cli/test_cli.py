"""G-CLI — full command-tree and doctor conformance."""

import os
import shutil
from pathlib import Path

import pytest


@pytest.mark.matrix("T-CLI-01")
def test_bare_invocation_prints_help_exit_0(repo_scenario):
    from conftest import run_cli

    world = repo_scenario()
    completed = run_cli([], world.env, world.parent_path)
    assert completed.returncode == 0 and completed.stderr == b""
    assert completed.stdout.startswith(b"usage: agent-fork")
    for command in (
        b"fork",
        b"cleanup",
        b"list",
        b"doctor",
        b"config",
        b"completion",
        b"help",
    ):
        assert command in completed.stdout


@pytest.mark.matrix("T-CLI-02")
def test_standard_global_flags_present(repo_scenario):
    from conftest import run_cli

    world = repo_scenario()
    for flag in ("-h", "--help"):
        completed = run_cli([flag], world.env, world.parent_path)
        assert completed.returncode == 0 and b"usage: agent-fork" in completed.stdout
    for flag in ("-V", "--version"):
        completed = run_cli([flag], world.env, world.parent_path)
        assert completed.returncode == 0
        assert completed.stdout == b"agent-fork 0.1.0\n"
    combined = run_cli(["-vv", "-q", "--debug"], world.env, world.parent_path)
    assert combined.returncode == 0 and b"usage: agent-fork" in combined.stdout
    path = world.parent_path.parent / "explicit.toml"
    path.write_text("[fork]\nverify = true\n")
    explicit = run_cli(
        ["--config", str(path), "config", "validate"], world.env, world.parent_path
    )
    assert explicit.returncode == 0 and explicit.stdout == b"config valid\n"
    help_text = run_cli(["--help"], world.env, world.parent_path).stdout
    for spelling in (
        b"-V",
        b"--version",
        b"-v",
        b"--verbose",
        b"-q",
        b"--quiet",
        b"--config",
        b"--debug",
    ):
        assert spelling in help_text
    fork_help = run_cli(["help", "fork"], world.env, world.parent_path)
    assert fork_help.returncode == 0
    for spelling in (
        b"--branch",
        b"--worktree-dir",
        b"--no-with-state",
        b"--no-verify",
    ):
        assert spelling in fork_help.stdout


@pytest.mark.matrix("T-CLI-03")
def test_malformed_usage_exits_2(repo_scenario):
    from conftest import run_cli

    world = repo_scenario()
    for args in (["cleanup"], ["completion", "powershell"], ["config", "get"]):
        completed = run_cli(args, world.env, world.parent_path)
        assert completed.returncode == 2
        assert b"usage:" in completed.stderr


@pytest.mark.matrix("T-CLI-04")
def test_unknown_agent_value_exits_3(repo_scenario):
    from conftest import run_cli

    world = repo_scenario()
    completed = run_cli(
        ["fork", "unknown", "--agent", "alien", "--parent-session", "id"],
        world.env,
        world.parent_path,
    )
    assert completed.returncode == 3
    assert b"unknown agent 'alien'" in completed.stderr


@pytest.mark.matrix("T-CLI-05")
def test_completion_subcommand_smoke_per_shell(repo_scenario):
    from conftest import run_cli

    world = repo_scenario()
    for shell in ("bash", "zsh", "fish"):
        completed = run_cli(["completion", shell], world.env, world.parent_path)
        assert completed.returncode == 0 and completed.stderr == b""
        assert b"agent-fork" in completed.stdout
        assert completed.stdout.strip()


def _doctor_env(world, *, agents=True, git_version="2.43.0"):
    directory = world.parent_path.parent / ("doctor-bin" if agents else "git-bin")
    directory.mkdir()
    real_git = Path(shutil.which("git") or "/usr/bin/git").resolve()
    git = directory / "git"
    git.write_text(
        "#!/bin/sh\n"
        f"if [ \"$1\" = --version ]; then echo 'git version {git_version}'; exit; fi\n"
        f'exec {real_git} "$@"\n'
    )
    git.chmod(0o755)
    if agents:
        for name, version in (("claude", "2.1.220"), ("codex", "codex-cli 0.147.0")):
            path = directory / name
            path.write_text(f"#!/bin/sh\necho '{version}'\n")
            path.chmod(0o755)
    return {
        **world.env,
        "PATH": f"{directory}{os.pathsep}{world.env['PATH'] if agents else ''}",
        "CLAUDECODE": "1",
        "CLAUDE_CODE_SESSION_ID": "11111111-1111-1111-1111-111111111111",
    }


@pytest.mark.parametrize(
    "subject",
    [
        pytest.param(
            "git-version", id="T-CLI-06", marks=pytest.mark.matrix("T-CLI-06")
        ),
        pytest.param("agent-clis", id="T-CLI-07", marks=pytest.mark.matrix("T-CLI-07")),
        pytest.param(
            "env-signals", id="T-CLI-08", marks=pytest.mark.matrix("T-CLI-08")
        ),
        pytest.param(
            "config-validity", id="T-CLI-09", marks=pytest.mark.matrix("T-CLI-09")
        ),
        pytest.param("xdg-paths", id="T-CLI-10", marks=pytest.mark.matrix("T-CLI-10")),
    ],
)
def test_doctor_content_reports_each_subject(repo_scenario, subject):
    from conftest import run_cli

    world = repo_scenario()
    environment = _doctor_env(world)
    completed = run_cli(["doctor"], environment, world.parent_path)
    assert completed.returncode == 0 and completed.stderr == b""
    output = completed.stdout.decode()
    expected = {
        "git-version": "git PRODUCT_GIT_MIN: 2.43.0 (minimum 2.19.0)",
        "agent-clis": "Claude CLI: 2.1.220",
        "env-signals": "environment signals: CLAUDECODE=1",
        "config-validity": "config validity: valid",
        "xdg-paths": "XDG paths:",
    }[subject]
    assert expected in output
    if subject == "agent-clis":
        assert "Codex CLI: 0.147.0" in output
    if subject == "config-validity":
        invalid = world.parent_path / ".agent-fork/agent-fork_config.toml"
        invalid.parent.mkdir()
        invalid.write_text("not valid toml = [")
        failed = run_cli(["doctor"], environment, world.parent_path)
        assert failed.returncode != 0
        assert b"FAIL config validity" in failed.stdout


@pytest.mark.matrix("T-CLI-11")
def test_a14_failing_doctor_check_nonzero_exit(repo_scenario):
    from conftest import run_cli

    world = repo_scenario()
    completed = run_cli(
        ["doctor", "--json"],
        _doctor_env(world, git_version="2.18.9"),
        world.parent_path,
    )
    assert completed.returncode != 0
    assert b'"ok":false' in completed.stdout
    assert b"git PRODUCT_GIT_MIN" in completed.stdout
    assert b"2.18.9" in completed.stdout and b"2.19.0" in completed.stdout


@pytest.mark.matrix("T-CLI-12")
def test_clean_flag_rejected_as_unknown(repo_scenario):
    from conftest import run_cli

    world = repo_scenario()
    completed = run_cli(["fork", "name", "--clean"], world.env, world.parent_path)
    assert completed.returncode == 2
    assert b"unrecognized arguments: --clean" in completed.stderr
    abbreviated = run_cli(["fork", "name", "--ver"], world.env, world.parent_path)
    assert abbreviated.returncode == 2
    assert b"unrecognized arguments: --ver" in abbreviated.stderr
