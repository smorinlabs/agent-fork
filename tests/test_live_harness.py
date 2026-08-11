"""Unit coverage for real-agent test-harness compatibility helpers."""

import subprocess

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
