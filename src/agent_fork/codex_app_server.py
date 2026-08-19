"""Bounded Codex app-server adapter for renamed-session lookup."""

from __future__ import annotations

import json
import os
import selectors
import signal
import subprocess
import time
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from importlib.metadata import version
from typing import cast

from agent_fork.errors import SessionResolutionUnavailableError

TIMEOUT = 5.0
MAX_PAGES = 100
MAX_RECORDS = 10_000
MAX_STREAM_BYTES = 1_048_576
MAX_PENDING_MESSAGES = 10_000
PAGE_SIZE = 100


@dataclass(frozen=True)
class CodexThread:
    id: str
    name: str | None
    forked_from_id: str | None = None


@contextmanager
def _sigpipe_ignored():
    """Keep a write to the app-server's closed stdin raising BrokenPipeError.

    The CLI runs with SIGPIPE at SIG_DFL (cli.main restores it for its own
    stdout contract), which would otherwise kill the process on such a write
    before the exception could be raised.
    """
    if not hasattr(signal, "SIGPIPE"):
        yield
        return
    previous = signal.signal(signal.SIGPIPE, signal.SIG_IGN)
    try:
        yield
    finally:
        if previous is not None:
            signal.signal(signal.SIGPIPE, previous)


def _failure(detail: str) -> SessionResolutionUnavailableError:
    return SessionResolutionUnavailableError(
        f"Codex session-name resolution unavailable: {detail}; pass the canonical "
        "UUID, or enforce UUID-only operation with "
        "--no-codex-session-name-resolution"
    )


