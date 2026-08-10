#!/usr/bin/env python3
"""Invoke agent-fork for the active Claude Code or Codex session."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence

INSTALL_HINT = "Install it with: uv tool install agent-fork"
RESERVED_OPTIONS = ("--agent", "--parent-session", "--json", "--output", "-o")


def detect_host(environment: Mapping[str, str]) -> tuple[str, str]:
    claude = environment.get("CLAUDECODE") == "1" and bool(
        environment.get("CLAUDE_CODE_SESSION_ID")
    )
    codex = bool(environment.get("CODEX_THREAD_ID"))
    if claude == codex:
        detail = (
            "both Claude Code and Codex are detected"
            if claude
            else "no active Claude Code or Codex session is detected"
        )
        raise ValueError(f"Cannot fork: {detail}.")
    if claude:
        return "claude", environment["CLAUDE_CODE_SESSION_ID"]
    return "codex", environment["CODEX_THREAD_ID"]


def validate_args(arguments: Sequence[str]) -> None:
    for argument in arguments:
        if any(
            argument == option or argument.startswith(f"{option}=")
            for option in RESERVED_OPTIONS
        ):
            raise ValueError(f"Cannot override skill-managed option: {argument}")


def render(document: object) -> str:
    if not isinstance(document, dict):
        raise ValueError("agent-fork returned a non-object JSON result")
    command = document.get("command")
    fork = document.get("fork")
    if not isinstance(command, str) or not command.strip():
        raise ValueError("agent-fork JSON result has no paste command")
    if not isinstance(fork, dict):
        raise ValueError("agent-fork JSON result has no fork details")
    name, branch, worktree = (fork.get(key) for key in ("name", "branch", "worktree"))
    if not all(isinstance(value, str) and value for value in (name, branch, worktree)):
        raise ValueError("agent-fork JSON result has incomplete fork details")
    return "\n".join(
        (
            f"Fork ready: {name}",
            f"Branch: {branch}",
            f"Worktree: {worktree}",
            "",
            "Paste this command into a fresh terminal:",
            command,
        )
    )


def main(arguments: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if arguments is None else arguments)
    try:
        validate_args(arguments)
        agent, session_id = detect_host(os.environ)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 3

    executable = shutil.which("agent-fork")
    if executable is None:
        print(
            f"agent-fork is not installed or is not on PATH. {INSTALL_HINT}",
            file=sys.stderr,
        )
        return 127

    command = [
        executable,
        "fork",
        *arguments,
        "--agent",
        agent,
        "--parent-session",
        session_id,
        "--json",
    ]
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode:
        message = (
            completed.stderr.strip()
            or completed.stdout.strip()
            or "agent-fork failed without diagnostic output"
        )
        print(message, file=sys.stderr)
        return completed.returncode
    try:
        output = render(json.loads(completed.stdout))
    except (json.JSONDecodeError, ValueError) as error:
        print(f"Invalid agent-fork JSON output: {error}", file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
