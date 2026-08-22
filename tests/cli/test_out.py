"""G-OUT — black-box streams plus rendering-boundary conformance."""

import ast
import json
import os
import shutil
import signal
import subprocess
from pathlib import Path

import pytest

PARENT = "11111111-1111-1111-1111-111111111111"


@pytest.mark.matrix("T-OUT-19")
def test_renamed_codex_identity_is_additive_in_json():
    from agent_fork.output import ForkOutput

    output = ForkOutput(
        agent="codex",
        parent_session_id=PARENT,
        mode="agent",
        name="child",
        branch="fork/child",
        worktree=Path("/tmp/child"),
        anchor_commit="a" * 40,
        with_state=False,
        with_ignored=False,
        with_submodules=False,
        verification={"enabled": True, "passed": True},
        command=f"codex fork {PARENT} -C /tmp/child",
        notices=("resolved Codex session name 'hello'",),
        parent_session_name="hello",
    )
    document = output.document()
    assert document["parent_session_id"] == PARENT
    assert document["parent_session_name"] == "hello"


@pytest.mark.matrix("T-OUT-20")
def test_dry_run_reports_resolution_notice():
    from agent_fork.output import DryRunOutput

    rendered = DryRunOutput(
        "fork/child",
        Path("/tmp/child"),
        0,
        0,
        0,
        0,
        f"codex fork {PARENT} -C /tmp/child",
        ("resolved Codex session name 'hello' to its UUID",),
    ).render()
    assert "notices: resolved Codex session name 'hello' to its UUID" in rendered
    assert f"paste command: codex fork {PARENT}" in rendered


def _agent_env(world, agent="claude", *, isolated_path=False):
    directory = world.parent_path.parent / "agent-bin"
    directory.mkdir()
    script = directory / agent
    version = "2.1.220 (Claude Code)" if agent == "claude" else "codex-cli 0.147.0"
    # The stub must answer --help with the recipe flags it claims to support,
    # or the A4 recipe-flag probe reports the stub's own missing flags.
    help_text = (
        "--session-id <uuid> -r, --resume [value] --fork-session -n, --name <x>"
        if agent == "claude"
        else "-C, --cd <DIR>"
    )
    script.write_text(
        "#!/bin/sh\n"
        'for arg in "$@"; do\n'
        '  [ "$arg" = "--help" ] && { echo ' + f"'{help_text}'" + "; exit 0; }\n"
        "done\n"
        f"echo '{version}'\n"
    )
    script.chmod(0o755)
    if isolated_path:
        script.unlink()
        git = Path(shutil.which("git") or "/usr/bin/git").resolve()
        (directory / "git").symlink_to(git)
        path = str(directory)
    else:
        path = f"{directory}{os.pathsep}{world.env['PATH']}"
    environment = {**world.env, "PATH": path}
    if agent == "claude":
        environment.update({"CLAUDECODE": "1", "CLAUDE_CODE_SESSION_ID": PARENT})
    else:
        environment["CODEX_THREAD_ID"] = PARENT
        home = world.parent_path.parent / "codex"
        rollout = home / "sessions/2026/08/10" / f"rollout-now-{PARENT}.jsonl"
        rollout.parent.mkdir(parents=True)
        rollout.write_text("{}\n")
        environment["CODEX_HOME"] = str(home)
    return environment


def _fork(
    repo_scenario,
    name,
    *,
    agent="claude",
    output="text",
    copy=False,
    extra=(),
):
    from conftest import run_cli

    world = repo_scenario("plain@main")
    environment = _agent_env(world, agent)
    args = ["fork", name, "-o", output, *extra]
    if copy:
        args.append("--copy")
    return world, environment, run_cli(args, environment, world.parent_path)


@pytest.mark.matrix("T-OUT-01")
def test_stdout_carries_only_requested_result(repo_scenario):
    _, _, completed = _fork(repo_scenario, "streams")
    assert completed.returncode == 0
    assert completed.stderr == b""
    assert completed.stdout.startswith(b"fork: streams\n")
    assert b"progress" not in completed.stdout and b"diagnostic" not in completed.stdout


@pytest.mark.matrix("T-OUT-02")
def test_human_format_ends_with_paste_command(repo_scenario):
    _, _, completed = _fork(repo_scenario, "human")
    lines = completed.stdout.decode().splitlines()
    assert lines[-1].startswith("cd ")
    assert "claude --session-id" in lines[-1]
    assert lines[-1].endswith("--fork-session -n human")


