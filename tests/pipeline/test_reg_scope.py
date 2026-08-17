"""G-REG per-repository scoping: the A3 clobber and misresolution rows."""

import json

import pytest


def _shared_registry(first, second):
    """Point both worlds at one registry, modelling a single user account."""
    return {**second.env, "XDG_STATE_HOME": first.env["XDG_STATE_HOME"]}


def _rows(env):
    from agent_fork.registry import registry_path

    path = registry_path(env)
    if not path.exists():
        return []
    return json.loads(path.read_text())["forks"]


def _fork(env, cwd, *args):
    from conftest import run_cli

    return run_cli(["fork", *args, "--no-agent"], env, cwd)


@pytest.mark.matrix("T-REG-09")
def test_same_name_fork_in_two_repositories_keeps_both_rows(repo_scenario):
    """Repro 1: add_entry must not delete another repository's same-named row."""
    first = repo_scenario()
    second = repo_scenario()
    shared = _shared_registry(first, second)

    assert _fork(first.env, first.parent_path, "shared").returncode == 0
    assert _fork(shared, second.parent_path, "shared").returncode == 0

    rows = _rows(shared)
    assert len(rows) == 2, f"one repository's row was clobbered: {rows}"
    assert {row["name"] for row in rows} == {"shared"}
    assert len({row["worktree"] for row in rows}) == 2


@pytest.mark.matrix("T-REG-10")
def test_cleanup_by_name_cannot_resolve_another_repositorys_fork(repo_scenario):
    """Repro 2: a bare name must not select a fork belonging elsewhere."""
    first = repo_scenario()
    second = repo_scenario()
    shared = _shared_registry(first, second)

    assert _fork(first.env, first.parent_path, "alpha").returncode == 0
    before = _rows(shared)

    from conftest import run_cli

    result = run_cli(
        ["cleanup", "alpha", "--dry-run", "--allow-unpushed"],
        shared,
        second.parent_path,
    )
    assert result.returncode != 0, result.stdout
    assert b"cleanup_registry_stale" in result.stderr, result.stderr
    assert str(first.parent_path) not in result.stdout.decode()
    assert _rows(shared) == before


@pytest.mark.matrix("T-REG-11")
def test_auto_named_forks_in_two_repositories_keep_both_rows(repo_scenario):
    """Repro 3: the default path derives one name from the branch and date."""
    first = repo_scenario("plain@main")
    second = repo_scenario("plain@main")
    shared = _shared_registry(first, second)

    one = _fork(first.env, first.parent_path)
    two = _fork(shared, second.parent_path)
    assert one.returncode == 0 and two.returncode == 0

    # Both repositories are on `main`, so both derive the same fork name.
    assert b"fork: main-" in one.stdout and b"fork: main-" in two.stdout
    rows = _rows(shared)
    assert len(rows) == 2, f"the second auto-named fork clobbered the first: {rows}"


@pytest.mark.matrix("T-REG-12")
def test_cleanup_after_auto_name_collision_stays_in_its_repository(repo_scenario):
    """Repro 4: the destructive consequence of the clobber."""
    first = repo_scenario("plain@main")
    second = repo_scenario("plain@main")
    shared = _shared_registry(first, second)

    one = _fork(first.env, first.parent_path)
    assert one.returncode == 0
    assert _fork(shared, second.parent_path).returncode == 0

    name = next(
        line.split(": ", 1)[1]
        for line in one.stdout.decode().splitlines()
        if line.startswith("fork: ")
    )

    from conftest import run_cli

    result = run_cli(
        ["cleanup", name, "--dry-run", "--allow-unpushed"], shared, first.parent_path
    )
    assert result.returncode == 0, result.stderr
    # The plan must name this repository's own worktree, never the other's.
    assert str(first.parent_path) in result.stdout.decode()
    assert str(second.parent_path) not in result.stdout.decode()
