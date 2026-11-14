"""Bounded `opencode api` calls against OpenCode's background service.

`opencode api` exits 1 on any HTTP error and when the service is unreachable,
so the exit status is trusted; a missing session is told apart by OpenCode's
`SessionNotFoundError` tag. When the service is stopped, `opencode api`
starts it, so read-only callers check `service_running` first.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping
from pathlib import Path

from agent_fork.agents import OPENCODE_SESSION_ID
from agent_fork.errors import AgentForkError
from agent_fork.text import escape_terminal_text

OPENCODE_API_TIMEOUT = 30.0
# Read-only lookups (the session report) wait less than the fork path does.
OPENCODE_LOOKUP_TIMEOUT = 5.0


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
    timeout: float | None = None,
    require_data: bool = True,
) -> dict[str, object]:
    """Run one session operation and return its `data` object.

    `require_data=False` is for operations whose reply is never read (move,
    remove): any successful reply is accepted and `{}` returned.
    """
    limit = OPENCODE_API_TIMEOUT if timeout is None else timeout
    argv = [binary, "api", operation, "--param", f"sessionID={session_id}"]
    if body is not None:
        argv += ["-d", json.dumps(body)]
    try:
        completed = subprocess.run(
            argv,
            env=dict(env),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=limit,
        )
    except subprocess.TimeoutExpired as error:
        raise OpencodeApiError(
            f"`opencode api {operation}` timed out after {limit:g}s"
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
    if not require_data or not completed.stdout.strip():
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


def service_running(binary: str, env: Mapping[str, str]) -> bool:
    """Whether OpenCode's background service runs; never starts it."""
    try:
        completed = subprocess.run(
            [binary, "service", "status"],
            env=dict(env),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=OPENCODE_LOOKUP_TIMEOUT,
        )
    except (OSError, UnicodeDecodeError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0 and completed.stdout.startswith("http")


def fork_into(
    binary: str, parent_id: str, directory: Path, env: Mapping[str, str]
) -> str:
    """Fork `parent_id` and move the child into `directory`; return the child ID.

    Compensation is best effort. Once `session.fork` answers, any later
    failure, an interrupt included, deletes the child; a child that cannot be
    deleted is named in the error with its recovery command. A fork that fails
    or times out without answering may still have created a child whose ID was
    never returned, and the error says so.
    """
    try:
        data = call(binary, "session.fork", parent_id, env, body={})
    except OpencodeApiError as error:
        if error.not_found:
            raise
        raise OpencodeApiError(
            f"{error}; OpenCode may have created a fork of {parent_id} anyway: "
            "check its session list"
        ) from error
    child = data.get("id")
    if not isinstance(child, str) or OPENCODE_SESSION_ID.fullmatch(child) is None:
        if isinstance(child, str) and child:
            _remove_child(binary, child, env)
        raise OpencodeApiError(
            f"`opencode api session.fork` returned no valid child ID for {parent_id}"
        )
    try:
        call(
            binary,
            "session.move",
            child,
            env,
            body={"directory": str(directory)},
            require_data=False,
        )
    except OpencodeApiError as error:
        leftover = _remove_child(binary, child, env)
        if leftover is None:
            raise
        raise OpencodeApiError(f"{error}; {leftover}") from error
    except BaseException:
        _remove_child(binary, child, env)
        raise
    return child


def _remove_child(binary: str, child: str, env: Mapping[str, str]) -> str | None:
    """Delete a forked child; on failure return a notice naming it."""
    try:
        call(binary, "session.remove", child, env, require_data=False)
    except Exception:
        return (
            f"the forked OpenCode session {escape_terminal_text(child)} could not "
            "be deleted; remove it with: opencode api session.remove --param "
            f"sessionID={escape_terminal_text(child)}"
        )
    return None
