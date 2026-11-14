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


@pytest.mark.parametrize(
    ("env", "status", "context", "present", "missing"),
    [
        pytest.param(
            {},
            "absent",
            None,
            (),
            (),
            id="T-DET-13",
            marks=pytest.mark.matrix("T-DET-13"),
        ),
        pytest.param(
            {"CLAUDECODE": "1"},
            "incomplete",
            None,
            ("CLAUDECODE=1",),
            ("CLAUDE_CODE_SESSION_ID",),
            id="T-DET-14",
            marks=pytest.mark.matrix("T-DET-14"),
        ),
        pytest.param(
            {"CLAUDE_CODE_SESSION_ID": "claude-parent"},
            "incomplete",
            None,
            ("CLAUDE_CODE_SESSION_ID",),
            ("CLAUDECODE=1",),
            id="T-DET-15",
            marks=pytest.mark.matrix("T-DET-15"),
        ),
        pytest.param(
            {
                "CLAUDECODE": "1",
                "CLAUDE_CODE_SESSION_ID": "claude-parent",
            },
            "detected",
            ("claude", "claude-parent"),
            ("CLAUDECODE=1", "CLAUDE_CODE_SESSION_ID"),
            (),
            id="T-DET-16",
            marks=pytest.mark.matrix("T-DET-16"),
        ),
        pytest.param(
            {"CODEX_THREAD_ID": "codex-parent"},
            "detected",
            ("codex", "codex-parent"),
            ("CODEX_THREAD_ID",),
            (),
            id="T-DET-17",
            marks=pytest.mark.matrix("T-DET-17"),
        ),
        pytest.param(
            {"CLAUDECODE": "1", "CODEX_THREAD_ID": "codex-parent"},
            "ambiguous",
            None,
            ("CLAUDECODE=1", "CODEX_THREAD_ID"),
            ("CLAUDE_CODE_SESSION_ID",),
            id="T-DET-18",
            marks=pytest.mark.matrix("T-DET-18"),
        ),
        pytest.param(
            {
                "CLAUDE_CODE_SESSION_ID": "claude-parent",
                "CODEX_THREAD_ID": "codex-parent",
            },
            "ambiguous",
            None,
            ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID"),
            ("CLAUDECODE=1",),
            id="T-DET-19",
            marks=pytest.mark.matrix("T-DET-19"),
        ),
        pytest.param(
            {
                "CLAUDECODE": "1",
                "CLAUDE_CODE_SESSION_ID": "claude-parent",
                "CODEX_THREAD_ID": "codex-parent",
            },
            "ambiguous",
            None,
            (
                "CLAUDECODE=1",
                "CLAUDE_CODE_SESSION_ID",
                "CODEX_THREAD_ID",
            ),
            (),
            id="T-DET-20",
            marks=pytest.mark.matrix("T-DET-20"),
        ),
    ],
)
def test_agent_signal_assessment_truth_table(
    repo_scenario, env, status, context, present, missing
):
    """T-DET-13..20 — every supported environment shape has one exact state."""
    from agent_fork.agents import AgentContext, assess_agent_signals

    repo_scenario()
    assessment = assess_agent_signals(env)
    expected_context = AgentContext(*context) if context is not None else None
    assert assessment.status == status
    assert assessment.context == expected_context
    assert assessment.present == present
    assert assessment.missing == missing


@pytest.mark.matrix("T-DET-21")
def test_partial_claude_signal_refuses_auto_and_strict_modes(repo_scenario):
    """T-DET-21 — both partial Claude shapes raise the typed refusal."""
    from agent_fork.agents import resolve_agent_mode
    from agent_fork.errors import AgentSignalIncompleteError

    repo_scenario()
    shapes = (
        ({"CLAUDECODE": "1"}, ("CLAUDE_CODE_SESSION_ID",)),
        ({"CLAUDE_CODE_SESSION_ID": "claude-parent"}, ("CLAUDECODE=1",)),
    )
    for mode in ("auto", "strict"):
        for env, missing in shapes:
            with pytest.raises(AgentSignalIncompleteError) as caught:
                resolve_agent_mode(mode, env)
            error = caught.value
            assert error.code == "agent_signal_incomplete"
            assert error.exit_code == 3
            assert error.details == {
                "status": "incomplete",
                "present": [
                    "CLAUDECODE=1" if "CLAUDECODE" in env else "CLAUDE_CODE_SESSION_ID"
                ],
                "missing": list(missing),
            }
            assert missing[0] in str(error)
            assert "--no-agent" in str(error)


