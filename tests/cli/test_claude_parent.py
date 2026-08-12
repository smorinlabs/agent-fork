import json

import pytest


def _seed(world):
    root = world.parent_path / ".claude"
    project = root / "projects" / "-repo"
    project.mkdir(parents=True)
    parent = "20000000-0000-4000-8000-000000000001"
    child = "20000000-0000-4000-8000-000000000002"
    uuids = [f"10000000-0000-4000-8000-{i:012d}" for i in range(1, 5)]
    for session, extra in ((parent, []), (child, [uuids[3]])):
        rows = []
        for index, uid in enumerate(uuids[:3]):
            rows.append(
                {
                    "sessionId": session,
                    "uuid": uid,
                    "parentUuid": uuids[index - 1] if index else None,
                    "type": "user" if index == 1 else "assistant",
                    "timestamp": f"2026-01-01T00:00:0{index}Z",
                }
            )
        if extra:
            rows.append(
                {
                    "sessionId": session,
                    "uuid": extra[0],
                    "parentUuid": uuids[2],
                    "type": "user",
                    "timestamp": "2026-01-01T00:00:03Z",
                }
            )
        (project / f"{session}.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in rows)
        )
    (root / "history.jsonl").write_text(
        json.dumps({"sessionId": parent, "timestamp": 1000})
        + "\n"
        + json.dumps({"sessionId": child, "timestamp": 2000})
        + "\n"
    )
    env = {
        **world.env,
        "CLAUDE_CONFIG_DIR": str(root),
        "XDG_CACHE_HOME": str(world.parent_path / "cache"),
    }
    return env, parent, child


@pytest.mark.matrix("T-CPI-07")
def test_infer_requires_explicit_target(repo_scenario):
    from conftest import run_cli

    world = repo_scenario()
    result = run_cli(
        ["session", "claude-parent", "infer"], world.env, world.parent_path
    )
    assert result.returncode == 2


@pytest.mark.matrix("T-CPI-08")
def test_infer_record_list_show_delete(repo_scenario):
    from conftest import run_cli

    world = repo_scenario()
    env, parent, child = _seed(world)
    inferred = run_cli(
        [
            "session",
            "claude-parent",
            "infer",
            "--session-id",
            child,
            "--record",
            "-o",
            "json",
        ],
        env,
        world.parent_path,
    )
    assert inferred.returncode == 0, inferred.stderr
    assert (
        json.loads(inferred.stdout)["relationship"]["likely_parent_session_id"]
        == parent
    )
    listed = run_cli(
        ["session", "claude-parent", "list", "-o", "json"],
        env,
        world.parent_path,
    )
    assert json.loads(listed.stdout)[0]["source"] == "inferred"
    shown = run_cli(
        [
            "session",
            "claude-parent",
            "show",
            "--session-id",
            child,
            "--source",
            "inferred",
            "-o",
            "json",
        ],
        env,
        world.parent_path,
    )
    assert json.loads(shown.stdout)["parent_session_id"] == parent
    deleted = run_cli(
        [
            "session",
            "claude-parent",
            "delete",
            "--session-id",
            child,
            "--source",
            "inferred",
            "--yes",
            "-o",
            "json",
        ],
        env,
        world.parent_path,
    )
    assert json.loads(deleted.stdout)["deleted"] is True


@pytest.mark.matrix("T-CPI-09")
def test_preview_does_not_write_inference_store(repo_scenario):
    from agent_fork.lineage_inference_store import inference_path
    from conftest import run_cli

    world = repo_scenario()
    env, _, child = _seed(world)
    result = run_cli(
        ["session", "claude-parent", "infer", "--session-id", child],
        env,
        world.parent_path,
    )
    assert result.returncode == 0
    assert not inference_path(env).exists()


@pytest.mark.matrix("T-CPI-29")
def test_unrecordable_machine_result_is_one_stderr_error(repo_scenario):
    from conftest import run_cli

    world = repo_scenario()
    env, _, child = _seed(world)
    child_path = world.parent_path / ".claude/projects/-repo" / f"{child}.jsonl"
    child_path.write_text(
        json.dumps(
            {
                "uuid": "10000000-0000-4000-8000-000000000099",
                "parentUuid": None,
                "type": "system",
            }
        )
        + "\n"
    )

    result = run_cli(
        [
            "session",
            "claude-parent",
            "infer",
            "--session-id",
            child,
            "--record",
            "-o",
            "json",
        ],
        env,
        world.parent_path,
    )

    assert result.returncode == 3
    assert result.stdout == b""
    error = json.loads(result.stderr)
    assert error["error"]["code"] == "claude_parent_not_recordable"
    assert (
        error["error"]["details"]["analysis"]["relationship"]["status"]
        == "insufficient_evidence"
    )


@pytest.mark.matrix("T-CPI-30")
def test_delete_json_without_yes_refuses_without_mutation(repo_scenario):
    from agent_fork.lineage_inference_store import find_inference
    from conftest import run_cli

    world = repo_scenario()
    env, _, child = _seed(world)
    recorded = run_cli(
        [
            "session",
            "claude-parent",
            "infer",
            "--session-id",
            child,
            "--record",
            "-o",
            "json",
        ],
        env,
        world.parent_path,
    )
    assert recorded.returncode == 0

    refused = run_cli(
        [
            "session",
            "claude-parent",
            "delete",
            "--session-id",
            child,
            "--source",
            "inferred",
            "-o",
            "json",
        ],
        env,
        world.parent_path,
    )

    assert refused.returncode == 2
    assert refused.stdout == b""
    assert json.loads(refused.stderr)["error"]["code"] == "config_error"
    assert find_inference(child, env=env) is not None


@pytest.mark.matrix("T-CPI-31")
def test_delete_help_exposes_noninteractive_consent_controls(repo_scenario):
    from conftest import run_cli

    world = repo_scenario()
    result = run_cli(
        ["session", "claude-parent", "delete", "--help"],
        world.env,
        world.parent_path,
    )

    assert result.returncode == 0
    assert b"--yes" in result.stdout
    assert b"--no-input" in result.stdout


@pytest.mark.matrix("T-CPI-32")
def test_bulk_preview_is_one_bounded_json_document(repo_scenario):
    from conftest import run_cli

    world = repo_scenario()
    env, _, _ = _seed(world)

    result = run_cli(
        ["session", "claude-parent", "infer", "--all", "-o", "json"],
        env,
        world.parent_path,
    )

    assert result.returncode == 0
    assert result.stderr == b""
    document = json.loads(result.stdout)
    assert document["summary"] == {"failed": 0, "recorded": 0, "total": 2}
    assert len(document["results"]) == 2
    assert all("candidate_count" in row for row in document["results"])


@pytest.mark.matrix("T-CPI-33")
def test_bulk_partial_record_is_one_stderr_document(repo_scenario):
    from agent_fork.lineage_inference_store import find_inference
    from conftest import run_cli

    world = repo_scenario()
    env, _, child = _seed(world)

    result = run_cli(
        [
            "session",
            "claude-parent",
            "infer",
            "--all",
            "--record-all",
            "-o",
            "json",
        ],
        env,
        world.parent_path,
    )

    assert result.returncode == 3
    assert result.stdout == b""
    document = json.loads(result.stderr)
    assert document["error"]["code"] == "claude_parent_partial_record"
    summary = document["error"]["details"]["analysis"]["summary"]
    assert summary == {"failed": 1, "recorded": 1, "total": 2}
    assert find_inference(child, env=env) is not None
