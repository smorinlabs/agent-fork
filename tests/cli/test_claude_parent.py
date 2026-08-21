import json
from pathlib import Path

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


def _current_signal_env(environment, **signals):
    result = {
        key: value
        for key, value in environment.items()
        if key not in {"CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID"}
    }
    result.update(signals)
    return result


@pytest.mark.matrix("T-CPI-36")
def test_current_inference_consumes_shared_agent_signal_assessment(
    repo_scenario, monkeypatch, capsys
):
    import agent_fork.claude_lineage_inference as inference
    from agent_fork.cli import main
    from conftest import run_cli

    world = repo_scenario()
    seeded, _, child = _seed(world)

    discovery_attempted = False

    def fail_if_discovery_starts(*args, **kwargs):
        nonlocal discovery_attempted
        discovery_attempted = True
        raise AssertionError("Claude lineage discovery started before assessment")

    with monkeypatch.context() as patch:
        patch.setattr(inference, "ClaudeLineageCorpus", fail_if_discovery_starts)
        for name in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID"):
            patch.delenv(name, raising=False)
        patch.setenv("CLAUDECODE", "1")
        assert (
            main(["session", "claude-parent", "infer", "--current", "-o", "json"]) == 3
        )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err)["error"]["code"] == "agent_signal_incomplete"
    assert discovery_attempted is False

    for signals in ({}, {"CODEX_THREAD_ID": "codex-parent"}):
        unavailable = run_cli(
            ["session", "claude-parent", "infer", "--current", "-o", "json"],
            _current_signal_env(seeded, **signals),
            world.parent_path,
        )
        assert unavailable.returncode == 3
        assert unavailable.stdout == b""
        assert json.loads(unavailable.stderr)["error"]["code"] == (
            "claude_parent_unavailable"
        )

    incomplete_shapes = (
        (
            {"CLAUDECODE": "1"},
            ["CLAUDECODE=1"],
            ["CLAUDE_CODE_SESSION_ID"],
        ),
        (
            {"CLAUDE_CODE_SESSION_ID": child},
            ["CLAUDE_CODE_SESSION_ID"],
            ["CLAUDECODE=1"],
        ),
    )
    for signals, present, missing in incomplete_shapes:
        missing_text = ", ".join(missing)
        incomplete = run_cli(
            ["session", "claude-parent", "infer", "--current", "-o", "json"],
            _current_signal_env(seeded, **signals),
            world.parent_path,
        )
        assert incomplete.returncode == 3
        assert incomplete.stdout == b""
        assert json.loads(incomplete.stderr) == {
            "error": {
                "code": "agent_signal_incomplete",
                "message": (
                    f"incomplete agent signal; missing {missing_text}; restore the "
                    "missing value before retrying"
                ),
                "details": {
                    "status": "incomplete",
                    "present": present,
                    "missing": missing,
                },
            }
        }

    ambiguous_shapes = (
        (
            {"CLAUDECODE": "1", "CODEX_THREAD_ID": "codex-parent"},
            ["CLAUDECODE=1", "CODEX_THREAD_ID"],
            ["CLAUDE_CODE_SESSION_ID"],
        ),
        (
            {"CLAUDE_CODE_SESSION_ID": child, "CODEX_THREAD_ID": "codex-parent"},
            ["CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID"],
            ["CLAUDECODE=1"],
        ),
        (
            {
                "CLAUDECODE": "1",
                "CLAUDE_CODE_SESSION_ID": child,
                "CODEX_THREAD_ID": "codex-parent",
            },
            ["CLAUDECODE=1", "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID"],
            [],
        ),
    )
    for signals, present, missing in ambiguous_shapes:
        diagnosis = (
            "Claude and Codex signals are present; incomplete Claude signal is "
            f"missing {', '.join(missing)}"
            if missing
            else "both Claude and Codex signals are present"
        )
        expected_message = f"current agent signals are ambiguous: {diagnosis}"
        ambiguous = run_cli(
            ["session", "claude-parent", "infer", "--current", "-o", "json"],
            _current_signal_env(seeded, **signals),
            world.parent_path,
        )
        assert ambiguous.returncode == 3
        assert ambiguous.stdout == b""
        error = json.loads(ambiguous.stderr)["error"]
        assert error["code"] == "claude_parent_unavailable"
        assert error["message"] == expected_message
        assert error["details"] == {
            "status": "ambiguous",
            "present": present,
            "missing": missing,
        }
        if missing:
            human = run_cli(
                ["session", "claude-parent", "infer", "--current"],
                _current_signal_env(seeded, **signals),
                world.parent_path,
            )
            assert human.returncode == 3
            assert human.stdout == b""
            assert human.stderr == (
                f"claude_parent_unavailable: {expected_message}\n".encode()
            )

    detected = run_cli(
        ["session", "claude-parent", "infer", "--current", "-o", "json"],
        _current_signal_env(seeded, CLAUDECODE="1", CLAUDE_CODE_SESSION_ID=child),
        world.parent_path,
    )
    assert detected.returncode == 0, detected.stderr
    assert detected.stderr == b""
    assert json.loads(detected.stdout)["session_id"] == child


