"""G-REG anchoring: which repository the destructive commands are aimed at.

Confirming a record against live state is not enough on its own. The commands
that remove a worktree and delete a branch must be aimed at the repository the
user is standing in, never at whatever repository currently occupies the path
the record happens to store.
"""

import json
import shutil
import subprocess

import pytest


def _fork(env, cwd, *args):
    from conftest import run_cli

    return run_cli(["fork", *args, "--no-agent"], env, cwd)


def _rows(env):
    from agent_fork.registry import registry_path

    path = registry_path(env)
    return json.loads(path.read_text())["forks"] if path.exists() else []


def _worktree_of(stdout):
    return next(
        line.split(": ", 1)[1]
        for line in stdout.decode().splitlines()
        if line.startswith("worktree: ")
    )


def _branch_of(stdout):
    return next(
        line.split(": ", 1)[1]
        for line in stdout.decode().splitlines()
        if line.startswith("branch: ")
    )


@pytest.mark.matrix("T-REG-25")
def test_path_reuse_on_the_same_branch_cannot_delete_the_other_repository(
    repo_scenario,
):
    """The reuse variant: same path, same branch, a different repository."""
    from conftest import run_cli

    first = repo_scenario()
    second = repo_scenario()
    shared = {**second.env, "XDG_STATE_HOME": first.env["XDG_STATE_HOME"]}

    created = _fork(first.env, first.parent_path, "collide")
    assert created.returncode == 0
    worktree = _worktree_of(created.stdout)
    branch = _branch_of(created.stdout)

    # The fork's directory goes away, but repository A keeps its metadata.
    shutil.rmtree(worktree)
    # Repository B now puts its own worktree at that exact path, on a branch
    # of the same name — the default-name collision A3 exists to handle.
    subprocess.run(
        ["git", "worktree", "add", worktree, "-b", branch],
        cwd=second.parent_path,
        env=shared,
        check=True,
        capture_output=True,
    )

    result = run_cli(
        ["cleanup", "collide", "--yes", "--allow-unpushed"],
        first.env,
        first.parent_path,
    )
    assert result.returncode != 0, result.stdout
    # Repository B's worktree and branch must both survive untouched.
    assert (
        subprocess.run(
            ["git", "-C", str(second.parent_path), "rev-parse", "--verify", branch],
            env=shared,
            capture_output=True,
        ).returncode
        == 0
    ), "the other repository's branch was deleted"
    from pathlib import Path

    assert Path(worktree).exists(), "the other repository's worktree was removed"


@pytest.mark.matrix("T-REG-29")
def test_a_foreign_record_cannot_authorize_deletion_in_the_occupying_repository(
    repo_scenario,
):
    """The destructive half of the cross-product T-REG-20 missed.

    Same reuse, but invoked from the repository that now holds the path. The
    record's own stored repository must veto it, even though its (worktree,
    branch) pair is genuinely live here.
    """
    from pathlib import Path

    from conftest import run_cli

    first = repo_scenario()
    second = repo_scenario()
    shared = {**second.env, "XDG_STATE_HOME": first.env["XDG_STATE_HOME"]}

    created = _fork(first.env, first.parent_path, "collide")
    assert created.returncode == 0
    worktree = _worktree_of(created.stdout)
    branch = _branch_of(created.stdout)
    shutil.rmtree(worktree)
    subprocess.run(
        ["git", "worktree", "add", worktree, "-b", branch],
        cwd=second.parent_path,
        env=shared,
        check=True,
        capture_output=True,
    )

    # Invoked from the OCCUPYING repository, whose live worktree genuinely
    # matches the stale record's pair.
    result = run_cli(
        ["cleanup", "collide", "--yes", "--allow-unpushed"],
        shared,
        second.parent_path,
    )
    assert result.returncode != 0, result.stdout
    assert Path(worktree).exists(), "the occupying repository's worktree was removed"
    assert (
        subprocess.run(
            ["git", "-C", str(second.parent_path), "rev-parse", "--verify", branch],
            env=shared,
            capture_output=True,
        ).returncode
        == 0
    ), "the occupying repository's branch was deleted"


