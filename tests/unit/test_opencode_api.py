"""P09 — the bounded `opencode api` client's fork compensation (tier U).

Matrix: docs/testing/TEST-MATRIX.md §G-RBK.
"""

import pytest


def _client(tmp_path, fake_opencode):
    fake = fake_opencode({"ses_parent1": {"title": "Parent", "directory": "/tmp"}})
    target = tmp_path / "worktree"
    target.mkdir()
    return fake, str(fake.binary), target, fake.path_env({"PATH": "/usr/bin:/bin"})


@pytest.mark.matrix("T-RBK-21")
def test_fork_into_names_any_child_it_could_not_clean_up(
    tmp_path, fake_opencode, monkeypatch
):
    """T-RBK-21 — a child that may survive is named with its recovery command."""
    import agent_fork.opencode_api as opencode_api

    fake, binary, target, env = _client(tmp_path, fake_opencode)
    fake.update(
        fail={
            "session.move": {"code": 1, "stderr": "HTTP 400\n"},
            "session.remove": {"code": 1, "stderr": "HTTP 500\n"},
        }
    )
    with pytest.raises(opencode_api.OpencodeApiError) as caught:
        opencode_api.fork_into(binary, "ses_parent1", target, env)
    message = str(caught.value)
    assert "session.move" in message
    assert "opencode api session.remove --param sessionID=ses_child1" in message

    # A reply naming the parent is malformed: the parent is never moved or deleted.
    fake.update(fail={}, replies={"session.fork": '{"data":{"id":"ses_parent1"}}'})
    with pytest.raises(opencode_api.OpencodeApiError, match="parent's own ID"):
        opencode_api.fork_into(binary, "ses_parent1", target, env)
    assert "ses_parent1" in fake.state()["sessions"]
    assert ["api", "session.remove", "--param", "sessionID=ses_parent1"] not in (
        fake.calls()
    )

    fake.update(fail={}, replies={"session.fork": '{"data":{"id":"bogus"}}'})
    with pytest.raises(opencode_api.OpencodeApiError, match="no valid child ID"):
        opencode_api.fork_into(binary, "ses_parent1", target, env)
    assert ["api", "session.remove", "--param", "sessionID=bogus"] in fake.calls()

    monkeypatch.setattr(opencode_api, "OPENCODE_API_TIMEOUT", 1)
    fake.update(replies={}, sleep={"session.fork": 5})
    with pytest.raises(opencode_api.OpencodeApiError) as slow:
        opencode_api.fork_into(binary, "ses_parent1", target, env)
    assert "may have created a fork of ses_parent1" in str(slow.value)
    assert slow.value.uncertain is True

    # A definite refusal (the server answered with an HTTP status) gets no hint.
    fake.update(sleep={}, fail={"session.fork": {"code": 1, "stderr": "HTTP 400\n"}})
    with pytest.raises(opencode_api.OpencodeApiError) as refused:
        opencode_api.fork_into(binary, "ses_parent1", target, env)
    assert "may have created" not in str(refused.value)


@pytest.mark.matrix("T-RBK-22")
def test_fork_into_ignores_move_reply_shapes(tmp_path, fake_opencode):
    """T-RBK-22 — move and remove replies are unused, so any successful reply
    shape is accepted; only fields actually read must be present."""
    import agent_fork.opencode_api as opencode_api

    fake, binary, target, env = _client(tmp_path, fake_opencode)
    for reply in ('{"data":true}', '{"data":null}', "ok"):
        fake.update(replies={"session.move": reply})
        child = opencode_api.fork_into(binary, "ses_parent1", target, env)
        assert fake.state()["sessions"][child]["directory"] == str(target)


