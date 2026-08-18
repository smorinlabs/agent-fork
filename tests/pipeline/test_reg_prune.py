"""G-REG staleness matrix and the prune verb.

Each staleness row deliberately makes one recorded value wrong and requires a
refusal, so that no destructive path can be authorized by a registry record
alone.
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


@pytest.mark.matrix("T-REG-13")
def test_cleanup_refuses_when_the_worktree_was_removed_by_hand(repo_scenario):
    from conftest import run_cli

    world = repo_scenario()
    created = _fork(world.env, world.parent_path, "gone")
    assert created.returncode == 0
    shutil.rmtree(_worktree_of(created.stdout))

    result = run_cli(["cleanup", "gone", "--yes"], world.env, world.parent_path)
    assert result.returncode == 5, result.stdout
    assert b"cleanup_registry_stale" in result.stderr
    assert len(_rows(world.env)) == 1, "a refusal must not remove the record"


@pytest.mark.matrix("T-REG-14")
def test_cleanup_refuses_when_the_branch_was_recreated_elsewhere(repo_scenario):
    """The pair must match: a live path on a different branch is not the row."""
    from conftest import run_cli

    world = repo_scenario()
    created = _fork(world.env, world.parent_path, "moved")
    assert created.returncode == 0
    worktree = _worktree_of(created.stdout)
    subprocess.run(
        ["git", "switch", "-c", "unrelated"],
        cwd=worktree,
        env=world.env,
        check=True,
        capture_output=True,
    )

    result = run_cli(["cleanup", "moved", "--yes"], world.env, world.parent_path)
    assert result.returncode == 5, result.stdout
    assert b"cleanup_registry_stale" in result.stderr


@pytest.mark.matrix("T-REG-15")
def test_prune_removes_only_records_whose_worktree_is_gone(repo_scenario):
    from conftest import run_cli

    world = repo_scenario()
    kept = _fork(world.env, world.parent_path, "kept")
    gone = _fork(world.env, world.parent_path, "gone")
    assert kept.returncode == 0 and gone.returncode == 0
    shutil.rmtree(_worktree_of(gone.stdout))
    assert len(_rows(world.env)) == 2

    preview = run_cli(["prune", "--dry-run"], world.env, world.parent_path)
    assert preview.returncode == 0
    assert b"would remove gone" in preview.stdout
    assert len(_rows(world.env)) == 2, "--dry-run must not write"

    applied = run_cli(["prune", "--yes"], world.env, world.parent_path)
    assert applied.returncode == 0, applied.stderr
    rows = _rows(world.env)
    assert [row["name"] for row in rows] == ["kept"]


@pytest.mark.matrix("T-REG-16")
def test_prune_keeps_a_record_whose_path_another_repository_occupies(repo_scenario):
    """Path reuse is reported, never pruned: the work may belong to someone."""
    from conftest import run_cli

    first = repo_scenario()
    second = repo_scenario()
    shared = {**second.env, "XDG_STATE_HOME": first.env["XDG_STATE_HOME"]}

    created = _fork(first.env, first.parent_path, "reused")
    assert created.returncode == 0
    worktree = _worktree_of(created.stdout)
    shutil.rmtree(worktree)
    # A different repository now occupies exactly that path.
    subprocess.run(
        ["git", "worktree", "add", worktree, "-b", "other"],
        cwd=second.parent_path,
        env=shared,
        check=True,
        capture_output=True,
    )

    result = run_cli(["prune", "--yes"], shared, second.parent_path)
    assert result.returncode == 0, result.stderr
    assert b"kept reused" in result.stdout
    assert b"path occupied by something else" in result.stdout
    assert len(_rows(shared)) == 1, "the record must survive"


@pytest.mark.matrix("T-REG-23")
def test_prune_reports_path_reuse_even_on_a_matching_branch_name(repo_scenario):
    """The dangerous variant: same path AND same branch, other repository."""
    from conftest import run_cli

    first = repo_scenario()
    second = repo_scenario()
    shared = {**second.env, "XDG_STATE_HOME": first.env["XDG_STATE_HOME"]}

    created = _fork(first.env, first.parent_path, "twin")
    assert created.returncode == 0
    worktree = _worktree_of(created.stdout)
    branch = next(
        line.split(": ", 1)[1]
        for line in created.stdout.decode().splitlines()
        if line.startswith("branch: ")
    )
    shutil.rmtree(worktree)
    subprocess.run(
        ["git", "worktree", "add", worktree, "-b", branch],
        cwd=second.parent_path,
        env=shared,
        check=True,
        capture_output=True,
    )

    result = run_cli(["prune", "--yes"], shared, second.parent_path)
    assert result.returncode == 0, result.stderr
    assert b"path occupied by something else" in result.stdout, result.stdout
    assert len(_rows(shared)) == 1


@pytest.mark.matrix("T-REG-18")
def test_v1_record_without_a_repository_is_still_cleanable(repo_scenario):
    """Migration keeps pre-1.1 records usable: liveness, not identity, decides."""
    from agent_fork.registry import registry_path
    from conftest import run_cli

    world = repo_scenario()
    created = _fork(world.env, world.parent_path, "legacy")
    assert created.returncode == 0

    # Rewrite the registry exactly as agent-fork 1.0 would have left it.
    path = registry_path(world.env)
    document = json.loads(path.read_text())
    for row in document["forks"]:
        row.pop("repository")
    document["version"] = 1
    path.write_text(json.dumps(document))

    rows = _rows(world.env)
    assert rows and "repository" not in rows[0]

    result = run_cli(
        ["cleanup", "legacy", "--yes", "--allow-unpushed"],
        world.env,
        world.parent_path,
    )
    assert result.returncode == 0, result.stderr
    assert _rows(world.env) == []


@pytest.mark.matrix("T-REG-19")
def test_forking_backfills_a_repository_onto_a_live_legacy_record(repo_scenario):
    """Backfill takes its evidence from live enumeration, not a stored path."""
    from agent_fork.registry import registry_path
    from conftest import run_cli

    world = repo_scenario()
    assert _fork(world.env, world.parent_path, "legacy").returncode == 0
    path = registry_path(world.env)
    document = json.loads(path.read_text())
    for row in document["forks"]:
        row.pop("repository")
    document["version"] = 1
    path.write_text(json.dumps(document))

    assert _fork(world.env, world.parent_path, "fresh").returncode == 0

    rows = {row["name"]: row for row in _rows(world.env)}
    assert rows["legacy"]["repository"] == rows["fresh"]["repository"]
    assert rows["legacy"]["repository"] is not None
    assert json.loads(path.read_text())["version"] == 2

    # Unrelated bookkeeping only: the legacy fork is untouched on disk.
    listed = run_cli(["list"], world.env, world.parent_path)
    assert b"legacy" in listed.stdout


@pytest.mark.matrix("T-REG-17")
def test_prune_reports_nothing_to_do_on_a_healthy_registry(repo_scenario):
    from conftest import run_cli

    world = repo_scenario()
    assert _fork(world.env, world.parent_path, "healthy").returncode == 0

    result = run_cli(["prune", "--yes"], world.env, world.parent_path)
    assert result.returncode == 0, result.stderr
    assert b"no registry records to remove" in result.stdout
    assert len(_rows(world.env)) == 1
