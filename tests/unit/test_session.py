"""G-SES — pure session evidence and assertion behavior."""

import json
from pathlib import Path
from typing import cast

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
        SessionForkCommand,
        SessionInspection,
        validate_session,
    )

    world = repo_scenario()
    inspection = SessionInspection(
        agent="codex",
        current_session=SessionEvidence("child", "CODEX_THREAD_ID"),
        parent_session=SessionEvidence("parent", "codex-app-server"),
        lineage_status="resolved",
        directory=world.parent_path,
        repository=None,
        fork_command=SessionForkCommand(
            status="available", command="codex fork child -C /tmp"
        ),
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
    session = cast(dict[str, object], result["session"])
    assert session["directory"] == str(world.parent_path)
    assert session["repository"] is None


@pytest.mark.matrix("T-SES-08")
def test_validation_mismatch_is_typed(repo_scenario):
    from agent_fork.errors import SessionValidationError
    from agent_fork.session import (
        SessionAssertions,
        SessionForkCommand,
        SessionInspection,
        validate_session,
    )

    world = repo_scenario()
    with pytest.raises(SessionValidationError):
        validate_session(
            SessionInspection(
                agent=None,
                current_session=None,
                parent_session=None,
                lineage_status="not_detected",
                directory=world.parent_path,
                repository=None,
                fork_command=SessionForkCommand(status="not_detected", command=None),
            ),
            SessionAssertions(),
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


@pytest.mark.matrix("T-SES-23")
def test_every_identity_outcome_includes_resolved_directory(repo_scenario):
    from agent_fork.session import inspect_session

    world = repo_scenario()
    directory = world.parent_path / "nested"
    directory.mkdir()
    environments = (
        world.env,
        {
            **world.env,
            "CLAUDECODE": "1",
            "CLAUDE_CODE_SESSION_ID": "claude",
        },
        {
            **world.env,
            "CLAUDECODE": "1",
            "CLAUDE_CODE_SESSION_ID": "claude",
            "CODEX_THREAD_ID": "codex",
        },
    )

    results = [inspect_session(env, cwd=directory) for env in environments]

    assert [result.directory for result in results] == [directory.resolve()] * 3
    assert [result.document()["directory"] for result in results] == [
        str(directory.resolve())
    ] * 3
    assert [result.lineage_status for result in results] == [
        "not_detected",
        "not_found",
        "ambiguous",
    ]


@pytest.mark.matrix("T-SES-24")
def test_repository_context_classifies_topologies_deterministically(repo_scenario):
    from agent_fork.git import run_git
    from agent_fork.session import inspect_session

    main_world = repo_scenario("plain@main")
    main = inspect_session(main_world.env, cwd=main_world.parent_path).repository
    topic_world = repo_scenario("plain@branch")
    topic = inspect_session(topic_world.env, cwd=topic_world.parent_path).repository
    detached_world = repo_scenario("detached")
    detached = inspect_session(
        detached_world.env, cwd=detached_world.parent_path
    ).repository
    linked_world = repo_scenario("linked-worktree")
    linked = inspect_session(linked_world.env, cwd=linked_world.parent_path).repository
    bare_world = repo_scenario("bare@bare")
    bare = inspect_session(bare_world.env, cwd=bare_world.parent_path).repository
    remote_world = repo_scenario("plain@main")
    run_git(
        remote_world.parent_path,
        ["update-ref", "refs/remotes/origin/develop", "HEAD"],
        env=remote_world.env,
    )
    run_git(
        remote_world.parent_path,
        [
            "symbolic-ref",
            "refs/remotes/origin/HEAD",
            "refs/remotes/origin/develop",
        ],
        env=remote_world.env,
    )
    remote = inspect_session(remote_world.env, cwd=remote_world.parent_path).repository
    unclassified_world = repo_scenario("plain@branch")
    run_git(
        unclassified_world.parent_path,
        ["branch", "-D", "main"],
        env=unclassified_world.env,
    )
    unclassified = inspect_session(
        unclassified_world.env, cwd=unclassified_world.parent_path
    ).repository

    assert main is not None
    assert main.branch == "main"
    assert main.remote_default_branch is None
    assert main.default_branch_candidates == ("main",)
    assert main.on_default_branch is True
    assert main.linked_worktree is False
    assert main.bare is False

    assert topic is not None
    assert topic.branch == "feature" and topic.on_default_branch is False

    assert detached is not None
    assert detached.branch is None and detached.detached is True
    assert detached.on_default_branch is False

    assert linked is not None
    assert linked.branch == "feature" and linked.linked_worktree is True
    assert linked.root == linked_world.parent_path

    assert bare is not None
    assert bare.root == bare_world.repo_root
    assert bare.branch == "main" and bare.bare is True
    assert bare.status is None

    assert remote is not None
    assert remote.remote_default_branch == "develop"
    assert remote.default_branch_candidates == ("develop", "main")
    assert remote.on_default_branch is True

    assert unclassified is not None
    assert unclassified.default_branch_candidates == ()
    assert unclassified.on_default_branch is None


@pytest.mark.matrix("T-SES-25")
def test_repository_status_counts_independent_states_and_operations(repo_scenario):
    from agent_fork.session import inspect_session
    from conftest import ignored, staged, unmerged, unstaged, untracked

    clean_world = repo_scenario("plain@main")
    clean = inspect_session(clean_world.env, cwd=clean_world.parent_path).repository
    assert clean is not None and clean.status is not None
    assert clean.status.clean is True
    assert clean.status.document() == {
        "clean": True,
        "staged": 0,
        "unstaged": 0,
        "untracked": 0,
        "unmerged": 0,
        "operation": None,
    }

    dirty_world = repo_scenario(
        "plain@main",
        states=(
            staged(add="staged.txt"),
            unstaged("unstaged.txt"),
            untracked("untracked.txt"),
        ),
    )
    dirty = inspect_session(dirty_world.env, cwd=dirty_world.parent_path).repository
    assert dirty is not None and dirty.status is not None
    assert (dirty.status.staged, dirty.status.unstaged, dirty.status.untracked) == (
        1,
        1,
        1,
    )
    assert dirty.status.unmerged == 0 and dirty.status.clean is False

    ignored_world = repo_scenario("plain@main", states=(ignored("ignored-secret.txt"),))
    ignored_state = inspect_session(
        ignored_world.env, cwd=ignored_world.parent_path
    ).repository
    assert ignored_state is not None and ignored_state.status is not None
    assert ignored_state.status.clean is True

    conflict_world = repo_scenario("plain@main", states=(unmerged(markerless=True),))
    conflict = inspect_session(
        conflict_world.env, cwd=conflict_world.parent_path
    ).repository
    assert conflict is not None and conflict.status is not None
    assert conflict.status.unmerged == 1 and conflict.status.clean is False

    operation_world = repo_scenario("plain@main")
    assert operation_world.git_dir is not None
    (operation_world.git_dir / "MERGE_HEAD").write_text("0" * 40 + "\n")
    operation = inspect_session(
        operation_world.env, cwd=operation_world.parent_path
    ).repository
    assert operation is not None and operation.status is not None
    assert operation.status.operation == "merge" and operation.status.clean is False


@pytest.mark.matrix("T-SES-26")
def test_repository_context_failure_preserves_identity_and_adds_notice(
    repo_scenario, monkeypatch
):
    import agent_fork.session as session_module

    world = repo_scenario()
    env = {
        **world.env,
        "CLAUDECODE": "1",
        "CLAUDE_CODE_SESSION_ID": "child",
    }

    detail = "repository metadata denied " + ("x" * 600)

    def refuse(*args, **kwargs):
        raise PermissionError(detail)

    monkeypatch.setattr(session_module, "inspect_repository", refuse)
    result = session_module.inspect_session(env, cwd=world.parent_path)

    assert result.agent == "claude"
    assert result.current_session is not None
    assert result.current_session.id == "child"
    assert result.repository is None
    notice = next(
        value
        for value in result.notices
        if value.startswith("repository context unavailable: ")
    )
    assert notice.startswith(
        "repository context unavailable: repository metadata denied"
    )
    assert notice.endswith("...")
    assert len(notice) == len("repository context unavailable: ") + 500


@pytest.mark.matrix("T-SES-28")
def test_fork_command_status_uses_identity_and_safety_not_lineage(
    repo_scenario, monkeypatch
):
    import agent_fork.session as session_module

    world = repo_scenario()
    no_identity = session_module.inspect_session(world.env, cwd=world.parent_path)
    assert no_identity.fork_command.status == "not_detected"
    assert no_identity.fork_command.command is None

    claude_env = {
        **world.env,
        "CLAUDECODE": "1",
        "CLAUDE_CODE_SESSION_ID": "claude-child",
    }
    claude = session_module.inspect_session(claude_env, cwd=world.parent_path)
    assert claude.fork_command.status == "available"
    assert claude.fork_command.command is not None

    ambiguous = session_module.inspect_session(
        {**claude_env, "CODEX_THREAD_ID": "codex-thread"}, cwd=world.parent_path
    )
    assert ambiguous.fork_command.status == "ambiguous"
    assert ambiguous.fork_command.command is None

    original_which = session_module.shutil.which
    monkeypatch.setattr(
        session_module.shutil,
        "which",
        lambda name, path=None: (
            None if name == "codex" else original_which(name, path=path)
        ),
    )
    codex = session_module.inspect_session(
        {**world.env, "CODEX_THREAD_ID": "codex-thread"}, cwd=world.parent_path
    )
    assert codex.lineage_status == "unavailable"
    assert codex.fork_command.status == "available"
    assert codex.fork_command.command is not None

    unsafe = session_module.inspect_session(
        {
            **world.env,
            "CLAUDECODE": "1",
            "CLAUDE_CODE_SESSION_ID": "unsafe\x1b]52;c;Zm9v\x07",
        },
        cwd=world.parent_path,
    )
    assert unsafe.fork_command.status == "unsafe_input"
    assert unsafe.fork_command.command is None

    with pytest.raises(ValueError, match="unknown session fork command status"):
        session_module.SessionForkCommand(
            cast(session_module.SessionForkStatus, "future"), None
        )
    with pytest.raises(ValueError, match="must be non-empty"):
        session_module.SessionForkCommand("available", None)
    with pytest.raises(ValueError, match="must be null"):
        session_module.SessionForkCommand("ambiguous", "unexpected")


@pytest.mark.matrix("T-SES-29")
def test_claude_child_uuid_lives_once_per_inspection(repo_scenario):
    import uuid

    from agent_fork.session import SessionAssertions, inspect_session, validate_session

    world = repo_scenario()
    env = {
        **world.env,
        "CLAUDECODE": "1",
        "CLAUDE_CODE_SESSION_ID": "claude-child",
    }
    fixed = "33333333-3333-4333-8333-333333333333"
    deterministic = inspect_session(env, cwd=world.parent_path, child_session_id=fixed)
    assert deterministic.document() == deterministic.document()
    assert deterministic.fork_command.child_session_id == fixed
    assert fixed in str(deterministic.document()["fork_command"])
    validated = validate_session(
        deterministic,
        SessionAssertions(agent="claude", session_id="claude-child"),
    )
    assert fixed in str(cast(dict[str, object], validated["session"])["fork_command"])

    first = inspect_session(env, cwd=world.parent_path)
    second = inspect_session(env, cwd=world.parent_path)
    first_child = first.fork_command.child_session_id
    second_child = second.fork_command.child_session_id
    assert first_child is not None and second_child is not None
    assert first_child != second_child
    assert uuid.UUID(first_child).version == 4
    assert uuid.UUID(second_child).version == 4
