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
    # A11 amendment: every route now defaults to None, not just `fork` — a
    # defaulted "text" was indistinguishable from an explicit `-o text`,
    # which meant `config.output` (from `[fork].output`/`AGENT_FORK_OUTPUT`,
    # decision 4, ratified ACCEPT) could never win for any command but
    # `fork` (A11 Gate-4 finding F8).
    assert defaults == [None] * 11
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

    # A11 amendment: the message now names the key, the offending value, the
    # allowed forms, and the winning source (owner decision 3), generated by
    # the shared `validate_values()` registry (F1/F2) rather than the bare
    # string A13(B) originally shipped.
    expected_message = (
        "fork.output: invalid value 'table' (not one of the allowed values); "
        "allowed: text, json (from AGENT_FORK_OUTPUT)"
    )

    invalid_fork = run_cli(
        ["fork", "invalid", "--dry-run", "--no-agent", "--no-with-state"],
        invalid_environment,
        world.parent_path,
    )
    assert invalid_fork.returncode == 2
    assert invalid_fork.stdout == b""
    assert invalid_fork.stderr == (expected_message + "\n").encode()

    rejected_table = run_cli(["session", "-o", "table"], environment, world.parent_path)
    assert rejected_table.returncode == 2
    assert b"invalid choice: 'table'" in rejected_table.stderr

    # A11 amendment: `session`, `list`, and `cleanup` no longer ignore
    # `AGENT_FORK_OUTPUT` — A13's own design doc named all three as
    # continuing to ignore it "because changing that broader configuration
    # inconsistency belongs to A11" (Gate-4 finding F9). They now reject an
    # invalid value the same as every other consumer, instead of being
    # output-invariant to it.
    for arguments in (
        ["session"],
        ["list"],
        ["cleanup", "format-cleanup", "--dry-run", "--yes"],
    ):
        rejected = run_cli(arguments, invalid_environment, world.parent_path)
        assert rejected.returncode == 2
        assert rejected.stdout == b""
        assert expected_message in rejected.stderr.decode()

    # An explicit --json rescues an invalid AGENT_FORK_OUTPUT the same way
    # fork's explicit -o/--json flags do above (flags beat env, even when
    # the env value is invalid, not only when it's merely a lower-precedence
    # valid one) — the CLI-flag-threading fix for A11 Gate-6 finding
    # (Codex): config view/doctor previously resolved configuration without
    # passing the explicit flag through, so it could never rescue an
    # otherwise-invalid AGENT_FORK_OUTPUT the way `fork` already could.
    rescued_config = run_cli(
        ["config", "view", "--json"], invalid_environment, world.parent_path
    )
    assert rescued_config.returncode == 0, rescued_config.stderr.decode()
    assert json.loads(rescued_config.stdout)["output"] == "json"

    invalid_config_no_flag = run_cli(
        ["config", "view"], invalid_environment, world.parent_path
    )
    assert invalid_config_no_flag.returncode == 2
    assert invalid_config_no_flag.stderr.decode().strip() == expected_message

    doctor_environment = {
        **_doctor_env(world),
        "AGENT_FORK_OUTPUT": "table",
    }
    rescued_doctor = run_cli(
        ["doctor", "--json"], doctor_environment, world.parent_path
    )
    assert rescued_doctor.returncode == 0, rescued_doctor.stdout.decode()
    doctor_document, checks = _doctor_checks(rescued_doctor)
    assert doctor_document["ok"] is True
    assert checks["config validity"]["ok"] is True

    # Without any rescuing flag, doctor still correctly fails the check.
    # Note: `--json`/`-o json` is itself a rescuing flag here (decision 4 —
    # a flag beats an invalid env value the same as a valid one), so
    # observing the failure means observing it in doctor's human rendering.
    invalid_doctor = run_cli(["doctor"], doctor_environment, world.parent_path)
    assert invalid_doctor.returncode == 1
    assert f"FAIL config validity: {expected_message}".encode() in invalid_doctor.stdout

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