@pytest.mark.matrix("T-RBK-23")
def test_fork_into_records_the_child_for_the_caller(tmp_path, fake_opencode):
    """T-RBK-23 — the caller's list holds a live child from the moment its ID is
    known; a child fork_into deleted is taken off it, so nothing deletes twice."""
    import agent_fork.opencode_api as opencode_api

    fake, binary, target, env = _client(tmp_path, fake_opencode)
    created: list[str] = []
    child = opencode_api.fork_into(binary, "ses_parent1", target, env, created=created)
    assert created == [child]

    fake.update(fail={"session.move": {"code": 1, "stderr": "HTTP 400\n"}})
    moved_badly: list[str] = []
    with pytest.raises(opencode_api.OpencodeApiError):
        opencode_api.fork_into(binary, "ses_parent1", target, env, created=moved_badly)
    assert moved_badly == []

    fake.update(
        fail={
            "session.move": {"code": 1, "stderr": "HTTP 400\n"},
            "session.remove": {"code": 1, "stderr": "HTTP 500\n"},
        }
    )
    stuck: list[str] = []
    with pytest.raises(opencode_api.OpencodeApiError):
        opencode_api.fork_into(binary, "ses_parent1", target, env, created=stuck)
    assert len(stuck) == 1


@pytest.mark.matrix("T-RBK-24")
def test_fork_into_stops_the_turn_the_move_starts(tmp_path, fake_opencode, monkeypatch):
    """T-RBK-24 — OpenCode 2.3.0 starts a turn in a child once it is moved, so
    fork_into interrupts it (resume=true keeps the move); it retries once when
    nothing was running yet, and a failed interrupt keeps the fork with a notice."""
    import agent_fork.opencode_api as opencode_api

    monkeypatch.setattr(opencode_api, "OPENCODE_INTERRUPT_RETRY_DELAY", 0)
    fake, binary, target, env = _client(tmp_path, fake_opencode)
    child = opencode_api.fork_into(binary, "ses_parent1", target, env)
    ops = [call[1] for call in fake.calls() if call[:1] == ["api"]]
    assert ops == ["session.fork", "session.move", "session.interrupt"]
    interrupt = [call for call in fake.calls() if call[1:2] == ["session.interrupt"]][0]
    assert interrupt == [
        "api",
        "session.interrupt",
        "--param",
        f"sessionID={child}",
        "--param",
        "resume=true",
    ]

    fake.update(interrupts=[False, True])
    before = len(fake.api_ops())
    opencode_api.fork_into(binary, "ses_parent1", target, env)
    assert fake.api_ops()[before:].count("session.interrupt") == 2

    fake.update(
        interrupts=[True],
        fail={"session.interrupt": {"code": 1, "stderr": "HTTP 500\n"}},
    )
    notices: list[str] = []
    kept = opencode_api.fork_into(binary, "ses_parent1", target, env, notices=notices)
    assert kept in fake.state()["sessions"]
    assert any("could not stop" in notice and kept in notice for notice in notices)

    # A malformed reply, or nothing running after the retry, is reported.
    fake.update(fail={}, interrupts=[True])
    for reply_kind, setup in (
        ("unconfirmed", {"replies": {"session.interrupt": "not json"}}),
        ("none-running", {"replies": {}, "interrupts": [False]}),
    ):
        fake.update(**setup)
        found: list[str] = []
        child = opencode_api.fork_into(
            binary, "ses_parent1", target, env, notices=found
        )
        assert any(child in notice for notice in found), reply_kind

    # An interrupt arriving during the stop step still deletes the child.
    import signal

    from agent_fork.interrupts import OperationInterrupted

    fake.update(replies={}, interrupts=[True])
    real_call = opencode_api.call

    def interrupting(binary, operation, session_id, env, **kwargs):
        if operation == "session.interrupt":
            raise OperationInterrupted(signal.SIGINT)
        return real_call(binary, operation, session_id, env, **kwargs)

    monkeypatch.setattr(opencode_api, "call", interrupting)
    created: list[str] = []
    with pytest.raises(OperationInterrupted):
        opencode_api.fork_into(binary, "ses_parent1", target, env, created=created)
    assert created == []

    # If deleting the child also fails, the interruption keeps its signal and
    # carries the child's recovery command.
    fake.update(fail={"session.remove": {"code": 1, "stderr": "HTTP 500\n"}})
    stuck: list[str] = []
    with pytest.raises(OperationInterrupted) as interrupted:
        opencode_api.fork_into(binary, "ses_parent1", target, env, created=stuck)
    assert interrupted.value.signum == signal.SIGINT
    assert "opencode api session.remove --param sessionID=" in str(interrupted.value)
    monkeypatch.setattr(opencode_api, "call", real_call)
