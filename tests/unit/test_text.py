"""Unit tests for safe rendering of repository-controlled text."""

import pytest

from agent_fork.agents import _terminal_safe
from agent_fork.text import BIDI_CONTROLS, escape_terminal_text


@pytest.mark.matrix("T-OUT-23")
def test_bidi_controls_are_escaped_and_rejected():
    """A bidi override reorders displayed text without being a control byte.

    ``U+202E`` is outside the C0 and C1 ranges, so the codepoint checks miss
    it, yet it makes a rendered branch name read differently from the name
    actually stored. Both the escaper and the predicate must catch it, and
    they must agree on the same set.
    """
    for control in BIDI_CONTROLS:
        rendered = escape_terminal_text(f"feat{control}name")
        assert control not in rendered, f"{control!r} survived escaping"
        assert f"\\u{ord(control):04x}" in rendered
        assert not _terminal_safe(f"feat{control}name")

    assert escape_terminal_text("feature/añejo") == "feature/añejo"
