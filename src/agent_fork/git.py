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

_INJECTED_CONFIG_NAMES = frozenset({"GIT_CONFIG_COUNT", "GIT_CONFIG_PARAMETERS"})
_INJECTED_CONFIG_PREFIXES = ("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")


def without_config_injection(env: Mapping[str, str] | None) -> dict[str, str]:
    """Drop inline Git configuration injected through the environment.

    Two channels do this. `GIT_CONFIG_COUNT` with
    `GIT_CONFIG_KEY_<n>`/`GIT_CONFIG_VALUE_<n>` adds settings that outrank every
    configuration file, and `GIT_CONFIG_PARAMETERS` — which Git uses internally
    to propagate `-c` to subprocesses — does the same. Either silently overrides
    what the repository and the user actually configured, and nothing in this
    tool needs them.

    Both were shown to produce the same real divergence: injected
    `core.symlinks=false` turns a committed symlink into a regular file in the
    child worktree, while the fork reports success. Stripping only the first
    channel left the second open, so both are removed.

    `GIT_CONFIG_GLOBAL` and `GIT_CONFIG_SYSTEM` are deliberately preserved.
    They name configuration *files*, which is how tooling — including this
    project's own test harness — deliberately controls Git; discarding them
    would amount to ignoring the user's configuration rather than protecting
    it.
    """
    source = os.environ if env is None else env
    return {
        name: value
        for name, value in source.items()
        if name not in _INJECTED_CONFIG_NAMES
        and not name.startswith(_INJECTED_CONFIG_PREFIXES)
    }


def signal_process_group(
    process: subprocess.Popen[bytes], signum: signal.Signals
) -> None:
    """Signal one owned process group without masking an active exception.

    Made public for the repository setup hook (A12) and kept public for that
    history; ``T-RBK-07`` pins the macOS ``EPERM`` handling below. A12's gate-6
    review then found the early return on an already-exited leader wrong for a
    hook, whose backgrounded children are the whole point of signalling, so
    ``include`` now carries a deliberately divergent ``_signal_hook_group()``.
    Git spawns nothing that outlives it, so this gate stays correct here.
    """
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signum)
    except ProcessLookupError:
        return
    except PermissionError:
        # macOS can report EPERM after another signal killed the group leader
        # but before the Popen object reaped it. Re-poll before falling back to
        # the direct child, and keep cleanup best-effort so the original
        # interruption remains observable.
        if process.poll() is not None:
            return
        try:
            process.send_signal(signum)
        except (ProcessLookupError, PermissionError):
            pass


def terminate_active_git() -> None:
    """Terminate the current Git process group during signal cleanup, if any."""
    process = getattr(_ACTIVE, "process", None)
    if process is None:
        return
    signal_process_group(process, signal.SIGKILL)


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
    config_pins: Sequence[tuple[str, str]] = (),
) -> GitResult:
    """Invoke `git` by name on every call so current PATH shims are observable.

    ``config_pins`` prepends ``-c key=value`` for each pair, before the
    subcommand. This is the one chokepoint every Git invocation passes
    through, which is why it is where recursive submodule commands pin
    semantics such as ``diff.ignoreSubmodules`` (A6's design doc). It is a
    distinct, explicit channel from the environment: `without_config_injection`
    below strips inline configuration injected through `GIT_CONFIG_COUNT` and
    friends (A2), and pins are not routed through that stripped environment.
    """
    command = (
        "git",
        *(flag for key, value in config_pins for flag in ("-c", f"{key}={value}")),
        "-C",
        str(cwd),
        *args,
    )
    process: subprocess.Popen[bytes] | None = None
    previous_mask = signal.pthread_sigmask(
        signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM}
    )
    restore_mask = True
    try:
        process = subprocess.Popen(
            command,
            env=without_config_injection(env),
            stdin=subprocess.PIPE if input_bytes is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        _ACTIVE.process = process
        signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
        restore_mask = False
        stdout, stderr = process.communicate(input=input_bytes)
    except BaseException:
        if process is not None:
            signal_process_group(process, signal.SIGTERM)
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                signal_process_group(process, signal.SIGKILL)
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    pass
        raise
    finally:
        if restore_mask:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
        if process is not None and getattr(_ACTIVE, "process", None) is process:
            _ACTIVE.process = None
    assert process is not None
    result = GitResult(
        args=tuple(args),
        returncode=process.returncode,
        stdout=stdout,
        stderr=stderr,
    )
    if check and result.returncode != 0:
        raise GitCommandError(result)
    return result
