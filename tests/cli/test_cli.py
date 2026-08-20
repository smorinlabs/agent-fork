"""G-CLI — full command-tree and doctor conformance."""

import json
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
        assert completed.stdout == b"agent-fork 1.2.0\n"  # x-release-please-version
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
        # Each stub answers --help with the recipe flags it claims to support,
        # so the A4 recipe-flag check sees a faithful CLI, not a bare stub.
        for name, version, help_text in (
            (
                "claude",
                "2.1.220",
                "--session-id <uuid> -r, --resume [value] --fork-session -n, --name",
            ),
            ("codex", "codex-cli 0.147.0", "-C, --cd <DIR>"),
        ):
            path = directory / name
            path.write_text(
                "#!/bin/sh\n"
                'for arg in "$@"; do\n'
                '  [ "$arg" = "--help" ] && { echo '
                + f"'{help_text}'"
                + "; exit 0; }\n"
                "done\n"
                f"echo '{version}'\n"
            )
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
        pytest.param(
            "recipe-flags", id="T-CLI-25", marks=pytest.mark.matrix("T-CLI-25")
        ),
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
        "env-signals": "environment signals: status=detected",
        "config-validity": "config validity: valid",
        "xdg-paths": "XDG paths:",
        "recipe-flags": "agent recipe flags: claude: 4 documented",
    }[subject]
    assert expected in output
    if subject == "recipe-flags":
        assert "codex: 1 documented" in output
    if subject == "agent-clis":
        assert "Codex CLI: 0.147.0" in output
    if subject == "config-validity":
        invalid = world.parent_path / ".agent-fork/agent-fork_config.toml"
        invalid.parent.mkdir()
        invalid.write_text("not valid toml = [")
        failed = run_cli(["doctor"], environment, world.parent_path)
        assert failed.returncode != 0
        assert b"FAIL config validity" in failed.stdout


@pytest.mark.matrix("T-CLI-26")
def test_doctor_recipe_drift_fails_only_for_the_selected_agent(repo_scenario):
    """An unused CLI's drift must not fail an otherwise healthy diagnosis."""
    from conftest import run_cli

    world = repo_scenario()
    environment = _doctor_env(world)
    drifted = Path(environment["PATH"].split(os.pathsep)[0]) / "codex"
    drifted.write_text("#!/bin/sh\necho 'codex-cli 0.147.0'\n")
    drifted.chmod(0o755)

    # CLAUDECODE is set by _doctor_env, so Claude is the selected agent.
    completed = run_cli(["doctor"], environment, world.parent_path)
    assert completed.returncode == 0
    assert b"undocumented -C (unselected)" in completed.stdout

    claude = Path(environment["PATH"].split(os.pathsep)[0]) / "claude"
    claude.write_text("#!/bin/sh\necho '2.1.220'\n")
    claude.chmod(0o755)
    failed = run_cli(["doctor"], environment, world.parent_path)
    assert failed.returncode != 0
    assert b"FAIL agent recipe flags" in failed.stdout


def _with_agent_signals(environment, **signals):
    result = {
        key: value
        for key, value in environment.items()
        if key not in {"CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID"}
    }
    result.update(signals)
    return result


def _doctor_checks(completed):
    document = json.loads(completed.stdout)
    return document, {check["name"]: check for check in document["checks"]}


def _signal_detail(status, present, missing, mode, selected):
    present_text = ", ".join(present)
    missing_text = ", ".join(missing)
    return (
        f"status={status}, present=[{present_text}], missing=[{missing_text}], "
        f"mode={mode}, selected={selected}"
    )


