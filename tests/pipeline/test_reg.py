"""G-REG filesystem locking, concurrency, and ownership rows."""

import json
import os
import signal
import threading
import time

import pytest


def _entry(name, worktree):
    from agent_fork.models import RegistryEntry

    return RegistryEntry.create(
        name=name, branch=f"fork/{name}", worktree=worktree, agent="codex"
    )


@pytest.mark.matrix("T-REG-03")
def test_locked_write_atomicity_serializes_concurrent_writers(repo_scenario):
    from agent_fork.registry import (
        add_entry,
        read_registry,
        registry_lock,
        registry_path,
    )

    world = repo_scenario()
    errors = []
    threads = [
        threading.Thread(
            target=lambda number=number: add_entry(
                _entry(f"n{number}", world.parent_path), env=world.env
            )
        )
        for number in range(20)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
        if thread.is_alive():
            errors.append("writer did not finish")
    assert not errors
    assert len(read_registry(env=world.env)) == 20
    json.loads(registry_path(world.env).read_text())

    ready = world.parent_path.parent / "lock-ready"
    pid = os.fork()
    if pid == 0:
        with registry_lock(registry_path(world.env)):
            ready.touch()
            while True:
                time.sleep(1)
    for _ in range(200):
        if ready.exists():
            break
        time.sleep(0.01)
    assert ready.exists()
    os.kill(pid, signal.SIGKILL)
    os.waitpid(pid, 0)
    add_entry(_entry("after-death", world.parent_path), env=world.env, timeout=0.2)
    assert len(read_registry(env=world.env)) == 21


@pytest.mark.matrix("T-REG-04")
def test_different_name_concurrent_race_both_succeed(repo_scenario):
    from agent_fork.registry import add_entry, read_registry
    from agent_fork.repository import create_worktree_at_anchor, validate_fork_guards

    world = repo_scenario()
    barrier = threading.Barrier(3)
    errors = []

    def writer(name):
        try:
            destination = world.parent_path.parent / name
            branch = f"fork/{name}"
            validate_fork_guards(world.parent_path, branch, destination, env=world.env)
            barrier.wait()
            create_worktree_at_anchor(
                world.parent_path, branch, destination, env=world.env
            )
            add_entry(_entry(name, destination), env=world.env)
        except BaseException as error:
            errors.append(error)

    threads = [threading.Thread(target=writer, args=(name,)) for name in ("one", "two")]
    for thread in threads:
        thread.start()
    started = time.monotonic()
    barrier.wait()
    for thread in threads:
        thread.join()
    assert time.monotonic() - started <= 5.0
    assert not errors
    assert {entry.name for entry in read_registry(env=world.env)} == {"one", "two"}
    assert all((world.parent_path.parent / name).is_dir() for name in ("one", "two"))


@pytest.mark.matrix("T-REG-05")
def test_lock_timeout_rolls_back_with_registry_busy(repo_scenario):
    from agent_fork.errors import RegistryBusyError
    from agent_fork.registry import add_entry, registry_lock, registry_path
    from agent_fork.repository import create_worktree_at_anchor
    from agent_fork.rollback import rollback_worktree

    world = repo_scenario()
    creation = create_worktree_at_anchor(
        world.parent_path,
        "fork/busy",
        world.parent_path.parent / "busy-child",
        env=world.env,
    )
    with registry_lock(registry_path(world.env)):
        started = time.monotonic()
        with pytest.raises(RegistryBusyError) as captured:
            add_entry(_entry("busy", creation.path), env=world.env, timeout=0.1)
        assert time.monotonic() - started < 0.5
    assert captured.value.code == "registry_busy"
    result = rollback_worktree(creation, env=world.env)
    assert result.cleaned and result.manual_recovery is None
    assert not creation.path.exists()


@pytest.mark.matrix("T-REG-06")
def test_registry_ownership_check_feeds_cleanup_refusal(repo_scenario):
    from agent_fork.registry import add_entry, find_owned

    world = repo_scenario()
    assert find_owned("unknown", env=world.env) is None
    entry = _entry("mine", world.parent_path)
    add_entry(entry, env=world.env)
    assert find_owned("mine", env=world.env) == entry
    assert find_owned("fork/mine", env=world.env) == entry
    assert find_owned(str(world.parent_path), env=world.env) == entry

    from agent_fork.registry import registry_path

    registry_path(world.env).write_text('{"version":1,"forks":[')
    with pytest.raises(ValueError, match="invalid agent-fork registry"):
        find_owned("mine", env=world.env)


@pytest.mark.matrix("T-SES-16")
def test_lineage_write_failure_compensates_registry_and_worktree(
    repo_scenario, monkeypatch
):
    from agent_fork.agents import AgentContext
    from agent_fork.pipeline import ForkRequest, fork
    from agent_fork.registry import read_registry

    world = repo_scenario()
    destination = world.parent_path.parent / "lineage-failure"
    monkeypatch.setattr(
        "agent_fork.pipeline.add_lineage",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("lineage failed")),
    )
    request = ForkRequest(
        parent=world.parent_path,
        destination=destination,
        name="lineage-failure",
        branch="fork/lineage-failure",
        agent=AgentContext("claude", "11111111-1111-1111-1111-111111111111"),
        agent_executable="/fake/claude",
        agent_version_output="Claude Code 2.1.220",
        git_version_output="git version 2.43.0",
        child_session_id="33333333-3333-3333-3333-333333333333",
    )
    with pytest.raises(OSError, match="lineage failed"):
        fork(request, env=world.env)
    assert not destination.exists()
    assert read_registry(env=world.env) == []
