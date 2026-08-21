"""G-CLN command consent and dry-run rows."""

import json
import subprocess
from pathlib import Path

import pytest


def _forked(repo_scenario, name, *, with_remote=True):
    from agent_fork.agents import AgentContext
    from agent_fork.pipeline import ForkRequest, fork
    from conftest import origin

    world = repo_scenario("plain@main", remote=origin() if with_remote else None)
    result = fork(
        ForkRequest(
            parent=world.parent_path,
            destination=world.parent_path.parent / f"child-{name}",
            name=name,
            branch=f"fork/{name}",
            agent=AgentContext("claude", "11111111-1111-1111-1111-111111111111"),
            agent_executable="/fake/claude",
            agent_version_output="Claude Code 2.1.220",
            git_version_output="git version 2.43.0",
            child_session_id="33333333-3333-3333-3333-333333333333",
        ),
        env=world.env,
    )
    return world, result


def _commit_unpushed(world, result, subject="wip: unpushed cleanup work"):
    path = result.creation.path / "commit.txt"
    path.write_text("unpushed\n")
    subprocess.run(
        ["git", "-C", str(result.creation.path), "add", "commit.txt"],
        env=world.env,
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(result.creation.path), "commit", "-m", subject],
        env=world.env,
        check=True,
        capture_output=True,
    )
    return (
        subprocess.run(
            ["git", "-C", str(result.creation.path), "rev-parse", "--short", "HEAD"],
            env=world.env,
            check=True,
            capture_output=True,
        )
        .stdout.decode()
        .strip()
    )


@pytest.mark.matrix("T-CLN-09")
def test_yes_flag_bypasses_consent_prompt(repo_scenario):
    from conftest import run_cli

    world, result = _forked(repo_scenario, "yes")
    completed = run_cli(["cleanup", "yes", "--yes"], world.env, world.parent_path)
    assert completed.returncode == 0
    assert b"[y/N]" not in completed.stderr
    assert not result.creation.path.exists()


@pytest.mark.matrix("T-CLN-10")
def test_no_input_without_yes_fails_exit_2(repo_scenario):
    from conftest import run_cli

    world, result = _forked(repo_scenario, "no-input")
    completed = run_cli(
        ["cleanup", "no-input", "--no-input"], world.env, world.parent_path
    )
    assert completed.returncode == 2
    assert b"requires --yes" in completed.stderr
    assert result.creation.path.exists()


@pytest.mark.matrix("T-CLN-11")
def test_tty_consent_prompt_names_exact_removal_targets(repo_scenario):
    from conftest import pty_run

    world, result = _forked(repo_scenario, "prompt")
    completed = pty_run(["cleanup", "prompt"], world.env, 2)
    assert completed.returncode == 2
    prompt = completed.tty.decode()
    assert f"remove worktree {result.creation.path}" in prompt
    assert "delete fork/prompt" in prompt
    assert "registry: prompt" in prompt
    assert result.creation.path.exists()


@pytest.mark.matrix("T-CLN-13")
def test_dry_run_prints_removal_plan_without_mutating(repo_scenario):
    from agent_fork.registry import find_owned
    from conftest import run_cli

    world, result = _forked(repo_scenario, "dry")
    completed = run_cli(["cleanup", "dry", "--dry-run"], world.env, world.parent_path)
    assert completed.returncode == 0 and completed.stderr == b""
    assert b"would remove worktree" in completed.stdout
    assert str(result.creation.path).encode() in completed.stdout
    assert result.creation.path.exists()
    assert find_owned("dry", env=world.env) is not None


@pytest.mark.matrix("T-CLN-15")
def test_force_does_not_substitute_for_consent(repo_scenario):
    from conftest import run_cli

    world, result = _forked(repo_scenario, "force-consent")
    completed = run_cli(
        ["cleanup", "force-consent", "--force", "--no-input"],
        world.env,
        world.parent_path,
    )
    assert completed.returncode == 2
    assert b"requires --yes" in completed.stderr
    assert result.creation.path.exists()


