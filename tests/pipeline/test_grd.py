"""G-GRD — Fork guards (tier F).

Matrix: docs/testing/TEST-MATRIX.md §G-GRD.
"""

import pytest


@pytest.mark.matrix("T-GRD-01")
def test_branch_already_exists_refuses(repo_scenario):
    """T-GRD-01 — an already-existing branch name refuses the fork.

    Given:  the target fork branch name already exists in the repo
    Expect: refusal, exit 5, conflict_branch_exists, nothing created
    Source: REQ-19; RESEARCH §2.1 step 2
    """
    import subprocess

    from agent_fork.errors import PreconditionError
    from agent_fork.repository import validate_fork_guards

    world = repo_scenario("plain@main")
    subprocess.run(
        ["git", "-C", str(world.parent_path), "branch", "fork/existing"],
        env=world.env,
        check=True,
    )
    destination = world.parent_path.parent / "destination"
    with pytest.raises(PreconditionError) as caught:
        validate_fork_guards(
            world.parent_path, "fork/existing", destination, env=world.env
        )
    assert caught.value.exit_code == 5
    assert caught.value.code == "conflict_branch_exists"
    assert not destination.exists()


@pytest.mark.matrix("T-GRD-02")
def test_branch_already_has_a_worktree_refuses(repo_scenario):
    """T-GRD-02 — a branch already checked out in another worktree refuses the fork.

    Given:  the target fork branch is already attached to an existing worktree
    Expect: refusal, exit 5, nothing created
    Source: REQ-19
    """
    import subprocess

    from agent_fork.errors import PreconditionError
    from agent_fork.repository import validate_fork_guards

    world = repo_scenario("plain@main")
    attached = world.parent_path.parent / "attached"
    subprocess.run(
        [
            "git",
            "-C",
            str(world.parent_path),
            "worktree",
            "add",
            "-b",
            "fork/attached",
            str(attached),
            "HEAD",
        ],
        env=world.env,
        check=True,
        capture_output=True,
    )
    destination = world.parent_path.parent / "other"
    with pytest.raises(PreconditionError) as caught:
        validate_fork_guards(
            world.parent_path, "fork/attached", destination, env=world.env
        )
    assert caught.value.code == "conflict_branch_worktree"
    assert str(attached) in str(caught.value)
    assert not destination.exists()


@pytest.mark.matrix("T-GRD-03")
def test_worktree_path_already_exists_refuses(repo_scenario):
    """T-GRD-03 — an already-existing worktree path refuses the fork.

    Given:  the computed worktree path already exists on disk
    Expect: refusal, exit 5, nothing created
    Source: REQ-19; RESEARCH §2.1 step 3
    """
    from agent_fork.errors import PreconditionError
    from agent_fork.repository import validate_fork_guards

    world = repo_scenario("plain@main")
    destination = world.parent_path.parent / "occupied"
    destination.mkdir()
    marker = destination / "keep"
    marker.write_text("untouched\n")
    with pytest.raises(PreconditionError) as caught:
        validate_fork_guards(world.parent_path, "fork/new", destination, env=world.env)
    assert caught.value.code == "conflict_worktree_path"
    assert marker.read_text() == "untouched\n"