def _inferred_record(
    child_session_id="child", parent_session_id="parent", fingerprints=()
):
    from agent_fork.lineage_inference_store import InferenceRecord

    return InferenceRecord(
        child_session_id,
        parent_session_id,
        "inferred",
        "boundary",
        3,
        1,
        1,
        "2026-01-01T00:00:00Z",
        fingerprints,
        "generation-1",
        "universe-1",
    )


def _fingerprint(path):
    import hashlib

    stat = path.stat()
    raw = (
        f"{path.absolute()}:{stat.st_dev}:{stat.st_ino}:"
        f"{stat.st_size}:{stat.st_mtime_ns}"
    )
    return f"{path}:{hashlib.sha256(raw.encode()).hexdigest()}"


@pytest.mark.matrix("T-CLI-40")
def test_delete_reports_additive_fields_and_removes_freshness(repo_scenario):
    from agent_fork.lineage import LineageClaim, add_lineage
    from agent_fork.lineage_inference_store import (
        add_inference,
        index_freshness_path,
        update_index_freshness,
    )
    from conftest import run_cli

    world = repo_scenario()
    add_inference(_inferred_record("child-a"), env=world.env)
    update_index_freshness("child-a", "universe-1", "generation-1", env=world.env)

    deleted = run_cli(
        [
            "session",
            "claude-parent",
            "delete",
            "--session-id",
            "child-a",
            "--source",
            "inferred",
            "--yes",
            "-o",
            "json",
        ],
        world.env,
        world.parent_path,
    )
    document = json.loads(deleted.stdout)
    assert document["deleted"] is True
    assert document["removed_record"] == "inferred"
    assert document["removed_freshness_entry"] is True
    assert document["retained_planned_record"] is False
    assert document["retained_inferred_record"] is False
    assert document["retained_screen_cache"] is True
    import json as json_module

    freshness_document = json_module.loads(index_freshness_path(world.env).read_text())
    assert "child-a" not in freshness_document["targets"]

    # planned delete with a surviving inferred record retains the freshness entry
    add_lineage(
        LineageClaim.create(
            agent="claude", child_session_id="child-b", parent_session_id="parent"
        ),
        env=world.env,
    )
    add_inference(_inferred_record("child-b"), env=world.env)
    update_index_freshness("child-b", "universe-1", "generation-1", env=world.env)

    deleted_planned = run_cli(
        [
            "session",
            "claude-parent",
            "delete",
            "--session-id",
            "child-b",
            "--source",
            "planned",
            "--yes",
            "-o",
            "json",
        ],
        world.env,
        world.parent_path,
    )
    document = json.loads(deleted_planned.stdout)
    assert document["removed_freshness_entry"] is False
    assert document["retained_inferred_record"] is True
    assert any("retained" in notice for notice in document["notices"])
    freshness_document = json_module.loads(index_freshness_path(world.env).read_text())
    assert "child-b" in freshness_document["targets"]


