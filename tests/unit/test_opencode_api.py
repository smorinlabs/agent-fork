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
