"""G-RBK — Rollback & signals (tier F).

Matrix: docs/testing/TEST-MATRIX.md §G-RBK.
"""

import pytest


@pytest.mark.matrix("T-RBK-01")
@pytest.mark.skip(reason="pending: T-RBK-01")
def test_materialize_failure_triggers_rollback(repo_scenario):
    """T-RBK-01 — a materialize failure triggers rollback of the worktree and,
    conditionally, the branch.

    Given:  materialize fails partway through a fork
    Expect: rollback removes the worktree; removes the branch only if it was created
            this call
    Source: REQ-22; RESEARCH §2.1 step 10
    """
    raise NotImplementedError


@pytest.mark.matrix("T-RBK-02")
@pytest.mark.skip(reason="pending: T-RBK-02")
def test_rollback_failure_emits_manual_recovery_text(repo_scenario):
    """T-RBK-02 — a rollback that itself fails emits the exact manual-recovery command.

    Given:  rollback fails after a materialize failure
    Expect: exact manual-recovery command text emitted (`rm -rf "<worktree>" && git -C
            "<root>" branch -D "<branch>"`)
    Source: REQ-22; RESEARCH §2.1 step 10
    """
    raise NotImplementedError


@pytest.mark.parametrize(
    "signal",
    [
        pytest.param("SIGINT", id="T-RBK-03", marks=pytest.mark.matrix("T-RBK-03")),
        pytest.param("SIGTERM", id="T-RBK-04", marks=pytest.mark.matrix("T-RBK-04")),
    ],
)
@pytest.mark.skip(reason="pending: T-RBK-03..T-RBK-04 family")
def test_signal_mid_materialize_exits_with_signal_code_and_rolls_back(
    repo_scenario, signal
):
    """A signal delivered mid-materialize exits with the signal's code and rolls back
    cleanly.

    T-RBK-03 — SIGINT mid-materialize (parent-side step-2 diff stall) exits 130, clean
    rollback of partial work.
    T-RBK-04 — SIGTERM mid-materialize (parent-side step-2 diff stall) exits 143, clean
    rollback of partial work.
    Source: REQ-22; spec §6.6 signal window
    """
    raise NotImplementedError


@pytest.mark.parametrize(
    "verify",
    [
        pytest.param("verify-on", id="T-RBK-05", marks=pytest.mark.matrix("T-RBK-05")),
        pytest.param("verify-off", id="T-RBK-06", marks=pytest.mark.matrix("T-RBK-06")),
    ],
)
@pytest.mark.skip(reason="pending: T-RBK-05..T-RBK-06 family")
def test_producer_pipe_failure_fails_and_rolls_back(repo_scenario, verify):
    """A producer-pipe failure fails materialize and rolls back regardless of verify
    state.

    T-RBK-05 — verify on: a fake git where `diff --cached` exits 1 with empty stdout
    fails materialize, rollback runs, exit 1.
    T-RBK-06 — verify off (--no-verify): the same fake failure still fails, rollback
    runs, exit 1.
    Source: REQ-22; spec §5; spec §6.6
    """
    raise NotImplementedError
