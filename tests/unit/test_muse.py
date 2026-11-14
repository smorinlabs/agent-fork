"""G-MUS — Muse as a full agent (P08), unit tier.

Matrix: docs/testing/TEST-MATRIX.md §G-MUS.
"""

from __future__ import annotations

import json
import shlex
import time
import uuid
from pathlib import Path

import pytest

from muse_fake import FAKE_MUSE, FORK, PARENT


def _fake_muse(tmp_path: Path) -> Path:
    directory = tmp_path / "fake-bin"
    directory.mkdir(exist_ok=True)
    binary = directory / "muse"
    binary.write_text(FAKE_MUSE)
    binary.chmod(0o755)
    return binary


def _muse_env(world, tmp_path: Path, **extra: str) -> dict[str, str]:
    binary = _fake_muse(tmp_path)
    data = tmp_path / "xdg-data"
    return {
        **world.env,
        "PATH": f"{binary.parent}:{world.env.get('PATH', '')}",
        "XDG_DATA_HOME": str(data),
        "FAKE_MUSE_LOG": str(tmp_path / "muse-log.jsonl"),
        **extra,
    }


def _session_log(env: dict[str, str], session_id: str, first: dict | None = None):
    path = (
        Path(env["XDG_DATA_HOME"])
        / "muse/sessions/2026/11/13"
        / session_id
        / "session.jsonl"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    record = first or {"payload_type": "runtime.command.accepted", "payload": {}}
    path.write_text(json.dumps(record) + "\n")
    return path


def _received(tmp_path: Path) -> list[dict]:
    log = tmp_path / "muse-log.jsonl"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines()]


# --- detection -------------------------------------------------------------


@pytest.mark.matrix("T-MUS-01")
def test_muse_session_id_alone_is_detected(repo_scenario):
    """MUSE_SESSION_ID alone is a detected Muse session."""
    from agent_fork.agents import assess_agent_signals, detect_agent

    env = {"MUSE_SESSION_ID": PARENT, "MUSE_THREAD_ID": PARENT}
    assessment = assess_agent_signals(env)
    assert assessment.status == "detected"
    assert assessment.present == ("MUSE_SESSION_ID",)
    assert assessment.context is not None
    assert (assessment.context.agent, assessment.context.parent_session_id) == (
        "muse",
        PARENT,
    )
    assert detect_agent(env).agent == "muse"


@pytest.mark.matrix("T-MUS-02")
def test_muse_with_another_agent_is_ambiguous(repo_scenario):
    """Q4.A: Muse signals together with Claude or Codex signals are ambiguous."""
    from agent_fork.agents import assess_agent_signals, detect_agent, resolve_agent_mode
    from agent_fork.errors import AgentDetectionError

    for other in (
        {"CLAUDECODE": "1", "CLAUDE_CODE_SESSION_ID": "c"},
        {"CODEX_THREAD_ID": "x"},
        {"CLAUDECODE": "1"},
    ):
        env = {**other, "MUSE_SESSION_ID": PARENT}
        assessment = assess_agent_signals(env)
        assert assessment.status == "ambiguous", other
        assert assessment.context is None
        assert "Muse" in assessment.diagnosis()
        with pytest.raises(AgentDetectionError, match="--agent"):
            detect_agent(env)
        with pytest.raises(AgentDetectionError):
            resolve_agent_mode("auto", env)


@pytest.mark.matrix("T-MUS-03")
def test_explicit_muse_agent_and_parent_session(repo_scenario):
    from agent_fork.agents import detect_agent
    from agent_fork.errors import AgentDetectionError

    explicit = detect_agent({}, explicit_agent="muse", explicit_parent_session=FORK)
    assert (explicit.agent, explicit.parent_session_id) == ("muse", FORK)
    from_env = detect_agent(
        {"MUSE_SESSION_ID": PARENT, "CLAUDECODE": "1"}, explicit_agent="muse"
    )
    assert from_env.parent_session_id == PARENT
    with pytest.raises(AgentDetectionError, match="--parent-session"):
        detect_agent({}, explicit_agent="muse")
    with pytest.raises(AgentDetectionError, match="claude, codex, or muse"):
        detect_agent({}, explicit_agent="opencode", explicit_parent_session="x")


# --- preflight ---------------------------------------------------------------