@pytest.mark.parametrize(
    ("config_toml", "expected_fragment"),
    [
        pytest.param(
            '[fork]\nworktree_location = "{bogus}/x"\n',
            "unknown placeholder",
            id="T-CLI-51",
            marks=pytest.mark.matrix("T-CLI-51"),
        ),
        pytest.param(
            '[fork]\nworktree_location = "{session-id}/w"\n',
            "not supported",
            id="T-CLI-52",
            marks=pytest.mark.matrix("T-CLI-52"),
        ),
        pytest.param(
            '[fork]\nbranch_prefix = "-bad/"\n',
            "must not begin with -",
            id="T-CLI-53",
            marks=pytest.mark.matrix("T-CLI-53"),
        ),
    ],
)
def test_invalid_config_rejected_identically_by_validate_and_fork(
    repo_scenario, config_toml, expected_fragment
):
    """T-CLI-51..53 — the same invalid input is rejected identically by
    `config validate`, `fork --dry-run`, and real `fork` — no
    validate-says-yes-then-fork-fails divergence (outcome 1)."""
    from conftest import run_cli

    world = repo_scenario("plain@main")
    environment = {
        key: value
        for key, value in world.env.items()
        if key not in {"CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID"}
    }
    config_path = world.parent_path / "invalid.toml"
    config_path.write_text(config_toml)
    args_prefix = ["--config", str(config_path)]

    validated = run_cli(
        [*args_prefix, "config", "validate"], environment, world.parent_path
    )
    assert validated.returncode == 2
    assert expected_fragment in validated.stderr.decode()

    dry_run = run_cli(
        [*args_prefix, "fork", "probe", "--dry-run", "--no-agent", "--no-with-state"],
        environment,
        world.parent_path,
    )
    assert dry_run.returncode == 2
    assert expected_fragment in dry_run.stderr.decode()
    assert validated.stderr == dry_run.stderr

    real_fork = run_cli(
        [*args_prefix, "fork", "probe", "--no-agent", "--no-with-state"],
        environment,
        world.parent_path,
    )
    assert real_fork.returncode == 2
    assert real_fork.stderr == dry_run.stderr


@pytest.mark.matrix("T-CLI-54")
def test_invalid_config_real_fork_creates_no_artifact(repo_scenario):
    """T-CLI-54 — the real-fork refusal case creates no branch, worktree,
    registry, lineage, or cache artifact — the choke point refuses before
    any mutation, not merely before printing success."""
    from conftest import run_cli

    world = repo_scenario("plain@main")
    environment = {
        key: value
        for key, value in world.env.items()
        if key not in {"CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID"}
    }
    config_path = world.parent_path / "invalid.toml"
    config_path.write_text('[fork]\nworktree_location = "{bogus}/x"\n')
    destination = world.parent_path.parent / "invalid-artifact-probe"
    before = _fork_state(world, environment, destination)

    completed = run_cli(
        [
            "--config",
            str(config_path),
            "fork",
            "invalid-artifact-probe",
            "--no-agent",
            "--no-with-state",
        ],
        environment,
        world.parent_path,
    )
    assert completed.returncode == 2
    assert _fork_state(world, environment, destination) == before


@pytest.mark.matrix("T-CLI-55")
def test_doctor_reports_every_finding_joined_on_one_line(repo_scenario):
    """T-CLI-55 — `doctor` reports every semantic finding for a
    multi-bad-key configuration, joined onto one line (F11 — not newlines,
    so `doctor`'s one-check-per-line renderer and the JSON `detail` field
    both stay well-formed), and exits 0 for a valid configuration."""
    from conftest import run_cli

    world = repo_scenario("plain@main")
    environment = _doctor_env(world)
    project_config = world.parent_path / ".agent-fork/agent-fork_config.toml"
    project_config.parent.mkdir(parents=True)
    project_config.write_text(
        '[fork]\nworktree_location = "{bogus}/x"\nbranch_prefix = "-bad/"\n'
    )

    failed = run_cli(["doctor"], environment, world.parent_path)
    assert failed.returncode == 1
    detail_line = next(
        line
        for line in failed.stdout.decode().splitlines()
        if line.startswith("FAIL config validity")
    )
    assert "fork.worktree_location" in detail_line
    assert "fork.branch_prefix" in detail_line
    assert "; " in detail_line

    project_config.unlink()
    valid = run_cli(["doctor"], environment, world.parent_path)
    assert valid.returncode == 0
    assert b"FAIL config validity" not in valid.stdout


