"""Unit tests for lineage store error contracts."""

import pytest

from agent_fork.lineage import LineageClaim, add_lineage, lineage_path, read_lineage


@pytest.mark.matrix("T-CPI-37")
def test_read_lineage_invalid_json_raises_value_error(tmp_path):
    env = {"XDG_STATE_HOME": str(tmp_path)}
    path = lineage_path(env)
    path.parent.mkdir(parents=True)
    path.write_text("{ this is not json")
    with pytest.raises(ValueError, match="invalid agent-fork lineage store"):
        read_lineage(env=env)


@pytest.mark.matrix("T-CPI-38")
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


@pytest.mark.matrix("T-CPI-39")
def test_invalid_utf8_store_raises_the_same_value_error(tmp_path):
    """Undecodable bytes are a corrupt store, not a decoder-specific failure.

    ``Path.read_text`` raises ``UnicodeDecodeError`` for invalid UTF-8. That is
    a ``ValueError`` subclass but not a ``JSONDecodeError``, so it escaped the
    normalizing handler until it was named explicitly.
    """
    env = {"XDG_STATE_HOME": str(tmp_path)}
    path = lineage_path(env)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xff\xfe not valid utf-8")
    with pytest.raises(ValueError, match="invalid agent-fork lineage store"):
        read_lineage(env=env)