@pytest.mark.matrix("T-CLI-27")
def test_doctor_uses_shared_incomplete_and_ambiguous_assessment(repo_scenario):
    """Auto and strict diagnostics must never reinterpret a partial signal."""
    from conftest import run_cli

    world = repo_scenario()
    base = _doctor_env(world)
    codex = Path(base["PATH"].split(os.pathsep)[0]) / "codex"
    codex.write_text("#!/bin/sh\necho 'codex-cli 0.147.0'\n")
    codex.chmod(0o755)
    shapes = (
        (
            {"CLAUDECODE": "1"},
            "incomplete",
            ("CLAUDECODE=1",),
            ("CLAUDE_CODE_SESSION_ID",),
            "claude",
        ),
        (
            {"CLAUDE_CODE_SESSION_ID": "claude-parent"},
            "incomplete",
            ("CLAUDE_CODE_SESSION_ID",),
            ("CLAUDECODE=1",),
            "claude",
        ),
        (
            {"CLAUDECODE": "1", "CODEX_THREAD_ID": "codex-parent"},
            "ambiguous",
            ("CLAUDECODE=1", "CODEX_THREAD_ID"),
            ("CLAUDE_CODE_SESSION_ID",),
            "ambiguous",
        ),
        (
            {
                "CLAUDE_CODE_SESSION_ID": "claude-parent",
                "CODEX_THREAD_ID": "codex-parent",
            },
            "ambiguous",
            ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID"),
            ("CLAUDECODE=1",),
            "ambiguous",
        ),
    )

    for mode, mode_args in (("auto", []), ("strict", ["--require-agent"])):
        for signals, status, present, missing, selected in shapes:
            completed = run_cli(
                ["doctor", "--json", *mode_args],
                _with_agent_signals(base, **signals),
                world.parent_path,
            )

            assert completed.returncode == 1
            assert completed.stderr == b""
            document, checks = _doctor_checks(completed)
            assert document["ok"] is False
            assert checks["environment signals"] == {
                "name": "environment signals",
                "ok": False,
                "detail": _signal_detail(status, present, missing, mode, selected),
            }
            assert checks["agent recipe flags"]["ok"] is True
            assert (
                "codex: undocumented -C (unselected)"
                in checks["agent recipe flags"]["detail"]
            )
            if status == "incomplete":
                assert "(optional)" not in checks["Claude CLI"]["detail"]
                assert checks["Codex CLI"]["detail"].endswith("(optional)")
            else:
                assert "(optional)" not in checks["Claude CLI"]["detail"]
                assert "(optional)" not in checks["Codex CLI"]["detail"]


@pytest.mark.matrix("T-CLI-28")
def test_doctor_explicit_git_only_reports_signals_without_failing(repo_scenario):
    from conftest import run_cli

    world = repo_scenario()
    base = _doctor_env(world)
    codex = Path(base["PATH"].split(os.pathsep)[0]) / "codex"
    codex.write_text("#!/bin/sh\necho 'codex-cli 0.147.0'\n")
    codex.chmod(0o755)
    shapes = (
        (
            {"CLAUDECODE": "1"},
            "incomplete",
            ("CLAUDECODE=1",),
            ("CLAUDE_CODE_SESSION_ID",),
        ),
        (
            {"CLAUDECODE": "1", "CODEX_THREAD_ID": "codex-parent"},
            "ambiguous",
            ("CLAUDECODE=1", "CODEX_THREAD_ID"),
            ("CLAUDE_CODE_SESSION_ID",),
        ),
    )

    for signals, status, present, missing in shapes:
        completed = run_cli(
            ["doctor", "--json", "--no-agent"],
            _with_agent_signals(base, **signals),
            world.parent_path,
        )

        assert completed.returncode == 0
        assert completed.stderr == b""
        document, checks = _doctor_checks(completed)
        assert document["ok"] is True
        assert checks["environment signals"] == {
            "name": "environment signals",
            "ok": True,
            "detail": _signal_detail(status, present, missing, "git-only", "git-only"),
        }
        assert checks["Claude CLI"]["detail"].endswith("(optional)")
        assert checks["Codex CLI"]["detail"].endswith("(optional)")
        assert checks["agent recipe flags"]["ok"] is True
        assert (
            "codex: undocumented -C (unselected)"
            in checks["agent recipe flags"]["detail"]
        )


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
        "-o",
        "--worktree-base-dir",
        "--worktree-name",
        "--parent-session",
        "--help",
        "--config",
        "--debug",
        "claude",
        "codex",
        "text",
        "json",
        "bash",
        "zsh",
        "fish",
    ):
        if token in script or token.removeprefix("--") in script:
            continue
        if len(token) == 2 and token.startswith("-") and f"-s '{token[1:]}'" in script:
            continue
        raise AssertionError(f"missing completion token: {token!r}")
    assert "table" not in script


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


def _output_route_arguments(output=None):
    suffix = [] if output is None else ["-o", output]
    return (
        ["fork", "format", "--dry-run", "--no-agent", "--no-with-state", *suffix],
        ["session", *suffix],
        ["session", "validate", *suffix],
        ["session", "claude-parent", "list", *suffix],
        [
            "session",
            "claude-parent",
            "show",
            "--session-id",
            "child",
            *suffix,
        ],
        ["session", "claude-parent", "infer", "--current", *suffix],
        [
            "session",
            "claude-parent",
            "delete",
            "--session-id",
            "child",
            "--no-input",
            *suffix,
        ],
        ["list", *suffix],
        ["cleanup", "missing", "--dry-run", "--yes", *suffix],
        ["doctor", *suffix],
        ["config", "view", *suffix],
    )


