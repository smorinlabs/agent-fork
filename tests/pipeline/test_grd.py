"""G-GRD — Fork guards (tier F).

Matrix: docs/testing/TEST-MATRIX.md §G-GRD.
"""

import pytest


@pytest.mark.matrix("T-GRD-01")
@pytest.mark.skip(reason="pending: T-GRD-01")
def test_branch_already_exists_refuses(repo_scenario):
    """T-GRD-01 — an already-existing branch name refuses the fork.

    Given:  the target fork branch name already exists in the repo
    Expect: refusal, exit 5, conflict_branch_exists, nothing created
    Source: REQ-19; RESEARCH §2.1 step 2
    """
    raise NotImplementedError


@pytest.mark.matrix("T-GRD-02")
@pytest.mark.skip(reason="pending: T-GRD-02")
def test_branch_already_has_a_worktree_refuses(repo_scenario):
    """T-GRD-02 — a branch already checked out in another worktree refuses the fork.

    Given:  the target fork branch is already attached to an existing worktree
    Expect: refusal, exit 5, nothing created
    Source: REQ-19
    """
    raise NotImplementedError


@pytest.mark.matrix("T-GRD-03")
@pytest.mark.skip(reason="pending: T-GRD-03")
def test_worktree_path_already_exists_refuses(repo_scenario):
    """T-GRD-03 — an already-existing worktree path refuses the fork.

    Given:  the computed worktree path already exists on disk
    Expect: refusal, exit 5, nothing created
    Source: REQ-19; RESEARCH §2.1 step 3
    """
    raise NotImplementedError


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
@pytest.mark.skip(reason="pending: T-GRD-04..T-GRD-08 family")
def test_parent_mid_operation_refuses_with_abort_hint(repo_scenario, operation):
    """Parent mid-operation refuses the fork with an operation-specific abort hint.

    T-GRD-04 — mid-rebase refuses exit 5; hint is `cd "<parent>" && git rebase --abort`.
    T-GRD-05 — mid-merge refuses exit 5; hint is `git merge --abort`.
    T-GRD-06 — mid-cherry-pick refuses exit 5; hint is `git cherry-pick --abort`.
    T-GRD-07 — mid-revert refuses exit 5; hint is `git revert --abort`.
    T-GRD-08 — mid-bisect refuses exit 5; hint is `git bisect reset`.
    Source: REQ-19; RESEARCH §2.1 step 4
    """
    raise NotImplementedError


@pytest.mark.matrix("T-GRD-09")
@pytest.mark.skip(reason="pending: T-GRD-09")
def test_not_a_repo_refuses(repo_scenario):
    """T-GRD-09 — invoking outside any git repo refuses the fork.

    Given:  the invoking cwd is not inside a git repository
    Expect: refusal, exit 5, nothing created
    Source: REQ-19
    """
    raise NotImplementedError


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
@pytest.mark.skip(reason="pending: T-GRD-10..T-GRD-11 family")
def test_unborn_head_refuses_with_remedy(repo_scenario, topology):
    """Unborn HEAD refuses the fork with a remedy naming an initial commit.

    T-GRD-10 — plain repo with unborn HEAD refuses exit 5, repo_no_commits, remedy text
    asserted.
    T-GRD-11 — bare repo with unborn HEAD refuses exit 5, repo_no_commits, remedy text
    asserted.
    Source: REQ-19 (A2)
    """
    raise NotImplementedError


@pytest.mark.parametrize(
    "markerless",
    [
        pytest.param(False, id="T-GRD-12", marks=pytest.mark.matrix("T-GRD-12")),
        pytest.param(True, id="T-GRD-13", marks=pytest.mark.matrix("T-GRD-13")),
    ],
)
@pytest.mark.skip(reason="pending: T-GRD-12..T-GRD-13 family")
def test_unmerged_index_refuses_with_conflicted_paths(repo_scenario, markerless):
    """Unmerged index state refuses the fork, listing conflicted paths.

    T-GRD-12 — conflict markers present in the unmerged index refuses exit 5,
    unmerged_index, conflicted paths listed.
    T-GRD-13 — markerless unmerged index (no conflict markers) refuses exit 5,
    unmerged_index, conflicted paths listed.
    Source: REQ-19 (A4)
    """
    raise NotImplementedError


@pytest.mark.matrix("T-GRD-14")
@pytest.mark.skip(reason="pending: T-GRD-14")
def test_race_loss_between_guard_pass_and_worktree_add(repo_scenario):
    """T-GRD-14 — A1 — a race loser between guard-pass and worktree add fails clean.

    Given:  a shim barrier parks run A after its guard pass but before `worktree add`;
            run B completes first
    Expect: once released, A exits 5, conflict_branch_exists, and nothing is left behind
    Source: REQ-11 (A1); spec §6.6
    """
    raise NotImplementedError
