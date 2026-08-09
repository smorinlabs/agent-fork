"""G-REG — Registry & list (tier C rows only; U rows in tests/unit/, F rows in
tests/pipeline/).

Matrix: docs/testing/TEST-MATRIX.md §G-REG.
"""

import pytest


@pytest.mark.matrix("T-REG-07")
@pytest.mark.skip(reason="pending: T-REG-07")
def test_list_renders_entries_and_json_schema(repo_scenario):
    """T-REG-07 — `list` renders registry entries in creation-time order and -o json
    emits the stable schema.

    Given:  multiple registry entries present
    Expect: list renders name, branch, worktree path, agent, worktree-still-exists in
            creation-time order; `-o json` emits the stable schema
    Source: REQ-31; D10; REQ-17
    """
    raise NotImplementedError