@pytest.mark.matrix("T-CLI-32")
def test_a13b_text_is_only_human_output_across_cli_boundaries(repo_scenario, capsys):
    """A13(B) removes the byte-identical table alias from every CLI boundary."""
    from agent_fork.cli import _parser
    from conftest import run_cli

    parser = _parser()
    defaults = [
        parser.parse_args(arguments).output for arguments in _output_route_arguments()
    ]
    assert defaults == [None, *("text",) * 10]
    for output in ("text", "json"):
        assert all(
            parser.parse_args(arguments).output == output
            for arguments in _output_route_arguments(output)
        )
    nested_routes = (
        ["validate"],
        ["claude-parent", "list"],
        ["claude-parent", "show", "--session-id", "child"],
        ["claude-parent", "infer", "--current"],
        [
            "claude-parent",
            "delete",
            "--session-id",
            "child",
            "--no-input",
        ],
    )
    for route in nested_routes:
        for option in (("-o", "json"), ("--json",)):
            before = parser.parse_args(["session", *option, *route])
            after = parser.parse_args(["session", *route, *option])
            assert ("json" if before.json else before.output) == "json"
            assert ("json" if after.json else after.output) == "json"
    for arguments in _output_route_arguments("table"):
        with pytest.raises(SystemExit) as caught:
            parser.parse_args(arguments)
        assert caught.value.code == 2
    capsys.readouterr()

    world = repo_scenario("plain@main")
    environment = {
        key: value
        for key, value in world.env.items()
        if key not in {"CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID"}
    }

    created = run_cli(
        ["fork", "format-cleanup", "--no-agent", "--no-with-state", "--json"],
        environment,
        world.parent_path,
    )
    assert created.returncode == 0, created.stderr.decode()

    command_pairs = (
        (
            ["fork", "preview", "--dry-run", "--no-agent", "--no-with-state"],
            [
                "fork",
                "preview",
                "--dry-run",
                "--no-agent",
                "--no-with-state",
                "-o",
                "text",
            ],
            environment,
        ),
        (["session"], ["session", "-o", "text"], environment),
        (["list"], ["list", "-o", "text"], environment),
        (
            ["cleanup", "format-cleanup", "--dry-run", "--yes"],
            ["cleanup", "format-cleanup", "--dry-run", "--yes", "-o", "text"],
            environment,
        ),
        (["doctor"], ["doctor", "-o", "text"], _doctor_env(world, agents=False)),
        (["config", "view"], ["config", "view", "-o", "text"], environment),
    )
    for default_arguments, text_arguments, command_environment in command_pairs:
        default = run_cli(default_arguments, command_environment, world.parent_path)
        explicit = run_cli(text_arguments, command_environment, world.parent_path)
        assert (default.returncode, default.stdout, default.stderr) == (
            explicit.returncode,
            explicit.stdout,
            explicit.stderr,
        )

    invalid_environment = {**environment, "AGENT_FORK_OUTPUT": "table"}
    for output_arguments in (("-o", "text"), ("-o", "json"), ("--json",)):
        explicit_output = run_cli(
            [
                "fork",
                "override",
                "--dry-run",
                "--no-agent",
                "--no-with-state",
                *output_arguments,
            ],
            invalid_environment,
            world.parent_path,
        )
        assert explicit_output.returncode == 0, explicit_output.stderr.decode()

    invalid_fork = run_cli(
        ["fork", "invalid", "--dry-run", "--no-agent", "--no-with-state"],
        invalid_environment,
        world.parent_path,
    )
    assert invalid_fork.returncode == 2
    assert invalid_fork.stdout == b""
    assert invalid_fork.stderr == b"output must be text or json\n"

    rejected_table = run_cli(["session", "-o", "table"], environment, world.parent_path)
    assert rejected_table.returncode == 2
    assert b"invalid choice: 'table'" in rejected_table.stderr

    for arguments in (
        ["session"],
        ["list"],
        ["cleanup", "format-cleanup", "--dry-run", "--yes"],
    ):
        baseline = run_cli(arguments, environment, world.parent_path)
        ignored = run_cli(arguments, invalid_environment, world.parent_path)
        assert (ignored.returncode, ignored.stdout, ignored.stderr) == (
            baseline.returncode,
            baseline.stdout,
            baseline.stderr,
        )

    invalid_config = run_cli(
        ["config", "view", "--json"], invalid_environment, world.parent_path
    )
    assert invalid_config.returncode == 2
    assert json.loads(invalid_config.stderr) == {
        "error": {
            "code": "config_error",
            "message": "output must be text or json",
        }
    }

    doctor_environment = {
        **_doctor_env(world),
        "AGENT_FORK_OUTPUT": "table",
    }
    invalid_doctor = run_cli(
        ["doctor", "--json"], doctor_environment, world.parent_path
    )
    assert invalid_doctor.returncode == 1
    doctor_document, checks = _doctor_checks(invalid_doctor)
    assert doctor_document["ok"] is False
    assert checks["config validity"] == {
        "name": "config validity",
        "ok": False,
        "detail": "output must be text or json",
    }

    for shell in ("bash", "zsh", "fish"):
        script = _completion(repo_scenario, shell)
        assert "text" in script
        assert "json" in script
        assert "table" not in script


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