def _query_threads(
    executable: str,
    env: Mapping[str, str],
    *,
    name: str | None = None,
    thread_id: str | None = None,
) -> tuple[CodexThread, ...]:
    """Return bounded exact-name candidates through Codex-owned state access."""
    # Resolved before the spawn: the metadata read costs milliseconds, and any
    # delay between Popen and the first stdin write widens the window in which
    # a short-lived app-server can exit before the handshake reaches it.
    client_version = version("agent-fork")
    try:
        process = subprocess.Popen(
            [executable, "app-server", "--listen", "stdio://"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=dict(env),
        )
    except OSError as error:
        raise _failure(str(error)) from error
    assert process.stdin is not None
    assert process.stdout is not None
    assert process.stderr is not None
    stdin = process.stdin
    selector = selectors.DefaultSelector()
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    messages: list[dict[str, object]] = []
    for label, stream in (("stdout", process.stdout), ("stderr", process.stderr)):
        os.set_blocking(stream.fileno(), False)
        selector.register(stream, selectors.EVENT_READ, label)

    deadline = time.monotonic() + TIMEOUT

    def send(message: dict[str, object]) -> None:
        payload = json.dumps(message, separators=(",", ":")).encode() + b"\n"
        with _sigpipe_ignored():
            try:
                stdin.write(payload)
                stdin.flush()
            except (BrokenPipeError, OSError) as error:
                raise _failure("app-server closed its input") from error

    def response(request_id: int) -> dict[str, object]:
        while time.monotonic() < deadline:
            for key, _ in selector.select(min(0.1, deadline - time.monotonic())):
                label = key.data
                try:
                    chunk = os.read(key.fd, 65536)
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                buffer = buffers[label]
                buffer.extend(chunk)
                if len(buffer) > MAX_STREAM_BYTES:
                    raise _failure(f"app-server {label} exceeded its output limit")
                if label == "stdout":
                    while b"\n" in buffer:
                        raw, _, remainder = buffer.partition(b"\n")
                        buffer[:] = remainder
                        try:
                            parsed = json.loads(raw)
                        except (UnicodeDecodeError, json.JSONDecodeError) as error:
                            raise _failure(
                                "app-server returned malformed JSON"
                            ) from error
                        if isinstance(parsed, dict):
                            messages.append(parsed)
                            if len(messages) > MAX_PENDING_MESSAGES:
                                raise _failure(
                                    "app-server exceeded its pending-message limit"
                                )
            for index, message in enumerate(messages):
                if message.get("id") == request_id:
                    return messages.pop(index)
            if process.poll() is not None and not selector.get_map():
                detail = buffers["stderr"].decode(errors="replace").strip()
                raise _failure(detail or "app-server exited before responding")
        raise _failure("app-server response timed out")

    try:
        send(
            {
                "id": 1,
                "method": "initialize",
                "params": {
                    "clientInfo": {
                        "name": "agent-fork",
                        "version": client_version,
                    }
                },
            }
        )
        initialized = response(1)
        if "error" in initialized or not isinstance(initialized.get("result"), dict):
            raise _failure("app-server initialization is unsupported")
        send({"method": "initialized", "params": {}})
        if thread_id is not None:
            send(
                {
                    "id": 2,
                    "method": "thread/read",
                    "params": {"threadId": thread_id, "includeTurns": False},
                }
            )
            reply = response(2)
            if "error" in reply:
                raise _failure("thread/read failed")
            result = reply.get("result")
            thread = result.get("thread") if isinstance(result, dict) else None
            if not isinstance(thread, dict) or thread.get("id") != thread_id:
                raise _failure("thread/read returned an unsupported schema")
            found_name = thread.get("name")
            parent = thread.get("forkedFromId")
            return (
                CodexThread(
                    thread_id,
                    found_name if isinstance(found_name, str) else None,
                    parent if isinstance(parent, str) else None,
                ),
            )
        assert name is not None
        cursor: str | None = None
        seen_cursors: set[str] = set()
        candidates: list[CodexThread] = []
        records = 0
        for page in range(MAX_PAGES):
            params: dict[str, object] = {
                "archived": False,
                "limit": PAGE_SIZE,
                "searchTerm": name,
                "sortDirection": "desc",
                "sortKey": "updated_at",
                "useStateDbOnly": True,
            }
            if cursor is not None:
                params["cursor"] = cursor
            request_id = page + 2
            send({"id": request_id, "method": "thread/list", "params": params})
            reply = response(request_id)
            if "error" in reply:
                raise _failure("thread/list is unsupported")
            result = reply.get("result")
            if not isinstance(result, dict):
                raise _failure("thread/list returned an unsupported schema")
            data_value = result.get("data")
            if not isinstance(data_value, list):
                raise _failure("thread/list returned an unsupported schema")
            data = cast(list[object], data_value)
            records += len(data)
            if records > MAX_RECORDS:
                raise _failure("thread/list exceeded its record limit")
            for item in data:
                if not isinstance(item, dict) or item.get("name") != name:
                    continue
                item_id = item.get("id")
                if isinstance(item_id, str):
                    parent = item.get("forkedFromId")
                    candidates.append(
                        CodexThread(
                            item_id,
                            name,
                            parent if isinstance(parent, str) else None,
                        )
                    )
            next_cursor = result.get("nextCursor")
            if next_cursor is None:
                return tuple(candidates)
            if not isinstance(next_cursor, str) or next_cursor in seen_cursors:
                raise _failure("thread/list returned an invalid pagination cursor")
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        raise _failure("thread/list exceeded its page limit")
    finally:
        selector.close()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=0.5)
        # A failed send leaves its payload in the BufferedWriter, and close()
        # retries that flush against the dead pipe — same SIGPIPE hazard.
        with _sigpipe_ignored():
            try:
                process.stdin.close()
            except OSError:
                pass
        process.stdout.close()
        process.stderr.close()


def list_named_threads(
    executable: str, name: str, env: Mapping[str, str]
) -> tuple[CodexThread, ...]:
    """Return bounded exact-name candidates through Codex-owned state access."""
    return _query_threads(executable, env, name=name)


def read_thread(
    executable: str, thread_id: str, env: Mapping[str, str]
) -> CodexThread | None:
    """Read one exact thread through the bounded Codex-owned app-server path."""
    matches = _query_threads(executable, env, thread_id=thread_id)
    return matches[0] if matches else None
