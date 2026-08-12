from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[2]
SKILL = ROOT / ".agents/skills/agent-fork"
SKILL_MD = SKILL / "SKILL.md"
WRAPPER = SKILL / "scripts/fork_session.py"


def _text() -> str:
    return SKILL_MD.read_text()


def test_skill_is_one_shared_claude_and_codex_artifact() -> None:
    claude_skill = ROOT / ".claude/skills/agent-fork"
    assert claude_skill.resolve() == SKILL.resolve()
    text = _text()
    assert text.startswith("---\nname: agent-fork\ndescription:")
    assert text.count("\n---\n") == 1
    assert len(text.splitlines()) < 500


def test_skill_locks_session_and_fork_command_routes() -> None:
    text = _text()
    assert "agent-fork session --json" in text
    assert "agent-fork fork '<normalized-name>' --require-agent --json" in text
    assert "agent-fork fork --require-agent --json" in text
    assert "Do not add `--agent` or `--parent-session`" in text


def test_omitted_name_uses_session_context_and_cli_automatic_naming() -> None:
    text = _text()
    assert "`repository.on_default_branch` is `false`" in text
    assert "Do not pass a positional name" in text
    assert "date and collision suffixes" in text
    assert "recommend one concise name" in text
    assert "If `agent` or `current_session` is null" in text
    assert "If `repository` is null" in text


def test_name_classification_precedes_restricted_normalization() -> None:
    text = _text()
    assert "Classify before normalizing" in text
    assert "[a-z0-9]+(?:-[a-z0-9]+)*" in text
    assert '"Review Auth" -> "review-auth"' in text
    assert '"feature/auth-refresh" -> "feature-auth-refresh"' in text
    assert "Ask for another name if normalization is empty" in text
    assert "shell-quoted argument" in text


def test_option_like_input_refuses_without_mutation() -> None:
    text = _text()
    assert "Apply the argument gate first" in text
    assert "Never remove `--session`" in text
    assert "Every other token beginning with `-`" in text
    assert "`--session` combined with any other text" in text
    assert "`--sesion`" in text
    assert "`--status`" in text
    assert "Use `--session`" in text
    assert "/agent-fork [name hint]" in text
    assert "/agent-fork --session" in text


def test_failure_and_success_json_contracts_remain_explicit() -> None:
    text = _text()
    assert "uv tool install agent-fork" in text
    assert "Invalid agent-fork JSON output" in text
    assert "`fork.name`, `fork.branch`, and `fork.worktree`" in text
    assert "exact returned `command` string" in text
    assert "Preserve nonzero CLI output" in text
    assert "Do not retry with guessed session IDs" in text
    assert "Do not search transcripts" in text
    assert "Do not run hand-written Git commands" in text


def test_wrapper_is_removed_without_a_replacement_executable() -> None:
    text = _text()
    assert not WRAPPER.exists()
    assert "fork_session.py" not in text
    assert "scripts/" not in text
    assert not (SKILL / "scripts").exists()


def test_generated_metadata_exposes_both_routes() -> None:
    metadata = (SKILL / "agents/openai.yaml").read_text()
    assert 'display_name: "Agent Fork"' in metadata
    assert 'short_description: "Inspect or fork the current agent session"' in metadata
    assert "$agent-fork" in metadata
    assert "inspect or fork" in metadata.lower()
