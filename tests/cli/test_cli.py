"""G-CLI — full command-tree and doctor conformance."""

import os
import shutil
import subprocess
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


@pytest.mark.matrix("T-CLI-13")
def test_fork_help_exposes_partial_destination_flags(repo_scenario):
    from conftest import run_cli

    world = repo_scenario()
    output = run_cli(["help", "fork"], world.env, world.parent_path).stdout
    assert b"--worktree-base-dir" in output
    assert b"--worktree-name" in output


@pytest.mark.matrix("T-CLI-15")
def test_help_documents_commands_options_and_exit_codes(repo_scenario):
    """P01-T19 — publishable help explains the surface and exit contract."""
    from conftest import run_cli

    world = repo_scenario()
    top = run_cli(["--help"], world.env, world.parent_path)
    assert top.returncode == 0 and top.stderr == b""
    for text in (
        b"adaptive coding-agent session integration",
        b"fork",
        b"Create a verified branch and worktree",
        b"cleanup",
        b"Remove a registered fork",
        b"Exit codes:",
        b"2 usage error",
        b"3 agent/session/target not found",
        b"5 conflict or precondition refusal",
        b"130/143 interrupted",
    ):
        assert text in top.stdout

    fork = run_cli(["help", "fork"], world.env, world.parent_path)
    for text in (
        b"Fork identity; derived from the current branch",
        b"Host agent (claude or codex); detected",
        b"Preview every planned local mutation",
        b"Replace only the derived worktree parent directory",
    ):
        assert text in fork.stdout

    cleanup = run_cli(["help", "cleanup"], world.env, world.parent_path)
    for text in (
        b"Fork name, branch, or worktree path",
        b"Confirm removal non-interactively",
        b"Never remove the invoking working",
    ):
        assert text in cleanup.stdout

    verbose = run_cli(["-vv", "config", "validate"], world.env, world.parent_path)
    assert verbose.returncode == 0
    assert b"agent-fork: command=config" in verbose.stderr
    assert b"agent-fork: cwd=" in verbose.stderr
    quiet = run_cli(["-vv", "-q", "config", "validate"], world.env, world.parent_path)
    assert quiet.returncode == 0 and quiet.stderr == b""

    debug = run_cli(
        [
            "--debug",
            "fork",
            "bad-agent",
            "--agent",
            "alien",
            "--parent-session",
            "id",
        ],
        world.env,
        world.parent_path,
    )
    assert debug.returncode == 3
    assert b"Traceback (most recent call last)" in debug.stderr
    assert b"unknown agent 'alien'" in debug.stderr


@pytest.mark.matrix("T-CLI-14")
def test_exact_destination_conflicts_with_either_partial_before_inspection(
    repo_scenario,
):
    from conftest import run_cli

    world = repo_scenario()
    for partial in (["--worktree-base-dir", "."], ["--worktree-name", "leaf"]):
        completed = run_cli(
            ["fork", "x", "--worktree-dir", "exact", *partial],
            {},
            world.parent_path.parent,
        )
        assert completed.returncode == 2
        assert b"cannot be combined" in completed.stderr


@pytest.mark.matrix("T-NAM-11")
def test_explicit_fixed_branch_collision_refuses_without_suffix(repo_scenario):
    from conftest import run_cli

    world = repo_scenario("plain@main")
    completed = run_cli(
        [
            "fork",
            "--branch",
            "main",
            "--dry-run",
            "--agent",
            "claude",
            "--parent-session",
            "11111111-1111-1111-1111-111111111111",
        ],
        world.env,
        world.parent_path,
    )
    assert completed.returncode == 5
    assert b"branch already exists: main" in completed.stderr
    assert b"main-2" not in completed.stderr

    occupied = world.parent_path.parent / "occupied"
    occupied.mkdir()
    path_collision = run_cli(
        [
            "fork",
            "--worktree-dir",
            str(occupied),
            "--dry-run",
            "--agent",
            "claude",
            "--parent-session",
            "11111111-1111-1111-1111-111111111111",
        ],
        world.env,
        world.parent_path,
    )
    assert path_collision.returncode == 5
    assert b"worktree destination already exists" in path_collision.stderr


@pytest.mark.matrix("T-LOC-12")
def test_relative_base_resolves_from_invocation_cwd(repo_scenario):
    from agent_fork.location import compose_worktree_destination

    world = repo_scenario()
    base = world.parent_path / "relative"
    base.mkdir()
    assert (
        compose_worktree_destination(
            world.parent_path / "derived",
            invocation_cwd=world.parent_path,
            base_dir=Path("relative"),
        )
        == base / "derived"
    )


@pytest.mark.matrix("T-LOC-13")
def test_explicit_base_must_exist_and_be_directory(repo_scenario):
    from agent_fork.errors import PreconditionError
    from agent_fork.location import compose_worktree_destination

    world = repo_scenario()
    for base in (world.parent_path / "missing", world.parent_path / "tracked.txt"):
        with pytest.raises(PreconditionError) as caught:
            compose_worktree_destination(
                world.parent_path / "derived",
                invocation_cwd=world.parent_path,
                base_dir=base,
            )
        assert caught.value.code == "invalid_worktree_base"


def _completion(repo_scenario, shell):
    from conftest import run_cli

    world = repo_scenario()
    completed = run_cli(["completion", shell], world.env, world.parent_path)
    assert completed.returncode == 0 and completed.stderr == b""
    return completed.stdout.decode()


