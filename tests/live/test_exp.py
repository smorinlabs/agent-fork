"""G-EXP — Phase B experiments against the real Claude and Codex CLIs."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import select
import shlex
import shutil
import struct
import subprocess
import sys
import termios
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

CLAUDE = shutil.which("claude")
CODEX = shutil.which("codex")
ANSI = re.compile(rb"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
REAL_AGENT_TIMEOUT_SECONDS = 180


@pytest.mark.matrix("T-SES-17")
@pytest.mark.requires_real_cli
@pytest.mark.skipif(
    CLAUDE is None, reason="requires_real_cli: claude executable not found"
)
def test_session_identity_inside_claude_print(tmp_path: Path):
    assert CLAUDE is not None
    output = tmp_path / "claude-session.json"
    command = shlex.join(
        [sys.executable, "-m", "agent_fork.cli", "session", "-o", "json"]
    )
    prompt = f"Execute `{command}` exactly once with Bash. Return only its raw stdout."
    _run(
        [
            "env",
            "-u",
            "CODEX_THREAD_ID",
            CLAUDE,
            "-p",
            prompt,
            "--output-format",
            "json",
            "--allowedTools",
            "Bash",
            "--permission-mode",
            "bypassPermissions",
            "--max-turns",
            "2",
        ],
        Path.cwd(),
        stdout=output,
    )
    outer = _claude_result_record(json.loads(output.read_text()))
    inner = json.loads(
        str(outer["result"]).strip().removeprefix("```json").removesuffix("```").strip()
    )
    assert inner["agent"] == "claude"
    assert inner["current_session"]["id"] == outer["session_id"]


@pytest.mark.matrix("T-SES-18")
@pytest.mark.requires_real_cli
@pytest.mark.skipif(
    CODEX is None, reason="requires_real_cli: codex executable not found"
)
def test_session_identity_inside_codex_exec(tmp_path: Path):
    assert CODEX is not None
    output = tmp_path / "codex-session.jsonl"
    command = shlex.join(
        [sys.executable, "-m", "agent_fork.cli", "session", "-o", "json"]
    )
    _run(
        [
            CODEX,
            "exec",
            "--json",
            "--sandbox",
            "danger-full-access",
            f"Execute `{command}` exactly once. Return only its stdout.",
        ],
        Path.cwd(),
        stdout=output,
    )
    events = [json.loads(line) for line in output.read_text().splitlines()]
    thread_id = next(
        item["thread_id"] for item in events if item.get("type") == "thread.started"
    )
    execution = next(
        item["item"]
        for item in events
        if item.get("type") == "item.completed"
        and item.get("item", {}).get("type") == "command_execution"
    )
    inner = json.loads(execution["aggregated_output"])
    assert execution["exit_code"] == 0
    assert inner["agent"] == "codex"
    assert inner["current_session"]["id"] == thread_id


@pytest.mark.matrix("T-SES-20")
@pytest.mark.requires_real_cli
@pytest.mark.skipif(
    CLAUDE is None, reason="requires_real_cli: claude executable not found"
)
def test_claude_resume_observes_recorded_parent(
    claude_fork: ClaudeForkResult, tmp_path: Path
):
    from agent_fork.lineage import LineageClaim, add_lineage, remove_lineage

    assert CLAUDE is not None
    claim = LineageClaim.create(
        agent="claude",
        child_session_id=claude_fork.child_id,
        parent_session_id=claude_fork.parent_id,
        name=claude_fork.name,
    )
    add_lineage(claim, env=os.environ)
    output = tmp_path / "claude-lineage.json"
    command = shlex.join(
        [sys.executable, "-m", "agent_fork.cli", "session", "-o", "json"]
    )
    try:
        _run(
            [
                "env",
                "-u",
                "CODEX_THREAD_ID",
                CLAUDE,
                "--resume",
                claude_fork.child_id,
                "-p",
                f"Execute `{command}` exactly once with Bash. Return only raw stdout.",
                "--output-format",
                "json",
                "--allowedTools",
                "Bash",
                "--permission-mode",
                "bypassPermissions",
                "--max-turns",
                "2",
            ],
            claude_fork.child,
            stdout=output,
        )
        outer = _claude_result_record(json.loads(output.read_text()))
        rendered = str(outer["result"]).strip()
        inner = json.loads(rendered.removeprefix("```json").removesuffix("```").strip())
        assert inner["current_session"]["id"] == claude_fork.child_id
        assert inner["parent_session"]["id"] == claude_fork.parent_id
        assert inner["parent_session"]["id_status"] == "claimed"
    finally:
        remove_lineage("claude", claude_fork.child_id, env=os.environ)


def _text(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value or ""


def _run(
    args: list[str], cwd: Path, *, stdout: Path | None = None
) -> subprocess.CompletedProcess[str]:
    try:
        if stdout is None:
            result = subprocess.run(
                args,
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=REAL_AGENT_TIMEOUT_SECONDS,
                check=False,
            )
            captured_stdout = result.stdout or ""
        else:
            with stdout.open("w") as target:
                result = subprocess.run(
                    args,
                    cwd=cwd,
                    stdin=subprocess.DEVNULL,
                    stdout=target,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=REAL_AGENT_TIMEOUT_SECONDS,
                    check=False,
                )
            captured_stdout = stdout.read_text()
    except subprocess.TimeoutExpired as error:
        captured_stdout = (
            stdout.read_text() if stdout is not None else _text(error.stdout)
        )
        rendered_stdout = captured_stdout.rstrip() or "<empty>"
        rendered_stderr = _text(error.stderr).rstrip() or "<empty>"
        raise RuntimeError(
            f"real-agent command timed out after {REAL_AGENT_TIMEOUT_SECONDS} seconds: "
            f"{shlex.join(args)}\n"
            f"stdout:\n{rendered_stdout}\n"
            f"stderr:\n{rendered_stderr}"
        ) from error
    if result.returncode != 0:
        rendered_stdout = captured_stdout.rstrip() or "<empty>"
        rendered_stderr = (result.stderr or "").rstrip() or "<empty>"
        raise RuntimeError(
            f"real-agent command failed with exit {result.returncode}: "
            f"{shlex.join(args)}\n"
            f"stdout:\n{rendered_stdout}\n"
            f"stderr:\n{rendered_stderr}"
        )
    return result


@pytest.mark.matrix("T-EXP-07")
@pytest.mark.requires_real_cli
def test_codex_renamed_session_resolves_through_real_app_server():
    """E7 — exercise Codex-owned name resolution without repository mutation."""
    from agent_fork.codex_app_server import list_named_threads

    if CODEX is None:
        pytest.skip("requires real Codex CLI")
    name = os.environ.get("AGENT_FORK_CODEX_RENAMED_SESSION", "hello-codex")
    candidates = list_named_threads(CODEX, name, os.environ)
    if not candidates:
        pytest.skip(f"requires a renamed Codex session named {name!r}")
    assert all(candidate.name == name for candidate in candidates)
    assert all(str(uuid.UUID(candidate.id)) == candidate.id for candidate in candidates)


def _git_repo(root: Path) -> tuple[Path, Path]:
    repo = root / "repo"
    child = root / "child-worktree"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "exp@example.invalid"], cwd=repo, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Agent Fork Experiment"], cwd=repo, check=True
    )
    (repo / "seed.txt").write_text("seed\n")
    subprocess.run(["git", "add", "seed.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=repo, check=True)
    subprocess.run(
        ["git", "worktree", "add", "-qb", "exp-child", str(child)], cwd=repo, check=True
    )
    return repo, child


def _claude_transcript(cwd: Path, session_id: str) -> Path:
    encoded = re.sub(r"[^a-zA-Z0-9]", "-", str(cwd))
    config_dir = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))
    return config_dir / "projects" / encoded / f"{session_id}.jsonl"


def _claude_result_record(payload: object) -> dict[str, object]:
    if isinstance(payload, dict):
        return cast(dict[str, object], payload)
    if isinstance(payload, list):
        results = [
            record
            for record in payload
            if isinstance(record, dict) and record.get("type") == "result"
        ]
        if len(results) == 1:
            return cast(dict[str, object], results[0])
        raise ValueError(
            "Claude JSON event array contains "
            f"{len(results)} result records; expected 1"
        )
    raise TypeError(
        "Claude JSON output must be an object or event array, got "
        f"{type(payload).__name__}"
    )


@dataclass(frozen=True)
class ClaudeForkResult:
    parent_id: str
    child_id: str
    token: str
    name: str
    child: Path
    parent_hash_before: str
    parent_hash_after: str
    child_output: dict[str, object]
    child_transcript: str


@pytest.fixture(scope="module")
def claude_fork(tmp_path_factory: pytest.TempPathFactory) -> ClaudeForkResult:
    if CLAUDE is None:
        pytest.skip("requires_real_cli: claude executable not found")
    root = tmp_path_factory.mktemp("claude-fork")
    repo, child = _git_repo(root)
    parent_id, child_id = str(uuid.uuid4()), str(uuid.uuid4())
    token = f"AFORK-{uuid.uuid4()}"
    name = f"agent-fork-e1-{uuid.uuid4().hex[:8]}"
    parent_prompt = (
        f"Remember this exact token for a later fork: {token}. Reply only PARENT_READY."
    )
    parent_out, child_out = root / "parent.json", root / "child.json"
    _run(
        [
            CLAUDE,
            "--session-id",
            parent_id,
            "-p",
            parent_prompt,
            "--output-format",
            "json",
            "--max-turns",
            "1",
        ],
        repo,
        stdout=parent_out,
    )
    parent_transcript = _claude_transcript(repo, parent_id)
    before = hashlib.sha256(parent_transcript.read_bytes()).hexdigest()
    _run(
        [
            CLAUDE,
            "--session-id",
            child_id,
            "--resume",
            parent_id,
            "--fork-session",
            "-n",
            name,
            "-p",
            "Reply only with the exact token I asked you to remember earlier.",
            "--output-format",
            "json",
            "--max-turns",
            "1",
        ],
        child,
        stdout=child_out,
    )
    return ClaudeForkResult(
        parent_id=parent_id,
        child_id=child_id,
        token=token,
        name=name,
        child=child,
        parent_hash_before=before,
        parent_hash_after=hashlib.sha256(parent_transcript.read_bytes()).hexdigest(),
        child_output=_claude_result_record(json.loads(child_out.read_text())),
        child_transcript=_claude_transcript(child, child_id).read_text(),
    )


def _pty_capture(args: list[str], cwd: Path, *, settle: float = 5.0) -> str:
    master, slave = os.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 100, 0, 0))
    env = os.environ.copy()
    env["TERM"] = "xterm-256color"
    process = subprocess.Popen(
        args,
        cwd=cwd,
        env=env,
        stdin=slave,
        stdout=slave,
        stderr=slave,
        start_new_session=True,
    )
    os.close(slave)
    output = bytearray()
    deadline = time.monotonic() + settle
    sent_enter = False
    try:
        while time.monotonic() < deadline:
            ready, _, _ = select.select([master], [], [], 0.2)
            if ready:
                try:
                    output.extend(os.read(master, 65536))
                except OSError:
                    break
            plain = ANSI.sub(b"", output)
            if (
                b"Do" in plain
                and b"you" in plain
                and b"trust" in plain
                and not sent_enter
            ):
                os.write(master, b"\r")
                sent_enter = True
            if b"Choose working directory" in plain or b"Thread forked from" in plain:
                break
            if process.poll() is not None and not ready:
                break
    finally:
        if process.poll() is None:
            os.write(master, b"\x03\x03")
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=5)
        os.close(master)
    return ANSI.sub(b"", output).decode(errors="replace")


@pytest.mark.matrix("T-EXP-01")
@pytest.mark.requires_real_cli
@pytest.mark.skipif(
    CLAUDE is None, reason="requires_real_cli: claude executable not found"
)
def test_e1_claude_flag_combo_no_silent_noop(claude_fork: ClaudeForkResult):
    assert f'"sessionId":"{claude_fork.child_id}"' in claude_fork.child_transcript
    assert f'"customTitle":"{claude_fork.name}"' in claude_fork.child_transcript
    assert f'"agentName":"{claude_fork.name}"' in claude_fork.child_transcript


@pytest.mark.matrix("T-EXP-02")
@pytest.mark.requires_real_cli
@pytest.mark.skipif(
    CODEX is None, reason="requires_real_cli: codex executable not found"
)
def test_e2_codex_cross_cwd_fork_explicit_id(tmp_path: Path):
    assert CODEX is not None
    repo, child = _git_repo(tmp_path)
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    events = tmp_path / "parent.jsonl"
    _run(
        [
            CODEX,
            "exec",
            "--json",
            "--sandbox",
            "read-only",
            "Reply only CODEX_PARENT_READY. Do not run tools.",
        ],
        repo,
        stdout=events,
    )
    thread_id = next(
        json.loads(line)["thread_id"]
        for line in events.read_text().splitlines()
        if json.loads(line).get("type") == "thread.started"
    )
    common = [
        CODEX,
        "fork",
        thread_id,
        "-c",
        "check_for_update_on_startup=false",
        "--no-alt-screen",
        "--dangerously-bypass-hook-trust",
    ]
    plain = _pty_capture(common, foreign)
    assert str(repo) in plain and str(foreign) in plain
    with_cd = _pty_capture([*common, "-C", str(child)], foreign)
    assert "child-worktr" in with_cd
    assert str(foreign) not in with_cd


@pytest.mark.matrix("T-EXP-03")
@pytest.mark.requires_real_cli
@pytest.mark.skipif(
    CLAUDE is None, reason="requires_real_cli: claude executable not found"
)
def test_e3_claude_e2e_full_paste_command(claude_fork: ClaudeForkResult):
    assert claude_fork.child_output["session_id"] == claude_fork.child_id
    assert claude_fork.child_output["result"] == claude_fork.token
    assert claude_fork.parent_hash_before == claude_fork.parent_hash_after
    assert claude_fork.token in claude_fork.child_transcript


@pytest.mark.matrix("T-EXP-04")
@pytest.mark.skip(
    reason="retired: T-EXP-04 until v1.1 (A8 — D14 mooted the .jsonl-copy fallback)"
)
def test_jsonl_copy_last_resort():
    """T-EXP-04 — retired. Returns with the v1.1 fallback ladder."""
    raise NotImplementedError