@pytest.mark.matrix("T-CLI-56")
def test_config_view_honors_valid_agent_fork_output_env(repo_scenario):
    """T-CLI-56 — `config view` honors a *valid* `AGENT_FORK_OUTPUT=json`
    with no explicit flag, closing the "validates it, then ignores it" gap
    found at Gate 4 (F8) alongside the invalid-value rejection already
    covered by T-CLI-32."""
    from conftest import run_cli

    world = repo_scenario("plain@main")
    environment = {**world.env, "AGENT_FORK_OUTPUT": "json"}
    completed = run_cli(["config", "view"], environment, world.parent_path)
    assert completed.returncode == 0
    document = json.loads(completed.stdout)
    assert document["output"] == "json"


@pytest.mark.matrix("T-CLI-57")
def test_boundary_spanning_branch_prefix_caught_only_at_fork_time(repo_scenario):
    """T-CLI-57 — T11h's fork-time `check-ref-format` guard on the *derived*
    branch is required, not optional hardening (F7): a `branch_prefix`
    ending `.loc` composed with a name starting `k` produces the component
    `foo.lock`, illegal only once the two are joined — no prefix-only or
    single-composed-sample check can catch it, so `config validate` and
    `doctor` both pass it, and only the real branch-creation guard refuses."""
    from conftest import run_cli

    world = repo_scenario("plain@main")
    environment = {
        key: value
        for key, value in world.env.items()
        if key not in {"CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID"}
    }
    config_path = world.parent_path / "boundary.toml"
    config_path.write_text('[fork]\nbranch_prefix = "foo.loc"\n')
    args_prefix = ["--config", str(config_path)]

    validated = run_cli(
        [*args_prefix, "config", "validate"], environment, world.parent_path
    )
    assert validated.returncode == 0, validated.stderr.decode()

    dry_run = run_cli(
        [*args_prefix, "fork", "k", "--dry-run", "--no-agent", "--no-with-state"],
        environment,
        world.parent_path,
    )
    assert dry_run.returncode == 5
    assert b"invalid_branch" in dry_run.stderr
    assert b"foo.lock" in dry_run.stderr

    real_fork = run_cli(
        [*args_prefix, "fork", "k", "--no-agent", "--no-with-state"],
        environment,
        world.parent_path,
    )
    assert real_fork.returncode == 5
    assert b"foo.lock" in real_fork.stderr


@pytest.mark.matrix("T-CLI-58")
def test_output_format_preserved_across_a_later_unrelated_error(repo_scenario):
    """T-CLI-58 — a valid, explicitly-resolved `AGENT_FORK_OUTPUT=json`
    keeps rendering errors as JSON even when the error that actually fires
    comes from a *different*, unrelated invalid key (F16/Gate-6 M1) — the
    output-format decision must survive past the point it was made, not only
    apply to the specific key that carried it."""
    from conftest import run_cli

    world = repo_scenario("plain@main")
    environment = {
        key: value
        for key, value in world.env.items()
        if key not in {"CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID"}
    }
    environment["AGENT_FORK_OUTPUT"] = "json"
    config_path = world.parent_path / "unrelated-invalid.toml"
    config_path.write_text('[fork]\nworktree_location = "{bogus}/x"\n')

    completed = run_cli(
        [
            "--config",
            str(config_path),
            "fork",
            "probe",
            "--dry-run",
            "--no-agent",
            "--no-with-state",
        ],
        environment,
        world.parent_path,
    )
    assert completed.returncode == 2
    assert completed.stdout == b""
    document = json.loads(completed.stderr)
    assert document["error"]["code"] == "config_error"
    assert "unknown placeholder" in document["error"]["message"]