def _assert_completion_semantics(script):
    for token in (
        "fork",
        "cleanup",
        "config",
        "view",
        "validate",
        "--worktree-base-dir",
        "--worktree-name",
        "--parent-session",
        "--help",
        "--config",
        "--debug",
        "claude",
        "codex",
        "table",
        "json",
        "bash",
        "zsh",
        "fish",
    ):
        assert token in script or token.removeprefix("--") in script


@pytest.mark.matrix("T-CLI-16")
def test_bash_completion_semantics_and_syntax(repo_scenario):
    script = _completion(repo_scenario, "bash")
    _assert_completion_semantics(script)
    completed = subprocess.run(
        ["bash", "-n"], input=script, text=True, capture_output=True, check=False
    )
    assert completed.returncode == 0, completed.stderr


@pytest.mark.matrix("T-CLI-17")
def test_zsh_completion_semantics_and_syntax(repo_scenario):
    script = _completion(repo_scenario, "zsh")
    _assert_completion_semantics(script)
    executable = shutil.which("zsh")
    if executable:
        completed = subprocess.run(
            [executable, "-n"], input=script, text=True, capture_output=True
        )
        assert completed.returncode == 0, completed.stderr


@pytest.mark.matrix("T-CLI-18")
def test_fish_completion_semantics_and_syntax(repo_scenario):
    script = _completion(repo_scenario, "fish")
    _assert_completion_semantics(script)
    executable = shutil.which("fish")
    if executable:
        completed = subprocess.run(
            [executable, "-n"], input=script, text=True, capture_output=True
        )
        assert completed.returncode == 0, completed.stderr


@pytest.mark.matrix("T-CLI-19")
def test_semantic_metavars_and_config_help_order(repo_scenario):
    from conftest import run_cli

    world = repo_scenario()
    fork = run_cli(["help", "fork"], world.env, world.parent_path).stdout
    for token in (
        b"[NAME]",
        b"--agent {claude,codex}",
        b"--parent-session ID_OR_NAME",
        b"--worktree-base-dir DIRECTORY",
        b"--worktree-name COMPONENT",
    ):
        assert token in fork
    config = run_cli(["help", "config"], world.env, world.parent_path).stdout
    assert b"{view,get,set,validate}" in config
    view = run_cli(["config", "view", "--help"], world.env, world.parent_path).stdout
    assert b"Select result format" in view


@pytest.mark.matrix("T-CLI-20")
def test_agent_metavar_does_not_change_unknown_agent_exit(repo_scenario):
    from conftest import run_cli

    world = repo_scenario()
    completed = run_cli(
        ["fork", "x", "--agent", "alien", "--parent-session", "id"],
        world.env,
        world.parent_path,
    )
    assert completed.returncode == 3
    assert b"agent_not_detected" in completed.stderr


@pytest.mark.matrix("T-CLI-21")
def test_agent_mode_flags_are_mutually_exclusive(repo_scenario):
    from conftest import run_cli

    world = repo_scenario()
    completed = run_cli(
        ["fork", "x", "--require-agent", "--no-agent"],
        world.env,
        world.parent_path,
    )
    assert completed.returncode == 2


@pytest.mark.matrix("T-CLI-22")
def test_no_agent_conflicts_with_explicit_identity(repo_scenario):
    from conftest import run_cli

    world = repo_scenario()
    completed = run_cli(
        ["fork", "x", "--no-agent", "--agent", "codex", "--parent-session", "id"],
        world.env,
        world.parent_path,
    )
    assert completed.returncode == 2
    assert b"--no-agent cannot be combined" in completed.stderr


@pytest.mark.matrix("T-CLI-23")
def test_default_auto_forks_git_only_without_session(repo_scenario):
    import json

    from conftest import run_cli

    world = repo_scenario("plain@main")
    env = {
        key: value
        for key, value in world.env.items()
        if key not in {"CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID"}
    }
    completed = run_cli(
        ["fork", "terminal", "--no-with-state", "--json"],
        env,
        world.parent_path,
    )
    assert completed.returncode == 0, completed.stderr.decode()
    document = json.loads(completed.stdout)
    assert document["mode"] == "git-only"
    assert document["command"].startswith("cd ")
    assert Path(document["fork"]["worktree"]).is_dir()
    doctor_env = _doctor_env(world, agents=False)
    for key in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID"):
        doctor_env.pop(key, None)
    doctor = run_cli(["doctor"], doctor_env, world.parent_path)
    assert doctor.returncode == 0
    assert b"selected=git-only" in doctor.stdout


@pytest.mark.matrix("T-CLI-24")
def test_codex_session_name_resolution_surface(repo_scenario):
    from conftest import run_cli

    world = repo_scenario()
    help_text = run_cli(["help", "fork"], world.env, world.parent_path).stdout
    assert b"--codex-session-name-resolution" in help_text
    assert b"--no-codex-session-name-resolution" in help_text
    assert b"renamed Codex session name" in b" ".join(help_text.split())

    configured = world.parent_path / "codex-resolution.toml"
    assert (
        run_cli(
            [
                "--config",
                str(configured),
                "config",
                "set",
                "agents.codex.session_name_resolution",
                "false",
            ],
            world.env,
            world.parent_path,
        ).returncode
        == 0
    )
    read = run_cli(
        [
            "--config",
            str(configured),
            "config",
            "get",
            "agents.codex.session_name_resolution",
        ],
        world.env,
        world.parent_path,
    )
    assert read.returncode == 0 and read.stdout == b"false\n"