@pytest.mark.matrix("T-OUT-03")
def test_tty_does_not_change_output_format(repo_scenario):
    from agent_fork.models import RegistryEntry
    from agent_fork.registry import add_entry
    from conftest import pty_run, run_cli

    world = repo_scenario()
    add_entry(
        RegistryEntry(
            "one", "fork/one", str(world.parent_path), "codex", "2026-01-01T00:00:00Z"
        ),
        env=world.env,
    )
    plain = run_cli(["list"], world.env, world.parent_path)
    tty = pty_run(["list"], world.env, 1)
    assert plain.returncode == tty.returncode == 0
    assert tty.tty == plain.stdout
    assert tty.stderr == plain.stderr == b""


@pytest.mark.parametrize(
    "agent",
    [
        pytest.param("codex", id="T-OUT-04", marks=pytest.mark.matrix("T-OUT-04")),
        pytest.param("claude", id="T-OUT-05", marks=pytest.mark.matrix("T-OUT-05")),
    ],
)
def test_cwd_prompt_expected_field_present_only_for_codex(repo_scenario, agent):
    _, _, completed = _fork(repo_scenario, f"json-{agent}", agent=agent, output="json")
    assert completed.returncode == 0 and completed.stderr == b""
    document = json.loads(completed.stdout)
    if agent == "codex":
        assert document["cwd_prompt_expected"] is False
        assert " -C " in document["command"]
    else:
        assert "cwd_prompt_expected" not in document


@pytest.mark.matrix("T-OUT-06")
def test_error_object_shape_on_stderr(repo_scenario):
    from conftest import run_cli

    world = repo_scenario()
    environment = _agent_env(world, isolated_path=True)
    completed = run_cli(["fork", "missing", "--json"], environment, world.parent_path)
    assert completed.returncode == 3 and completed.stdout == b""
    assert json.loads(completed.stderr) == {
        "error": {
            "code": "session_not_found",
            "message": (
                f"detected agent=claude session={PARENT}, but required claude CLI "
                "is missing from PATH; run agent-fork doctor for diagnostics"
            ),
        }
    }


@pytest.mark.matrix("T-OUT-07")
def test_stable_error_codes_round_trip_in_json(repo_scenario):
    from agent_fork.errors import AgentForkError
    from agent_fork.output import STABLE_ERROR_CODES, render_error

    repo_scenario()
    for code in STABLE_ERROR_CODES:
        error_type = type(f"Error_{code}", (AgentForkError,), {"code": code})
        rendered = json.loads(
            render_error(error_type(f"message for {code}"), machine=True)
        )
        assert rendered == {"error": {"code": code, "message": f"message for {code}"}}


@pytest.mark.matrix("T-OUT-08")
def test_dry_run_lists_planned_mutations_and_local_only(repo_scenario):
    from conftest import run_cli, staged, untracked

    world = repo_scenario(
        "plain@main", states=(staged(add="new.txt"), untracked("loose.txt"))
    )
    environment = _agent_env(world)
    explicit_worktree = world.parent_path.parent / "explicit destination"
    completed = run_cli(
        [
            "fork",
            "planned",
            "--branch",
            "review/custom",
            "--worktree-dir",
            str(explicit_worktree),
            "--dry-run",
        ],
        environment,
        world.parent_path,
    )
    assert completed.returncode == 0 and completed.stderr == b""
    output = completed.stdout.decode()
    assert "branch: create review/custom" in output
    assert f"worktree: create {explicit_worktree}" in output
    assert "staged=1" in output and "untracked=1" in output
    assert "paste command:" in output and "local-only; no mutation" in output
    assert not explicit_worktree.exists()