@pytest.mark.parametrize(
    "operation",
    [
        pytest.param("rebase", id="T-GRD-04", marks=pytest.mark.matrix("T-GRD-04")),
        pytest.param("merge", id="T-GRD-05", marks=pytest.mark.matrix("T-GRD-05")),
        pytest.param(
            "cherry-pick", id="T-GRD-06", marks=pytest.mark.matrix("T-GRD-06")
        ),
        pytest.param("revert", id="T-GRD-07", marks=pytest.mark.matrix("T-GRD-07")),
        pytest.param("bisect", id="T-GRD-08", marks=pytest.mark.matrix("T-GRD-08")),
    ],
)
def test_parent_mid_operation_refuses_with_abort_hint(repo_scenario, operation):
    """Parent mid-operation refuses the fork with an operation-specific abort hint.

    T-GRD-04 — mid-rebase refuses exit 5; hint is `cd "<parent>" && git rebase --abort`.
    T-GRD-05 — mid-merge refuses exit 5; hint is `git merge --abort`.
    T-GRD-06 — mid-cherry-pick refuses exit 5; hint is `git cherry-pick --abort`.
    T-GRD-07 — mid-revert refuses exit 5; hint is `git revert --abort`.
    T-GRD-08 — mid-bisect refuses exit 5; hint is `git bisect reset`.
    Source: REQ-19; RESEARCH §2.1 step 4
    """
    from agent_fork.errors import PreconditionError
    from agent_fork.repository import validate_fork_guards

    world = repo_scenario("plain@main")
    sentinels = {
        "rebase": "rebase-merge",
        "merge": "MERGE_HEAD",
        "cherry-pick": "CHERRY_PICK_HEAD",
        "revert": "REVERT_HEAD",
        "bisect": "BISECT_LOG",
    }
    sentinel = world.git_dir / sentinels[operation]
    if operation == "rebase":
        sentinel.mkdir()
    else:
        sentinel.write_text("active\n")
    destination = world.parent_path.parent / f"during-{operation}"
    with pytest.raises(PreconditionError) as caught:
        validate_fork_guards(
            world.parent_path, f"fork/{operation}", destination, env=world.env
        )
    expected = (
        f'cd "{world.parent_path}" && git bisect reset'
        if operation == "bisect"
        else f'cd "{world.parent_path}" && git {operation} --abort'
    )
    assert caught.value.code == "parent_mid_operation"
    assert expected in str(caught.value)
    assert not destination.exists()


@pytest.mark.matrix("T-GRD-09")
def test_not_a_repo_refuses(repo_scenario):
    """T-GRD-09 — invoking outside any git repo refuses the fork.

    Given:  the invoking cwd is not inside a git repository
    Expect: refusal, exit 5, nothing created
    Source: REQ-19
    """
    from agent_fork.errors import PreconditionError
    from agent_fork.repository import validate_fork_guards

    world = repo_scenario("plain@main")
    outside = world.parent_path.parent / "not-a-repo"
    outside.mkdir()
    destination = outside.parent / "never-created"
    with pytest.raises(PreconditionError) as caught:
        validate_fork_guards(outside, "fork/nope", destination, env=world.env)
    assert caught.value.code == "not_git_repository"
    assert not destination.exists()


@pytest.mark.parametrize(
    "topology",
    [
        pytest.param(
            "unborn(plain)", id="T-GRD-10", marks=pytest.mark.matrix("T-GRD-10")
        ),
        pytest.param(
            "unborn(bare)", id="T-GRD-11", marks=pytest.mark.matrix("T-GRD-11")
        ),
    ],
)
def test_unborn_head_refuses_with_remedy(repo_scenario, topology):
    """Unborn HEAD refuses the fork with a remedy naming an initial commit.

    T-GRD-10 — plain repo with unborn HEAD refuses exit 5, repo_no_commits, remedy text
    asserted.
    T-GRD-11 — bare repo with unborn HEAD refuses exit 5, repo_no_commits, remedy text
    asserted.
    Source: REQ-19 (A2)
    """
    from agent_fork.errors import PreconditionError
    from agent_fork.repository import validate_fork_guards

    world = repo_scenario(topology)
    destination = world.parent_path.parent / "never-created"
    with pytest.raises(PreconditionError) as caught:
        validate_fork_guards(
            world.parent_path, "fork/unborn", destination, env=world.env
        )
    assert caught.value.exit_code == 5
    assert caught.value.code == "repo_no_commits"
    assert "make an initial commit" in str(caught.value)
    assert "re-run" in str(caught.value)
    assert not destination.exists()


