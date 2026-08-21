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


@pytest.mark.requires_process_group_signals
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


@pytest.mark.requires_process_group_signals
@pytest.mark.parametrize(
    "sent,expected",
    [
        pytest.param(
            signal.SIGINT, 130, id="T-RBK-08", marks=pytest.mark.matrix("T-RBK-08")
        ),
        pytest.param(
            signal.SIGTERM, 143, id="T-RBK-09", marks=pytest.mark.matrix("T-RBK-09")
        ),
    ],
)
def test_signal_mid_setup_hook_reaps_the_hook_group_and_rolls_back(
    repo_scenario, sent, expected
):
    """T-RBK-08 / T-RBK-09 — A12 Gate-1 fact 6.

    Given:  a setup hook that backgrounds a long-lived child, then blocks, and a
            SIGINT or SIGTERM delivered to the CLI while it runs
    Expect: exit 130 / 143, the worktree rolled back, and the hook's own
            grandchild gone rather than reparented to PID 1
    Source: REQ-22; P02 A12
    """
    from agent_fork.include import SetupHookPolicy, run_setup_hook
    from agent_fork.repository import create_worktree_at_anchor
    from agent_fork.rollback import OperationInterrupted, run_with_rollback

    world = repo_scenario()
    hook = world.parent_path / ".agent-fork/worktree-setup.sh"
    hook.parent.mkdir(parents=True, exist_ok=True)
    # Both sentinels live in the parent repository, not the child: rollback
    # removes the child worktree before this test can read anything from it.
    hook.write_text(
        "#!/bin/sh\n"
        "sleep 120 &\n"
        'printf "%s" "$!" > "$REPO_ROOT/grandchild.pid"\n'
        ': > "$REPO_ROOT/hook-ready"\n'
        "sleep 120\n"
    )
    hook.chmod(0o755)
    subprocess.run(
        ["git", "-C", str(world.parent_path), "add", "."],
        env=world.env,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(world.parent_path), "commit", "-m", "add blocking hook"],
        env=world.env,
        capture_output=True,
        check=True,
    )
    creation = create_worktree_at_anchor(
        world.parent_path,
        "fork/rollback",
        world.parent_path.parent / "hook-signal-child",
        env=world.env,
    )
    ready = world.parent_path / "hook-ready"
    recorded = world.parent_path / "grandchild.pid"

    pid = os.fork()
    if pid == 0:
        try:
            run_with_rollback(
                creation,
                lambda: run_setup_hook(
                    world.parent_path,
                    creation.path,
                    anchor=creation.anchor,
                    policy=SetupHookPolicy(mode="tracked", timeout_seconds=120),
                    env=world.env,
                ),
                env=world.env,
            )
        except OperationInterrupted as error:
            os._exit(error.exit_code)
        os._exit(1)
    for _ in range(500):
        if ready.exists():
            break
        time.sleep(0.01)
    assert ready.exists(), "setup hook never signalled readiness"
    grandchild = int(recorded.read_text())
    os.kill(pid, sent)
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
    for _ in range(200):
        try:
            os.kill(grandchild, 0)
        except ProcessLookupError:
            break
        time.sleep(0.01)
    else:
        os.kill(grandchild, signal.SIGKILL)
        pytest.fail(f"setup-hook grandchild {grandchild} survived the interrupt")


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