@pytest.mark.matrix("T-OUT-21")
def test_dry_run_honors_json_output_aliases_without_mutation(repo_scenario):
    from conftest import run_cli, staged, untracked

    world = repo_scenario(
        "plain@main", states=(staged(add="new.txt"), untracked("loose.txt"))
    )
    environment = _agent_env(world)
    destination = world.parent_path.parent / "json preview"
    base_args = [
        "fork",
        "planned-json",
        "--branch",
        "review/json-preview",
        "--worktree-dir",
        str(destination),
        "--dry-run",
    ]

    documents = []
    for output_args in (("-o", "json"), ("--json",)):
        completed = run_cli([*base_args, *output_args], environment, world.parent_path)
        assert completed.returncode == 0 and completed.stderr == b""
        documents.append(json.loads(completed.stdout))

    for document in documents:
        assert document == {
            "dry_run": True,
            "plan": {
                "branch": {"action": "create", "name": "review/json-preview"},
                "worktree": {"action": "create", "path": str(destination)},
                "files_to_carry": {
                    "staged": 1,
                    "unstaged": 0,
                    "untracked": 1,
                    "ignored": 0,
                },
                # A12 added this key to the dry-run plan; T-CLI-61 owns its
                # per-state assertions, so this row only pins its presence.
                "setup_hook": document["plan"]["setup_hook"],
            },
            "command": document["command"],
            "notices": [],
            "validation": {"scope": "local", "passed": True},
            "mutation_performed": False,
        }
        assert document["command"].startswith(
            f"cd '{destination}' && claude --session-id "
        )
        assert document["command"].endswith(
            f"--resume {PARENT} --fork-session -n planned-json"
        )

    no_state = run_cli(
        [*base_args, "--no-with-state", "--json"], environment, world.parent_path
    )
    assert no_state.returncode == 0 and no_state.stderr == b""
    assert json.loads(no_state.stdout)["plan"]["files_to_carry"] == {
        "staged": 0,
        "unstaged": 0,
        "untracked": 0,
        "ignored": 0,
    }
    assert not destination.exists()


@pytest.mark.matrix("T-OUT-09")
def test_clipboard_copy_failure_emits_notice_only(repo_scenario):
    world = repo_scenario("plain@main")
    environment = _agent_env(world)
    directory = Path(environment["PATH"].split(os.pathsep)[0])
    git = Path(shutil.which("git") or "/usr/bin/git").resolve()
    (directory / "git").symlink_to(git)
    environment["PATH"] = str(directory)
    from conftest import run_cli

    completed = run_cli(["fork", "copy", "--copy"], environment, world.parent_path)
    assert completed.returncode == 0
    assert b"clipboard copy failed" not in completed.stdout
    assert completed.stderr == (
        b"clipboard copy failed; paste command remains available on stdout\n"
    )
    assert completed.stdout.decode().splitlines()[-1].endswith("--fork-session -n copy")

    machine = run_cli(
        ["fork", "copy-json", "--copy", "--json"],
        environment,
        world.parent_path,
    )
    assert machine.returncode == 0
    document = json.loads(machine.stdout)
    assert document["notices"] == [
        "clipboard copy failed; paste command remains available on stdout"
    ]
    assert machine.stderr == (
        b"clipboard copy failed; paste command remains available on stdout\n"
    )


@pytest.mark.matrix("T-OUT-10")
def test_non_c_locale_json_output_byte_identical(repo_scenario):
    from agent_fork.models import RegistryEntry
    from agent_fork.registry import add_entry
    from conftest import run_cli

    world = repo_scenario()
    add_entry(
        RegistryEntry(
            "é", "fork/é", str(world.parent_path), "claude", "2026-01-01T00:00:00Z"
        ),
        env=world.env,
    )
    baseline = run_cli(
        ["list", "-o", "json"], {**world.env, "LC_ALL": "C"}, world.parent_path
    )
    alternate = run_cli(
        ["list", "-o", "json"], {**world.env, "LC_ALL": "C.UTF-8"}, world.parent_path
    )
    assert baseline.returncode == alternate.returncode == 0
    assert baseline.stdout == alternate.stdout