@pytest.mark.matrix("T-REG-30")
def test_force_targeting_confirms_the_path_before_deleting_it(repo_scenario):
    """--force extends targeting; it does not skip confirmation.

    A repository keeps listing a worktree path whose directory was replaced,
    so the raw listing is not evidence. Targeting such a path from the
    repository that still lists it must refuse, not delete the newcomer.
    """
    from pathlib import Path

    from conftest import run_cli

    first = repo_scenario()
    second = repo_scenario()
    shared = {**second.env, "XDG_STATE_HOME": first.env["XDG_STATE_HOME"]}

    # The worktree must be UNREGISTERED, or cleanup refuses on the record
    # before the force fallback is ever reached and the test proves nothing.
    worktree = str(first.parent_path.parent / "handover")
    subprocess.run(
        ["git", "worktree", "add", worktree, "-b", "handover"],
        cwd=first.parent_path,
        env=first.env,
        check=True,
        capture_output=True,
    )
    assert not _rows(first.env), "the target must not be in the registry"
    shutil.rmtree(worktree)
    subprocess.run(
        ["git", "worktree", "add", worktree, "-b", "newcomer"],
        cwd=second.parent_path,
        env=shared,
        check=True,
        capture_output=True,
    )

    # From the repository that still lists the path in its own metadata.
    result = run_cli(
        ["cleanup", worktree, "--force", "--yes", "--allow-unpushed"],
        first.env,
        first.parent_path,
    )
    # The refusal must be the *targeting* one. Asserting only a non-zero exit
    # would also pass if Git happened to reject the removal for its own
    # reasons — which it does — so this test would survive the fix being
    # reverted and prove nothing. Verified by mutation: reverting confirmed
    # discovery to the raw listing leaves the two assertions below true, and
    # only this one fails.
    assert result.returncode == 3, result.stdout
    assert b"cleanup_target_unknown" in result.stderr, result.stderr
    assert Path(worktree).exists(), "--force deleted the occupying worktree"
    assert (
        subprocess.run(
            ["git", "-C", str(second.parent_path), "rev-parse", "--verify", "newcomer"],
            env=shared,
            capture_output=True,
        ).returncode
        == 0
    ), "the occupying repository's branch was deleted"


@pytest.mark.matrix("T-REG-31")
def test_forking_a_live_name_refuses_instead_of_orphaning_it(repo_scenario):
    """Replacing a live record would leave its worktree with nothing naming it.

    The guards do not catch this: an explicit branch and destination differ
    from the first fork's, so the collision only surfaces at the registry.
    """
    from pathlib import Path

    from conftest import run_cli

    world = repo_scenario()
    first = _fork(world.env, world.parent_path, "twice")
    assert first.returncode == 0
    original = _worktree_of(first.stdout)

    second = run_cli(
        [
            "fork",
            "twice",
            "--no-agent",
            "--branch",
            "fork/twice-again",
            "--worktree-name",
            "twice-again",
        ],
        world.env,
        world.parent_path,
    )
    assert second.returncode == 5, second.stdout
    assert b"conflict_fork_registered" in second.stderr, second.stderr

    rows = _rows(world.env)
    assert len(rows) == 1 and rows[0]["worktree"] == original, (
        f"the first fork's record must survive: {rows}"
    )
    assert Path(original).exists()


