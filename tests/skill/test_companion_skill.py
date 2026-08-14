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
    assert "Exact `--session-only`" in text
    assert "`fork_command`" in text
    assert "character-for-character" in text


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
    assert "Every token beginning with `-` other than those three exact forms" in text
    assert "`--session` combined with any other text" in text
    assert "`--session-only` is one exact token" in text
    assert "`--session-only` combined with any other text" in text
    assert "`--sesion`" in text
    assert "`--status`" in text
    assert "Use `--session`" in text
    assert "/agent-fork [name hint]" in text
    assert "/agent-fork --session" in text
    assert "/agent-fork --session-only" in text


def test_now_is_a_third_exact_option_token() -> None:
    text = _text()
    assert 'argument-hint: "[name-hint] [--now] | --session | --session-only"' in text
    assert "Exact `--now` skips the fork confirmation." in text
    assert "never accompany `--session` or `--session-only`" in text
    assert "other than those three exact forms" in text
    assert "all remaining text is one name hint" in text
    assert "/agent-fork [name hint] [--now]" in text


def test_frontmatter_declares_argument_and_tool_hints() -> None:
    text = _text()
    assert 'argument-hint: "[name-hint] [--now] | --session | --session-only"' in text
    assert "allowed-tools: Bash(agent-fork:*)" in text
    assert "AskUserQuestion" in text
    assert text.count("\n---\n") == 1


def test_missing_cli_preflight_precedes_every_route() -> None:
    text = _text()
    assert "exit `127`" in text
    assert "command not found" in text
    assert "uvx --from git+https://github.com/smorinlabs/agent-fork" in text
    assert "Never run a network-fetched command" in text
    assert "agent-fork doctor" in text
    assert text.index("exit `127`") < text.index("## Classify the request")


def test_missing_cli_offers_a_consent_gated_source_checkout_fallback() -> None:
    text = _text()
    assert "uv run --directory '<checkout>' agent-fork" in text
    assert "pyproject.toml" in text
    assert "`.agents/skills/agent-fork`" in text
    assert "ask before running the fallback" in text
    assert "dirty" in text
    assert "still print the install command" in text
    assert text.index("uv run --directory") > text.index(
        "## Confirm the CLI before any route"
    )
    assert text.index("uv run --directory") < text.index("## Classify the request")


def test_source_checkout_fallback_degrades_and_never_self_installs() -> None:
    text = _text()
    assert "If no checkout is discoverable" in text
    assert "Never install, fetch, or execute network-fetched code automatically" in text
    assert "Do not search the filesystem more widely" in text
    assert "Do not run hand-written Git commands" in text


def test_stale_cli_contract_reports_a_specific_upgrade_path() -> None:
    text = _text()
    assert "predates" in text
    assert (
        "uv tool install --force git+https://github.com/smorinlabs/agent-fork" in text
    )
    assert "contract changed without a version bump" in text


def test_failure_and_success_json_contracts_remain_explicit() -> None:
    text = _text()
    assert "uv tool install git+https://github.com/smorinlabs/agent-fork" in text
    assert "uv tool install agent-fork" not in text
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


def test_generated_metadata_exposes_inspection_command_and_fork_routes() -> None:
    metadata = (SKILL / "agents/openai.yaml").read_text()
    assert 'display_name: "Agent Fork"' in metadata
    assert 'short_description: "Inspect, print a session command, or fork"' in metadata
    assert "$agent-fork" in metadata
    assert "session-only" in metadata.lower()