@pytest.mark.matrix("T-OUT-11")
def test_json_success_object_carries_req17_minimum_fields(repo_scenario):
    world, _, completed = _fork(repo_scenario, "schema", output="json")
    document = json.loads(completed.stdout)
    assert set(document) >= {
        "agent",
        "parent_session_id",
        "fork",
        "verification",
        "command",
        "notices",
    }
    assert document["agent"] == "claude" and document["parent_session_id"] == PARENT
    assert set(document["fork"]) >= {"branch", "worktree", "anchor_commit", "mode"}
    assert document["fork"]["branch"] == "fork/schema"
    assert Path(document["fork"]["worktree"]).is_dir()
    assert document["fork"]["mode"] == {
        "with_state": True,
        "with_ignored": False,
        "with_submodules": True,
    }
    assert document["verification"] == {"enabled": True, "passed": True}
    assert document["command"].endswith("--fork-session -n schema")
    assert document["notices"] == []

    explicit = world.parent_path.parent / "actual explicit worktree"
    _, _, overridden = _fork(
        repo_scenario,
        "overridden",
        output="json",
        extra=("--branch", "review/explicit", "--worktree-dir", str(explicit)),
    )
    overridden_document = json.loads(overridden.stdout)
    assert overridden_document["fork"]["branch"] == "review/explicit"
    assert overridden_document["fork"]["worktree"] == str(explicit)
    assert explicit.is_dir()

    from conftest import run_cli

    configured = repo_scenario("plain@main")
    config_path = configured.parent_path / ".agent-fork/agent-fork_config.toml"
    config_path.parent.mkdir()
    config_path.write_text(
        '[agents.claude]\nextra_args = ["--model", "claude future"]\n'
    )
    configured_result = run_cli(
        ["fork", "configured", "--json"],
        _agent_env(configured),
        configured.parent_path,
    )
    assert configured_result.returncode == 0
    assert "--model 'claude future'" in json.loads(configured_result.stdout)["command"]


@pytest.mark.matrix("T-OUT-12")
def test_dry_run_reports_composed_destination_without_mutation(repo_scenario):
    world = repo_scenario("plain@main")
    base = world.parent_path.parent / "fork base"
    base.mkdir()
    from conftest import run_cli

    completed = run_cli(
        [
            "fork",
            "identity",
            "--worktree-base-dir",
            str(base),
            "--worktree-name",
            "Exact Leaf",
            "--dry-run",
        ],
        _agent_env(world),
        world.parent_path,
    )
    destination = base / "Exact Leaf"
    assert completed.returncode == 0
    assert f"worktree: create {destination}".encode() in completed.stdout
    assert not destination.exists()


@pytest.mark.matrix("T-OUT-13")
def test_human_and_json_report_same_composed_path(repo_scenario):
    first = repo_scenario("plain@main")
    base = first.parent_path.parent / "forks"
    base.mkdir()
    from conftest import run_cli

    human = run_cli(
        [
            "fork",
            "human-path",
            "--worktree-base-dir",
            str(base),
            "--worktree-name",
            "Human Leaf",
        ],
        _agent_env(first),
        first.parent_path,
    )
    assert human.returncode == 0
    assert str(base / "Human Leaf").encode() in human.stdout

    second = repo_scenario("plain@main")
    base2 = second.parent_path.parent / "forks"
    base2.mkdir()
    machine = run_cli(
        [
            "fork",
            "json-path",
            "--worktree-base-dir",
            str(base2),
            "--worktree-name",
            "JSON Leaf",
            "--json",
        ],
        _agent_env(second),
        second.parent_path,
    )
    assert machine.returncode == 0
    assert json.loads(machine.stdout)["fork"]["worktree"] == str(base2 / "JSON Leaf")


@pytest.mark.matrix("T-OUT-14")
def test_production_boundary_codes_equal_authoritative_catalog(repo_scenario):
    from agent_fork.errors import ERROR_CATALOG

    repo_scenario()
    discovered = set()
    for path in (Path(__file__).parents[2] / "src/agent_fork").glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Assign)
                and any(
                    isinstance(target, ast.Name) and target.id == "code"
                    for target in node.targets
                )
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ):
                discovered.add(node.value.value)
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "PreconditionError"
                and node.args
                and isinstance(node.args[0], ast.Constant)
            ):
                discovered.add(node.args[0].value)
    assert discovered == set(ERROR_CATALOG)


@pytest.mark.matrix("T-OUT-15")
def test_error_catalog_json_and_exit_families(repo_scenario):
    from agent_fork.errors import ERROR_CATALOG, AgentForkError
    from agent_fork.output import STABLE_ERROR_CODES, render_error

    repo_scenario()
    assert STABLE_ERROR_CODES == tuple(ERROR_CATALOG)
    for code, spec in ERROR_CATALOG.items():
        error_type = type(
            f"CatalogError_{code}",
            (AgentForkError,),
            {"code": code, "exit_code": spec.exit_code},
        )
        error = error_type("catalog message")
        assert error.exit_code == spec.exit_code
        assert json.loads(render_error(error, machine=True)) == {
            "error": {"code": code, "message": "catalog message"}
        }


