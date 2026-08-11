"""G-SES — pure session evidence and assertion behavior."""

import json
from pathlib import Path

import pytest


@pytest.mark.matrix("T-SES-01")
def test_inspection_without_agent_is_observational(repo_scenario):
    from agent_fork.session import inspect_session

    world = repo_scenario()
    result = inspect_session(world.env, cwd=world.parent_path)
    assert result.agent is None
    assert result.current_session is None
    assert result.lineage_status == "not_detected"


@pytest.mark.matrix("T-SES-02")
def test_claude_environment_is_current_identity(repo_scenario):
    from agent_fork.session import inspect_session

    world = repo_scenario()
    env = {
        **world.env,
        "CLAUDECODE": "1",
        "CLAUDE_CODE_SESSION_ID": "child-claude",
    }
    result = inspect_session(env, cwd=world.parent_path)
    assert result.agent == "claude"
    assert result.current_session is not None
    assert result.current_session.id == "child-claude"
    assert result.current_session.id_source == "CLAUDE_CODE_SESSION_ID"


@pytest.mark.matrix("T-SES-03")
def test_ambiguous_environment_is_reported(repo_scenario):
    from agent_fork.session import inspect_session

    world = repo_scenario()
    env = {
        **world.env,
        "CLAUDECODE": "1",
        "CLAUDE_CODE_SESSION_ID": "claude",
        "CODEX_THREAD_ID": "codex",
    }
    result = inspect_session(env, cwd=world.parent_path)
    assert result.agent is None and result.lineage_status == "ambiguous"


@pytest.mark.matrix("T-SES-04")
def test_claude_name_comes_from_exact_current_transcript(repo_scenario):
    from agent_fork.session import inspect_session

    world = repo_scenario()
    session_id = "child-claude"
    env = {
        **world.env,
        "CLAUDECODE": "1",
        "CLAUDE_CODE_SESSION_ID": session_id,
        "CLAUDE_CONFIG_DIR": str(world.parent_path.parent / "claude"),
    }
    encoded = __import__("re").sub(r"[^a-zA-Z0-9]", "-", str(world.parent_path))
    transcript = (
        Path(env["CLAUDE_CONFIG_DIR"]) / "projects" / encoded / f"{session_id}.jsonl"
    )
    transcript.parent.mkdir(parents=True)
    transcript.write_text(
        json.dumps(
            {"type": "custom-title", "customTitle": "hello", "sessionId": session_id}
        )
        + "\n"
    )
    result = inspect_session(env, cwd=world.parent_path)
    assert result.current_session is not None
    assert result.current_session.name == "hello"
    assert result.current_session.name_status == "resolved"


@pytest.mark.matrix("T-SES-05")
def test_claude_lineage_claim_is_not_observation(repo_scenario):
    from agent_fork.lineage import LineageClaim, add_lineage
    from agent_fork.session import inspect_session

    world = repo_scenario()
    add_lineage(
        LineageClaim.create(
            agent="claude",
            child_session_id="child",
            parent_session_id="parent",
            name="named-child",
        ),
        env=world.env,
    )
    env = {
        **world.env,
        "CLAUDECODE": "1",
        "CLAUDE_CODE_SESSION_ID": "child",
    }
    result = inspect_session(env, cwd=world.parent_path)
    assert result.parent_session is not None
    assert result.current_session is not None
    assert result.parent_session.id == "parent"
    assert result.parent_session.id_status == "claimed"
    assert result.current_session.name_status == "claimed"


@pytest.mark.matrix("T-SES-06")
def test_lineage_store_round_trip_and_replacement(repo_scenario):
    from agent_fork.lineage import LineageClaim, add_lineage, read_lineage

    world = repo_scenario()
    for parent in ("first", "second"):
        add_lineage(
            LineageClaim.create(
                agent="claude", child_session_id="child", parent_session_id=parent
            ),
            env=world.env,
        )
    claims = read_lineage(env=world.env)
    assert len(claims) == 1 and claims[0].parent_session_id == "second"


@pytest.mark.matrix("T-SES-07")
def test_validation_constraints_compose(repo_scenario):
    from agent_fork.session import (
        SessionAssertions,
        SessionEvidence,
        SessionInspection,
        validate_session,
    )

    repo_scenario()
    inspection = SessionInspection(
        "codex",
        SessionEvidence("child", "CODEX_THREAD_ID"),
        SessionEvidence("parent", "codex-app-server"),
        "resolved",
    )
    result = validate_session(
        inspection,
        SessionAssertions(
            agent="codex",
            session_id="child",
            parent_session_id="parent",
            has_parent=True,
        ),
    )
    assertions = result["assertions"]
    assert isinstance(assertions, list)
    assert result["valid"] is True and len(assertions) == 5


@pytest.mark.matrix("T-SES-08")
def test_validation_mismatch_is_typed(repo_scenario):
    from agent_fork.errors import SessionValidationError
    from agent_fork.session import (
        SessionAssertions,
        SessionInspection,
        validate_session,
    )

    repo_scenario()
    with pytest.raises(SessionValidationError):
        validate_session(
            SessionInspection(None, None, None, "not_detected"), SessionAssertions()
        )


@pytest.mark.matrix("T-SES-21")
def test_claude_session_id_cannot_escape_transcript_path(repo_scenario):
    from agent_fork.session import inspect_session

    world = repo_scenario()
    env = {
        **world.env,
        "CLAUDECODE": "1",
        "CLAUDE_CODE_SESSION_ID": "../../outside",
        "CLAUDE_CONFIG_DIR": str(world.parent_path.parent / "claude"),
    }
    outside = world.parent_path.parent / "outside.jsonl"
    outside.write_text('{"customTitle":"unsafe","sessionId":"../../outside"}\n')
    result = inspect_session(env, cwd=world.parent_path)
    assert result.current_session is not None
    assert result.current_session.name is None