@pytest.mark.matrix("T-MUS-04")
def test_muse_preflight_refuses_missing_cli_unreadable_version_and_non_uuid(
    repo_scenario, tmp_path
):
    from agent_fork.agents import AgentContext, preflight_agent
    from agent_fork.errors import AgentPreflightError

    world = repo_scenario()
    env = _muse_env(world, tmp_path)
    _session_log(env, PARENT)
    with pytest.raises(AgentPreflightError, match="muse CLI is missing"):
        preflight_agent(AgentContext("muse", PARENT), {**env, "PATH": "/nonexistent"})
    with pytest.raises(AgentPreflightError, match="version was unreadable"):
        preflight_agent(
            AgentContext("muse", PARENT),
            env,
            executable="/fake/muse",
            version_output="Muse Code",
        )
    with pytest.raises(AgentPreflightError, match="session UUID"):
        preflight_agent(
            AgentContext("muse", "gold-asteroid"),
            env,
            executable="/fake/muse",
            version_output="Muse Code 1.4.20",
            help_output="Commands:\n  resume\n  serve",
        )


@pytest.mark.matrix("T-MUS-05")
def test_muse_preflight_requires_the_parent_session_log(repo_scenario, tmp_path):
    from agent_fork.agents import AgentContext, preflight_agent
    from agent_fork.errors import AgentPreflightError

    world = repo_scenario()
    env = _muse_env(world, tmp_path)
    with pytest.raises(AgentPreflightError, match="not found under") as raised:
        preflight_agent(AgentContext("muse", PARENT), env)
    assert raised.value.code == "session_not_found"
    assert raised.value.exit_code == 3
    _session_log(env, PARENT)
    result = preflight_agent(AgentContext("muse", PARENT), env)
    assert result.agent == "muse"
    assert result.version == (1, 4, 20)
    # "Muse Code 1.4.20 (1.4.20-R8619.1)" names one version, not three.
    assert result.notices == ()
    assert result.context == AgentContext("muse", PARENT)


@pytest.mark.matrix("T-MUS-06")
def test_muse_preflight_help_drift_is_a_notice(repo_scenario, tmp_path):
    from agent_fork.agents import AgentContext, preflight_agent

    world = repo_scenario()
    env = _muse_env(world, tmp_path)
    _session_log(env, PARENT)
    drifted = preflight_agent(
        AgentContext("muse", PARENT),
        env,
        executable="/fake/muse",
        version_output="Muse Code 1.4.20",
        help_output="Commands:\n  resume  Resume a previous session",
    )
    assert any("serve" in notice for notice in drifted.notices)
    unread = preflight_agent(
        AgentContext("muse", PARENT),
        env,
        executable="/nonexistent/muse",
        version_output="Muse Code 1.4.20",
    )
    assert any("unverified" in notice for notice in unread.notices)


# --- MSP fork client ---------------------------------------------------------


@pytest.mark.matrix("T-MUS-07")
def test_msp_fork_returns_the_fork_id_and_leaves_it(
    repo_scenario, tmp_path, monkeypatch
):
    import agent_fork.muse_server as muse_server
    from agent_fork.muse_server import fork_session

    world = repo_scenario()
    env = _muse_env(world, tmp_path)
    binary = env["PATH"].split(":")[0] + "/muse"
    # The fake, like Muse, exits on EOF only once left with `stop: true`; with
    # a long shutdown bound, a fast return proves the leave made it exit.
    monkeypatch.setattr(muse_server, "SHUTDOWN_TIMEOUT", 20.0)
    started = time.monotonic()
    assert fork_session(binary, PARENT, env) == FORK
    assert time.monotonic() - started < 10
    received = _received(tmp_path)
    methods = [message.get("method") for message in received]
    assert methods == ["initialize", "initialized", "session/fork", "session/leave"]
    fork_params = received[2]["params"]
    assert fork_params["sessionId"] == PARENT
    assert fork_params["excludeItems"] is True
    assert uuid.UUID(fork_params["commandId"]).version == 7
    leave_params = received[3]["params"]
    assert (leave_params["sessionId"], leave_params["stop"]) == (FORK, True)
    assert uuid.UUID(leave_params["commandId"]).version == 7

    # A server->client request that reuses the client's id is not the reply.
    colliding = {**env, "FAKE_MUSE_MODE": "serverreq"}
    assert muse_server.fork_session(binary, PARENT, colliding) == FORK

    # A host that stays up after stdin EOF is terminated within the bound.
    noisy = {**env, "FAKE_MUSE_MODE": "noise"}
    assert muse_server.fork_session(binary, PARENT, noisy) == FORK

    monkeypatch.setattr(muse_server, "SHUTDOWN_TIMEOUT", 0.5)
    pidfile = tmp_path / "linger.pid"
    lingering = {**env, "FAKE_MUSE_MODE": "linger", "FAKE_MUSE_PIDFILE": str(pidfile)}
    started = time.monotonic()
    assert muse_server.fork_session(binary, PARENT, lingering) == FORK
    assert time.monotonic() - started < 10
    import os

    with pytest.raises(ProcessLookupError):
        os.kill(int(pidfile.read_text()), 0)


