"""The sole PATH-resolved Git subprocess primitive."""

from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

PRODUCT_GIT_MIN = (2, 19, 0)


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
    completed = subprocess.run(
        command,
        env=dict(env) if env is not None else None,
        input=input_bytes,
        capture_output=True,
    )
    result = GitResult(
        args=tuple(args),
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
    if check and result.returncode != 0:
        raise GitCommandError(result)
    return result
