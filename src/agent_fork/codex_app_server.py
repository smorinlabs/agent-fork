"""Bounded Codex app-server adapter for renamed-session lookup."""

from __future__ import annotations

import json
import os
import selectors
import subprocess
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from agent_fork.errors import SessionResolutionUnavailableError

TIMEOUT = 5.0
MAX_PAGES = 100
MAX_RECORDS = 10_000
MAX_STREAM_BYTES = 1_048_576
PAGE_SIZE = 100


@dataclass(frozen=True)
class CodexThread:
    id: str
    name: str


def _failure(detail: str) -> SessionResolutionUnavailableError:
    return SessionResolutionUnavailableError(
        f"Codex session-name resolution unavailable: {detail}; pass the canonical "
        "UUID, or enforce UUID-only operation with "
        "--no-codex-session-name-resolution"
    )


def list_named_threads(
    executable: str, name: str, env: Mapping[str, str]
) -> tuple[CodexThread, ...]:
    """Return bounded exact-name candidates through Codex-owned state access."""
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
                "params": {"clientInfo": {"name": "agent-fork", "version": "0.1.0"}},
            }
        )
        initialized = response(1)
        if "error" in initialized or not isinstance(initialized.get("result"), dict):
            raise _failure("app-server initialization is unsupported")
        send({"method": "initialized", "params": {}})
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
                thread_id = item.get("id")
                if isinstance(thread_id, str):
                    candidates.append(CodexThread(thread_id, name))
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
        process.stdin.close()
        process.stdout.close()
        process.stderr.close()
