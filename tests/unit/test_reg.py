"""G-REG — Registry & list (U-tier rows only; F/C rows land in Task 8).

Matrix: docs/testing/TEST-MATRIX.md §G-REG.
"""

import pytest


@pytest.mark.matrix("T-REG-01")
@pytest.mark.skip(reason="pending: T-REG-01")
def test_registry_write_populates_schema_fields(repo_scenario):
    """T-REG-01 — a registry write on fork populates the schema fields.

    Given:  a completed fork
    Expect: registry entry has name, branch, worktree path, agent, and creation
            time populated
    Source: REQ-41; D10
    """
    raise NotImplementedError


@pytest.mark.matrix("T-REG-02")
@pytest.mark.skip(reason="pending: T-REG-02")
def test_list_output_ordered_by_creation_time_deterministically(repo_scenario):
    """T-REG-02 — list output is ordered by creation time, deterministically.

    Given:  multiple registry entries, list run repeatedly
    Expect: output ordered by creation time, deterministic across repeated runs
    Source: D10
    """
    raise NotImplementedError
