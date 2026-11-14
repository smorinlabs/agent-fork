"""Bounded Muse Session Protocol (MSP) client that forks one Muse session.

Muse has no CLI fork verb; `session/fork` is a stable MSP method served by
`muse serve` over stdio (newline-delimited JSON-RPC). Behavior observed in
the P08 probes (Muse Code 1.4.20):

- the client sends `initialize`, then the `initialized` notification;
- `session/fork` copies the source's completed turns into a new session and
  loads only that new session into the host;
- a host with a loaded session does not exit on stdin EOF, but exits cleanly
  after `session/leave` with `stop: true`, which also records `session.end`
  (without it, the next resume warns the session "ended abnormally").
"""

from __future__ import annotations

import json
import os
import selectors
import signal
import subprocess
import threading
import time
import uuid
from collections.abc import Callable, Mapping
from importlib.metadata import version
from types import FrameType

from agent_fork.codex_app_server import _sigpipe_ignored
from agent_fork.errors import MuseForkError

TIMEOUT = 30.0
SHUTDOWN_TIMEOUT = 5.0
MAX_LINE_BYTES = 1_048_576
MAX_STDERR_BYTES = 65_536


def _uuid7() -> str:
    """A UUIDv7, which MSP requires for every `commandId`."""
    milliseconds = time.time_ns() // 1_000_000
    random = int.from_bytes(os.urandom(10), "big")
    value = (milliseconds & ((1 << 48) - 1)) << 80
    value |= 0x7 << 76
    value |= ((random >> 62) & 0xFFF) << 64
    value |= 0b10 << 62
    value |= random & ((1 << 62) - 1)
    return str(uuid.UUID(int=value))


def _failure(detail: str) -> MuseForkError:
    return MuseForkError(f"Muse fork failed: {detail}")