@pytest.mark.matrix("T-MUS-08")
def test_msp_fork_failures_are_typed(repo_scenario, tmp_path, monkeypatch):
    import agent_fork.muse_server as muse_server
    from agent_fork.errors import ERROR_CATALOG, MuseForkError

    world = repo_scenario()
    monkeypatch.setattr(muse_server, "TIMEOUT", 2.0)
    for mode, message in (
        ("error", "session not found"),
        ("malformed", "malformed JSON"),
        ("exit", "exited before responding"),
        ("hang", "timed out"),
        ("big", "output limit"),
        ("badid", "unsupported fork result"),
        ("noresult", "invalid reply"),
    ):
        env = _muse_env(world, tmp_path, FAKE_MUSE_MODE=mode)
        binary = env["PATH"].split(":")[0] + "/muse"
        with pytest.raises(MuseForkError, match=message) as raised:
            muse_server.fork_session(binary, PARENT, env)
        assert raised.value.code == "muse_fork_failed"
        assert raised.value.exit_code == ERROR_CATALOG["muse_fork_failed"].exit_code
        assert raised.value.exit_code == 3
    # A reply naming the parent itself is not a new fork.
    echo = _muse_env(world, tmp_path, FAKE_MUSE_FORK_ID=PARENT)
    with pytest.raises(MuseForkError, match="unsupported fork result"):
        muse_server.fork_session(echo["PATH"].split(":")[0] + "/muse", PARENT, echo)


# --- commands, transcript, inspection ---------------------------------------


@pytest.mark.matrix("T-MUS-09")
def test_muse_native_commands(repo_scenario, tmp_path, monkeypatch):
    import agent_fork.agents as agents
    from agent_fork.agents import (
        AgentContext,
        UnsafeCommandInputError,
        build_launch_command,
        build_session_resume_command,
    )

    executable = "/opt/agent fork/bin/agent-fork"
    monkeypatch.setattr(agents, "agent_fork_executable", lambda: (executable,))
    worktree = tmp_path / "my worktree"
    q = shlex.quote
    launch = build_launch_command(
        AgentContext("muse", PARENT),
        worktree=worktree,
        name="fork-name",
        extra_args=("--model", "a b"),
    )
    assert launch.child_session_id is None
    assert launch.command == (
        f"cd {q(str(worktree))} && muse resume "
        f'"$({q(executable)} muse-fork {q(PARENT)})" --model {q("a b")}'
    )
    resume = build_session_resume_command(
        AgentContext("muse", PARENT), directory=worktree
    )
    assert resume.command == f"cd {q(str(worktree))} && muse resume {q(PARENT)}"
    with pytest.raises(UnsafeCommandInputError):
        build_launch_command(
            AgentContext("muse", "bad\x1b[31m"), worktree=worktree, name="n"
        )
    # Started as a module, the paste command names this interpreter, never a
    # bare `agent-fork` that could resolve to another installation.
    import sys

    monkeypatch.undo()
    monkeypatch.setattr(sys, "argv", ["/src/agent_fork/cli.py"])
    module = build_launch_command(
        AgentContext("muse", PARENT), worktree=worktree, name="fork-name"
    )
    assert f"$({q(sys.executable)} -m agent_fork.cli muse-fork" in module.command


@pytest.mark.matrix("T-MUS-10")
def test_muse_transcript_path_and_lineage(repo_scenario, tmp_path):
    from agent_fork.agents import muse_forked_from, muse_session_log

    world = repo_scenario()
    env = _muse_env(world, tmp_path)
    assert muse_session_log(PARENT, env) is None
    parent_log = _session_log(env, PARENT)
    assert muse_session_log(PARENT, env) == parent_log.resolve()
    assert muse_forked_from(parent_log) is None
    fork_log = _session_log(
        env,
        FORK,
        {
            "payload_type": "session.fork.created",
            "payload": {"fork_session_id": FORK, "source_session_id": PARENT},
        },
    )
    assert muse_forked_from(fork_log) == PARENT
    home_env = {k: v for k, v in env.items() if k != "XDG_DATA_HOME"}
    home_env["HOME"] = str(tmp_path / "home")
    home_log = (
        tmp_path
        / "home/.local/share/muse/sessions/2026/11/13"
        / PARENT
        / "session.jsonl"
    )
    home_log.parent.mkdir(parents=True)
    home_log.write_text("{}\n")
    assert muse_session_log(PARENT, home_env) == home_log.resolve()


