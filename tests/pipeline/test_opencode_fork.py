"""P09 — the OpenCode fork runs as the pipeline's last step (tier F).

Matrix: docs/testing/TEST-MATRIX.md §G-RBK and §G-EMT.
"""

import pytest


def _fork_world(repo_scenario, fake_opencode, name):
    from agent_fork.agents import AgentContext
    from agent_fork.pipeline import ForkRequest

    world = repo_scenario()
    fake = fake_opencode(
        {"ses_parent1": {"title": "Parent", "directory": str(world.parent_path)}}
    )
    env = fake.path_env(world.env)
    destination = world.parent_path.parent / f"{name}-child"
    request = ForkRequest(
        parent=world.parent_path,
        destination=destination,
        name=name,
        branch=f"fork/{name}",
        agent=AgentContext("opencode", "ses_parent1"),
        git_version_output="git version 2.43.0",
    )
    return world, fake, env, request


def _registered(env):
    from agent_fork.registry import read_registry

    return [entry.name for entry in read_registry(env=env)]


@pytest.mark.matrix("T-EMT-14")
def test_opencode_fork_runs_last_and_prints_the_child_resume_command(
    repo_scenario, fake_opencode
):
    """T-EMT-14 — fork and move happen after the worktree exists; the paste
    command opens the forked child in the worktree."""
    from agent_fork.pipeline import fork

    world, fake, env, request = _fork_world(repo_scenario, fake_opencode, "oc-ok")
    result = fork(request, env=env)
    worktree = request.destination.resolve()
    assert result.launch.command == f"cd {worktree} && opencode --session ses_child1"
    assert result.launch.child_session_id == "ses_child1"
    assert fake.api_ops() == ["session.get", "session.fork", "session.move"]
    sessions = fake.state()["sessions"]
    assert sessions["ses_child1"]["directory"] == str(worktree)
    assert sessions["ses_child1"]["parent"] == "ses_parent1"
    assert sessions["ses_parent1"]["directory"] == str(world.parent_path)
    assert _registered(env) == ["oc-ok"]


@pytest.mark.matrix("T-RBK-17")
def test_opencode_fork_failure_rolls_back_worktree_and_registry(
    repo_scenario, fake_opencode
):
    """T-RBK-17 — a failed `session.fork` leaves no worktree and no record."""
    from agent_fork.pipeline import fork

    _, fake, env, request = _fork_world(repo_scenario, fake_opencode, "oc-ff")
    fake.update(fail={"session.fork": {"code": 1, "stderr": "HTTP 500\n"}})
    with pytest.raises(Exception, match="session.fork"):
        fork(request, env=env)
    assert not request.destination.exists()
    assert _registered(env) == []
    assert set(fake.state()["sessions"]) == {"ses_parent1"}


@pytest.mark.matrix("T-RBK-18")
def test_opencode_move_failure_deletes_the_child_and_rolls_back(
    repo_scenario, fake_opencode
):
    """T-RBK-18 — a failed `session.move` deletes the just-forked child."""
    from agent_fork.pipeline import fork

    _, fake, env, request = _fork_world(repo_scenario, fake_opencode, "oc-mf")
    fake.update(fail={"session.move": {"code": 1, "stderr": "HTTP 400\n"}})
    with pytest.raises(Exception, match="session.move"):
        fork(request, env=env)
    assert fake.api_ops() == [
        "session.get",
        "session.fork",
        "session.move",
        "session.remove",
    ]
    assert set(fake.state()["sessions"]) == {"ses_parent1"}
    assert not request.destination.exists()
    assert _registered(env) == []


@pytest.mark.matrix("T-RBK-19")
def test_opencode_interrupt_during_move_deletes_child_and_rolls_back(
    repo_scenario, fake_opencode, monkeypatch
):
    """T-RBK-19 — an interrupt between fork and move still cleans everything."""
    import signal

    import agent_fork.opencode_api as opencode_api
    from agent_fork.interrupts import OperationInterrupted
    from agent_fork.pipeline import fork

    _, fake, env, request = _fork_world(repo_scenario, fake_opencode, "oc-int")
    real_call = opencode_api.call

    def interrupting(binary, operation, session_id, env, **kwargs):
        if operation == "session.move":
            raise OperationInterrupted(signal.SIGINT)
        return real_call(binary, operation, session_id, env, **kwargs)

    monkeypatch.setattr(opencode_api, "call", interrupting)
    with pytest.raises(OperationInterrupted):
        fork(request, env=env)
    assert fake.api_ops() == ["session.get", "session.fork", "session.remove"]
    assert set(fake.state()["sessions"]) == {"ses_parent1"}
    assert not request.destination.exists()
    assert _registered(env) == []


@pytest.mark.matrix("T-RBK-20")
def test_opencode_fork_never_runs_when_an_earlier_step_fails(
    repo_scenario, fake_opencode, monkeypatch
):
    """T-RBK-20 — a failure before the last step makes no OpenCode change."""
    import agent_fork.pipeline as pipeline

    _, fake, env, request = _fork_world(repo_scenario, fake_opencode, "oc-hook")

    def failing_hook(*_args, **_kwargs):
        raise RuntimeError("injected setup-hook failure")

    monkeypatch.setattr(pipeline, "run_setup_hook", failing_hook)
    with pytest.raises(RuntimeError, match="injected"):
        pipeline.fork(request, env=env)
    assert fake.api_ops() == ["session.get"]
    assert not request.destination.exists()
    assert _registered(env) == []