@pytest.mark.matrix("T-CLN-16")
def test_force_dry_run_reports_dirty_paths_without_mutating(repo_scenario):
    from conftest import run_cli

    world, result = _forked(repo_scenario, "force-dry-dirty")
    (result.creation.path / "tracked.txt").write_text("modified\n")
    (result.creation.path / "important_untracked.txt").write_text("untracked\n")

    completed = run_cli(
        ["cleanup", "force-dry-dirty", "--force", "--dry-run"],
        world.env,
        world.parent_path,
    )

    assert completed.returncode == 0
    assert b"would remove worktree" in completed.stdout
    assert b"nothing was removed" in completed.stdout
    assert b"WOULD DESTROY 2 uncommitted changes" in completed.stderr
    assert b" M tracked.txt" in completed.stderr
    assert b"?? important_untracked.txt" in completed.stderr
    assert result.creation.path.exists()


@pytest.mark.matrix("T-CLN-17")
def test_dirty_refusal_reports_modified_and_untracked_paths(repo_scenario):
    from conftest import run_cli

    world, result = _forked(repo_scenario, "dirty-details")
    (result.creation.path / "tracked.txt").write_text("modified\n")
    (result.creation.path / "important_untracked.txt").write_text("untracked\n")

    completed = run_cli(
        ["cleanup", "dirty-details", "--dry-run"], world.env, world.parent_path
    )

    assert completed.returncode == 5 and completed.stdout == b""
    assert b"cleanup_dirty_worktree: refusing to remove" in completed.stderr
    assert b"2 uncommitted changes" in completed.stderr
    assert b" M tracked.txt" in completed.stderr
    assert b"?? important_untracked.txt" in completed.stderr
    assert b"Override with --allow-dirty" in completed.stderr
    assert result.creation.path.exists()


@pytest.mark.matrix("T-CLN-18")
def test_unpushed_refusal_reports_commit_sha_and_subject(repo_scenario):
    from conftest import run_cli

    world, result = _forked(repo_scenario, "unpushed-details")
    subject = "wip: preserve parser experiment"
    short_sha = _commit_unpushed(world, result, subject)

    completed = run_cli(
        ["cleanup", "unpushed-details", "--dry-run"],
        world.env,
        world.parent_path,
    )

    assert completed.returncode == 5 and completed.stdout == b""
    assert b"cleanup_unpushed_commits: refusing to remove fork/unpushed-details" in (
        completed.stderr
    )
    assert b"1 commit not reachable from any remote" in completed.stderr
    assert short_sha.encode() in completed.stderr
    assert subject.encode() in completed.stderr
    assert b"Override with --allow-unpushed" in completed.stderr
    assert b"or push first" in completed.stderr
    assert b"No Git remote is configured" not in completed.stderr
    assert result.creation.path.exists()


@pytest.mark.matrix("T-CLN-24")
def test_unpushed_refusal_explains_remote_setup_when_none_configured(
    repo_scenario,
):
    from conftest import run_cli

    world, result = _forked(repo_scenario, "no-remote", with_remote=False)

    human = run_cli(["cleanup", "no-remote", "--dry-run"], world.env, world.parent_path)
    machine = run_cli(
        ["cleanup", "no-remote", "--dry-run", "--json"],
        world.env,
        world.parent_path,
    )

    assert human.returncode == 5 and human.stdout == b""
    assert b"cleanup_unpushed_commits" in human.stderr
    assert b"No Git remote is configured." in human.stderr
    assert b"Configure one before pushing these commits" in human.stderr
    assert b"git remote add REMOTE-NAME REMOTE-URL" in human.stderr
    assert b"or push first" not in human.stderr

    assert machine.returncode == 5 and machine.stdout == b""
    error = json.loads(machine.stderr)["error"]
    assert set(error) == {"code", "details", "message"}
    assert error["code"] == "cleanup_unpushed_commits"
    assert error["message"] == "refusing to remove fork/no-remote"
    assert set(error["details"]) == {
        "dirty",
        "dirty_count",
        "dirty_truncated",
        "unpushed",
        "unpushed_count",
        "unpushed_truncated",
    }
    assert error["details"]["dirty"] == []
    assert error["details"]["dirty_count"] == 0
    assert error["details"]["unpushed_count"] == 1
    assert len(error["details"]["unpushed"]) == 1
    assert result.creation.path.exists()


