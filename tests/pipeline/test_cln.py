"""G-CLN — Cleanup (tier F rows only; C rows in tests/cli/).

Matrix: docs/testing/TEST-MATRIX.md §G-CLN.
"""

import pytest


@pytest.mark.matrix("T-CLN-01")
@pytest.mark.skip(reason="pending: T-CLN-01")
def test_cleanup_target_accepts_name_branch_or_path(repo_scenario):
    """T-CLN-01 — cleanup's TARGET argument accepts a fork name, a branch name, or a
    worktree path.

    Given:  a completed fork, targeted by each of its name, branch, and worktree path
            forms
    Expect: each form resolves to the same fork
    Source: REQ-31
    """
    raise NotImplementedError


@pytest.mark.matrix("T-CLN-02")
@pytest.mark.skip(reason="pending: T-CLN-02")
def test_cleanup_removes_and_prunes_worktree(repo_scenario):
    """T-CLN-02 — cleanup removes the worktree via `git worktree remove` and prunes it.

    Given:  a fork targeted for cleanup
    Expect: worktree removed via `git worktree remove` and pruned
    Source: REQ-31
    """
    raise NotImplementedError


@pytest.mark.matrix("T-CLN-03")
@pytest.mark.skip(reason="pending: T-CLN-03")
def test_cleanup_deletes_branch_unless_keep_branch(repo_scenario):
    """T-CLN-03 — cleanup deletes the fork branch by default; --keep-branch preserves
    it.

    Given:  cleanup run with and without `--keep-branch`
    Expect: the fork branch is deleted by default; `--keep-branch` preserves it
    Source: REQ-31
    """
    raise NotImplementedError


@pytest.mark.matrix("T-CLN-04")
@pytest.mark.skip(reason="pending: T-CLN-04")
def test_cleanup_removes_registry_entry(repo_scenario):
    """T-CLN-04 — cleanup removes the fork's registry entry.

    Given:  a completed cleanup
    Expect: the fork's registry entry is removed
    Source: REQ-31
    """
    raise NotImplementedError


@pytest.mark.parametrize(
    "guard",
    [
        pytest.param(
            "dirty-worktree", id="T-CLN-05", marks=pytest.mark.matrix("T-CLN-05")
        ),
        pytest.param(
            "unpushed-commits", id="T-CLN-06", marks=pytest.mark.matrix("T-CLN-06")
        ),
        pytest.param(
            "target-is-cwd", id="T-CLN-07", marks=pytest.mark.matrix("T-CLN-07")
        ),
    ],
)
@pytest.mark.skip(reason="pending: T-CLN-05..T-CLN-07 family")
def test_cleanup_guard_refuses_without_force(repo_scenario, guard):
    """Each cleanup guard refuses the target with exit 5 unless overridden.

    T-CLN-05 — a dirty worktree (uncommitted changes) refuses cleanup, exit 5.
    T-CLN-06 — commits not reachable from any upstream (unpushed) refuses cleanup, exit
    5.
    T-CLN-07 — a target that is the invoking cwd refuses cleanup, exit 5.
    Source: REQ-32; DESIGN-DECISIONS D12
    """
    raise NotImplementedError


@pytest.mark.matrix("T-CLN-08")
@pytest.mark.skip(reason="pending: T-CLN-08")
def test_cleanup_force_extends_targeting_and_overrides_guards(repo_scenario):
    """T-CLN-08 — --force extends cleanup targeting beyond registry-recorded forks and
    overrides the dirty/unpushed guards only.

    Given:  cleanup run with `--force` against a non-registry target and against
            dirty/unpushed guard conditions
    Expect: targeting is extended beyond registry-recorded forks; the dirty/unpushed
            guards are overridden. The invoking-cwd guard is never overridden by
            `--force` (see T-CLN-14).
    Source: DESIGN-DECISIONS D12
    """
    raise NotImplementedError


@pytest.mark.matrix("T-CLN-14")
@pytest.mark.skip(reason="pending: T-CLN-14")
def test_cleanup_force_does_not_override_cwd_guard(repo_scenario):
    """T-CLN-14 — --force combined with a target-is-invoking-cwd guard still refuses.

    Given:  cleanup run with `--force` against a target that is the invoking cwd
    Expect: still refuse, exit 5 — the invoking-cwd guard is non-overridable
    Source: REQ-32; DESIGN-DECISIONS D12
    """
    raise NotImplementedError


@pytest.mark.matrix("T-CLN-12")
@pytest.mark.skip(reason="pending: T-CLN-12")
def test_cleanup_never_deletes_session_files(repo_scenario):
    """T-CLN-12 — cleanup never deletes session files and notes the session remains
    resumable.

    Given:  cleanup run against a fork with an associated agent session
    Expect: session files are never deleted; output notes the fork session remains
            resumable
    Source: REQ-34
    """
    raise NotImplementedError