@pytest.mark.matrix("T-CLI-47")
def test_inferred_delete_reports_surviving_planned_claim(repo_scenario):
    """A child holding BOTH a planned claim and an inferred record, deleted
    via --source inferred, must report retained_planned_record as true, and
    the planned claim must genuinely still be listed afterward."""
    from agent_fork.lineage import LineageClaim, add_lineage
    from agent_fork.lineage_inference_store import add_inference, update_index_freshness
    from conftest import run_cli

    world = repo_scenario()
    add_lineage(
        LineageClaim.create(
            agent="claude",
            child_session_id="child-both",
            parent_session_id="parent",
        ),
        env=world.env,
    )
    add_inference(_inferred_record("child-both"), env=world.env)
    update_index_freshness("child-both", "universe-1", "generation-1", env=world.env)

    deleted = run_cli(
        [
            "session",
            "claude-parent",
            "delete",
            "--session-id",
            "child-both",
            "--source",
            "inferred",
            "--yes",
            "-o",
            "json",
        ],
        world.env,
        world.parent_path,
    )
    document = json.loads(deleted.stdout)
    assert document["deleted"] is True
    assert document["removed_record"] == "inferred"
    assert document["retained_planned_record"] is True

    listed = run_cli(
        ["session", "claude-parent", "list", "-o", "json"], world.env, world.parent_path
    )
    records = json.loads(listed.stdout)
    assert any(
        r["child_session_id"] == "child-both" and r["source"] == "planned"
        for r in records
    )


@pytest.mark.matrix("T-CLI-42")
def test_delete_removes_freshness_before_record_and_tolerates_mid_delete_failure(
    repo_scenario, monkeypatch
):
    import agent_fork.lineage_inference_store as store
    from agent_fork.cli import main
    from agent_fork.lineage_inference_store import (
        add_inference,
        update_index_freshness,
    )
    from agent_fork.session import inspect_session

    world = repo_scenario()
    transcript = world.parent_path / "child-c.jsonl"
    transcript.write_text("{}\n")
    add_inference(
        _inferred_record("child-c", fingerprints=(_fingerprint(transcript),)),
        env=world.env,
    )
    update_index_freshness("child-c", "universe-1", "generation-1", env=world.env)

    call_order = []
    original_remove_index_freshness = store.remove_index_freshness
    original_remove_inference = store.remove_inference

    def recording_remove_index_freshness(*args, **kwargs):
        call_order.append("remove_index_freshness")
        return original_remove_index_freshness(*args, **kwargs)

    def failing_remove_inference(*args, **kwargs):
        call_order.append("remove_inference")
        raise RuntimeError("simulated failure after freshness removal committed")

    monkeypatch.setattr(
        store, "remove_index_freshness", recording_remove_index_freshness
    )
    monkeypatch.setattr(store, "remove_inference", failing_remove_inference)
    monkeypatch.setattr("os.environ", world.env)

    exit_code = main(
        [
            "session",
            "claude-parent",
            "delete",
            "--session-id",
            "child-c",
            "--source",
            "inferred",
            "--yes",
            "-o",
            "json",
        ]
    )
    assert exit_code == 1

    assert call_order == ["remove_index_freshness", "remove_inference"]

    monkeypatch.setattr(
        store, "remove_index_freshness", original_remove_index_freshness
    )
    monkeypatch.setattr(store, "remove_inference", original_remove_inference)
    env = {**world.env, "CLAUDECODE": "1", "CLAUDE_CODE_SESSION_ID": "child-c"}
    result = inspect_session(env, cwd=world.parent_path)
    assert result.parent_inference.status == "freshness_unknown"
    assert result.parent_session is None


@pytest.mark.matrix("T-CLI-50")
def test_delete_tolerates_corrupted_freshness_index(repo_scenario):
    """An advisory, unrelated fault -- a corrupted freshness index -- must
    never block the user from removing their own primary record. The
    primary record is still removed and the command still succeeds; only
    the freshness-removal confirmation degrades to 'could not confirm'."""
    from agent_fork.lineage_inference_store import (
        add_inference,
        find_inference,
        index_freshness_path,
    )
    from conftest import run_cli

    world = repo_scenario()
    add_inference(_inferred_record("child-corrupt"), env=world.env)
    state_path = index_freshness_path(world.env)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(["not", "a", "dict"]))

    completed = run_cli(
        [
            "session",
            "claude-parent",
            "delete",
            "--session-id",
            "child-corrupt",
            "--source",
            "inferred",
            "--yes",
            "-o",
            "json",
        ],
        world.env,
        world.parent_path,
    )
    assert completed.returncode == 0
    document = json.loads(completed.stdout)
    assert document["deleted"] is True
    assert document["removed_freshness_entry"] is False
    assert any("could not confirm" in notice for notice in document["notices"])
    # the primary record is genuinely gone, corrupted freshness index or not
    assert find_inference("child-corrupt", env=world.env) is None


