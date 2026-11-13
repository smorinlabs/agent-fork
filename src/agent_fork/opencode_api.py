"""Bounded `opencode api` calls against OpenCode's background service.

`opencode api` exits 1 on any HTTP error and when the service is unreachable,
so the exit status is trusted; a missing session is told apart by OpenCode's
`SessionNotFoundError` tag.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path

from agent_fork.agents import OPENCODE_SESSION_ID
from agent_fork.errors import AgentForkError
from agent_fork.text import escape_terminal_text

OPENCODE_API_TIMEOUT = 30.0


class OpencodeApiError(AgentForkError):
    """An `opencode api` call failed; `not_found` marks an unknown session."""

    def __init__(self, message: str, *, not_found: bool = False) -> None:
        super().__init__(message)
        self.not_found = not_found


def call(
    binary: str,
    operation: str,
    session_id: str,
    env: Mapping[str, str],
    *,
    body: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Run one session operation and return its `data` object ({} when empty)."""
    argv = [binary, "api", operation, "--param", f"sessionID={session_id}"]
    if body is not None:
        argv += ["-d", json.dumps(body)]
    try:
        completed = subprocess.run(
            argv,
            env=dict(env),
            capture_output=True,
            text=True,
            timeout=OPENCODE_API_TIMEOUT,
        )
    except subprocess.TimeoutExpired as error:
        raise OpencodeApiError(
            f"`opencode api {operation}` timed out after {OPENCODE_API_TIMEOUT:g}s"
        ) from error
    except (OSError, UnicodeDecodeError) as error:
        raise OpencodeApiError(f"`opencode api {operation}` failed: {error}") from error
    if completed.returncode != 0:
        output = (completed.stdout or completed.stderr).strip()
        detail = output.splitlines()[0] if output else f"exit {completed.returncode}"
        raise OpencodeApiError(
            f"`opencode api {operation}` failed: {escape_terminal_text(detail)}",
            not_found='"SessionNotFoundError"' in completed.stdout,
        )
    if not completed.stdout.strip():
        return {}
    try:
        document = json.loads(completed.stdout)
    except ValueError as error:
        raise OpencodeApiError(
            f"`opencode api {operation}` returned unreadable output"
        ) from error
    data = document.get("data") if isinstance(document, dict) else None
    if not isinstance(data, dict):
        raise OpencodeApiError(f"`opencode api {operation}` returned no data object")
    return data


def fork_into(
    binary: str, parent_id: str, directory: Path, env: Mapping[str, str]
) -> str:
    """Fork `parent_id` and move the child into `directory`; return the child ID.

    The child exists from the moment `session.fork` answers, so any failure
    after it, an interrupt included, deletes the child before re-raising.
    """
    data = call(binary, "session.fork", parent_id, env, body={})
    child = data.get("id")
    if not isinstance(child, str) or OPENCODE_SESSION_ID.fullmatch(child) is None:
        raise OpencodeApiError("`opencode api session.fork` returned no child ID")
    try:
        call(binary, "session.move", child, env, body={"directory": str(directory)})
    except BaseException:
        # Best-effort: the failure that triggered this is the one to report.
        with suppress(Exception):
            call(binary, "session.remove", child, env)
        raise
    return child