def _canonical(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return str(uuid.UUID(value)) == value.lower()
    except ValueError:
        return False


def fork_session(
    executable: str,
    parent_session_id: str,
    env: Mapping[str, str],
    *,
    warn: Callable[[str], None] | None = None,
) -> str:
    """Fork `parent_session_id` through `muse serve`; return the new session ID."""
    if not _canonical(parent_session_id):
        raise _failure(f"parent {parent_session_id!r} is not a session UUID")
    client_version = version("agent-fork")
    deadline = time.monotonic() + TIMEOUT
    # SIGTERM and SIGHUP (a closed terminal) would otherwise end the process
    # without running the cleanup below, orphaning `muse serve` with the new
    # fork loaded. Raising runs it; SIGINT already raises KeyboardInterrupt.
    previous_handlers: dict[
        int, Callable[[int, FrameType | None], object] | int | None
    ] = {}
    if threading.current_thread() is threading.main_thread():

        def interrupted(signum: int, _frame: FrameType | None) -> None:
            raise _failure(f"interrupted by {signal.Signals(signum).name}")

        for signum in (signal.SIGTERM, signal.SIGHUP):
            previous_handlers[signum] = signal.signal(signum, interrupted)
    try:
        return _fork(executable, parent_session_id, env, warn, client_version, deadline)
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


def _fork(
    executable: str,
    parent_session_id: str,
    env: Mapping[str, str],
    warn: Callable[[str], None] | None,
    client_version: str,
    deadline: float,
) -> str:
    try:
        process = subprocess.Popen(
            [executable, "serve"],
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
    line = bytearray()
    stderr_tail = bytearray()
    # Requests are sequential, so only the reply to the one in flight is kept;
    # any other reply is dropped rather than retained.
    awaited: dict[str, object] = {}
    selector: selectors.BaseSelector | None = None
    # Cleanup owns the process from here on, including selector setup.
    try:
        selector = selectors.DefaultSelector()
        for label, stream in (("stdout", process.stdout), ("stderr", process.stderr)):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, label)
        active = selector

        def pump(timeout: float, request_id: int | None) -> None:
            for key, _ in active.select(timeout):
                try:
                    chunk = os.read(key.fd, 65536)
                except BlockingIOError:
                    continue
                if not chunk:
                    active.unregister(key.fileobj)
                    continue
                if key.data == "stderr":
                    stderr_tail.extend(chunk)
                    del stderr_tail[:-MAX_STDERR_BYTES]
                    continue
                line.extend(chunk)
                while b"\n" in line:
                    raw, _, remainder = line.partition(b"\n")
                    line[:] = remainder
                    if len(raw) > MAX_LINE_BYTES:
                        raise _failure("muse serve exceeded its output limit")
                    try:
                        parsed = json.loads(raw)
                    except (UnicodeDecodeError, ValueError, RecursionError) as error:
                        raise _failure("muse serve returned malformed JSON") from error
                    # A reply carries the awaited id and no method; a
                    # server->client request carries a method and may reuse an
                    # id this client sent.
                    if (
                        request_id is not None
                        and isinstance(parsed, dict)
                        and parsed.get("id") == request_id
                        and "method" not in parsed
                    ):
                        if "result" not in parsed and "error" not in parsed:
                            raise _failure("muse serve returned an invalid reply")
                        awaited["reply"] = parsed
                if len(line) > MAX_LINE_BYTES:
                    raise _failure("muse serve exceeded its output limit")

        def send(message: dict[str, object]) -> None:
            payload = json.dumps(message, separators=(",", ":")).encode() + b"\n"
            with _sigpipe_ignored():
                try:
                    stdin.write(payload)
                    stdin.flush()
                except (BrokenPipeError, OSError) as error:
                    raise _failure("muse serve closed its input") from error

        def request(request_id: int, method: str, params: dict[str, object]):
            awaited.clear()
            send(
                {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
            )
            while time.monotonic() < deadline:
                pump(min(0.1, max(0.0, deadline - time.monotonic())), request_id)
                reply = awaited.pop("reply", None)
                if isinstance(reply, dict):
                    return reply
                if process.poll() is not None and not active.get_map():
                    detail = stderr_tail.decode(errors="replace").strip()
                    raise _failure(detail or "muse serve exited before responding")
            raise _failure(f"muse serve timed out waiting for {method}")

        def error_text(reply: dict[str, object]) -> str:
            error = reply.get("error")
            message = error.get("message") if isinstance(error, dict) else None
            return message if isinstance(message, str) and message else "unknown error"

        reply = request(
            1,
            "initialize",
            {"clientInfo": {"name": "agent_fork", "version": client_version}},
        )
        if "error" in reply:
            raise _failure(f"initialize failed: {error_text(reply)}")
        send({"jsonrpc": "2.0", "method": "initialized", "params": {}})
        reply = request(
            2,
            "session/fork",
            {
                "commandId": _uuid7(),
                "sessionId": parent_session_id,
                "excludeItems": True,
            },
        )
        if "error" in reply:
            raise _failure(f"session/fork failed: {error_text(reply)}")
        result = reply.get("result")
        session = result.get("session") if isinstance(result, dict) else None
        fork_id = session.get("sessionId") if isinstance(session, dict) else None
        if not _canonical(fork_id) or fork_id == parent_session_id.lower():
            raise _failure("muse serve returned an unsupported fork result")
        assert isinstance(fork_id, str)
        # The fork exists from here on and Muse cannot delete it, so a failure
        # to leave it cleanly is a warning, not a failure: opening the fork
        # beats losing it. Its only cost is an "ended abnormally" notice on the
        # fork's first resume.
        try:
            left = request(
                3,
                "session/leave",
                {"commandId": _uuid7(), "sessionId": fork_id, "stop": True},
            )
            if "error" in left and warn is not None:
                warn(f"Muse fork {fork_id} was not left cleanly: {error_text(left)}")
        except MuseForkError as error:
            if warn is not None:
                warn(f"Muse fork {fork_id} was not left cleanly: {error}")

        def drain() -> None:
            closing = time.monotonic() + SHUTDOWN_TIMEOUT
            while process.poll() is None and time.monotonic() < closing:
                pump(0.1, None)

        with _sigpipe_ignored():
            try:
                stdin.close()
            except OSError:
                pass
        try:
            drain()
        except MuseForkError:
            pass
        return fork_id
    except OSError as error:
        raise _failure(str(error)) from error
    finally:
        with _sigpipe_ignored():
            try:
                stdin.close()
            except OSError:
                pass
        if selector is not None:
            selector.close()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2.0)
        process.stdout.close()
        process.stderr.close()
