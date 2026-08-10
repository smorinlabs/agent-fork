from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[2]
SKILL = ROOT / ".agents/skills/agent-fork"
SCRIPT = SKILL / "scripts/fork_session.py"


def _shim(tmp_path: Path) -> tuple[Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    binary = tmp_path / "agent-fork"
    argv_log = tmp_path / "argv.json"
    binary.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "open(os.environ['ARGV_LOG'], 'w').write(json.dumps(sys.argv[1:]))\n"
        "if os.environ.get('SHIM_MODE') == 'invalid':\n"
        "    print('not-json')\n"
        "    raise SystemExit(0)\n"
        "print(json.dumps({'command': 'codex -C /tmp/fork resume --fork abc', "
        "'fork': {'name': 'demo', 'branch': 'fork/demo', 'worktree': '/tmp/fork'}}))\n"
    )
    binary.chmod(0o755)
    return binary, argv_log


def _run(
    tmp_path: Path, host: str, *arguments: str, shim_mode: str = ""
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    _, argv_log = _shim(tmp_path)
    env = {"PATH": f"{tmp_path}:{os.environ['PATH']}", "ARGV_LOG": str(argv_log)}
    if shim_mode:
        env["SHIM_MODE"] = shim_mode
    if host == "claude":
        env.update(CLAUDECODE="1", CLAUDE_CODE_SESSION_ID="claude-parent")
    elif host == "codex":
        env["CODEX_THREAD_ID"] = "codex-parent"
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), *arguments],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    argv = json.loads(argv_log.read_text()) if argv_log.exists() else []
    return completed, argv


def test_skill_is_shared_by_codex_and_claude() -> None:
    claude_skill = ROOT / ".claude/skills/agent-fork"
    assert claude_skill.resolve() == SKILL.resolve()
    text = (SKILL / "SKILL.md").read_text()
    assert text.startswith("---\nname: agent-fork\ndescription:")
    assert "Do not retry with guessed session IDs" in text


def test_claude_invocation_passes_explicit_identity_and_json(tmp_path: Path) -> None:
    completed, argv = _run(tmp_path, "claude", "my-fork", "--with-ignored")
    assert completed.returncode == 0
    assert argv == [
        "fork",
        "my-fork",
        "--with-ignored",
        "--agent",
        "claude",
        "--parent-session",
        "claude-parent",
        "--json",
    ]
    assert completed.stdout.endswith("codex -C /tmp/fork resume --fork abc\n")


def test_codex_invocation_passes_explicit_identity_and_json(tmp_path: Path) -> None:
    completed, argv = _run(tmp_path, "codex")
    assert completed.returncode == 0
    assert argv == [
        "fork",
        "--agent",
        "codex",
        "--parent-session",
        "codex-parent",
        "--json",
    ]
    assert "Paste this command into a fresh terminal:" in completed.stdout


def test_ambiguous_or_missing_host_refuses(tmp_path: Path) -> None:
    missing, _ = _run(tmp_path / "missing", "none")
    both_path = tmp_path / "both"
    _, argv_log = _shim(both_path)
    env = {
        "PATH": f"{both_path}:{os.environ['PATH']}",
        "ARGV_LOG": str(argv_log),
        "CLAUDECODE": "1",
        "CLAUDE_CODE_SESSION_ID": "claude-parent",
        "CODEX_THREAD_ID": "codex-parent",
    }
    both = subprocess.run(
        [sys.executable, str(SCRIPT)], env=env, text=True, capture_output=True
    )
    assert missing.returncode == both.returncode == 3
    assert "no active Claude Code or Codex" in missing.stderr
    assert "both Claude Code and Codex" in both.stderr


def test_skill_managed_identity_cannot_be_overridden(tmp_path: Path) -> None:
    completed, argv = _run(tmp_path, "codex", "--agent=claude")
    assert completed.returncode == 3
    assert argv == []
    assert "Cannot override skill-managed option" in completed.stderr


def test_missing_cli_has_install_hint(tmp_path: Path) -> None:
    env = {"PATH": str(tmp_path), "CODEX_THREAD_ID": "codex-parent"}
    completed = subprocess.run(
        [sys.executable, str(SCRIPT)], env=env, text=True, capture_output=True
    )
    assert completed.returncode == 127
    assert "uv tool install agent-fork" in completed.stderr


def test_malformed_cli_json_is_diagnostic(tmp_path: Path) -> None:
    completed, _ = _run(tmp_path, "codex", shim_mode="invalid")
    assert completed.returncode == 1
    assert "Invalid agent-fork JSON output" in completed.stderr


def test_destination_and_branch_options_pass_through_before_managed_identity(
    tmp_path: Path,
) -> None:
    completed, argv = _run(
        tmp_path,
        "codex",
        "experiment",
        "--branch",
        "review/manual",
        "--worktree-base-dir",
        "/work/forks",
        "--worktree-name",
        "Manual Worktree",
    )
    assert completed.returncode == 0
    assert argv[:8] == [
        "fork",
        "experiment",
        "--branch",
        "review/manual",
        "--worktree-base-dir",
        "/work/forks",
        "--worktree-name",
        "Manual Worktree",
    ]
    assert argv[8:] == [
        "--agent",
        "codex",
        "--parent-session",
        "codex-parent",
        "--json",
    ]


def test_new_passthrough_does_not_relax_managed_option_rejection(
    tmp_path: Path,
) -> None:
    completed, argv = _run(tmp_path, "claude", "--worktree-name", "leaf", "--json")
    assert completed.returncode == 3
    assert argv == []
