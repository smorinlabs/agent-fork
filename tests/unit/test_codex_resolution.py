"""D17/REQ-46 Codex renamed-session resolution tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

UUID = "019fed92-fa7e-7262-b93e-6bd73a38ac72"


def _world(repo_scenario):
    world = repo_scenario()
    home = world.parent_path.parent / "codex-home"
    rollout = home / "sessions/2026/08/10" / f"rollout-now-{UUID}.jsonl"
    rollout.parent.mkdir(parents=True)
    rollout.write_text("{}\n")
    return world, {**world.env, "CODEX_HOME": str(home)}


@pytest.mark.matrix("T-PRE-11")
def test_uuid_fast_path_never_starts_resolver(repo_scenario, monkeypatch):
    from agent_fork.agents import AgentContext, preflight_agent

    _, env = _world(repo_scenario)
    monkeypatch.setattr(
        "agent_fork.codex_app_server.list_named_threads",
        lambda *args: pytest.fail("UUID path started app-server"),
    )
    result = preflight_agent(
        AgentContext("codex", UUID),
        env,
        executable="/fake/codex",
        version_output="codex-cli 0.147.0",
    )
    assert result.context == AgentContext("codex", UUID)


@pytest.mark.matrix("T-PRE-12")
def test_exact_name_resolves_once(repo_scenario, monkeypatch):
    from agent_fork.agents import AgentContext, preflight_agent
    from agent_fork.codex_app_server import CodexThread

    _, env = _world(repo_scenario)
    calls = []

    def resolve(*args):
        calls.append(args)
        return (CodexThread(UUID, "hello-codex"),)

    monkeypatch.setattr("agent_fork.codex_app_server.list_named_threads", resolve)
    result = preflight_agent(
        AgentContext("codex", "hello-codex"),
        env,
        executable="/fake/codex",
        version_output="codex-cli 0.147.0",
    )
    assert len(calls) == 1
    assert result.context == AgentContext("codex", UUID)
    assert result.parent_session_name == "hello-codex"


@pytest.mark.matrix("T-PRE-13")
def test_disabled_resolution_requires_uuid_without_spawn(repo_scenario, monkeypatch):
    from agent_fork.agents import AgentContext, preflight_agent
    from agent_fork.errors import SessionResolutionUnavailableError

    world = repo_scenario()
    monkeypatch.setattr(
        "agent_fork.codex_app_server.list_named_threads",
        lambda *args: pytest.fail("disabled path started app-server"),
    )
    with pytest.raises(SessionResolutionUnavailableError, match="disabled.*UUID"):
        preflight_agent(
            AgentContext("codex", "hello-codex"),
            world.env,
            executable="/fake/codex",
            version_output="codex-cli 0.147.0",
            codex_session_name_resolution=False,
        )


@pytest.mark.matrix("T-PRE-14")
def test_unknown_name_is_not_reported_as_unflushed(repo_scenario, monkeypatch):
    from agent_fork.agents import AgentContext, preflight_agent
    from agent_fork.errors import AgentPreflightError

    world = repo_scenario()
    monkeypatch.setattr(
        "agent_fork.codex_app_server.list_named_threads", lambda *args: ()
    )
    with pytest.raises(AgentPreflightError, match="was not found") as captured:
        preflight_agent(
            AgentContext("codex", "missing"),
            world.env,
            executable="/fake/codex",
            version_output="codex-cli 0.147.0",
        )
    assert "not flushed" not in str(captured.value)


@pytest.mark.matrix("T-PRE-15")
def test_duplicate_name_refuses_deterministically(repo_scenario, monkeypatch):
    from agent_fork.agents import AgentContext, preflight_agent
    from agent_fork.codex_app_server import CodexThread
    from agent_fork.errors import SessionNameAmbiguousError

    world = repo_scenario()
    other = "019fed92-fa7e-7262-b93e-6bd73a38ac73"
    monkeypatch.setattr(
        "agent_fork.codex_app_server.list_named_threads",
        lambda *args: (
            CodexThread(other, "same"),
            CodexThread(UUID, "same"),
        ),
    )
    with pytest.raises(SessionNameAmbiguousError) as captured:
        preflight_agent(
            AgentContext("codex", "same"),
            world.env,
            executable="/fake/codex",
            version_output="codex-cli 0.147.0",
        )
    assert str(captured.value).index(UUID) < str(captured.value).index(other)


def _server(tmp_path: Path, responses: list[dict[str, object]]) -> Path:
    path = tmp_path / "codex"
    lines = json.dumps(responses)
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import json,sys\n"
        f"responses={lines!r}\n"
        "responses=json.loads(responses)\n"
        "for line in sys.stdin:\n"
        " request=json.loads(line)\n"
        " if 'id' not in request: continue\n"
        " response=responses.pop(0)\n"
        " response['id']=request['id']\n"
        " print(json.dumps(response), flush=True)\n"
    )
    path.chmod(0o755)
    return path


@pytest.mark.matrix("T-PRE-16")
def test_malformed_app_server_is_typed(repo_scenario, tmp_path):
    from agent_fork.codex_app_server import list_named_threads
    from agent_fork.errors import SessionResolutionUnavailableError

    repo_scenario()
    server = tmp_path / "codex"
    server.write_text("#!/bin/sh\nprintf 'not-json\\n'\n")
    server.chmod(0o755)
    with pytest.raises(SessionResolutionUnavailableError, match="malformed JSON"):
        list_named_threads(str(server), "hello", {})


@pytest.mark.matrix("T-PRE-30")
def test_app_server_closed_stdin_is_typed_under_default_sigpipe(
    repo_scenario, tmp_path
):
    import signal

    from agent_fork.codex_app_server import list_named_threads
    from agent_fork.errors import SessionResolutionUnavailableError

    repo_scenario()
    # The server closes its stdin BEFORE answering the initialize request, so
    # by the time the client sends its next message the pipe's read end is
    # deterministically gone (the response acts as an ordering barrier).
    server = tmp_path / "codex"
    server.write_text(
        "#!/usr/bin/env python3\n"
        "import os,sys,time\n"
        "sys.stdin.readline()\n"
        "os.close(0)\n"
        'print(\'{"id":1,"result":{}}\',flush=True)\n'
        "time.sleep(5)\n"
    )
    server.chmod(0o755)
    # cli.main() sets SIGPIPE to SIG_DFL for the real CLI's stdout contract;
    # reproduce that disposition so a raw write here would be fatal, then
    # assert the adapter still surfaces the typed failure instead of dying.
    previous = signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    try:
        with pytest.raises(SessionResolutionUnavailableError, match="closed its input"):
            list_named_threads(str(server), "hello", {})
    finally:
        signal.signal(signal.SIGPIPE, previous)


@pytest.mark.matrix("T-PRE-17")
def test_resolved_stale_rollout_is_accurate(repo_scenario, monkeypatch):
    from agent_fork.agents import AgentContext, preflight_agent
    from agent_fork.codex_app_server import CodexThread
    from agent_fork.errors import AgentPreflightError

    world = repo_scenario()
    monkeypatch.setattr(
        "agent_fork.codex_app_server.list_named_threads",
        lambda *args: (CodexThread(UUID, "hello"),),
    )
    with pytest.raises(AgentPreflightError, match=UUID):
        preflight_agent(
            AgentContext("codex", "hello"),
            world.env,
            executable="/fake/codex",
            version_output="codex-cli 0.147.0",
        )


@pytest.mark.matrix("T-PRE-18")
def test_adapter_paginates_and_exact_matches(repo_scenario, tmp_path):
    from agent_fork.codex_app_server import list_named_threads

    repo_scenario()
    server = _server(
        tmp_path,
        [
            {"result": {}},
            {
                "result": {
                    "data": [{"id": UUID, "name": "hello-extra"}],
                    "nextCursor": "next",
                }
            },
            {"result": {"data": [{"id": UUID, "name": "hello"}]}},
        ],
    )
    assert list_named_threads(str(server), "hello", {})[0].name == "hello"


@pytest.mark.matrix("T-PRE-19")
def test_adapter_ignores_notifications_and_reaps(repo_scenario, tmp_path):
    from agent_fork.codex_app_server import list_named_threads

    repo_scenario()
    server = tmp_path / "codex"
    server.write_text(
        "#!/usr/bin/env python3\n"
        "import json,sys\n"
        "for line in sys.stdin:\n"
        " r=json.loads(line)\n"
        " if 'id' not in r: continue\n"
        " print(json.dumps({'method':'notice','params':{}}),flush=True)\n"
        " result={} if r['id']==1 else {'data':[]}\n"
        " print(json.dumps({'id':r['id'],'result':result}),flush=True)\n"
    )
    server.chmod(0o755)
    assert list_named_threads(str(server), "hello", {}) == ()


@pytest.mark.matrix("T-PRE-20")
def test_adapter_bounds_notification_flood(repo_scenario, tmp_path, monkeypatch):
    from agent_fork import codex_app_server
    from agent_fork.errors import SessionResolutionUnavailableError

    repo_scenario()
    server = tmp_path / "codex"
    server.write_text(
        "#!/usr/bin/env python3\n"
        "import json,sys\n"
        "for line in sys.stdin:\n"
        " r=json.loads(line)\n"
        " if 'id' not in r: continue\n"
        " print(json.dumps({'method':'notice','params':{}}),flush=True)\n"
        " result={} if r['id']==1 else {'data':[]}\n"
        " print(json.dumps({'id':r['id'],'result':result}),flush=True)\n"
    )
    server.chmod(0o755)
    monkeypatch.setattr(codex_app_server, "MAX_PENDING_MESSAGES", 1)
    with pytest.raises(
        SessionResolutionUnavailableError, match="pending-message limit"
    ):
        codex_app_server.list_named_threads(str(server), "hello", {})


@pytest.mark.matrix("T-SES-14")
def test_thread_read_returns_name_and_parent(repo_scenario, tmp_path):
    from agent_fork.codex_app_server import read_thread

    repo_scenario()
    server = _server(
        tmp_path,
        [
            {"result": {}},
            {
                "result": {
                    "thread": {
                        "id": UUID,
                        "name": "hello",
                        "forkedFromId": "parent",
                    }
                }
            },
        ],
    )
    result = read_thread(str(server), UUID, {})
    assert result is not None
    assert result.name == "hello" and result.forked_from_id == "parent"


@pytest.mark.matrix("T-EMT-07")
def test_resolved_name_emits_canonical_uuid(repo_scenario):
    from agent_fork.agents import AgentContext, build_launch_command

    repo_scenario()
    command = build_launch_command(
        AgentContext("codex", UUID), worktree=Path("/tmp/fork"), name="fork"
    ).command
    assert command == f"codex fork {UUID} -C /tmp/fork"


@pytest.mark.matrix("T-SES-42")
def test_codex_rollout_path_resolves_the_matching_rollout(repo_scenario):
    from agent_fork.agents import (
        AgentContext,
        codex_rollout_exists,
        codex_rollout_path,
    )

    _, env = _world(repo_scenario)
    context = AgentContext("codex", UUID)

    resolved = codex_rollout_path(context, env)
    assert resolved is not None
    assert resolved.name == f"rollout-now-{UUID}.jsonl"
    assert resolved.is_file()
    assert codex_rollout_exists(context, env) is True

    home = Path(env["CODEX_HOME"])
    newer = home / "sessions/2026/08/11" / f"rollout-later-{UUID}.jsonl"
    newer.parent.mkdir(parents=True)
    newer.write_text("{}\n")
    assert codex_rollout_path(context, env) == newer

    missing = AgentContext("codex", "019fed92-fa7e-7262-b93e-6bd73a38ac73")
    assert codex_rollout_path(missing, env) is None
    assert codex_rollout_exists(missing, env) is False

    # Only real files count. A directory or a broken symlink carrying a
    # rollout-shaped name must never be returned, and — because the newest
    # match wins — must never shadow the real rollout by sorting after it.
    shadow_dir = home / "sessions/2026/08/11" / f"rollout-zzz-dir-{UUID}.jsonl"
    shadow_dir.mkdir()
    shadow_link = home / "sessions/2026/08/11" / f"rollout-zzzz-link-{UUID}.jsonl"
    shadow_link.symlink_to(home / "sessions/2026/08/11/absent-target.jsonl")
    assert not shadow_link.is_file() and shadow_link.is_symlink()
    assert codex_rollout_path(context, env) == newer
    assert codex_rollout_exists(context, env) is True

    # With every real file gone, rollout-shaped non-files resolve to nothing.
    newer.unlink()
    (home / "sessions/2026/08/10" / f"rollout-now-{UUID}.jsonl").unlink()
    assert codex_rollout_path(context, env) is None
    assert codex_rollout_exists(context, env) is False
