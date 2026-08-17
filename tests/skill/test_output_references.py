"""Per-agent presentation references loaded by the skill via progressive disclosure."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[2]
SKILL = ROOT / ".agents/skills/agent-fork"
SKILL_MD = SKILL / "SKILL.md"
CLAUDE_REF = SKILL / "references/output-claude.md"
CODEX_REF = SKILL / "references/output-codex.md"


def _flat(path: Path) -> str:
    """One-space-normalized text so phrase assertions survive line wrapping."""
    return " ".join(path.read_text().split())


def test_skill_routes_presentation_to_per_agent_references() -> None:
    text = SKILL_MD.read_text()
    assert "references/output-claude.md" in text
    assert "references/output-codex.md" in text
    assert "formatting only" in text
    assert text.index("references/output-claude.md") < text.index(
        "## Validate and present CLI results"
    )


def test_reference_selection_is_keyed_on_the_reported_agent() -> None:
    text = _flat(SKILL_MD)
    assert '`"claude"`' in text
    assert '`"codex"`' in text
    assert "When `agent` is null or the CLI is missing, no reference applies." in text


def test_both_reference_files_cover_all_four_modes() -> None:
    for reference in (CLAUDE_REF, CODEX_REF):
        text = reference.read_text()
        assert "## `--session`" in text
        assert "## `--session-only`" in text
        assert "## Fork confirmation" in text
        assert "## Fork result" in text


def test_reference_examples_are_illustrative_never_templates() -> None:
    for reference in (CLAUDE_REF, CODEX_REF):
        text = reference.read_text()
        assert "character-for-character" in text
        assert "formatting only" in text
        assert "terminal-escaped" in text


def test_session_summary_and_confirmation_use_tables() -> None:
    for reference in (CLAUDE_REF, CODEX_REF):
        text = reference.read_text()
        assert "| Field | Value |" in text
        assert "| Staged | Unstaged | Untracked | Ignored |" in text
        assert "| Rule | Value |" in text


def test_confirmation_mode_values_are_documented_defaults_not_live() -> None:
    for reference in (CLAUDE_REF, CODEX_REF):
        text = _flat(reference)
        assert "`with_state`" in text
        assert "`with_ignored`" in text
        assert "documented defaults" in text
        assert "not read from the dry run" in text


def test_session_only_stays_a_bare_unfenced_line() -> None:
    for reference in (CLAUDE_REF, CODEX_REF):
        text = _flat(reference)
        assert "no label" in text
        assert "no code fence" in text


def test_claude_reference_carries_claude_command_shape_and_notes() -> None:
    text = CLAUDE_REF.read_text()
    assert "--fork-session" in text
    assert "--session-id" in text
    assert "minted fresh" in text
    assert "workspace-trust prompt" in text
    assert "codex fork" not in text


def test_codex_reference_carries_codex_command_shape_and_notes() -> None:
    text = _flat(CODEX_REF)
    assert "codex fork" in text
    assert "CODEX_THREAD_ID" in text
    assert "its own thread ID" in text
    assert "not passed to `codex`" in text
    assert "--fork-session" not in text
