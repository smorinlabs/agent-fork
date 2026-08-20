"""Unit tests for lineage store error contracts."""

import pytest

from agent_fork.lineage import LineageClaim, add_lineage, lineage_path, read_lineage


def test_read_lineage_invalid_json_raises_value_error(tmp_path):
    env = {"XDG_STATE_HOME": str(tmp_path)}
    path = lineage_path(env)
    path.parent.mkdir(parents=True)
    path.write_text("{ this is not json")
    with pytest.raises(ValueError, match="invalid agent-fork lineage store"):
        read_lineage(env=env)


def test_add_lineage_invalid_json_raises_value_error(tmp_path):
    env = {"XDG_STATE_HOME": str(tmp_path)}
    path = lineage_path(env)
    path.parent.mkdir(parents=True)
    path.write_text("{ this is not json")
    claim = LineageClaim.create(
        agent="claude",
        child_session_id="child",
        parent_session_id="parent",
    )
    with pytest.raises(ValueError, match="invalid agent-fork lineage store"):
        add_lineage(claim, env=env)