@pytest.mark.matrix("T-OUT-16")
def test_config_failure_json_uses_specific_code_and_exit_2(repo_scenario):
    from conftest import run_cli

    world = repo_scenario()
    invalid = world.parent_path / "invalid.toml"
    invalid.write_text("not valid toml = [")
    completed = run_cli(
        ["--config", str(invalid), "config", "view", "--json"],
        world.env,
        world.parent_path,
    )
    assert completed.returncode == 2 and completed.stdout == b""
    assert json.loads(completed.stderr)["error"]["code"] == "config_error"


@pytest.mark.matrix("T-OUT-17")
def test_git_only_json_omits_agent_identity(repo_scenario):
    from conftest import run_cli

    world = repo_scenario("plain@main")
    completed = run_cli(
        ["fork", "plain-json", "--no-agent", "--no-with-state", "--json"],
        world.env,
        world.parent_path,
    )
    document = json.loads(completed.stdout)
    assert document["mode"] == "git-only"
    assert "agent" not in document and "parent_session_id" not in document


@pytest.mark.matrix("T-OUT-18")
def test_agent_json_preserves_identity_and_mode(repo_scenario):
    _, _, completed = _fork(repo_scenario, "agent-json", output="json")
    document = json.loads(completed.stdout)
    assert document["mode"] == "agent"
    assert document["agent"] == "claude"
    assert document["parent_session_id"] == PARENT


@pytest.mark.matrix("T-OUT-22")
def test_incomplete_agent_signal_error_has_stable_catalog_and_machine_details(
    repo_scenario,
):
    """T-OUT-22 — the typed refusal is stable and machine details contain no IDs."""
    from agent_fork.agents import resolve_agent_mode
    from agent_fork.errors import ERROR_CATALOG, AgentSignalIncompleteError
    from agent_fork.output import STABLE_ERROR_CODES, render_error

    repo_scenario()
    with pytest.raises(AgentSignalIncompleteError) as caught:
        resolve_agent_mode("auto", {"CLAUDECODE": "1"})

    error = caught.value
    assert ERROR_CATALOG["agent_signal_incomplete"].exit_code == 3
    assert "agent_signal_incomplete" in STABLE_ERROR_CODES
    assert error.code == "agent_signal_incomplete"
    assert error.exit_code == 3
    assert json.loads(render_error(error, machine=True)) == {
        "error": {
            "code": "agent_signal_incomplete",
            "message": str(error),
            "details": {
                "status": "incomplete",
                "present": ["CLAUDECODE=1"],
                "missing": ["CLAUDE_CODE_SESSION_ID"],
            },
        }
    }
    rendered = render_error(error, machine=True)
    assert "claude-parent" not in rendered
    assert PARENT not in rendered


@pytest.mark.matrix("T-OUT-24")
def test_invalid_output_env_never_leaks_human_formatted_stdout(repo_scenario):
    """T-OUT-24 — an invalid `AGENT_FORK_OUTPUT` produces empty stdout across
    every command that resolves configuration, not a partial or
    human-formatted success rendering ahead of the refusal."""
    from conftest import run_cli

    world = repo_scenario("plain@main")
    environment = {
        **world.env,
        "AGENT_FORK_OUTPUT": "table",
    }
    for arguments in (
        ["fork", "probe", "--dry-run", "--no-agent", "--no-with-state"],
        ["config", "view"],
        ["session"],
        ["list"],
    ):
        completed = run_cli(arguments, environment, world.parent_path)
        assert completed.returncode == 2, arguments
        assert completed.stdout == b"", arguments


def _commit_setup_hook(world, body):
    hook = world.parent_path / ".agent-fork/worktree-setup.sh"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(body)
    hook.chmod(0o755)
    for arguments in (["add", "."], ["commit", "-m", "add setup hook"]):
        subprocess.run(
            ["git", "-C", str(world.parent_path), *arguments],
            env=world.env,
            capture_output=True,
            check=True,
        )
    return hook