@pytest.mark.matrix("T-CLN-19")
def test_dirty_enumeration_is_bounded_in_human_and_json_errors(repo_scenario):
    from conftest import run_cli

    world, result = _forked(repo_scenario, "bounded-dirty")
    (result.creation.path / "tracked.txt").write_text("modified\n")
    for index in range(11):
        (result.creation.path / f"untracked-{index:02}.txt").write_text("untracked\n")

    human = run_cli(
        ["cleanup", "bounded-dirty", "--dry-run"], world.env, world.parent_path
    )
    machine = run_cli(
        ["cleanup", "bounded-dirty", "--dry-run", "--json"],
        world.env,
        world.parent_path,
    )

    assert human.returncode == 5
    assert b" M tracked.txt" in human.stderr
    assert b"untracked-08.txt" in human.stderr
    assert b"untracked-09.txt" not in human.stderr
    assert "… and 2 more".encode() in human.stderr
    document = json.loads(machine.stderr)
    details = document["error"]["details"]
    assert details["dirty_count"] == 12
    assert details["dirty_truncated"] is True
    assert len(details["dirty"]) == 10
    assert details["dirty"][0]["status"] == " M"
    assert all(item["status"] == "??" for item in details["dirty"][1:])
    assert result.creation.path.exists()


@pytest.mark.matrix("T-CLN-20")
def test_granular_overrides_are_independent(repo_scenario):
    from conftest import run_cli

    dirty_world, dirty_result = _forked(repo_scenario, "allow-dirty")
    (dirty_result.creation.path / "dirty.txt").write_text("dirty\n")
    dirty_allowed = run_cli(
        ["cleanup", "allow-dirty", "--allow-dirty", "--yes"],
        dirty_world.env,
        dirty_world.parent_path,
    )
    assert dirty_allowed.returncode == 0
    assert not dirty_result.creation.path.exists()

    both_world, both_result = _forked(repo_scenario, "dirty-and-unpushed")
    _commit_unpushed(both_world, both_result)
    (both_result.creation.path / "dirty.txt").write_text("dirty\n")
    still_refused = run_cli(
        ["cleanup", "dirty-and-unpushed", "--allow-dirty", "--yes"],
        both_world.env,
        both_world.parent_path,
    )
    assert still_refused.returncode == 5
    assert b"cleanup_unpushed_commits" in still_refused.stderr
    assert both_result.creation.path.exists()

    unpushed_world, unpushed_result = _forked(repo_scenario, "allow-unpushed")
    _commit_unpushed(unpushed_world, unpushed_result)
    unpushed_allowed = run_cli(
        ["cleanup", "allow-unpushed", "--allow-unpushed", "--yes"],
        unpushed_world.env,
        unpushed_world.parent_path,
    )
    assert unpushed_allowed.returncode == 0
    assert not unpushed_result.creation.path.exists()


@pytest.mark.matrix("T-CLN-21")
def test_json_error_and_forced_preview_carry_the_same_details(repo_scenario):
    from conftest import run_cli

    world, result = _forked(repo_scenario, "json-details")
    short_sha = _commit_unpushed(world, result, "wip: json details")
    (result.creation.path / "tracked.txt").write_text("modified\n")
    (result.creation.path / "important_untracked.txt").write_text("untracked\n")

    refused = run_cli(
        ["cleanup", "json-details", "--dry-run", "--json"],
        world.env,
        world.parent_path,
    )
    preview = run_cli(
        ["cleanup", "json-details", "--force", "--dry-run", "--json"],
        world.env,
        world.parent_path,
    )

    assert refused.returncode == 5 and refused.stdout == b""
    error = json.loads(refused.stderr)["error"]
    assert error["code"] == "cleanup_dirty_worktree"
    assert error["message"] == f"refusing to remove {result.creation.path}"
    assert preview.returncode == 0 and preview.stderr == b""
    result_document = json.loads(preview.stdout)
    assert result_document["details"] == error["details"]
    assert result_document["details"]["dirty"] == [
        {"path": "tracked.txt", "status": " M"},
        {"path": "important_untracked.txt", "status": "??"},
    ]
    assert result_document["details"]["unpushed"] == [
        {"sha": short_sha, "subject": "wip: json details"}
    ]
    assert result_document["removed"] is False
    assert result.creation.path.exists()