def _patch_limits(monkeypatch, **overrides):
    import agent_fork.claude_lineage_inference as inference_module

    real_corpus_cls = inference_module.ClaudeLineageCorpus

    def limited_corpus(env, limits=None):
        return real_corpus_cls(env, limits or inference_module.Limits(**overrides))

    monkeypatch.setattr(inference_module, "ClaudeLineageCorpus", limited_corpus)


@pytest.mark.matrix("T-CLI-41")
def test_whole_corpus_limit_exits_incomplete_analysis(repo_scenario, monkeypatch):
    import io
    import json as json_module
    from contextlib import redirect_stderr, redirect_stdout

    from agent_fork.cli import main
    from agent_fork.lineage_inference_store import inference_path

    world = repo_scenario()
    env, _parent, child = _seed(world)
    _patch_limits(monkeypatch, max_files=1)

    current_env = {**env, "CLAUDECODE": "1", "CLAUDE_CODE_SESSION_ID": child}
    for invocation, invocation_env in (
        (["--session-id", child], env),
        (["--session-id", child, "--record"], env),
        (["--current"], current_env),
        (["--all"], env),
    ):
        monkeypatch.setattr("os.environ", invocation_env)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            exit_code = main(
                [
                    "session",
                    "claude-parent",
                    "infer",
                    *invocation,
                    "-o",
                    "json",
                ]
            )
        assert exit_code == 3
        assert out.getvalue() == ""
        error_document = json_module.loads(err.getvalue())
        assert error_document["error"]["code"] == "claude_parent_incomplete_analysis"

    assert not inference_path(env).exists()


@pytest.mark.matrix("T-CLI-46")
def test_single_target_per_target_limit_exits_incomplete_analysis(
    repo_scenario, monkeypatch
):
    """Distinct from the whole-corpus case above: max_candidates is raised
    inside infer_one() for one target, not in discover() before any target
    is reached. A single-target (non---all) invocation must still route
    through to the typed claude_parent_incomplete_analysis code rather than
    falling through to the generic not-recordable/unavailable classes."""
    import io
    import json as json_module
    from contextlib import redirect_stderr, redirect_stdout

    from agent_fork.cli import main
    from agent_fork.lineage_inference_store import inference_path

    world = repo_scenario()
    env, _parent, child = _seed(world)
    # child and parent share evidence (per _seed), so a single target lookup
    # for `child` alone finds at least one candidate — max_candidates=0
    # trips inside infer_one(), never inside discover()/the constructor.
    _patch_limits(monkeypatch, max_candidates=0)

    for invocation in (
        ["--session-id", child],
        ["--session-id", child, "--record"],
    ):
        monkeypatch.setattr("os.environ", env)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            exit_code = main(
                ["session", "claude-parent", "infer", *invocation, "-o", "json"]
            )
        assert exit_code == 3
        assert out.getvalue() == ""
        error_document = json_module.loads(err.getvalue())
        assert error_document["error"]["code"] == "claude_parent_incomplete_analysis"
        assert (
            error_document["error"]["details"]["analysis"]["limit"]["name"]
            == "max_candidates"
        )

    assert not inference_path(env).exists()