@pytest.mark.matrix("T-OUT-25")
def test_setup_hook_is_structured_on_stdout_and_narrated_only_on_stderr(repo_scenario):
    """T-OUT-25 — A12 outcome 7 and 8: visible to a human, parseable by a machine.

    Given:  a fork whose setup hook runs, in `--json` mode and in `text` mode
    Expect: `--json` stdout is exactly one parseable line carrying the whole
            `setup_hook` object and no progress text; `text` mode narrates the
            hook on stderr and leaves stdout byte-identical to a hookless fork
    Source: P02 A12; R7.1, R7.6, R7.8
    """
    from conftest import run_cli

    machine_world = repo_scenario("plain@main")
    machine_env = _agent_env(machine_world)
    _commit_setup_hook(machine_world, "#!/bin/sh\nprintf 'installed 42 packages\\n'\n")
    machine = run_cli(
        ["fork", "hooked", "--json"], machine_env, machine_world.parent_path
    )
    assert machine.returncode == 0, machine.stderr.decode()
    assert machine.stdout.count(b"\n") == 1
    document = json.loads(machine.stdout)
    assert document["setup_hook"] == {
        "path": ".agent-fork/worktree-setup.sh",
        "present": True,
        "policy": "tracked",
        "eligibility": "eligible",
        "status": "ran",
        "reason": None,
        "exit_code": 0,
        "timed_out": False,
        "descendants_cleared": True,
        "duration_seconds": document["setup_hook"]["duration_seconds"],
        "timeout_seconds": 300,
        "output": {
            "stdout": "installed 42 packages\\n",
            "stderr": "",
            "stdout_bytes": 22,
            "stderr_bytes": 0,
            "truncated": False,
        },
    }
    assert isinstance(document["setup_hook"]["duration_seconds"], float)
    assert b"setup hook:" not in machine.stdout
    assert b"setup hook:" not in machine.stderr

    absent_world = repo_scenario("plain@main")
    absent = run_cli(
        ["fork", "bare", "--json"], _agent_env(absent_world), absent_world.parent_path
    )
    assert absent.returncode == 0
    assert json.loads(absent.stdout)["setup_hook"]["status"] == "absent"

    # A skipped hook under `--json`: stdout stays one parseable line carrying
    # the reason, and the skip *notice* still reaches stderr as plain text.
    # That plain text is the pre-existing duplicate-notice defect A13(a),
    # tracked as P02-T13ABF and explicitly out of A12's scope — the design keeps
    # notices flowing for backward compatibility. Asserted here so the exception
    # to "machine-mode stderr is exactly one JSON error object" is a pinned,
    # named behavior rather than an unnoticed leak.
    skipped_world = repo_scenario("plain@main")
    hook = skipped_world.parent_path / ".agent-fork/worktree-setup.sh"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text("#!/bin/sh\nprintf 'never\\n'\n")
    hook.chmod(0o755)
    skipped = run_cli(
        ["fork", "skipped", "--json"],
        _agent_env(skipped_world),
        skipped_world.parent_path,
    )
    assert skipped.returncode == 0, skipped.stderr.decode()
    assert skipped.stdout.count(b"\n") == 1
    document = json.loads(skipped.stdout)
    assert document["setup_hook"]["status"] == "skipped"
    assert document["setup_hook"]["eligibility"] == "untracked"
    assert document["setup_hook"]["reason"] == (
        "present but not committed at the fork anchor"
    )
    assert b"setup hook: " not in skipped.stderr  # progress stays suppressed
    assert b"setup hook skipped: " in skipped.stderr  # the P02-T13ABF notice

    hooked_world = repo_scenario("plain@main")
    hooked_env = _agent_env(hooked_world)
    _commit_setup_hook(hooked_world, "#!/bin/sh\nexit 0\n")
    hooked = run_cli(["fork", "narrated"], hooked_env, hooked_world.parent_path)
    assert hooked.returncode == 0, hooked.stderr.decode()
    assert b"setup hook: running .agent-fork/worktree-setup.sh (timeout 300s)" in (
        hooked.stderr
    )
    assert b"setup hook: ok in " in hooked.stderr
    assert b"setup hook" not in hooked.stdout

    # The hook adds nothing to stdout: a hookless fork of the same shape
    # produces the same line structure, with only the paths differing.
    plain_world = repo_scenario("plain@main")
    plain = run_cli(
        ["fork", "narrated"], _agent_env(plain_world), plain_world.parent_path
    )
    assert plain.returncode == 0

    hooked_lines = hooked.stdout.splitlines()
    plain_lines = plain.stdout.splitlines()
    assert len(hooked_lines) == len(plain_lines) == 5
    for lines in (hooked_lines, plain_lines):
        assert [line.split(b":")[0] for line in lines[:3]] == [
            b"fork",
            b"branch",
            b"worktree",
        ]
        assert lines[3] == b""
        assert lines[4].startswith(b"cd ")


