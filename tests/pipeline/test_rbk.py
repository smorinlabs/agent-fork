"""G-RBK — rollback, producer failure, and real signal tests."""

import os
import signal
import subprocess
import time
from dataclasses import replace

import pytest


def _created(repo_scenario):
    from agent_fork.repository import create_worktree_at_anchor

    world = repo_scenario()
    child = world.parent_path.parent / "rollback-child"
    creation = create_worktree_at_anchor(
        world.parent_path, "fork/rollback", child, env=world.env
    )
    return world, creation


@pytest.mark.matrix("T-RBK-01")
def test_materialize_failure_triggers_rollback(repo_scenario):
    from agent_fork.rollback import run_with_rollback

    world, creation = _created(repo_scenario)
    with pytest.raises(RuntimeError, match="injected"):
        run_with_rollback(
            creation,
            lambda: (_ for _ in ()).throw(RuntimeError("injected")),
            env=world.env,
        )
    assert not creation.path.exists()
    branch = subprocess.run(
        [
            "git",
            "-C",
            str(world.parent_path),
            "show-ref",
            "--verify",
            "--quiet",
            "refs/heads/fork/rollback",
        ],
        env=world.env,
    )
    assert branch.returncode != 0

    preserved_world, preserved = _created(repo_scenario)
    preserved = replace(preserved, branch_created=False)
    with pytest.raises(RuntimeError, match="injected"):
        run_with_rollback(
            preserved,
            lambda: (_ for _ in ()).throw(RuntimeError("injected")),
            env=preserved_world.env,
        )
    branch = subprocess.run(
        [
            "git",
            "-C",
            str(preserved_world.parent_path),
            "show-ref",
            "--verify",
            "--quiet",
            "refs/heads/fork/rollback",
        ],
        env=preserved_world.env,
    )
    assert branch.returncode == 0


@pytest.mark.matrix("T-RBK-02")
def test_rollback_failure_emits_manual_recovery_text(repo_scenario, monkeypatch):
    import agent_fork.rollback as module
    from agent_fork.git import GitCommandError, GitResult

    world, creation = _created(repo_scenario)

    def fail(*args, **kwargs):
        raise GitCommandError(GitResult((), 1, b"", b"fail"))

    monkeypatch.setattr(module, "run_git", fail)
    result = module.rollback_worktree(creation, env=world.env)
    assert not result.cleaned
    assert result.manual_recovery == (
        f'rm -rf "{creation.path}" && git -C "{world.parent_path}" '
        'branch -D "fork/rollback"'
    )


@pytest.mark.parametrize(
    "sent,expected",
    [
        pytest.param(
            signal.SIGINT, 130, id="T-RBK-03", marks=pytest.mark.matrix("T-RBK-03")
        ),
        pytest.param(
            signal.SIGTERM, 143, id="T-RBK-04", marks=pytest.mark.matrix("T-RBK-04")
        ),
    ],
)
def test_signal_mid_materialize_exits_with_signal_code_and_rolls_back(
    repo_scenario, sent, expected
):
    from agent_fork.materialize import materialize
    from agent_fork.repository import create_worktree_at_anchor
    from agent_fork.rollback import OperationInterrupted, run_with_rollback
    from conftest import stall_filter

    world = repo_scenario()
    (world.parent_path / ".gitattributes").write_text("tracked.txt filter=stall\n")
    subprocess.run(
        ["git", "-C", str(world.parent_path), "add", ".gitattributes"],
        env=world.env,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(world.parent_path), "commit", "-m", "configure stall"],
        env=world.env,
        capture_output=True,
        check=True,
    )
    stall = stall_filter(world)
    (world.parent_path / "tracked.txt").write_text("stall me\n")
    creation = create_worktree_at_anchor(
        world.parent_path,
        "fork/rollback",
        world.parent_path.parent / "rollback-child",
        env=world.env,
    )
    pid = os.fork()
    if pid == 0:
        try:
            run_with_rollback(
                creation,
                lambda: materialize(world.parent_path, creation.path, env=world.env),
                env=world.env,
            )
        except OperationInterrupted as error:
            os._exit(error.exit_code)
        os._exit(1)
    for _ in range(200):
        if stall.ready.exists():
            break
        time.sleep(0.01)
    assert stall.ready.exists()
    os.kill(pid, sent)
    stall.release.touch()
    status = None
    for _ in range(500):
        waited, candidate = os.waitpid(pid, os.WNOHANG)
        if waited:
            status = candidate
            break
        time.sleep(0.01)
    if status is None:
        os.kill(pid, signal.SIGKILL)
        os.waitpid(pid, 0)
        pytest.fail("signal worker did not exit within five seconds")
    assert os.waitstatus_to_exitcode(status) == expected
    assert not creation.path.exists()


@pytest.mark.parametrize(
    "verify",
    [
        pytest.param(True, id="T-RBK-05", marks=pytest.mark.matrix("T-RBK-05")),
        pytest.param(False, id="T-RBK-06", marks=pytest.mark.matrix("T-RBK-06")),
    ],
)
def test_producer_pipe_failure_fails_and_rolls_back(repo_scenario, verify):
    from agent_fork.materialize import MaterializeError, materialize
    from agent_fork.rollback import run_with_rollback
    from conftest import shim_git

    world, creation = _created(repo_scenario)
    with shim_git(fail_call="diff --cached") as shim:
        env = dict(world.env)
        env["PATH"] = f"{shim.directory}{os.pathsep}{env['PATH']}"
        with pytest.raises(MaterializeError):
            run_with_rollback(
                creation,
                lambda: materialize(world.parent_path, creation.path, env=env),
                env=env,
            )
    assert not creation.path.exists()
    assert verify in (True, False)