@pytest.mark.parametrize(
    "markerless",
    [
        pytest.param(False, id="T-GRD-12", marks=pytest.mark.matrix("T-GRD-12")),
        pytest.param(True, id="T-GRD-13", marks=pytest.mark.matrix("T-GRD-13")),
    ],
)
def test_unmerged_index_refuses_with_conflicted_paths(repo_scenario, markerless):
    """Unmerged index state refuses the fork, listing conflicted paths.

    T-GRD-12 — conflict markers present in the unmerged index refuses exit 5,
    unmerged_index, conflicted paths listed.
    T-GRD-13 — markerless unmerged index (no conflict markers) refuses exit 5,
    unmerged_index, conflicted paths listed.
    Source: REQ-19 (A4)
    """
    from agent_fork.errors import PreconditionError
    from agent_fork.repository import validate_fork_guards
    from conftest import unmerged

    world = repo_scenario("plain@main", states=(unmerged(markerless),))
    destination = world.parent_path.parent / "never-created"
    with pytest.raises(PreconditionError) as caught:
        validate_fork_guards(
            world.parent_path, "fork/conflicted", destination, env=world.env
        )
    assert caught.value.code == "unmerged_index"
    assert "conflicted.txt" in str(caught.value)
    assert "resolve conflicts" in str(caught.value)
    assert not destination.exists()


@pytest.mark.matrix("T-GRD-14")
def test_race_loss_between_guard_pass_and_worktree_add(repo_scenario):
    """T-GRD-14 — A1 — a race loser between guard-pass and worktree add fails clean.

    Given:  a shim barrier parks run A after its guard pass but before `worktree add`;
            run B completes first
    Expect: once released, A exits 5, conflict_branch_exists, and nothing is left behind
    Source: REQ-11 (A1); spec §6.6
    """
    import time
    from concurrent.futures import ThreadPoolExecutor

    from agent_fork.errors import PreconditionError
    from agent_fork.repository import (
        create_worktree_at_anchor,
        resolve_anchor,
        validate_fork_guards,
    )
    from conftest import shim_git

    for attempt in range(3):
        world = repo_scenario("plain@main")
        branch = f"fork/race-{attempt}"
        loser_path = world.parent_path.parent / "loser"
        winner_path = world.parent_path.parent / "winner"
        validate_fork_guards(world.parent_path, branch, loser_path, env=world.env)
        anchor = resolve_anchor(world.parent_path, env=world.env)
        with shim_git(park_at="worktree add") as shim:
            loser_env = dict(world.env)
            loser_env["PATH"] = f"{shim.directory}:{loser_env['PATH']}"
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    create_worktree_at_anchor,
                    world.parent_path,
                    branch,
                    loser_path,
                    anchor=anchor,
                    env=loser_env,
                )
                deadline = time.monotonic() + 3
                while not shim.ready.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                assert shim.ready.exists(), "race shim did not reach worktree add"
                winner = create_worktree_at_anchor(
                    world.parent_path,
                    branch,
                    winner_path,
                    anchor=anchor,
                    env=world.env,
                )
                shim.release.touch()
                with pytest.raises(PreconditionError) as caught:
                    future.result(timeout=3)
        assert caught.value.code == "conflict_branch_exists"
        assert winner.path == winner_path.resolve()
        assert winner_path.exists()
        assert not loser_path.exists()
        assert not list((world.parent_path / ".agent-fork").glob("**/*"))