@pytest.mark.matrix("T-DET-22")
def test_complete_explicit_identity_overrides_ambient_signal_state(repo_scenario):
    """T-DET-22 — explicit identity overrides incomplete and ambiguous ambient input."""
    from agent_fork.agents import AgentContext, resolve_agent_mode

    repo_scenario()
    assert resolve_agent_mode(
        "auto",
        {"CLAUDECODE": "1"},
        explicit_agent="codex",
        explicit_parent_session="explicit-codex",
    ) == AgentContext("codex", "explicit-codex")
    assert resolve_agent_mode(
        "strict",
        {
            "CLAUDECODE": "1",
            "CLAUDE_CODE_SESSION_ID": "ambient-claude",
            "CODEX_THREAD_ID": "ambient-codex",
        },
        explicit_agent="claude",
        explicit_parent_session="explicit-claude",
    ) == AgentContext("claude", "explicit-claude")


@pytest.mark.matrix("T-DET-23")
def test_explicit_git_only_ignores_incomplete_or_ambiguous_signals(repo_scenario):
    """T-DET-23 — Git-only is authoritative for every non-detected conflict."""
    from agent_fork.agents import resolve_agent_mode

    repo_scenario()
    environments = (
        {"CLAUDECODE": "1"},
        {"CLAUDE_CODE_SESSION_ID": "claude-parent"},
        {"CLAUDECODE": "1", "CODEX_THREAD_ID": "codex-parent"},
        {
            "CLAUDE_CODE_SESSION_ID": "claude-parent",
            "CODEX_THREAD_ID": "codex-parent",
        },
        {
            "CLAUDECODE": "1",
            "CLAUDE_CODE_SESSION_ID": "claude-parent",
            "CODEX_THREAD_ID": "codex-parent",
        },
    )
    assert all(resolve_agent_mode("git-only", env) is None for env in environments)


@pytest.mark.matrix("T-DET-24")
def test_complete_single_agent_signals_retain_resolution_behavior(repo_scenario):
    """T-DET-24 — complete Claude and Codex signals resolve in both modes."""
    from agent_fork.agents import AgentContext, resolve_agent_mode

    repo_scenario()
    shapes = (
        (
            {
                "CLAUDECODE": "1",
                "CLAUDE_CODE_SESSION_ID": "claude-parent",
            },
            AgentContext("claude", "claude-parent"),
        ),
        (
            {"CODEX_THREAD_ID": "codex-parent"},
            AgentContext("codex", "codex-parent"),
        ),
    )
    for mode in ("auto", "strict"):
        for env, expected in shapes:
            assert resolve_agent_mode(mode, env) == expected


@pytest.mark.matrix("T-DET-25")
def test_explicit_agent_retains_matching_environment_id_fallback(repo_scenario):
    """T-DET-25 — explicit agent fallback does not require the Claude marker."""
    from agent_fork.agents import AgentContext, resolve_agent_mode

    repo_scenario()
    assert resolve_agent_mode(
        "auto",
        {"CLAUDE_CODE_SESSION_ID": "claude-parent"},
        explicit_agent="claude",
    ) == AgentContext("claude", "claude-parent")
    assert resolve_agent_mode(
        "strict",
        {"CODEX_THREAD_ID": "codex-parent"},
        explicit_agent="codex",
    ) == AgentContext("codex", "codex-parent")


@pytest.mark.matrix("T-DET-26")
def test_partial_claude_plus_codex_is_ambiguous_in_auto_and_strict(repo_scenario):
    """T-DET-26 — any observed Claude value conflicts with a Codex signal."""
    from agent_fork.agents import resolve_agent_mode
    from agent_fork.errors import AgentDetectionError, AgentSignalIncompleteError

    repo_scenario()
    environments = (
        {"CLAUDECODE": "1", "CODEX_THREAD_ID": "codex-parent"},
        {
            "CLAUDE_CODE_SESSION_ID": "claude-parent",
            "CODEX_THREAD_ID": "codex-parent",
        },
    )
    for mode in ("auto", "strict"):
        for env in environments:
            with pytest.raises(AgentDetectionError, match="Claude and Codex") as caught:
                resolve_agent_mode(mode, env)
            assert not isinstance(caught.value, AgentSignalIncompleteError)