def _assert_incomplete_error(completed, *, present, missing):
    missing_text = ", ".join(missing)
    assert completed.returncode == 3
    assert completed.stdout == b""
    assert json.loads(completed.stderr) == {
        "error": {
            "code": "agent_signal_incomplete",
            "message": (
                f"incomplete agent signal; missing {missing_text}; restore the "
                "missing value or choose --no-agent intentionally"
            ),
            "details": {
                "status": "incomplete",
                "present": list(present),
                "missing": list(missing),
            },
        }
    }


def _fork_state(world, environment, destination):
    from agent_fork.git import run_git
    from agent_fork.lineage import lineage_path
    from agent_fork.lineage_inference_store import (
        index_freshness_path,
        inference_path,
    )
    from agent_fork.registry import registry_path

    cache_home = Path(
        environment.get("XDG_CACHE_HOME", Path(environment["HOME"]) / ".cache")
    )
    artifacts = (
        registry_path(environment),
        lineage_path(environment),
        inference_path(environment),
        index_freshness_path(environment),
        cache_home / "agent-fork",
    )
    return {
        "branches": run_git(
            world.parent_path,
            ["for-each-ref", "--format=%(refname)", "refs/heads"],
            env=environment,
        ).stdout,
        "worktrees": run_git(
            world.parent_path,
            ["worktree", "list", "--porcelain"],
            env=environment,
        ).stdout,
        "destination_exists": destination.exists(),
        "artifact_exists": tuple(path.exists() for path in artifacts),
    }


@pytest.mark.matrix("T-CLI-29")
def test_auto_fork_refuses_incomplete_signal_with_exact_json(repo_scenario):
    from conftest import run_cli

    world = repo_scenario("plain@main")
    environment = _with_agent_signals(world.env, CLAUDECODE="1")
    destination = world.parent_path.parent / "incomplete-auto"
    before = _fork_state(world, environment, destination)

    completed = run_cli(
        [
            "fork",
            "incomplete-auto",
            "--json",
            "--no-with-state",
            "--worktree-dir",
            str(destination),
        ],
        environment,
        world.parent_path,
    )

    _assert_incomplete_error(
        completed,
        present=("CLAUDECODE=1",),
        missing=("CLAUDE_CODE_SESSION_ID",),
    )
    assert _fork_state(world, environment, destination) == before


@pytest.mark.matrix("T-CLI-30")
def test_strict_fork_refuses_incomplete_signal_with_exact_json(repo_scenario):
    from conftest import run_cli

    world = repo_scenario("plain@main")
    environment = _with_agent_signals(world.env, CLAUDE_CODE_SESSION_ID="claude-parent")
    destination = world.parent_path.parent / "incomplete-strict"
    before = _fork_state(world, environment, destination)

    completed = run_cli(
        [
            "fork",
            "incomplete-strict",
            "--require-agent",
            "--json",
            "--no-with-state",
            "--worktree-dir",
            str(destination),
        ],
        environment,
        world.parent_path,
    )

    _assert_incomplete_error(
        completed,
        present=("CLAUDE_CODE_SESSION_ID",),
        missing=("CLAUDECODE=1",),
    )
    assert _fork_state(world, environment, destination) == before


@pytest.mark.matrix("T-CLI-31")
def test_incomplete_dry_run_refuses_before_any_mutation(repo_scenario):
    from conftest import run_cli

    world = repo_scenario("plain@main")
    environment = _with_agent_signals(world.env, CLAUDECODE="1")
    destination = world.parent_path.parent / "incomplete-dry-run"
    before = _fork_state(world, environment, destination)
    assert before["destination_exists"] is False
    assert not any(before["artifact_exists"])

    completed = run_cli(
        [
            "fork",
            "incomplete-dry-run",
            "--dry-run",
            "--json",
            "--worktree-dir",
            str(destination),
        ],
        environment,
        world.parent_path,
    )

    _assert_incomplete_error(
        completed,
        present=("CLAUDECODE=1",),
        missing=("CLAUDE_CODE_SESSION_ID",),
    )
    assert _fork_state(world, environment, destination) == before