@pytest.mark.matrix("T-OUT-27")
def test_human_output_echoes_the_hook_tails_on_failure_and_under_debug(repo_scenario):
    """T-OUT-27 — Axis C1's human echo: the tails are shown, not just stored.

    Axis C1 promises human mode echoes the bounded `stdout_tail`/`stderr_tail`
    to stderr when the hook failed, timed out, or `--debug` is set. The failure
    path only ever showed the tail by accident, folded into the failure notice
    inside `include.py`, and `--debug` did nothing at all for the hook.

    Given:  a failing hook, then a succeeding hook run with `--debug`
    Expect: both echo the already-escaped, already-bounded tails to stderr, and
            a succeeding hook without `--debug` echoes nothing
    Source: P02 A12 Axis C1; R7.1, R7.6
    """
    from conftest import run_cli

    failing = repo_scenario("plain@main")
    _commit_setup_hook(
        failing,
        "#!/bin/sh\nprintf 'step one done\\n'\nprintf 'boom\\n' >&2\nexit 17\n",
    )
    failed = run_cli(["fork", "failed"], _agent_env(failing), failing.parent_path)
    assert failed.returncode == 0, failed.stderr.decode()
    assert b"setup hook stdout: step one done\\n" in failed.stderr
    assert b"setup hook stderr: boom\\n" in failed.stderr

    debugged_world = repo_scenario("plain@main")
    _commit_setup_hook(debugged_world, "#!/bin/sh\nprintf 'installed\\n'\n")
    debugged = run_cli(
        # `--debug` is a top-level flag, so it precedes the subcommand.
        ["--debug", "fork", "debugged"],
        _agent_env(debugged_world),
        debugged_world.parent_path,
    )
    assert debugged.returncode == 0, debugged.stderr.decode()
    assert b"setup hook stdout: installed\\n" in debugged.stderr
    assert b"setup hook" not in debugged.stdout

    quiet_world = repo_scenario("plain@main")
    _commit_setup_hook(quiet_world, "#!/bin/sh\nprintf 'installed\\n'\n")
    quiet = run_cli(["fork", "quiet"], _agent_env(quiet_world), quiet_world.parent_path)
    assert quiet.returncode == 0
    assert b"setup hook: ok in " in quiet.stderr
    assert b"setup hook stdout:" not in quiet.stderr


@pytest.mark.requires_process_group_signals
@pytest.mark.matrix("T-OUT-28")
def test_human_output_echoes_the_hook_tails_on_timeout(repo_scenario):
    """T-OUT-28 — the timeout branch of the same Axis C1 echo.

    Given:  a hook that prints, then blocks past a one-second timeout
    Expect: the timeout line and the bounded tail of what it printed first,
            both on stderr, with the fork still succeeding
    Source: P02 A12 Axis C1; R7.1, R7.6
    """
    from conftest import run_cli

    world = repo_scenario("plain@main")
    _commit_setup_hook(world, "#!/bin/sh\nprintf 'started\\n'\nsleep 30\n")
    timed = run_cli(
        ["fork", "slow", "--setup-hook-timeout", "1"],
        _agent_env(world),
        world.parent_path,
    )
    assert timed.returncode == 0, timed.stderr.decode()
    assert b"setup hook: timed out after 1s" in timed.stderr
    assert b"setup hook stdout: started\\n" in timed.stderr


