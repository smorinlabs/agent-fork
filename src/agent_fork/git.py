"""The sole PATH-resolved Git subprocess primitive."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

PRODUCT_GIT_MIN = (2, 19, 0)
_ACTIVE = threading.local()


def terminate_active_git() -> None:
    """Terminate the current Git process group during signal cleanup, if any."""
    process = getattr(_ACTIVE, "process", None)
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


@dataclass(frozen=True)
class GitResult:
    args: tuple[str, ...]
    returncode: int
    stdout: bytes
    stderr: bytes


class GitCommandError(RuntimeError):
    def __init__(self, result: GitResult):
        self.result = result
        message = result.stderr.decode(errors="replace").strip()
        super().__init__(message or f"git command failed with exit {result.returncode}")


def run_git(
    cwd: Path,
    args: Sequence[str],
    *,
    env: Mapping[str, str] | None = None,
    input_bytes: bytes | None = None,
    check: bool = True,
) -> GitResult:
    """Invoke `git` by name on every call so current PATH shims are observable."""
    command = ("git", "-C", str(cwd), *args)
    process = subprocess.Popen(
        command,
        env=dict(env) if env is not None else None,
        stdin=subprocess.PIPE if input_bytes is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    _ACTIVE.process = process
    try:
        stdout, stderr = process.communicate(input=input_bytes)
    except BaseException:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        raise
    finally:
        if getattr(_ACTIVE, "process", None) is process:
            _ACTIVE.process = None
    result = GitResult(
        args=tuple(args),
        returncode=process.returncode,
        stdout=stdout,
        stderr=stderr,
    )
    if check and result.returncode != 0:
        raise GitCommandError(result)
    return result