@pytest.mark.matrix("T-CLN-22")
def test_granular_overrides_do_not_override_cwd_guard(repo_scenario):
    from conftest import run_cli

    for index, flag in enumerate(("--allow-dirty", "--allow-unpushed")):
        name = f"cwd-granular-{index}"
        world, result = _forked(repo_scenario, name)
        completed = run_cli(
            ["cleanup", name, flag, "--dry-run"], world.env, result.creation.path
        )
        assert completed.returncode == 5
        assert b"cleanup_target_is_cwd" in completed.stderr
        assert result.creation.path.exists()


@pytest.mark.matrix("T-CLN-23")
def test_human_cleanup_details_escape_terminal_controls(repo_scenario):
    from agent_fork.cleanup import (
        CleanupDetails,
        CleanupPlan,
        DirtyPath,
        UnpushedCommit,
        _refusal_message,
    )
    from agent_fork.models import RegistryEntry
    from conftest import run_cli

    world, result = _forked(repo_scenario, "terminal-safe-details")
    dirty_name = "literal\\path-\x1b[31m.txt"
    subject = "wip: \x1b[32mgreen\x1b[0m"
    (result.creation.path / dirty_name).write_text("untracked\n")
    _commit_unpushed(world, result, subject)

    human = run_cli(
        ["cleanup", "terminal-safe-details", "--dry-run"],
        world.env,
        world.parent_path,
    )
    machine = run_cli(
        ["cleanup", "terminal-safe-details", "--dry-run", "--json"],
        world.env,
        world.parent_path,
    )

    assert human.returncode == 5
    assert b"\x1b" not in human.stderr
    assert b"literal\\\\path-\\x1b[31m.txt" in human.stderr
    assert b"wip: \\x1b[32mgreen\\x1b[0m" in human.stderr

    details = json.loads(machine.stderr)["error"]["details"]
    assert details["dirty"] == [{"path": dirty_name, "status": "??"}]
    assert details["unpushed"][0]["subject"] == subject

    unsafe = "value-\x1b[31m"
    unsafe_worktree = Path(f"/tmp/{unsafe}")
    entry = RegistryEntry.create(
        name=unsafe,
        branch=unsafe,
        worktree=unsafe_worktree,
        agent=None,
    )
    plan = CleanupPlan(entry, unsafe_worktree, unsafe, Path("/tmp/repo"), True)
    rendered_details = CleanupDetails(
        dirty=(DirtyPath("??", unsafe),),
        dirty_count=1,
        unpushed=(UnpushedCommit("abc1234", unsafe),),
        unpushed_count=1,
    )

    assert "\x1b" not in plan.render()
    assert "\\x1b" in plan.render()
    assert "\x1b" not in rendered_details.render_preview(unsafe)
    assert "\\x1b" in rendered_details.render_preview(unsafe)
    raw_message, human_message = _refusal_message(
        plan, rendered_details, code="cleanup_dirty_worktree"
    )
    assert "\x1b" in raw_message
    assert "\x1b" not in human_message
    assert "\\x1b" in human_message