@pytest.mark.matrix("T-CLI-59")
def test_explicit_output_flag_beats_a_valid_agent_fork_output_on_error_too(
    repo_scenario,
):
    """T-CLI-59 — an explicit `-o text` still wins over a *valid*
    `AGENT_FORK_OUTPUT=json` on an error path, including when the error
    comes from a key unrelated to output (Gate-6 second-pass regression:
    the T-CLI-58 environment fallback must not override an explicit flag
    that says otherwise)."""
    from conftest import run_cli

    world = repo_scenario("plain@main")
    environment = {
        key: value
        for key, value in world.env.items()
        if key not in {"CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID"}
    }
    environment["AGENT_FORK_OUTPUT"] = "json"
    environment["AGENT_FORK_AGENT_MODE"] = "bogus"

    view = run_cli(["config", "view", "-o", "text"], environment, world.parent_path)
    assert view.returncode == 2
    assert not view.stderr.decode().strip().startswith("{")
    assert "fork.agent_mode" in view.stderr.decode()

    fork_environment = {**environment, "AGENT_FORK_AGENT_MODE": "auto"}
    fork_completed = run_cli(
        [
            "fork",
            "k",
            "--dry-run",
            "--no-agent",
            "--branch",
            "bad..branch",
            "-o",
            "text",
        ],
        fork_environment,
        world.parent_path,
    )
    assert fork_completed.returncode == 5
    assert not fork_completed.stderr.decode().strip().startswith("{")
    assert "invalid_branch" in fork_completed.stderr.decode()


@pytest.mark.matrix("T-CLI-60")
def test_doctor_honors_valid_output_env_on_an_unrelated_config_failure(
    repo_scenario,
):
    """T-CLI-60 — Gate-6 second-pass finding: `doctor`'s own except-branch
    fell back straight to `"text"` without consulting a valid
    `AGENT_FORK_OUTPUT`, so a JSON consumer got unparseable text from
    `doctor` precisely when the config was broken by an unrelated key —
    the case it most needs to machine-read."""
    from conftest import run_cli

    world = repo_scenario("plain@main")
    environment = _doctor_env(world)
    config_path = world.parent_path / "unrelated-invalid.toml"
    config_path.write_text('[fork]\nworktree_location = "{bogus}/x"\n')
    environment["AGENT_FORK_CONFIG"] = str(config_path)
    environment["AGENT_FORK_OUTPUT"] = "json"

    completed = run_cli(["doctor"], environment, world.parent_path)
    assert completed.returncode == 1
    document, checks = _doctor_checks(completed)
    assert document["ok"] is False
    assert checks["config validity"]["ok"] is False
    assert "fork.worktree_location" in checks["config validity"]["detail"]


HOOK_RELATIVE = ".agent-fork/worktree-setup.sh"


def _commit_hook(world, body, *, mode=0o755, commit=True):
    """Place the repository setup hook, optionally leaving it uncommitted."""
    hook = world.parent_path / HOOK_RELATIVE
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(body)
    hook.chmod(mode)
    if commit:
        for arguments in (["add", "."], ["commit", "-m", "add setup hook"]):
            subprocess.run(
                ["git", "-C", str(world.parent_path), *arguments],
                env=world.env,
                capture_output=True,
                check=True,
            )
    return hook