@pytest.mark.parametrize(
    ("env", "status", "context", "present", "missing"),
    [
        pytest.param(
            {"OPENCODE": "1", "OPENCODE_SESSION_ID": "ses_parent1"},
            "detected",
            ("opencode", "ses_parent1"),
            ("OPENCODE_SESSION_ID",),
            (),
            id="T-DET-27",
            marks=pytest.mark.matrix("T-DET-27"),
        ),
        pytest.param(
            {"OPENCODE": "1"},
            "absent",
            None,
            (),
            (),
            id="T-DET-28",
            marks=pytest.mark.matrix("T-DET-28"),
        ),
        pytest.param(
            {
                "CLAUDECODE": "1",
                "CLAUDE_CODE_SESSION_ID": "claude-parent",
                "OPENCODE_SESSION_ID": "ses_parent1",
            },
            "ambiguous",
            None,
            ("CLAUDECODE=1", "CLAUDE_CODE_SESSION_ID", "OPENCODE_SESSION_ID"),
            (),
            id="T-DET-29",
            marks=pytest.mark.matrix("T-DET-29"),
        ),
    ],
)
def test_opencode_signal_assessment_truth_table(
    repo_scenario, env, status, context, present, missing
):
    """T-DET-27..29 — OpenCode follows the Codex rule: its session ID alone detects."""
    from agent_fork.agents import AgentContext, assess_agent_signals

    repo_scenario()
    assessment = assess_agent_signals(env)
    expected_context = AgentContext(*context) if context is not None else None
    assert assessment.status == status
    assert assessment.context == expected_context
    assert assessment.present == present
    assert assessment.missing == missing


@pytest.mark.matrix("T-DET-30")
def test_opencode_with_another_agent_refuses_as_ambiguous(repo_scenario):
    """T-DET-30 — OpenCode plus any Claude or Codex signal names every agent."""
    from agent_fork.agents import assess_agent_signals, resolve_agent_mode
    from agent_fork.errors import AgentDetectionError, AgentSignalIncompleteError

    repo_scenario()
    shapes = (
        (
            {"CODEX_THREAD_ID": "codex-parent", "OPENCODE_SESSION_ID": "ses_p"},
            "both Codex and OpenCode signals are present",
        ),
        (
            {
                "MUSE_SESSION_ID": "01a1d375-470a-73b0-939a-6381da238f05",
                "OPENCODE_SESSION_ID": "ses_p",
            },
            "both Muse and OpenCode signals are present",
        ),
        (
            {"CLAUDECODE": "1", "OPENCODE_SESSION_ID": "ses_p"},
            "Claude and OpenCode signals are present; incomplete Claude signal "
            "is missing CLAUDE_CODE_SESSION_ID",
        ),
        (
            {
                "CLAUDECODE": "1",
                "CLAUDE_CODE_SESSION_ID": "claude-parent",
                "CODEX_THREAD_ID": "codex-parent",
                "OPENCODE_SESSION_ID": "ses_p",
            },
            "Claude, Codex, and OpenCode signals are present",
        ),
    )
    for env, diagnosis in shapes:
        assert assess_agent_signals(env).diagnosis() == diagnosis
        for mode in ("auto", "strict"):
            with pytest.raises(AgentDetectionError, match=diagnosis) as caught:
                resolve_agent_mode(mode, env)
            assert not isinstance(caught.value, AgentSignalIncompleteError)
    # The Claude-and-Codex wording is unchanged.
    both = {
        "CLAUDECODE": "1",
        "CLAUDE_CODE_SESSION_ID": "claude-parent",
        "CODEX_THREAD_ID": "codex-parent",
    }
    assert (
        assess_agent_signals(both).diagnosis()
        == "both Claude and Codex signals are present"
    )


@pytest.mark.matrix("T-DET-31")
def test_opencode_resolves_in_auto_strict_and_explicit_modes(repo_scenario):
    """T-DET-31 — OpenCode resolves like Codex in every mode and by explicit flags."""
    from agent_fork.agents import AgentContext, detect_agent, resolve_agent_mode
    from agent_fork.errors import AgentDetectionError

    repo_scenario()
    env = {"OPENCODE": "1", "OPENCODE_SESSION_ID": "ses_parent1"}
    for mode in ("auto", "strict"):
        assert resolve_agent_mode(mode, env) == AgentContext("opencode", "ses_parent1")
        assert resolve_agent_mode(
            mode, {"OPENCODE_SESSION_ID": "ses_parent1"}
        ) == AgentContext("opencode", "ses_parent1")
    assert resolve_agent_mode("git-only", env) is None
    assert detect_agent(
        {"CODEX_THREAD_ID": "ambient"},
        explicit_agent="opencode",
        explicit_parent_session="ses_explicit",
    ) == AgentContext("opencode", "ses_explicit")
    assert detect_agent(env, explicit_agent="opencode") == AgentContext(
        "opencode", "ses_parent1"
    )
    with pytest.raises(AgentDetectionError, match="--agent opencode requires"):
        detect_agent({}, explicit_agent="opencode")
    with pytest.raises(AgentDetectionError, match="claude, codex, muse, or opencode"):
        detect_agent({}, explicit_agent="alien", explicit_parent_session="x")
