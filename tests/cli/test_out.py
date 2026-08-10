"""G-OUT — black-box streams plus rendering-boundary conformance."""

import ast
import json
import os
import shutil
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
    script.write_text(f"#!/bin/sh\necho '{version}'\n")
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
    assert b"clipboard copy failed" in completed.stderr
    assert completed.stdout.decode().splitlines()[-1].endswith("--fork-session -n copy")


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
    assert document["fork"]["mode"] == {"with_state": True, "with_ignored": False}
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