@pytest.mark.matrix("T-CLI-43")
def test_per_target_limit_under_all_does_not_void_batch(
    repo_scenario, monkeypatch, capsys
):
    import json as json_module

    from agent_fork.cli import main

    world = repo_scenario()
    env, parent, child = _seed(world)

    # an isolated, unrelated transcript: zero shared candidates, never trips
    # a per-target candidate limit
    isolated = "20000000-0000-4000-8000-000000000099"
    root = Path(env["CLAUDE_CONFIG_DIR"])
    (root / "projects" / "-repo" / f"{isolated}.jsonl").write_text(
        json_module.dumps(
            {
                "sessionId": isolated,
                "uuid": "10000000-0000-4000-8000-000000009001",
                "parentUuid": None,
                "type": "user",
                "timestamp": "2026-06-01T00:00:00Z",
            }
        )
        + "\n"
    )

    _patch_limits(monkeypatch, max_candidates=0)
    monkeypatch.setattr("os.environ", env)

    exit_code = main(
        ["session", "claude-parent", "infer", "--all", "--record-all", "-o", "json"]
    )
    assert exit_code == 3
    captured = capsys.readouterr()
    document = json_module.loads(captured.err)
    analysis = document["error"]["details"]["analysis"]
    results = analysis["results"]
    # the bulk spool closed cleanly and rendered a complete, valid summary —
    # a hung or unclosed spool would not have produced parseable JSON here
    assert analysis["summary"]["total"] == len(results)
    child_result = next(r for r in results if r["session_id"] == child)
    assert child_result["relationship"]["status"] == "incomplete"
    assert child_result["limit"]["scope"] == "target"
    assert child_result["recorded"] is False
    isolated_result = next(r for r in results if r["session_id"] == isolated)
    # unaffected by the other target's limit breach: it ran its own
    # inference to completion (no candidates found for a genuinely isolated
    # transcript, so nothing recordable — but critically, no error, no
    # "incomplete" status, and no corpus-level abort)
    assert isolated_result["relationship"]["status"] == "insufficient_evidence"
    assert "error" not in isolated_result
    assert isolated_result["recorded"] is False
    from agent_fork.lineage_inference_store import find_inference

    assert find_inference(child, env=env) is None


@pytest.mark.matrix("T-CLI-44")
def test_max_seconds_under_all_reports_corpus_scope_and_exits_cleanly(
    repo_scenario, monkeypatch, capsys
):
    import json as json_module

    from agent_fork.cli import main

    world = repo_scenario()
    env, parent, child = _seed(world)

    isolated = "20000000-0000-4000-8000-000000000098"
    root = Path(env["CLAUDE_CONFIG_DIR"])
    (root / "projects" / "-repo" / f"{isolated}.jsonl").write_text(
        json_module.dumps(
            {
                "sessionId": isolated,
                "uuid": "10000000-0000-4000-8000-000000009002",
                "parentUuid": None,
                "type": "user",
                "timestamp": "2026-06-01T00:00:00Z",
            }
        )
        + "\n"
    )

    # an already-expired shared deadline: every target trips it immediately,
    # proving this is a corpus-wide clock, not an independent per-target one
    _patch_limits(monkeypatch, max_seconds=-1)
    monkeypatch.setattr("os.environ", env)

    exit_code = main(
        ["session", "claude-parent", "infer", "--all", "--record-all", "-o", "json"]
    )
    assert exit_code == 3
    captured = capsys.readouterr()
    document = json_module.loads(captured.err)
    analysis = document["error"]["details"]["analysis"]
    results = analysis["results"]
    assert analysis["summary"]["total"] == len(results)
    assert len(results) >= 2
    for result in results:
        assert result["relationship"]["status"] == "incomplete"
        assert result["limit"]["name"] == "max_seconds"
        assert result["limit"]["scope"] == "corpus"
        assert result["recorded"] is False


@pytest.mark.matrix("T-CLI-45")
def test_freshness_write_failure_notice_composed_at_cli_layer(
    repo_scenario, monkeypatch
):
    import io
    import json as json_module
    from contextlib import redirect_stdout

    import agent_fork.lineage_inference_store as store
    from agent_fork.cli import main

    world = repo_scenario()
    env, _parent, child = _seed(world)

    def fail_update(*args, **kwargs):
        raise OSError("injected freshness write failure")

    monkeypatch.setattr(store, "update_index_freshness", fail_update)
    monkeypatch.setattr("os.environ", env)

    out = io.StringIO()
    with redirect_stdout(out):
        code = main(
            [
                "session",
                "claude-parent",
                "infer",
                "--session-id",
                child,
                "--record",
                "-o",
                "json",
            ]
        )
    assert code == 0
    document = json_module.loads(out.getvalue())
    assert document["recorded"] is True
    assert document["work"]["freshness_write_failures"] == 1
    assert any("freshness_unknown" in notice for notice in document["notices"])

    out2 = io.StringIO()
    with redirect_stdout(out2):
        code2 = main(
            [
                "session",
                "claude-parent",
                "infer",
                "--session-id",
                child,
                "-o",
                "json",
            ]
        )
    assert code2 == 0
    preview_document = json_module.loads(out2.getvalue())
    assert preview_document["recorded"] is False
    assert preview_document["work"]["freshness_write_failures"] == 1
    assert preview_document["notices"] == []