@pytest.mark.matrix("T-CLI-61")
def test_dry_run_discloses_the_setup_hook_without_mutating(repo_scenario):
    """T-CLI-61 — A12 outcome 1: the hook is disclosed before it can run.

    Given:  `fork --dry-run` against an eligible, an ineligible, an absent, and
            a disabled setup hook
    Expect: human and JSON disclose path, eligibility, whether it would run, and
            the timeout; the JSON says `prediction: true`; `mutation_performed`
            stays false and nothing is created
    Source: P02 A12; R8.6
    """
    from conftest import run_cli

    common = ["--dry-run", "--no-agent", "--json"]

    eligible = repo_scenario("plain@main")
    _commit_hook(eligible, "#!/bin/sh\nexit 0\n")
    completed = run_cli(["fork", "ok", *common], eligible.env, eligible.parent_path)
    assert completed.returncode == 0, completed.stderr.decode()
    document = json.loads(completed.stdout)
    hook = document["plan"]["setup_hook"]
    assert hook == {
        "path": HOOK_RELATIVE,
        "present": True,
        "policy": "tracked",
        "eligibility": "eligible",
        "would_run": True,
        "reason": None,
        "timeout_seconds": 300,
        "prediction": True,
    }
    assert document["mutation_performed"] is False
    assert not (eligible.parent_path.parent / "ok").exists()
    human = run_cli(
        ["fork", "ok", "--dry-run", "--no-agent"], eligible.env, eligible.parent_path
    )
    assert f"setup-hook: {HOOK_RELATIVE}".encode() in human.stdout
    assert b"would run" in human.stdout and b"timeout 300s" in human.stdout

    ineligible = repo_scenario("plain@main")
    _commit_hook(ineligible, "#!/bin/sh\nexit 0\n", commit=False)
    skipped = run_cli(["fork", "skip", *common], ineligible.env, ineligible.parent_path)
    hook = json.loads(skipped.stdout)["plan"]["setup_hook"]
    assert hook["eligibility"] == "untracked"
    assert hook["would_run"] is False
    assert hook["reason"] == "present but not committed at the fork anchor"
    skipped_human = run_cli(
        ["fork", "skip", "--dry-run", "--no-agent"],
        ineligible.env,
        ineligible.parent_path,
    )
    assert b"would skip" in skipped_human.stdout
    assert b"--setup-hook-policy any" in skipped_human.stdout

    absent = repo_scenario("plain@main")
    empty = run_cli(["fork", "none", *common], absent.env, absent.parent_path)
    hook = json.loads(empty.stdout)["plan"]["setup_hook"]
    assert hook["present"] is False and hook["eligibility"] == "absent"
    assert hook["would_run"] is False
    absent_human = run_cli(
        ["fork", "none", "--dry-run", "--no-agent"], absent.env, absent.parent_path
    )
    assert b"setup-hook: none" in absent_human.stdout

    disabled = repo_scenario("plain@main")
    _commit_hook(disabled, "#!/bin/sh\nexit 0\n")
    off = run_cli(
        ["fork", "off", *common, "--setup-hook-policy", "off"],
        disabled.env,
        disabled.parent_path,
    )
    hook = json.loads(off.stdout)["plan"]["setup_hook"]
    assert hook["policy"] == "off"
    assert hook["eligibility"] == "unchecked"
    assert hook["would_run"] is False
    off_human = run_cli(
        ["fork", "off", "--dry-run", "--no-agent", "--setup-hook-policy", "off"],
        disabled.env,
        disabled.parent_path,
    )
    assert b"setup-hook: disabled (--setup-hook-policy off)" in off_human.stdout