@pytest.mark.matrix("T-CLN-25")
def test_cleanup_discloses_retained_lineage_metadata(repo_scenario):
    from agent_fork.lineage_inference_store import (
        InferenceRecord,
        add_inference,
        update_index_freshness,
    )
    from conftest import run_cli

    world, result = _forked(repo_scenario, "disclose")
    child = "33333333-3333-3333-3333-333333333333"
    add_inference(
        InferenceRecord(
            child,
            "parent",
            "inferred",
            "boundary",
            3,
            1,
            1,
            "2026-01-01T00:00:00Z",
            (),
            "generation-1",
            "universe-1",
        ),
        env=world.env,
    )
    update_index_freshness(child, "universe-1", "generation-1", env=world.env)

    dry = run_cli(
        ["cleanup", "disclose", "--dry-run", "-o", "json"], world.env, world.parent_path
    )
    dry_document = json.loads(dry.stdout)
    assert child in dry_document["retained_metadata"]["lineage_claims"]
    assert child in dry_document["retained_metadata"]["inferred_records"]
    assert child in dry_document["retained_metadata"]["freshness_entries"]
    assert dry_document["retained_metadata"]["removal_commands"]
    commands = {
        entry["source"]: entry["command"]
        for entry in dry_document["retained_metadata"]["removal_commands"]
        if entry["session_id"] == child
    }
    assert commands == {
        "planned": (
            f"agent-fork session claude-parent delete --session-id {child} "
            "--source planned --yes"
        ),
        "inferred": (
            f"agent-fork session claude-parent delete --session-id {child} "
            "--source inferred --yes"
        ),
    }
    from agent_fork.lineage import lineage_path
    from agent_fork.lineage_inference_store import (
        index_freshness_path as _idx_path,
    )
    from agent_fork.lineage_inference_store import inference_path

    dry_human = run_cli(
        ["cleanup", "disclose", "--dry-run"], world.env, world.parent_path
    ).stdout.decode()
    assert str(lineage_path(world.env)) in dry_human
    assert str(inference_path(world.env)) in dry_human
    assert str(_idx_path(world.env)) in dry_human
    assert result.creation.path.exists()

    real = run_cli(
        ["cleanup", "disclose", "--yes", "-o", "json"], world.env, world.parent_path
    )
    real_document = json.loads(real.stdout)
    assert child in real_document["retained_metadata"]["lineage_claims"]
    assert not result.creation.path.exists()

    from agent_fork.lineage import read_lineage
    from agent_fork.lineage_inference_store import find_inference, index_freshness_path

    assert any(claim.child_session_id == child for claim in read_lineage(env=world.env))
    assert find_inference(child, env=world.env) is not None
    assert index_freshness_path(world.env).exists()


@pytest.mark.matrix("T-CLN-26")
def test_cleanup_disclosure_handles_no_match_and_read_failure(
    repo_scenario, monkeypatch
):
    from agent_fork.lineage import remove_lineage
    from conftest import run_cli

    world, result = _forked(repo_scenario, "no-claim")
    remove_lineage("claude", "33333333-3333-3333-3333-333333333333", env=world.env)

    completed = run_cli(
        ["cleanup", "no-claim", "--yes", "-o", "json"], world.env, world.parent_path
    )
    document = json.loads(completed.stdout)
    assert document["retained_metadata"] == {
        "lineage_claims": [],
        "inferred_records": [],
        "freshness_entries": [],
        "removal_commands": [],
    }

    # a store-read failure degrades to the neutral notice + empty metadata,
    # without failing the cleanup itself
    import io
    from contextlib import redirect_stdout

    from agent_fork.cli import main
    from agent_fork.pipeline import ForkRequest, fork

    other_world = repo_scenario("plain@main")
    fork_result = fork(
        ForkRequest(
            parent=other_world.parent_path,
            destination=other_world.parent_path.parent / "child-failure",
            name="failure",
            branch="fork/failure",
            agent=None,
            agent_executable=None,
            agent_version_output=None,
            git_version_output="git version 2.43.0",
            child_session_id=None,
        ),
        env=other_world.env,
    )

    def failing_read_lineage(*args, **kwargs):
        raise ValueError("injected store read failure")

    import agent_fork.lineage as lineage_module

    monkeypatch.setattr(lineage_module, "read_lineage", failing_read_lineage)
    monkeypatch.setattr("os.environ", other_world.env)

    out = io.StringIO()
    with redirect_stdout(out):
        exit_code = main(["cleanup", "failure", "--force", "--yes", "-o", "json"])
    assert exit_code == 0
    failure_document = json.loads(out.getvalue())
    assert failure_document["retained_metadata"] == {
        "lineage_claims": [],
        "inferred_records": [],
        "freshness_entries": [],
        "removal_commands": [],
    }
    assert any("could not read" in notice for notice in failure_document["notices"])
    assert not fork_result.creation.path.exists()


@pytest.mark.matrix("T-CLN-27")
def test_cleanup_retained_metadata_reaches_json_output(repo_scenario):
    from conftest import run_cli

    world, result = _forked(repo_scenario, "wiring")
    completed = run_cli(
        ["cleanup", "wiring", "--dry-run", "-o", "json"], world.env, world.parent_path
    )
    document = json.loads(completed.stdout)
    assert "retained_metadata" in document
    assert "notices" in document


