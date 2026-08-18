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


@pytest.mark.matrix("T-REG-20")
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


@pytest.mark.matrix("T-REG-24")
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


@pytest.mark.matrix("T-REG-21")
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


@pytest.mark.matrix("T-REG-22")
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