@pytest.mark.matrix("T-CLI-62")
def test_doctor_reports_and_can_fail_on_the_repository_setup_hook(repo_scenario):
    """T-CLI-62 — A12 owner decision 4: an ineligible hook is a doctor failure.

    Given:  `doctor` in a worktree whose hook is eligible, ineligible under the
            default `tracked` policy, ineligible but allowed under `any`,
            absent, or disabled
    Expect: a `repository setup hook` row in both renderings whose `ok` is false
            only in the ineligible-under-`tracked` state, and a nonzero doctor
            exit code in that state alone
    Source: P02 A12 owner decision 4; R9.10
    """
    from conftest import run_cli

    name = "repository setup hook"

    eligible = repo_scenario()
    environment = _doctor_env(eligible)
    _commit_hook(eligible, "#!/bin/sh\nexit 0\n")
    completed = run_cli(["doctor", "--json"], environment, eligible.parent_path)
    assert completed.returncode == 0, completed.stdout.decode()
    _, checks = _doctor_checks(completed)
    assert checks[name]["ok"] is True
    assert "eligible at HEAD" in checks[name]["detail"]
    assert "policy=tracked" in checks[name]["detail"]
    assert "timeout=300s" in checks[name]["detail"]
    human = run_cli(["doctor"], environment, eligible.parent_path)
    assert f"ok {name}:".encode() in human.stdout

    modified = repo_scenario()
    modified_env = _doctor_env(modified)
    _commit_hook(modified, "#!/bin/sh\nexit 0\n")
    _commit_hook(modified, "#!/bin/sh\nexit 1\n", commit=False)
    blocked = run_cli(["doctor", "--json"], modified_env, modified.parent_path)
    assert blocked.returncode != 0
    document, checks = _doctor_checks(blocked)
    assert checks[name]["ok"] is False and document["ok"] is False
    assert "modified since HEAD" in checks[name]["detail"]
    assert "--setup-hook-policy any" in checks[name]["detail"]
    blocked_human = run_cli(["doctor"], modified_env, modified.parent_path)
    assert f"FAIL {name}:".encode() in blocked_human.stdout

    config_path = modified.parent_path / ".agent-fork/agent-fork_config.toml"
    config_path.write_text('[fork]\nsetup_hook_policy = "any"\n')
    allowed = run_cli(["doctor", "--json"], modified_env, modified.parent_path)
    assert allowed.returncode == 0
    _, checks = _doctor_checks(allowed)
    assert checks[name]["ok"] is True
    assert "policy=any" in checks[name]["detail"]
    # CodeRabbit, PR #65: the hook actually runs under `any`, same as the
    # eligible case above, but the detail used to omit the timeout bound.
    assert "timeout=300s" in checks[name]["detail"]

    config_path.write_text('[fork]\nsetup_hook_policy = "off"\n')
    off = run_cli(["doctor", "--json"], modified_env, modified.parent_path)
    assert off.returncode == 0
    _, checks = _doctor_checks(off)
    assert checks[name]["ok"] is True and "disabled" in checks[name]["detail"]

    absent = repo_scenario()
    absent_env = _doctor_env(absent)
    empty = run_cli(["doctor", "--json"], absent_env, absent.parent_path)
    assert empty.returncode == 0
    _, checks = _doctor_checks(empty)
    assert checks[name]["ok"] is True and "none in " in checks[name]["detail"]


@pytest.mark.matrix("T-CLI-67")
def test_doctor_names_the_read_failure_for_an_unchecked_hook(
    repo_scenario, monkeypatch
):
    """T-CLI-67 — an `unchecked` reason must read as a read failure, not a verdict.

    `setup_hook_eligibility` can answer `unchecked` with reasons like "HEAD
    could not be read" when the provenance check itself cannot run — an
    unborn branch, an unparseable tree entry, an unreadable committed blob.
    Composing that reason straight after the path the way every other reason
    is composed ("present but ...") used to read as a provenance verdict when
    the real cause was that the check never ran at all.

    Given:  `setup_hook_eligibility` reporting `unchecked` under both `tracked`
            and `any` policy
    Expect: the detail names the failure as unread provenance, not a verdict,
            in both wordings, and `ok` still follows owner decision 4 (fails
            under `tracked`, passes under `any`)
    Source: P02 A12 gate-6 review (CodeRabbit, PR #65); R9.10
    """
    from agent_fork import doctor

    world = repo_scenario()
    monkeypatch.setattr(
        doctor,
        "setup_hook_eligibility",
        lambda *args, **kwargs: ("unchecked", "HEAD could not be read"),
    )

    tracked = doctor._setup_hook_check(world.parent_path, world.env, "tracked", 300)
    assert tracked.ok is False
    assert "provenance could not be checked: HEAD could not be read" in tracked.detail
    assert "blocked under policy=tracked" in tracked.detail

    allowed = doctor._setup_hook_check(world.parent_path, world.env, "any", 300)
    assert allowed.ok is True
    assert "provenance could not be checked: HEAD could not be read" in allowed.detail
    assert "allowed to run under policy=any" in allowed.detail
    assert "timeout=300s" in allowed.detail


