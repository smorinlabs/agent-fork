"""G-DET — Agent detection (U-tier rows only; F rows land in Task 8).

Tombstones T-DET-06/07/08 are tier F (pre-0.95 Codex fallback ladder) and get
no stub anywhere in this file — they belong to G-DET's F-tier file, not here.

Matrix: docs/testing/TEST-MATRIX.md §G-DET.
"""

import pytest


@pytest.mark.matrix("T-DET-01")
@pytest.mark.skip(reason="pending: T-DET-01")
def test_claude_detected_via_env_signals(repo_scenario):
    """T-DET-01 — Claude is detected via CLAUDECODE=1 and CLAUDE_CODE_SESSION_ID.

    Given:  CLAUDECODE=1 and CLAUDE_CODE_SESSION_ID present, no explicit flags
    Expect: resolved agent is claude
    Source: REQ-26; RESEARCH §5.0
    """
    raise NotImplementedError


@pytest.mark.matrix("T-DET-02")
@pytest.mark.skip(reason="pending: T-DET-02")
def test_codex_detected_via_env_signal(repo_scenario):
    """T-DET-02 — Codex is detected via CODEX_THREAD_ID.

    Given:  CODEX_THREAD_ID present, no explicit flags
    Expect: resolved agent is codex
    Source: REQ-26 (A7); RESEARCH §5.1 Q3
    """
    raise NotImplementedError


@pytest.mark.matrix("T-DET-03")
@pytest.mark.skip(reason="pending: T-DET-03")
def test_explicit_flags_win_over_contradicting_env_signal(repo_scenario):
    """T-DET-03 — explicit --agent/--parent-session flags win over a contradicting env.

    Given:  --agent/--parent-session flags set, env signal contradicts them
    Expect: resolved agent follows the explicit flags
    Source: REQ-03; REQ-26
    """
    raise NotImplementedError
