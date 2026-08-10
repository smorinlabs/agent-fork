"""G-DET — Agent detection (U-tier rows only; F rows land in Task 8).

Tombstones T-DET-06/07/08 are tier F (pre-0.95 Codex fallback ladder) and get
no stub anywhere in this file — they belong to G-DET's F-tier file, not here.

Matrix: docs/testing/TEST-MATRIX.md §G-DET.
"""

import pytest


@pytest.mark.matrix("T-DET-01")
def test_claude_detected_via_env_signals(repo_scenario):
    """T-DET-01 — Claude is detected via CLAUDECODE=1 and CLAUDE_CODE_SESSION_ID.

    Given:  CLAUDECODE=1 and CLAUDE_CODE_SESSION_ID present, no explicit flags
    Expect: resolved agent is claude
    Source: REQ-26; RESEARCH §5.0
    """
    from agent_fork.agents import detect_agent

    detected = detect_agent(
        {"CLAUDECODE": "1", "CLAUDE_CODE_SESSION_ID": "claude-parent"}
    )
    assert detected.agent == "claude"
    assert detected.parent_session_id == "claude-parent"


@pytest.mark.matrix("T-DET-02")
def test_codex_detected_via_env_signal(repo_scenario):
    """T-DET-02 — Codex is detected via CODEX_THREAD_ID.

    Given:  CODEX_THREAD_ID present, no explicit flags
    Expect: resolved agent is codex
    Source: REQ-26 (A7); RESEARCH §5.1 Q3
    """
    from agent_fork.agents import detect_agent

    detected = detect_agent({"CODEX_THREAD_ID": "codex-parent"})
    assert detected.agent == "codex"
    assert detected.parent_session_id == "codex-parent"


@pytest.mark.matrix("T-DET-03")
def test_explicit_flags_win_over_contradicting_env_signal(repo_scenario):
    """T-DET-03 — explicit --agent/--parent-session flags win over a contradicting env.

    Given:  --agent/--parent-session flags set, env signal contradicts them
    Expect: resolved agent follows the explicit flags
    Source: REQ-03; REQ-26
    """
    from agent_fork.agents import detect_agent

    detected = detect_agent(
        {"CODEX_THREAD_ID": "ambient-codex"},
        explicit_agent="claude",
        explicit_parent_session="explicit-claude",
    )
    assert detected.agent == "claude"
    assert detected.parent_session_id == "explicit-claude"
    without_env = detect_agent(
        {}, explicit_agent="codex", explicit_parent_session="explicit-codex"
    )
    assert without_env.agent == "codex"
    assert without_env.parent_session_id == "explicit-codex"


@pytest.mark.matrix("T-DET-09")
def test_auto_without_signals_selects_git_only(repo_scenario):
    from agent_fork.agents import resolve_agent_mode

    assert resolve_agent_mode("auto", {}) is None
    assert (
        resolve_agent_mode(
            "git-only",
            {
                "CLAUDECODE": "1",
                "CLAUDE_CODE_SESSION_ID": "claude",
                "CODEX_THREAD_ID": "codex",
            },
        )
        is None
    )


@pytest.mark.matrix("T-DET-10")
def test_auto_with_one_signal_selects_agent(repo_scenario):
    from agent_fork.agents import resolve_agent_mode

    context = resolve_agent_mode(
        "auto", {"CLAUDECODE": "1", "CLAUDE_CODE_SESSION_ID": "parent"}
    )
    assert context is not None and context.agent == "claude"


@pytest.mark.matrix("T-DET-11")
def test_strict_without_signals_refuses(repo_scenario):
    from agent_fork.agents import resolve_agent_mode
    from agent_fork.errors import AgentDetectionError

    with pytest.raises(AgentDetectionError, match="no agent signal"):
        resolve_agent_mode("strict", {})


@pytest.mark.matrix("T-DET-12")
def test_auto_with_dual_signals_refuses(repo_scenario):
    from agent_fork.agents import resolve_agent_mode
    from agent_fork.errors import AgentDetectionError

    env = {
        "CLAUDECODE": "1",
        "CLAUDE_CODE_SESSION_ID": "claude",
        "CODEX_THREAD_ID": "codex",
    }
    with pytest.raises(AgentDetectionError, match="both Claude and Codex"):
        resolve_agent_mode("auto", env)