@pytest.mark.requires_process_group_signals
@pytest.mark.matrix("T-CLI-63")
def test_main_translates_a_signal_during_the_hook_into_exit_130(repo_scenario):
    """T-CLI-63 — A12 Gate-1 fact 7: `OperationInterrupted` escaped `main()`.

    `OperationInterrupted` derives from `BaseException` and `main()` caught only
    `Exception`, so a signal mid-pipeline produced a traceback and exit 1 —
    contradicting REQ-22 and README's published "SIGINT and SIGTERM exit 130 and
    143 after rollback". T-RBK-03/04 assert at the library boundary and never
    exercised `main()`, which is why the gap survived.

    Given:  a real SIGINT delivered to the CLI while the setup hook blocks
    Expect: exit 130 with a rendered error and no traceback; `--json` prints
            exactly one JSON error object on stderr with code `interrupted_sigint`
    Source: REQ-22; README interrupt contract; P02 A12 Gate-1 fact 7
    """
    import signal
    import sys
    import time

    def interrupt(world, extra):
        _commit_hook(
            world,
            '#!/bin/sh\n: > "$REPO_ROOT/hook-ready"\nsleep 120\n',
        )
        executable = Path(sys.executable).with_name("agent-fork")
        process = subprocess.Popen(
            [str(executable), "fork", "interrupted", "--no-agent", *extra],
            env=world.env,
            cwd=world.parent_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        ready = world.parent_path / "hook-ready"
        for _ in range(1000):
            if ready.exists():
                break
            time.sleep(0.01)
        assert ready.exists(), "setup hook never signalled readiness"
        os.kill(process.pid, signal.SIGINT)
        stdout, stderr = process.communicate(timeout=30)
        return process.returncode, stdout, stderr

    human_world = repo_scenario("plain@main")
    code, _, stderr = interrupt(human_world, [])
    assert code == 130, stderr.decode()
    assert b"Traceback" not in stderr
    assert b"interrupted_sigint" in stderr
    assert not (human_world.parent_path.parent / "interrupted").exists()

    machine_world = repo_scenario("plain@main")
    code, _, stderr = interrupt(machine_world, ["--json"])
    assert code == 130, stderr.decode()
    assert b"Traceback" not in stderr
    lines = [line for line in stderr.decode().splitlines() if line.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0]) == {
        "error": {
            "code": "interrupted_sigint",
            "details": {"exit_code": 130, "signal": "SIGINT"},
            "message": "interrupted after rollback",
        }
    }


@pytest.mark.requires_process_group_signals
@pytest.mark.matrix("T-CLI-64")
def test_interrupt_renders_json_when_the_mode_comes_from_configuration(repo_scenario):
    """T-CLI-64 — R7.8 is owed to the resolved output mode, not to `--json` alone.

    `main()`'s interrupt boundary decided human-versus-machine rendering from the
    raw arguments, while `_fork_cli()` resolves the mode from `--json`, `-o`,
    and `AGENT_FORK_OUTPUT`. A fork put into JSON mode by the environment rather
    than by a flag therefore printed a human-readable error where the contract
    promises exactly one JSON error object on stderr. (`output` is deliberately
    not a `[fork]` configuration key — `load_config()` rejects it — so the
    environment variable is the whole of the non-flag route.)

    Given:  `AGENT_FORK_OUTPUT=json`, no `--json` flag, and a real SIGINT while
            the setup hook blocks
    Expect: exit 130 and exactly one JSON error object on stderr
    Source: R7.8; REQ-22; P02 A12 gate-6 review
    """
    import signal
    import sys
    import time

    world = repo_scenario("plain@main")
    _commit_hook(world, '#!/bin/sh\n: > "$REPO_ROOT/hook-ready"\nsleep 120\n')
    environment = dict(world.env, AGENT_FORK_OUTPUT="json")
    executable = Path(sys.executable).with_name("agent-fork")
    process = subprocess.Popen(
        [str(executable), "fork", "interrupted", "--no-agent"],
        env=environment,
        cwd=world.parent_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    ready = world.parent_path / "hook-ready"
    for _ in range(1000):
        if ready.exists():
            break
        time.sleep(0.01)
    assert ready.exists(), "setup hook never signalled readiness"
    os.kill(process.pid, signal.SIGINT)
    _, stderr = process.communicate(timeout=30)
    assert process.returncode == 130, stderr.decode()
    assert b"Traceback" not in stderr
    lines = [line for line in stderr.decode().splitlines() if line.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0]) == {
        "error": {
            "code": "interrupted_sigint",
            "details": {"exit_code": 130, "signal": "SIGINT"},
            "message": "interrupted after rollback",
        }
    }


