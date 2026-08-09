"""G-REG — Registry & list (tier F rows only; U rows in tests/unit/, C rows in
tests/cli/).

Matrix: docs/testing/TEST-MATRIX.md §G-REG.
"""

import pytest


@pytest.mark.matrix("T-REG-03")
@pytest.mark.skip(reason="pending: T-REG-03")
def test_locked_write_atomicity_serializes_concurrent_writers(repo_scenario):
    """T-REG-03 — locked registry writes serialize concurrent writers without torn
    entries.

    Given:  multiple concurrent registry writers
    Expect: writes serialize; no torn/corrupt registry entries
    Source: REQ-41; REQ-12
    """
    raise NotImplementedError


@pytest.mark.matrix("T-REG-04")
@pytest.mark.skip(reason="pending: T-REG-04")
def test_different_name_concurrent_race_both_succeed(repo_scenario):
    """T-REG-04 — A13 — two concurrent forks of one repo under different names both
    succeed.

    Given:  two forks of the same repo started concurrently under different names
    Expect: both succeed, both entries present, bounded wait observed (<=~5s)
    Source: REQ-41 (A13)
    """
    raise NotImplementedError


@pytest.mark.matrix("T-REG-05")
@pytest.mark.skip(reason="pending: T-REG-05")
def test_lock_timeout_rolls_back_with_registry_busy(repo_scenario):
    """T-REG-05 — A13 — a lock held past the bound rolls the fork back with
    registry_busy.

    Given:  the registry lock held past the wait bound
    Expect: registry_busy; fork rolled back with the manual-recovery message
    Source: REQ-41 (A13)
    """
    raise NotImplementedError


@pytest.mark.matrix("T-REG-06")
@pytest.mark.skip(reason="pending: T-REG-06")
def test_registry_ownership_check_feeds_cleanup_refusal(repo_scenario):
    """T-REG-06 — the registry ownership check makes cleanup refuse a target it did not
    create.

    Given:  a cleanup target not created by this registry, `--force` not passed
    Expect: cleanup refuses the target unless `--force` is passed
    Source: REQ-31; D12
    """
    raise NotImplementedError
