"""G-INC — Include & setup hook (tier F).

Matrix: docs/testing/TEST-MATRIX.md §G-INC.
"""

import pytest


@pytest.mark.matrix("T-INC-01")
@pytest.mark.skip(reason="pending: T-INC-01")
def test_worktreeinclude_copies_listed_gitignored_files(repo_scenario):
    """T-INC-01 — .worktreeinclude copies the gitignored files it lists.

    Given:  a `.worktreeinclude` file listing paths that are gitignored
    Expect: the listed gitignored files are copied into the fork
    Source: REQ-24; RESEARCH §2.1 step 11
    """
    raise NotImplementedError


@pytest.mark.matrix("T-INC-02")
@pytest.mark.skip(reason="pending: T-INC-02")
def test_worktreeinclude_yields_to_materialized_copies(repo_scenario):
    """T-INC-02 — materialized copies win; .worktreeinclude skips a file already present
    in the fork.

    Given:  a `.worktreeinclude` entry naming a file that materialize already copied
    Expect: the materialized copy wins; .worktreeinclude skips that file
    Source: REQ-24; RESEARCH §2.1 step 11
    """
    raise NotImplementedError


@pytest.mark.matrix("T-INC-03")
@pytest.mark.skip(reason="pending: T-INC-03")
def test_setup_hook_runs_with_worktree_cwd_and_env(repo_scenario):
    """T-INC-03 — the setup hook runs with cwd set to the new worktree and
    repo-root/worktree-path env vars.

    Given:  a `.agent-fork/worktree-setup.sh` hook present
    Expect: hook runs with cwd = new worktree, env vars carrying repo root + worktree
            path
    Source: REQ-24; RESEARCH §2.1 step 12; spec §5
    """
    raise NotImplementedError


@pytest.mark.matrix("T-INC-04")
@pytest.mark.skip(reason="pending: T-INC-04")
def test_setup_hook_failure_is_non_fatal(repo_scenario):
    """T-INC-04 — a failing setup hook is non-fatal; the fork still succeeds.

    Given:  the setup hook exits non-zero
    Expect: non-fatal, stderr notice, fork still succeeds
    Source: REQ-24; RESEARCH §2.1 step 12
    """
    raise NotImplementedError


@pytest.mark.matrix("T-INC-05")
@pytest.mark.skip(reason="pending: T-INC-05")
def test_include_and_hook_run_after_verify(repo_scenario):
    """T-INC-05 — include and hook run after verify; their filesystem changes are
    excluded from the verify comparison.

    Given:  a fork with both `.worktreeinclude` entries and a setup hook
    Expect: include/hook run after verify; their filesystem changes are excluded from
            the verify comparison
    Source: spec §5
    """
    raise NotImplementedError