@pytest.mark.matrix("T-CLN-28")
def test_cleanup_removal_commands_are_source_qualified_and_escaped(repo_scenario):
    from agent_fork.lineage_inference_store import (
        InferenceRecord,
        add_inference,
        update_index_freshness,
    )
    from conftest import run_cli

    world, result = _forked(repo_scenario, "qualified")
    child = "33333333-3333-3333-3333-333333333333"
    add_inference(
        InferenceRecord(
            child,
            "parent",
            "inferred",
            "boundary",
            3,
            1,
            1,
            "2026-01-01T00:00:00Z",
            (),
            "generation-1",
            "universe-1",
        ),
        env=world.env,
    )
    update_index_freshness(child, "universe-1", "generation-1", env=world.env)

    completed = run_cli(
        ["cleanup", "qualified", "--dry-run", "-o", "json"],
        world.env,
        world.parent_path,
    )
    document = json.loads(completed.stdout)
    commands = document["retained_metadata"]["removal_commands"]
    sources = {entry["source"] for entry in commands if entry["session_id"] == child}
    assert sources == {"planned", "inferred"}
    for entry in commands:
        assert "--source" in entry["command"]

    human = run_cli(["cleanup", "qualified", "--dry-run"], world.env, world.parent_path)
    assert b"\x1b" not in human.stdout


@pytest.mark.matrix("T-CLN-29")
def test_cleanup_disclosure_escapes_notices_but_not_json(repo_scenario):
    """A genuinely load-bearing escaping proof: a control character embedded
    in a stored session ID must reach JSON output raw (so a script can paste
    it back verbatim) but must never appear as a raw byte in human notices."""
    from agent_fork.lineage import LineageClaim, add_lineage
    from conftest import run_cli

    world, result = _forked(repo_scenario, "control-char")
    hostile_child = "hostile\x1bchild"
    add_lineage(
        LineageClaim.create(
            agent="claude",
            child_session_id=hostile_child,
            parent_session_id="parent",
            worktree=result.creation.path,
        ),
        env=world.env,
    )

    machine = run_cli(
        ["cleanup", "control-char", "--dry-run", "-o", "json"],
        world.env,
        world.parent_path,
    )
    document = json.loads(machine.stdout)
    assert hostile_child in document["retained_metadata"]["lineage_claims"]
    commands = document["retained_metadata"]["removal_commands"]
    assert any(entry["session_id"] == hostile_child for entry in commands)

    human = run_cli(
        ["cleanup", "control-char", "--dry-run"], world.env, world.parent_path
    )
    assert b"\x1b" not in human.stdout


@pytest.mark.matrix("T-CLN-32")
def test_cleanup_removal_command_quotes_hostile_session_id(repo_scenario):
    """A hostile session ID (embedded newline/shell metacharacters) must not
    let the generated removal command break out of its argument position —
    it is meant to be copy-pasted and run verbatim."""
    import shlex

    from agent_fork.lineage import LineageClaim, add_lineage
    from conftest import run_cli

    world, result = _forked(repo_scenario, "hostile-cmd")
    hostile_child = "evil\necho PWNED; rm -rf /tmp/x"
    add_lineage(
        LineageClaim.create(
            agent="claude",
            child_session_id=hostile_child,
            parent_session_id="parent",
            worktree=result.creation.path,
        ),
        env=world.env,
    )

    completed = run_cli(
        ["cleanup", "hostile-cmd", "--dry-run", "-o", "json"],
        world.env,
        world.parent_path,
    )
    document = json.loads(completed.stdout)
    commands = document["retained_metadata"]["removal_commands"]
    matching = [entry for entry in commands if entry["session_id"] == hostile_child]
    assert matching
    for entry in matching:
        # the raw session ID is preserved in the field...
        assert entry["session_id"] == hostile_child
        # ...but the assembled command safely quotes it as one shell
        # argument: parsing the command back with shlex must recover the
        # hostile string as a single token, not split it into separate
        # words/commands an unsuspecting user's shell would execute.
        parsed = shlex.split(entry["command"])
        assert hostile_child in parsed
        assert parsed.count("--session-id") == 1
        session_id_index = parsed.index("--session-id")
        assert parsed[session_id_index + 1] == hostile_child


