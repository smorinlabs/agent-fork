"""Unit coverage for real-agent and PTY test-harness compatibility helpers."""

import os
import subprocess
import sys

import pytest
from tests.live import test_exp
from tests.live.test_exp import _claude_result_record


def test_claude_result_record_accepts_legacy_single_object():
    payload = {"type": "result", "session_id": "legacy", "result": "ready"}

    assert _claude_result_record(payload) is payload


def test_claude_result_record_selects_result_from_event_array():
    result = {"type": "result", "session_id": "current", "result": "ready"}
    payload = [{"type": "system"}, {"type": "assistant"}, result]

    assert _claude_result_record(payload) is result


@pytest.mark.parametrize("payload", [[], [{"type": "system"}]])
def test_claude_result_record_requires_one_result_in_event_array(payload):
    with pytest.raises(ValueError, match="contains 0 result records; expected 1"):
        _claude_result_record(payload)


def test_real_agent_command_failure_reports_command_stdout_and_stderr(
    monkeypatch, tmp_path
):
    events = tmp_path / "events.jsonl"

    def fail(args, **kwargs):
        kwargs["stdout"].write('{"type":"turn.failed"}\n')
        return subprocess.CompletedProcess(
            args,
            1,
            stdout=None,
            stderr="configured model requires a newer Codex CLI\n",
        )

    monkeypatch.setattr(test_exp.subprocess, "run", fail)

    with pytest.raises(RuntimeError) as raised:
        test_exp._run(
            ["/opt/codex", "exec", "--json", "prompt"],
            tmp_path,
            stdout=events,
        )

    message = str(raised.value)
    assert "real-agent command failed with exit 1" in message
    assert "/opt/codex exec --json prompt" in message
    assert '{"type":"turn.failed"}' in message
    assert "configured model requires a newer Codex CLI" in message


def test_real_agent_command_timeout_reports_partial_output(monkeypatch, tmp_path):
    events = tmp_path / "events.jsonl"

    def time_out(args, **kwargs):
        kwargs["stdout"].write('{"type":"turn.started"}\n')
        raise subprocess.TimeoutExpired(
            args,
            test_exp.REAL_AGENT_TIMEOUT_SECONDS,
            stderr=b"still waiting for the model\n",
        )

    monkeypatch.setattr(test_exp.subprocess, "run", time_out)

    with pytest.raises(RuntimeError) as raised:
        test_exp._run(
            ["/opt/codex", "exec", "--json", "prompt"],
            tmp_path,
            stdout=events,
        )

    message = str(raised.value)
    assert "real-agent command timed out after 180 seconds" in message
    assert '{"type":"turn.started"}' in message
    assert "still waiting for the model" in message


def test_live_preflight_timeout_becomes_failed_command_result(monkeypatch):
    from scripts import check_live_tests

    def time_out(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            args[0],
            check_live_tests.COMMAND_TIMEOUT_SECONDS,
            output=b"partial output\n",
            stderr=b"partial error\n",
        )

    monkeypatch.setattr(check_live_tests.subprocess, "run", time_out)

    result = check_live_tests._run(["codex", "login", "status"])

    assert result.returncode == 124
    assert result.stdout == "partial output\n"
    assert "partial error" in result.stderr
    assert "command timed out after 15 seconds: codex login status" in result.stderr


def test_pty_timeout_terminates_and_reaps_child_process_group(monkeypatch):
    import conftest as harness

    real_popen = subprocess.Popen
    children = []

    def start_sleeper(args, **kwargs):
        process = real_popen(
            [sys.executable, "-c", "import time; time.sleep(60)"], **kwargs
        )
        children.append(process)
        return process

    monkeypatch.setattr(harness, "PTY_PROCESS_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(harness.subprocess, "Popen", start_sleeper)

    with pytest.raises(subprocess.TimeoutExpired):
        harness.pty_run([], os.environ.copy(), 1)

    assert len(children) == 1
    assert children[0].poll() is not None


def test_cli_identity_reports_selected_path_resolved_path_and_version(
    monkeypatch, tmp_path
):
    from scripts import check_live_tests

    target = tmp_path / "codex-real"
    target.touch()
    selected = tmp_path / "codex"
    selected.symlink_to(target)
    monkeypatch.setattr(
        check_live_tests,
        "_run",
        lambda command: subprocess.CompletedProcess(
            command, 0, stdout="codex-cli 0.147.0\n", stderr=""
        ),
    )

    identity, error = check_live_tests._cli_identity("Codex", str(selected))

    assert error is None
    assert identity == (
        f"Codex: executable={selected}; resolved={target}; version=codex-cli 0.147.0"
    )
