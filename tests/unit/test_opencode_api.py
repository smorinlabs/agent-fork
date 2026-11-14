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
            "session.move": {"code": 1, "stdout": "HTTP 400\n"},
            "session.remove": {"code": 1, "stdout": "HTTP 500\n"},
        }
    )
    with pytest.raises(opencode_api.OpencodeApiError) as caught:
        opencode_api.fork_into(binary, "ses_parent1", target, env)
    message = str(caught.value)
    assert "session.move" in message
    assert "opencode api session.remove --param sessionID=ses_child1" in message

    fake.update(fail={}, replies={"session.fork": '{"data":{"id":"bogus"}}'})
    with pytest.raises(opencode_api.OpencodeApiError, match="no valid child ID"):
        opencode_api.fork_into(binary, "ses_parent1", target, env)
    assert ["api", "session.remove", "--param", "sessionID=bogus"] in fake.calls()

    monkeypatch.setattr(opencode_api, "OPENCODE_API_TIMEOUT", 1)
    fake.update(replies={}, sleep={"session.fork": 5})
    with pytest.raises(opencode_api.OpencodeApiError) as slow:
        opencode_api.fork_into(binary, "ses_parent1", target, env)
    assert "may have created a fork of ses_parent1" in str(slow.value)


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