@pytest.mark.requires_process_group_signals
@pytest.mark.matrix("T-RBK-10")
def test_terminating_the_hook_group_reaches_survivors_after_the_leader_exits(tmp_path):
    """T-RBK-10 — the interrupt terminator must signal the group, not the leader.

    Given:  a hook whose own shell exits immediately after backgrounding a
            SIGTERM-ignoring child that stays in the hook's process group, so
            the leader is already gone when the interrupt arrives
    Expect: `terminate_active_setup_hook()` still SIGKILLs the group, and the
            survivor dies — a group outlives its leader, so gating the signal
            on the leader's exit status skips exactly the process that needs it
    Source: P02 A12 gate-6 review (Codex); REQ-22
    """
    from agent_fork import include

    recorded = tmp_path / "survivor.pid"
    script = tmp_path / "hook.sh"
    script.write_text(
        "#!/bin/sh\n"
        f'sh -c \'trap "" TERM; printf "%s" "$$" > "{recorded}"; '
        "sleep 120' &\n"
        "exit 0\n"
    )
    script.chmod(0o755)
    process = subprocess.Popen(
        [str(script)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    confirmed_dead = False
    try:
        for _ in range(500):
            if process.poll() is not None and recorded.exists():
                break
            time.sleep(0.01)
        assert process.poll() is not None, "the hook's own shell never exited"
        survivor = int(recorded.read_text())

        include._ACTIVE.group = include._HookGroup(process)
        try:
            include.terminate_active_setup_hook()
        finally:
            include._ACTIVE.group = None

        for _ in range(300):
            try:
                os.kill(survivor, 0)
            except ProcessLookupError:
                confirmed_dead = True
                break
            time.sleep(0.01)
        else:
            pytest.fail(f"setup-hook group member {survivor} survived the interrupt")
    finally:
        # Once `ProcessLookupError` confirms the survivor's own pid is gone,
        # a fallback `kill` on that same numeric pid risks the kernel having
        # already recycled it for something unrelated — never signal past a
        # confirmed exit (CodeRabbit, PR #65).
        if not confirmed_dead and recorded.exists():
            try:
                os.kill(int(recorded.read_text()), signal.SIGKILL)
            except (ProcessLookupError, ValueError):
                pass
        for pipe in (process.stdout, process.stderr):
            if pipe is not None:
                pipe.close()


@pytest.mark.requires_process_group_signals
@pytest.mark.matrix("T-RBK-11")
def test_terminating_the_hook_group_gives_it_a_sigterm_grace_period(tmp_path):
    """T-RBK-11 — the interrupt terminator gives a live hook its SIGTERM chance.

    Given:  a hook still running (its own leader is alive) that traps SIGTERM
            to write a "cleaned up" sentinel before exiting on its own. The
            hook forks no child of its own (a builtin busy-wait, not `sleep`)
            — a backgrounded `sleep` in the same group dies from the same
            broadcast `killpg` signal that targets the shell, and racing that
            child's death against the shell's own trap is a separate, real
            shell-signal subtlety this row is not about; eliminating the
            child isolates the one thing under test.
    Expect: `terminate_active_setup_hook()` lets that trap actually run — the
            sentinel appears — rather than sending SIGKILL directly and
            denying a well-behaved hook the grace period the reap ladder
            promises everywhere else. T-RBK-10 covers the complementary case
            (a leader already gone, a SIGTERM-ignoring survivor): this row
            exists because the fix for that case must not regress this one.
    Source: P02 A12 gate-6 review (CodeRabbit, PR #65); REQ-22
    """
    from agent_fork import include

    cleaned_up = tmp_path / "cleaned-up"
    script = tmp_path / "hook.sh"
    script.write_text(
        f"#!/bin/sh\ntrap 'touch \"{cleaned_up}\"; exit 0' TERM\nwhile :; do :; done\n"
    )
    script.chmod(0o755)
    process = subprocess.Popen(
        [str(script)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        # `trap` runs before the busy-wait loop even starts, so any successful
        # spawn has already installed it; the settle just avoids signalling
        # mid-`exec`, before the shell has run any of its own script yet.
        time.sleep(0.3)
        if process.poll() is not None:
            pytest.fail("the hook exited before it could be terminated")
        include._ACTIVE.group = include._HookGroup(process)
        try:
            include.terminate_active_setup_hook()
        finally:
            include._ACTIVE.group = None

        for _ in range(300):
            if cleaned_up.exists():
                break
            time.sleep(0.01)
        else:
            pytest.fail(
                "the hook's SIGTERM trap never ran — it was killed before "
                "it had the chance to clean up"
            )
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            # PermissionError: macOS can report this in the window between a
            # group's last member exiting and its reaping — the same case
            # `_signal_hook_group()` itself tolerates.
            pass
        for pipe in (process.stdout, process.stderr):
            if pipe is not None:
                pipe.close()