@pytest.mark.matrix("T-MUS-11")
def test_muse_session_inspection(repo_scenario, tmp_path, monkeypatch):
    import agent_fork.agents as agents
    from agent_fork.session import inspect_session

    world = repo_scenario()
    monkeypatch.setattr(agents, "agent_fork_executable", lambda: ("/bin/agent-fork",))
    env = _muse_env(
        world,
        tmp_path,
        MUSE_SESSION_ID=FORK,
        MUSE_THREAD_ID=FORK,
        FAKE_MUSE_SESSIONS=json.dumps(
            {"sessions": [{"sessionId": FORK, "name": "gold-asteroid"}]}
        ),
    )
    fork_log = _session_log(
        env,
        FORK,
        {
            "payload_type": "session.fork.created",
            "payload": {"fork_session_id": FORK, "source_session_id": PARENT},
        },
    )
    report = inspect_session(env, cwd=world.parent_path)
    assert report.agent == "muse"
    assert report.current_session is not None
    assert (report.current_session.id, report.current_session.id_source) == (
        FORK,
        "MUSE_SESSION_ID",
    )
    assert report.current_session.name == "gold-asteroid"
    assert report.parent_session is not None
    assert (report.parent_session.id, report.parent_session.id_source) == (
        PARENT,
        "muse-session-log",
    )
    assert report.lineage_status == "resolved"
    assert report.transcript.path == fork_log.resolve()
    assert report.transcript.exists is True
    assert report.fork_command.status == "available"
    assert "muse-fork" in (report.fork_command.command or "")
    assert report.resume_command.command == (
        f"cd {shlex.quote(str(world.parent_path.resolve()))} && "
        f"muse resume {shlex.quote(FORK)}"
    )
    assert report.messaging.status == "not_applicable"
    assert (report.message_route.agent, report.message_route.status) == (
        "muse",
        "address_only",
    )
    document = report.document()
    assert document["agent"] == "muse"


# --- configuration and docs --------------------------------------------------


@pytest.mark.matrix("T-MUS-12")
def test_muse_extra_args_config(repo_scenario, tmp_path):
    from agent_fork.config import load_config, resolve_config, set_user_value

    repo_scenario()
    path = tmp_path / "config.toml"
    path.write_text('[agents.muse]\nextra_args = ["--model", "x"]\n')
    values = load_config(path)
    assert values.muse_extra_args == ("--model", "x")
    resolved = resolve_config(sources=[values])
    assert resolved.muse_extra_args == ("--model", "x")
    path.write_text("[agents.muse]\nsession_name_resolution = true\n")
    from agent_fork.config import ConfigError

    with pytest.raises(ConfigError, match=r"\[agents.muse\] is invalid"):
        load_config(path)
    path.write_text('[agents.muse]\nextra_args = ["--model", "x"]\n')
    set_user_value(path, "fork.branch_prefix", "try/")
    assert load_config(path).muse_extra_args == ("--model", "x")


@pytest.mark.matrix("T-MUS-13")
def test_readme_exit_table_lists_muse_fork_failed(repo_scenario):
    from agent_fork.errors import ERROR_CATALOG

    repo_scenario()
    readme = (Path(__file__).parents[2] / "README.md").read_text()
    spec = ERROR_CATALOG["muse_fork_failed"]
    rows = [
        line for line in readme.splitlines() if line.startswith(f"| {spec.exit_code} |")
    ]
    assert len(rows) == 1
    assert "`muse_fork_failed`" in rows[0]


@pytest.mark.matrix("T-MUS-19")
def test_msp_fork_cleans_up_the_host_on_sigterm(repo_scenario, tmp_path, monkeypatch):
    import os
    import signal
    import threading

    import agent_fork.muse_server as muse_server
    from agent_fork.errors import MuseForkError

    world = repo_scenario()
    pidfile = tmp_path / "muse.pid"
    env = _muse_env(
        world, tmp_path, FAKE_MUSE_MODE="hang", FAKE_MUSE_PIDFILE=str(pidfile)
    )
    monkeypatch.setattr(muse_server, "TIMEOUT", 20.0)
    binary = env["PATH"].split(":")[0] + "/muse"
    previous = signal.getsignal(signal.SIGTERM)
    timer = threading.Timer(1.0, os.kill, (os.getpid(), signal.SIGTERM))
    timer.start()
    try:
        with pytest.raises(MuseForkError, match="SIGTERM"):
            muse_server.fork_session(binary, PARENT, env)
    finally:
        timer.cancel()
    assert signal.getsignal(signal.SIGTERM) == previous
    host = int(pidfile.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(host, 0)


@pytest.mark.matrix("T-MUS-20")
def test_muse_fork_command_maps_unexpected_errors_to_exit_3(
    repo_scenario, tmp_path, monkeypatch, capsys
):
    import agent_fork.muse_server as muse_server
    from agent_fork.cli import main

    world = repo_scenario()
    env = _muse_env(world, tmp_path)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    def explode(*args, **kwargs):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(muse_server, "fork_session", explode)
    assert main(["muse-fork", PARENT]) == 3
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "muse_fork_failed" in captured.err or "Muse fork failed" in captured.err