@pytest.mark.matrix("T-REG-33")
def test_forking_replaces_a_record_whose_worktree_is_gone(repo_scenario):
    """A record describing nothing is replaced freely: it orphans nothing.

    The replacement uses a *different* branch and destination from the dead
    record, so this exercises general dead-record replacement rather than the
    same-slot path a same-path re-fork would take.
    """
    from conftest import run_cli

    world = repo_scenario()
    created = _fork(world.env, world.parent_path, "again")
    assert created.returncode == 0
    worktree = _worktree_of(created.stdout)

    # Remove the fork the way a user would outside agent-fork, branch and all.
    shutil.rmtree(worktree)
    subprocess.run(
        ["git", "worktree", "prune"],
        cwd=world.parent_path,
        env=world.env,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "branch", "-D", _branch_of(created.stdout)],
        cwd=world.parent_path,
        env=world.env,
        check=True,
        capture_output=True,
    )

    again = run_cli(
        [
            "fork",
            "again",
            "--no-agent",
            "--branch",
            "fork/again-elsewhere",
            "--worktree-name",
            "again-elsewhere",
        ],
        world.env,
        world.parent_path,
    )
    assert again.returncode == 0, again.stderr
    rows = _rows(world.env)
    assert len(rows) == 1, f"the dead record should have been replaced: {rows}"
    assert rows[0]["branch"] == "fork/again-elsewhere"


@pytest.mark.matrix("T-REG-35")
def test_the_conflict_refusal_runs_before_the_setup_hook(repo_scenario):
    """A refusal must arrive before anything with side effects has happened.

    The setup hook is arbitrary user code; rollback removes the worktree and
    branch it created but cannot reverse what the hook did outside them. So a
    conflict has to be detected at preflight, not after the hook has run.
    """

    from conftest import run_cli

    world = repo_scenario()
    assert _fork(world.env, world.parent_path, "hooked").returncode == 0

    # The hook lives in the parent as untracked state, is carried into the
    # child by the fork, and runs there — so it only executes if the fork gets
    # far enough to copy and run it.
    marker = world.parent_path.parent / "hook-ran"
    hook = world.parent_path / ".agent-fork" / "worktree-setup.sh"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(f'#!/bin/sh\necho ran > "{marker}"\n')
    hook.chmod(0o755)

    second = run_cli(
        [
            "fork",
            "hooked",
            "--no-agent",
            "--branch",
            "fork/hooked-again",
            "--worktree-name",
            "hooked-again",
        ],
        world.env,
        world.parent_path,
    )
    assert second.returncode == 5, second.stdout
    assert b"conflict_fork_registered" in second.stderr, second.stderr
    assert not marker.exists(), "the setup hook ran before the conflict was refused"
    assert not (world.parent_path.parent / "hooked-again").exists(), (
        "a worktree was created before the conflict was refused"
    )


@pytest.mark.matrix("T-REG-26")
def test_force_does_not_override_the_stale_refusal(repo_scenario):
    """--force overrides the dirty and unpushed guards, never ownership."""
    from conftest import run_cli

    first = repo_scenario()
    second = repo_scenario()
    shared = {**second.env, "XDG_STATE_HOME": first.env["XDG_STATE_HOME"]}

    created = _fork(first.env, first.parent_path, "elsewhere")
    assert created.returncode == 0
    worktree = _worktree_of(created.stdout)

    result = run_cli(
        ["cleanup", "elsewhere", "--force", "--yes"], shared, second.parent_path
    )
    assert result.returncode == 5, result.stdout
    assert b"cleanup_registry_stale" in result.stderr, result.stderr

    from pathlib import Path

    assert Path(worktree).exists(), "--force destroyed another repository's fork"
    assert len(_rows(shared)) == 1


@pytest.mark.matrix("T-REG-27")
def test_registered_fork_is_cleanable_by_absolute_path_from_outside_a_repository(
    repo_scenario, tmp_path
):
    """An explicit path is fresh user input, so it can anchor the repository."""
    from conftest import run_cli

    world = repo_scenario()
    created = _fork(world.env, world.parent_path, "bypath")
    assert created.returncode == 0
    worktree = _worktree_of(created.stdout)

    outside = tmp_path / "not-a-repo"
    outside.mkdir()
    result = run_cli(
        ["cleanup", worktree, "--yes", "--allow-unpushed"], world.env, outside
    )
    assert result.returncode == 0, result.stderr

    from pathlib import Path

    assert not Path(worktree).exists()
    assert _rows(world.env) == [], "the record must be removed, not orphaned"