@pytest.mark.matrix("T-CLI-65")
def test_interrupt_before_the_hook_step_renders_json_when_configured(
    repo_scenario, monkeypatch, capsys
):
    """T-CLI-65 — R7.8 is owed from the moment the output mode is knowable.

    `_fork_cli()` published the resolved mode immediately before the hook step,
    which left agent-mode resolution, repository inspection, anchor and branch
    Git calls, naming, and destination calculation — everything between
    configuration resolution and that publication — rendering interrupts from
    the raw flags. A fork put into JSON mode by `AGENT_FORK_OUTPUT` and
    interrupted anywhere in that window printed human text. The publication now
    happens as soon as configuration resolves, which is the earliest point the
    mode exists.

    Given:  `AGENT_FORK_OUTPUT=json`, no `--json` flag, and an interrupt raised
            from `inspect_repository()` — the first step after resolution
    Expect: exit 130 and exactly one JSON error object on stderr
    Source: R7.8; REQ-22; P02 A12 gate-6 round 3
    """
    from agent_fork import repository
    from agent_fork.cli import main

    world = repo_scenario("plain@main")
    monkeypatch.setattr("os.environ", dict(world.env, AGENT_FORK_OUTPUT="json"))
    monkeypatch.chdir(world.parent_path)

    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(repository, "inspect_repository", interrupted)
    assert main(["fork", "early", "--no-agent"]) == 130
    captured = capsys.readouterr()
    lines = [line for line in captured.err.splitlines() if line.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0]) == {
        "error": {
            "code": "interrupted_sigint",
            "message": "interrupted before any mutation",
        }
    }


@pytest.mark.matrix("T-CLI-66")
def test_a_signal_while_the_output_mode_resolves_is_deferred_until_it_is_published(
    repo_scenario, monkeypatch, capsys
):
    """T-CLI-66 — resolving the mode and publishing it have to be one step.

    Moving the publication next to `resolve_discovered_config()` narrowed the
    window but could not close it: resolving, computing `output_kind`, and
    assigning `args._resolved_machine` are three statements, and CPython runs
    signal handlers between bytecodes. A SIGINT landing in that gap unwinds
    with the resolved mode still unpublished, so `main()`'s boundary falls back
    to the raw flags and prints human text for a fork that `AGENT_FORK_OUTPUT`
    put in JSON mode. Blocking SIGINT and SIGTERM across the three statements
    defers such a signal until after the assignment, which is the only lever
    that closes the gap rather than narrowing it.

    Given:  `AGENT_FORK_OUTPUT=json`, no `--json` flag, and a resolved config
            whose `output` read raises a real SIGINT at this process — so the
            interrupt is pending exactly between the resolution and the
            assignment
    Expect: exit 130 and exactly one JSON error object on stderr
    Source: R7.8; REQ-22; P02 A12 gate-6 round 4
    """
    import signal

    from agent_fork import config as config_module
    from agent_fork.cli import main

    world = repo_scenario("plain@main")
    monkeypatch.setattr("os.environ", dict(world.env, AGENT_FORK_OUTPUT="json"))
    monkeypatch.chdir(world.parent_path)
    real = config_module.resolve_discovered_config

    class _SignallingConfig:
        """The resolved config, with the window opened where it really is."""

        def __init__(self, resolved):
            self._resolved = resolved

        def __getattr__(self, name):
            return getattr(self._resolved, name)

        @property
        def output(self):
            # `output_kind = ... or config.output` has run; the assignment to
            # `args._resolved_machine` has not. This is the window.
            os.kill(os.getpid(), signal.SIGINT)
            return self._resolved.output

    def signalling(*args, **kwargs):
        return _SignallingConfig(real(*args, **kwargs))

    monkeypatch.setattr(config_module, "resolve_discovered_config", signalling)
    entry_mask = signal.pthread_sigmask(signal.SIG_BLOCK, set())
    assert main(["fork", "windowed", "--no-agent"]) == 130
    assert signal.pthread_sigmask(signal.SIG_BLOCK, set()) == entry_mask
    captured = capsys.readouterr()
    lines = [line for line in captured.err.splitlines() if line.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0]) == {
        "error": {
            "code": "interrupted_sigint",
            "message": "interrupted before any mutation",
        }
    }