@pytest.mark.matrix("T-OUT-26")
def test_interrupt_error_codes_join_the_stable_catalog(repo_scenario):
    """T-OUT-26 — the two interrupt codes are published, not ad hoc.

    Given:  `interrupted_sigint` and `interrupted_sigterm`
    Expect: both are in `ERROR_CATALOG` and `STABLE_ERROR_CODES` at exit codes
            130 and 143, both have exactly one class carrying that code (which
            is what keeps T-OUT-14 green), and both round-trip through
            `render_error(machine=True)`
    Source: P02 A12; R7.12
    """
    from agent_fork.errors import (
        ERROR_CATALOG,
        INTERRUPT_ERRORS,
        InterruptedBySigintError,
        InterruptedBySigtermError,
    )
    from agent_fork.output import STABLE_ERROR_CODES, render_error

    repo_scenario()
    expected = {
        "interrupted_sigint": (130, InterruptedBySigintError),
        "interrupted_sigterm": (143, InterruptedBySigtermError),
    }
    for code, (exit_code, error_type) in expected.items():
        assert ERROR_CATALOG[code].exit_code == exit_code
        assert code in STABLE_ERROR_CODES
        assert error_type.code == code and error_type.exit_code == exit_code
        error = error_type("interrupted after rollback")
        assert json.loads(render_error(error, machine=True)) == {
            "error": {"code": code, "message": "interrupted after rollback"}
        }
    assert INTERRUPT_ERRORS == {
        signal.SIGINT: InterruptedBySigintError,
        signal.SIGTERM: InterruptedBySigtermError,
    }


@pytest.mark.matrix("T-OUT-29")
def test_strict_skip_refusal_has_exact_ordered_json_details(repo_scenario):
    """A strict refusal is one stable error with an ordered skipped schema."""
    from agent_fork.content import SkipRecord
    from agent_fork.errors import ERROR_CATALOG, StrictSkipRefusedError
    from agent_fork.output import STABLE_ERROR_CODES, render_error

    repo_scenario()
    sentinel = (0, 0, 0, 0, 0, 0)
    error = StrictSkipRefusedError(
        (
            SkipRecord("z-last", "unsupported-type", "materialize", sentinel),
            SkipRecord("a-first", "unreadable", "capture", sentinel),
        )
    )
    assert ERROR_CATALOG["strict_skip_refused"].exit_code == 1
    assert "strict_skip_refused" in STABLE_ERROR_CODES
    assert json.loads(render_error(error, machine=True)) == {
        "error": {
            "code": "strict_skip_refused",
            "message": str(error),
            "details": {
                "skipped": [
                    {"path": "a-first", "reason": "unreadable", "phase": "capture"},
                    {
                        "path": "z-last",
                        "reason": "unsupported-type",
                        "phase": "materialize",
                    },
                ],
                "count": 2,
            },
        }
    }


@pytest.mark.matrix("T-OUT-30")
def test_entry_unreadable_has_exact_escaped_ordered_json_details(repo_scenario):
    """The companion error exposes its entry and every deletion blocker."""
    from agent_fork.errors import EntryUnreadableError
    from agent_fork.output import render_error
    from agent_fork.text import escape_terminal_text

    repo_scenario()
    error = EntryUnreadableError(
        "cannot read carried entry",
        path="bad\nentry",
        reason="unreadable",
        phase="capture",
        deletion_blockers=("z-last", "a-first"),
    )
    assert json.loads(render_error(error, machine=True)) == {
        "error": {
            "code": "entry_unreadable",
            "message": "cannot read carried entry",
            "details": {
                "entry": {
                    "path": escape_terminal_text("bad\nentry"),
                    "reason": "unreadable",
                    "phase": "capture",
                },
                "deletion_blockers": ["a-first", "z-last"],
            },
        }
    }


@pytest.mark.matrix("T-OUT-31")
def test_successful_skip_notice_uses_stderr_once_and_stays_in_json(repo_scenario):
    """A13 notice routing applies unchanged to A5's successful skip."""
    from conftest import run_cli

    def run(name, *, machine):
        world = repo_scenario("plain@main")
        locked = world.parent_path / "locked.txt"
        locked.write_text("secret\n")
        os.chmod(locked, 0)
        arguments = ["fork", name, "--no-agent"]
        if machine:
            arguments.append("--json")
        try:
            completed = run_cli(arguments, world.env, world.parent_path)
        finally:
            os.chmod(locked, 0o644)
        return completed

    human = run("skip-human", machine=False)
    assert human.returncode == 0
    assert b"locked.txt" not in human.stdout
    assert human.stderr.count(b"skipped entry, not carried: locked.txt") == 1

    machine = run("skip-json", machine=True)
    assert machine.returncode == 0
    document = json.loads(machine.stdout)
    notice = "skipped entry, not carried: locked.txt"
    assert document["notices"].count(notice) == 1
    assert document["skipped"] == [
        {"path": "locked.txt", "reason": "unreadable", "phase": "capture"}
    ]
    assert machine.stderr.decode().count(notice) == 1