@pytest.mark.matrix("T-CLN-30")
def test_cleanup_disclosure_reports_legacy_only_freshness_location(repo_scenario):
    """A freshness entry that lives only at the legacy XDG_CACHE_HOME path
    (not yet migrated) must be disclosed as such, not claimed to live at the
    new XDG_STATE_HOME path it was never written to."""
    from agent_fork.lineage_inference_store import (
        InferenceRecord,
        _legacy_index_freshness_path,
        add_inference,
        index_freshness_path,
    )
    from conftest import run_cli

    world, result = _forked(repo_scenario, "legacy-loc")
    child = "33333333-3333-3333-3333-333333333333"
    add_inference(
        InferenceRecord(
            child,
            "parent",
            "inferred",
            "boundary",
            3,
            1,
            1,
            "2026-01-01T00:00:00Z",
            (),
            "generation-1",
            "universe-1",
        ),
        env=world.env,
    )
    # write directly to the legacy location only; never call
    # update_index_freshness, which would migrate it to the state path
    legacy_path = _legacy_index_freshness_path(world.env)
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_text(
        json.dumps(
            {
                "version": 1,
                "targets": {
                    child: {
                        "candidate_universe_digest": "universe-1",
                        "analysis_index_generation": "generation-1",
                    }
                },
            }
        )
    )
    assert not index_freshness_path(world.env).exists()

    completed = run_cli(
        ["cleanup", "legacy-loc", "--dry-run"], world.env, world.parent_path
    )
    human_text = completed.stdout.decode()
    assert "not yet migrated" in human_text
    assert str(legacy_path) in human_text
    assert str(index_freshness_path(world.env)) not in human_text


@pytest.mark.matrix("T-CLN-31")
def test_cleanup_disclosure_degrades_neutrally_on_invalid_freshness_store(
    repo_scenario,
):
    """A structurally invalid freshness-index file (not the JSON shape this
    store expects) must degrade only the freshness half of disclosure to the
    neutral empty shape plus its own notice, never propagate a crash, and
    never suppress an unrelated, independently-readable lineage claim."""
    from agent_fork.lineage_inference_store import index_freshness_path
    from conftest import run_cli

    world, result = _forked(repo_scenario, "invalid-store")
    state_path = index_freshness_path(world.env)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(["not", "a", "dict"]))

    completed = run_cli(
        ["cleanup", "invalid-store", "--dry-run", "-o", "json"],
        world.env,
        world.parent_path,
    )
    document = json.loads(completed.stdout)
    metadata = document["retained_metadata"]
    # the fork's own baseline lineage claim is independently readable and
    # must still be disclosed; only freshness is a fault here
    assert metadata["lineage_claims"] == ["33333333-3333-3333-3333-333333333333"]
    assert metadata["inferred_records"] == []
    assert metadata["freshness_entries"] == []
    assert any("could not read" in notice for notice in document["notices"])
    assert result.creation.path.exists()  # dry-run: nothing actually removed


@pytest.mark.matrix("T-CLN-33")
def test_cleanup_freshness_read_failure_does_not_suppress_lineage_disclosure(
    repo_scenario,
):
    """An unrelated failure reading the freshness index must not swallow the
    disclosure of a real, independently-readable retained lineage claim."""
    from agent_fork.lineage import LineageClaim, add_lineage
    from agent_fork.lineage_inference_store import index_freshness_path
    from conftest import run_cli

    world, result = _forked(repo_scenario, "partial-invalid")
    child = "44444444-4444-4444-4444-444444444444"
    add_lineage(
        LineageClaim.create(
            agent="claude",
            child_session_id=child,
            parent_session_id="parent",
            worktree=result.creation.path,
        ),
        env=world.env,
    )
    state_path = index_freshness_path(world.env)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(["not", "a", "dict"]))

    completed = run_cli(
        ["cleanup", "partial-invalid", "--dry-run", "-o", "json"],
        world.env,
        world.parent_path,
    )
    document = json.loads(completed.stdout)
    metadata = document["retained_metadata"]
    # the fork itself registers its own baseline claim; ours must appear
    # alongside it, not be crowded out by it or by the freshness fault
    assert child in metadata["lineage_claims"]
    assert metadata["freshness_entries"] == []
    assert any(
        entry["session_id"] == child and entry["source"] == "planned"
        for entry in metadata["removal_commands"]
    )
    assert any("could not read" in notice for notice in document["notices"])