@pytest.mark.matrix("T-GRD-37")
def test_destination_still_registered_as_missing_worktree_refuses(repo_scenario):
    """T-GRD-37 — P02 A15 — a destination Git still records as a worktree refuses.

    Given:  Git still holds worktree metadata for the destination, whose
            directory was deleted (`git worktree list` marks it prunable)
    Expect: refusal before any mutation as conflict_worktree_path with a
            `git worktree prune` remedy; the fork leaves no branch behind,
            rather than failing as a misreported concurrent-creation race
    Source: P02 A15 (found during P02-TS07)
    """
    import shutil
    import subprocess

    from agent_fork.errors import PreconditionError
    from agent_fork.pipeline import ForkRequest, fork
    from agent_fork.repository import validate_fork_guards

    world = repo_scenario("plain@main")
    destination = world.parent_path.parent / "stale"

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(world.parent_path), *args],
            env=world.env,
            check=True,
            capture_output=True,
            text=True,
        ).stdout

    git("worktree", "add", "-q", "-b", "earlier", str(destination))
    shutil.rmtree(destination)
    assert "prunable" in git("worktree", "list", "--porcelain")
    branches_before = git("branch", "--list", "--format=%(refname:short)")

    with pytest.raises(PreconditionError) as guard:
        validate_fork_guards(world.parent_path, "fork/new", destination, env=world.env)
    assert guard.value.code == "conflict_worktree_path"
    assert "git worktree prune" in str(guard.value)

    request = ForkRequest(
        parent=world.parent_path,
        destination=destination,
        name="new",
        branch="fork/new",
        agent=None,
    )
    with pytest.raises(PreconditionError) as forked:
        fork(request, env=world.env)
    assert forked.value.code == "conflict_worktree_path"
    assert git("branch", "--list", "--format=%(refname:short)") == branches_before


def _git_out(world, *args):
    import subprocess

    return subprocess.run(
        ["git", "-C", str(world.parent_path), *args],
        env=world.env,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


@pytest.mark.matrix("T-GRD-38")
def test_case_variant_of_registered_missing_worktree_refuses(repo_scenario):
    """T-GRD-38 — P02 A15 review F1 — the stale-record guard honours core.ignorecase.

    Given:  Git still records a missing worktree at `Stale`, and the repository
            reports core.ignorecase (the macOS default)
    Expect: forking to `stale` refuses as conflict_worktree_path, and no branch leaks
    Source: P02 A15 gate-6 review
    """
    import shutil

    from agent_fork.errors import PreconditionError
    from agent_fork.pipeline import ForkRequest, fork

    world = repo_scenario("plain@main")
    if _git_out(world, "config", "--bool", "core.ignorecase").strip() != "true":
        pytest.skip("repository is case-sensitive")
    registered = world.parent_path.parent / "Stale"
    _git_out(world, "worktree", "add", "-q", "-b", "earlier", str(registered))
    shutil.rmtree(registered)
    branches_before = _git_out(world, "branch", "--list", "--format=%(refname:short)")

    request = ForkRequest(
        parent=world.parent_path,
        destination=world.parent_path.parent / "stale",
        name="case",
        branch="fork/case",
        agent=None,
    )
    with pytest.raises(PreconditionError) as caught:
        fork(request, env=world.env)
    assert caught.value.code == "conflict_worktree_path"
    assert _git_out(world, "branch", "--list", "--format=%(refname:short)") == (
        branches_before
    )


@pytest.mark.matrix("T-GRD-39")
def test_worktree_add_failure_after_branch_creation_rolls_branch_back(repo_scenario):
    """T-GRD-39 — P02 A15 review F2 — a failure Git hits after creating the branch.

    Given:  the destination's parent directory is read-only, which no guard
            detects, so `git worktree add -b` creates the branch and then fails
    Expect: the branch this attempt created is removed and Git's real failure is
            reported, never conflict_branch_exists ("won a concurrent creation race")
    Source: P02 A15 gate-6 review
    """
    import os

    from agent_fork.errors import PreconditionError
    from agent_fork.pipeline import ForkRequest, fork

    if os.geteuid() == 0:
        pytest.skip("root ignores directory permissions")
    world = repo_scenario("plain@main")
    locked = world.parent_path.parent / "read-only"
    locked.mkdir()
    locked.chmod(0o555)
    branches_before = _git_out(world, "branch", "--list", "--format=%(refname:short)")
    request = ForkRequest(
        parent=world.parent_path,
        destination=locked / "child",
        name="ro",
        branch="fork/ro",
        agent=None,
    )
    try:
        with pytest.raises(Exception) as caught:
            fork(request, env=world.env)
    finally:
        locked.chmod(0o755)
    assert not (
        isinstance(caught.value, PreconditionError)
        and caught.value.code == "conflict_branch_exists"
    ), caught.value
    assert _git_out(world, "branch", "--list", "--format=%(refname:short)") == (
        branches_before
    )