@pytest.mark.matrix("T-CLI-48")
def test_freshness_write_failure_notice_is_per_target_not_batch_wide(
    repo_scenario, monkeypatch, capsys
):
    """A single Work object is shared across every target in one --all run.
    The freshness-write-failure notice must reflect whether THIS target's
    write failed, not whether the corpus-wide counter is merely nonzero --
    otherwise one early target's failure produces a false-positive notice
    on every later, genuinely-successful target."""
    import json as json_module

    import agent_fork.lineage_inference_store as store
    from agent_fork.cli import main

    world = repo_scenario()
    root = world.parent_path / ".claude"
    project = root / "projects" / "-repo"
    project.mkdir(parents=True)

    def _write_pair(prefix, parent, child):
        uuids = [f"{prefix}-0000-4000-8000-{i:012d}" for i in range(1, 5)]
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
                "".join(json_module.dumps(row) + "\n" for row in rows)
            )

    parent_a = "2a000000-0000-4000-8000-000000000001"
    child_a = "2a000000-0000-4000-8000-000000000002"
    parent_b = "2b000000-0000-4000-8000-000000000001"
    child_b = "2b000000-0000-4000-8000-000000000002"
    _write_pair("1a000000", parent_a, child_a)
    _write_pair("1b000000", parent_b, child_b)
    (root / "history.jsonl").write_text(
        "".join(
            json_module.dumps({"sessionId": sid, "timestamp": ts}) + "\n"
            for sid, ts in (
                (parent_a, 1000),
                (child_a, 2000),
                (parent_b, 1000),
                (child_b, 2000),
            )
        )
    )
    env = {
        **world.env,
        "CLAUDE_CONFIG_DIR": str(root),
        "XDG_CACHE_HOME": str(world.parent_path / "cache"),
    }

    real_update = store.update_index_freshness

    def flaky_update(child_session_id, *args, **kwargs):
        # fail only for child_a's own write, regardless of processing
        # order across the four targets (two parents, two children) --
        # only the children are ever recordable here, so pinning the
        # failure to one specific recordable child keeps this test
        # independent of corpus discovery/iteration order
        if child_session_id == child_a:
            raise OSError("injected freshness write failure for child_a")
        return real_update(child_session_id, *args, **kwargs)

    monkeypatch.setattr(store, "update_index_freshness", flaky_update)
    monkeypatch.setattr("os.environ", env)

    code = main(
        ["session", "claude-parent", "infer", "--all", "--record-all", "-o", "json"]
    )
    # the two parent transcripts are never recordable (their only candidate
    # is their own younger child, so neither has an eligible older
    # candidate) -- that alone makes this batch a partial-record failure,
    # independent of anything this test is actually proving about the
    # children's freshness-write notices
    assert code == 3
    captured = capsys.readouterr()
    document = json_module.loads(captured.err)
    results = document["error"]["details"]["analysis"]["results"]
    recorded_children = [r for r in results if r["session_id"] in (child_a, child_b)]
    assert len(recorded_children) == 2
    assert all(r["recorded"] is True for r in recorded_children)

    with_notice = [
        r
        for r in recorded_children
        if any("freshness_unknown" in n for n in r["notices"])
    ]
    without_notice = [
        r
        for r in recorded_children
        if not any("freshness_unknown" in n for n in r["notices"])
    ]
    # exactly one target's write genuinely failed -- exactly one target's
    # document may carry the notice, never both (the shared-counter bug
    # would put it on both once the first target's write failed)
    assert len(with_notice) == 1
    assert len(without_notice) == 1
