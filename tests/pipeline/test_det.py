"""G-DET — Agent detection (tier F rows only; U rows in tests/unit/).

Tombstones T-DET-06/07/08 are pre-0.95 Codex fallback rows and get no stub
anywhere in this file.

Matrix: docs/testing/TEST-MATRIX.md §G-DET.
"""

import pytest


@pytest.mark.parametrize(
    "signal_state",
    [
        pytest.param(
            "both-present", id="T-DET-04", marks=pytest.mark.matrix("T-DET-04")
        ),
        pytest.param(
            "neither-present", id="T-DET-05", marks=pytest.mark.matrix("T-DET-05")
        ),
    ],
)
def test_agent_detection_ambiguous_or_absent_signals_exit_3(
    repo_scenario, signal_state
):
    """Ambiguous or absent agent env signals, with no explicit flags, exit 3.

    T-DET-04 — both Claude and Codex env signals present, no explicit flags, exits 3.
    T-DET-05 — neither env signal present, no explicit flags, exits 3.
    Source: REQ-26
    """
    from agent_fork.agents import detect_agent
    from agent_fork.errors import AgentDetectionError

    env = (
        {
            "CLAUDECODE": "1",
            "CLAUDE_CODE_SESSION_ID": "claude-parent",
            "CODEX_THREAD_ID": "codex-parent",
        }
        if signal_state == "both-present"
        else {}
    )
    with pytest.raises(AgentDetectionError) as caught:
        detect_agent(env)
    assert caught.value.exit_code == 3
    assert caught.value.code == "agent_not_detected"
    assert "--agent" in str(caught.value)
