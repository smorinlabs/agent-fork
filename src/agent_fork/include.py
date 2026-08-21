"""Post-verification .worktreeinclude and setup-hook support."""

from __future__ import annotations

import fnmatch
import hashlib
import os
import shutil
import signal
import stat
import subprocess
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from agent_fork.git import GitCommandError, run_git, signal_process_group
from agent_fork.text import escape_terminal_text

SETUP_HOOK_RELATIVE_PATH = ".agent-fork/worktree-setup.sh"
SETUP_HOOK_POLICIES = ("tracked", "any", "off")
DEFAULT_SETUP_HOOK_POLICY = "tracked"
DEFAULT_SETUP_HOOK_TIMEOUT = 300
OUTPUT_TAIL_BYTES = 4096
OVERRIDE_HINT = "run it anyway with --setup-hook-policy any"

# The active hook process, mirroring `git._ACTIVE` so `rollback.interrupt()`
# can reach a running hook's process group during signal cleanup.
_ACTIVE = threading.local()


@dataclass(frozen=True)
class IncludeResult:
    copied: tuple[str, ...]
    notices: tuple[str, ...]


@dataclass(frozen=True)
class SetupHookPolicy:
    """The resolved execution policy for one setup-hook step."""

    mode: str = DEFAULT_SETUP_HOOK_POLICY
    timeout_seconds: int = DEFAULT_SETUP_HOOK_TIMEOUT


@dataclass(frozen=True)
class SetupHookResult:
    """Everything observable about one setup-hook step, run or not."""

    path: str
    present: bool
    policy: str
    eligibility: str
    status: str
    reason: str | None = None
    exit_code: int | None = None
    timed_out: bool = False
    duration_seconds: float | None = None
    timeout_seconds: int = DEFAULT_SETUP_HOOK_TIMEOUT
    stdout_tail: str = ""
    stderr_tail: str = ""
    stdout_bytes: int = 0
    stderr_bytes: int = 0
    truncated: bool = False
    notices: tuple[str, ...] = ()

    def document(self) -> dict[str, object]:
        """One stable machine shape, emitted whether or not the hook ran."""
        return {
            "path": self.path,
            "present": self.present,
            "policy": self.policy,
            "eligibility": self.eligibility,
            "status": self.status,
            "reason": self.reason,
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "duration_seconds": self.duration_seconds,
            "timeout_seconds": self.timeout_seconds,
            "output": {
                "stdout": self.stdout_tail,
                "stderr": self.stderr_tail,
                "stdout_bytes": self.stdout_bytes,
                "stderr_bytes": self.stderr_bytes,
                "truncated": self.truncated,
            },
        }


def _patterns(parent: Path) -> tuple[str, ...]:
    source = parent / ".worktreeinclude"
    if not source.is_file():
        return ()
    return tuple(
        line.strip()
        for line in source.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def _matches(path: str, patterns: tuple[str, ...]) -> bool:
    return any(
        fnmatch.fnmatchcase(path, pattern)
        or fnmatch.fnmatchcase(path, pattern.rstrip("/") + "/**")
        for pattern in patterns
    )


def copy_worktree_includes(
    parent: Path, child: Path, *, env: Mapping[str, str] | None = None
) -> IncludeResult:
    """Copy matching ignored files, without overwriting materialized destinations."""
    patterns = _patterns(parent)
    if not patterns:
        return IncludeResult((), ())
    ignored = run_git(
        parent,
        ["ls-files", "--others", "--ignored", "--exclude-standard", "-z"],
        env=env,
    ).stdout
    copied: list[str] = []
    notices: list[str] = []
    child_root = child.resolve()
    for raw in ignored.split(b"\0"):
        if not raw:
            continue
        relative = os.fsdecode(raw)
        if not _matches(relative, patterns):
            continue
        source = parent / relative
        destination = (child / relative).resolve(strict=False)
        if child_root not in destination.parents:
            notices.append(
                f"skipped unsafe .worktreeinclude path: "
                f"{escape_terminal_text(relative)}"
            )
            continue
        if destination.exists() or destination.is_symlink():
            continue
        info = source.lstat()
        destination.parent.mkdir(parents=True, exist_ok=True)
        if stat.S_ISLNK(info.st_mode):
            destination.symlink_to(os.readlink(source))
        elif stat.S_ISREG(info.st_mode):
            shutil.copy2(source, destination, follow_symlinks=False)
        else:
            notices.append(
                f"skipped unsupported .worktreeinclude path: "
                f"{escape_terminal_text(relative)}"
            )
            continue
        copied.append(relative)
    return IncludeResult(tuple(copied), tuple(notices))


def terminate_active_setup_hook() -> None:
    """Terminate the current setup-hook process group during signal cleanup."""
    process = getattr(_ACTIVE, "process", None)
    if process is None:
        return
    signal_process_group(process, signal.SIGKILL)


def _reap(process: subprocess.Popen[bytes]) -> tuple[str, ...]:
    """Escalate SIGTERM then SIGKILL over the hook's whole process group.

    Identical ladder to ``git.run_git``'s: a hook's descendants share its
    session, so signalling the group is what actually reaches a backgrounded
    grandchild. Cleanup stays best-effort so the original timeout or
    interruption remains the observable outcome.
    """
    signal_process_group(process, signal.SIGTERM)
    try:
        process.wait(timeout=1)
        return ()
    except subprocess.TimeoutExpired:
        pass
    signal_process_group(process, signal.SIGKILL)
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        return (
            f"setup hook process group {process.pid} did not exit after SIGKILL; "
            "surviving processes may need manual cleanup",
        )
    return ()


def _hook_eligibility(
    child: Path, hook: Path, anchor: str, env: Mapping[str, str] | None
) -> tuple[str, str | None]:
    """Compare the bytes that would execute against the bytes committed at the anchor.

    Evaluated in the child, because ``materialize()`` carries the parent's
    uncommitted state across: a parent-side check would clear a committed copy
    while the child executes a modified one.

    Raw blob bytes are compared rather than ``git hash-object`` output, which
    applies the path's clean filter and could make differing bytes hash equal.
    """
    try:
        info = hook.lstat()
    except OSError:
        return "absent", None
    if not stat.S_ISREG(info.st_mode):
        return "not_a_regular_blob", "present but not a regular file on disk"
    try:
        listed = run_git(
            child,
            ["ls-tree", "-z", anchor, "--", SETUP_HOOK_RELATIVE_PATH],
            env=env,
        ).stdout
    except (GitCommandError, OSError):
        return "unchecked", "the fork anchor could not be read"
    entry = listed.split(b"\0")[0]
    if not entry:
        return "untracked", "present but not committed at the fork anchor"
    header = entry.partition(b"\t")[0].split(b" ")
    if len(header) != 3:
        return "unchecked", "the fork anchor entry could not be parsed"
    mode, _, oid = header
    if mode not in (b"100644", b"100755"):
        return (
            "not_a_regular_blob",
            "recorded at the fork anchor as a symlink or submodule, not a file",
        )
    try:
        committed = run_git(child, ["cat-file", "blob", oid.decode()], env=env).stdout
        on_disk = hook.read_bytes()
    except (GitCommandError, OSError):
        return "unchecked", "the committed hook bytes could not be read"
    if hashlib.sha256(committed).digest() != hashlib.sha256(on_disk).digest():
        return "modified", "present but modified since the fork anchor"
    return "eligible", None


def _bounded(raw: bytes) -> tuple[str, int, bool]:
    """Decode at most the trailing bound, reporting the pre-bound byte total."""
    return (
        raw[-OUTPUT_TAIL_BYTES:].decode("utf-8", "surrogateescape"),
        len(raw),
        len(raw) > OUTPUT_TAIL_BYTES,
    )


def run_setup_hook(
    repo_root: Path,
    child: Path,
    *,
    anchor: str,
    policy: SetupHookPolicy,
    env: Mapping[str, str] | None = None,
    progress: Callable[[str], None] | None = None,
) -> SetupHookResult:
    """Run the repository setup hook under the resolved policy, bounded and reaped.

    Failure stays non-fatal: ``REQ-24`` is a ``SHOULD``, so an ineligible,
    failing, or timed-out hook is reported, never raised.
    """
    hook = child / SETUP_HOOK_RELATIVE_PATH
    try:
        hook.lstat()
        present = True
    except OSError:
        present = False

    base = SetupHookResult(
        path=SETUP_HOOK_RELATIVE_PATH,
        present=present,
        policy=policy.mode,
        eligibility="unchecked",
        status="disabled",
        timeout_seconds=policy.timeout_seconds,
    )

    def announce(line: str) -> None:
        if progress is not None:
            progress(line)

    if policy.mode == "off":
        announce("setup hook: disabled (--setup-hook-policy off)")
        return base
    if not present:
        return replace(base, eligibility="absent", status="absent")
    eligibility, reason = _hook_eligibility(child, hook, anchor, env)
    if policy.mode == "tracked" and eligibility != "eligible":
        notice = f"setup hook skipped: {reason} ({OVERRIDE_HINT})"
        announce(f"setup hook: skipped — {reason} ({OVERRIDE_HINT})")
        return replace(
            base,
            eligibility=eligibility,
            status="skipped",
            reason=reason,
            notices=(notice,),
        )

    environment = dict(env or os.environ)
    environment.update(
        {
            "REPO_ROOT": str(repo_root.resolve()),
            "WORKTREE_PATH": str(child.resolve()),
        }
    )
    announce(
        f"setup hook: running {SETUP_HOOK_RELATIVE_PATH} "
        f"(timeout {policy.timeout_seconds}s)"
    )
    started = time.monotonic()
    try:
        process = subprocess.Popen(
            [str(hook)],
            cwd=child,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            # A new session is what makes `killpg` reach the hook's own
            # children; it also removes the controlling terminal, so stdin is
            # DEVNULL rather than an inherited TTY the hook would block on.
            start_new_session=True,
        )
    except OSError as error:
        detail = escape_terminal_text(str(error))
        announce(f"setup hook: failed to start: {detail}")
        return replace(
            base,
            eligibility=eligibility,
            status="failed_to_start",
            reason=detail,
            notices=(f"setup hook failed to start: {detail}",),
        )

    _ACTIVE.process = process
    timed_out = False
    reap_notices: tuple[str, ...] = ()
    try:
        try:
            stdout, stderr = process.communicate(timeout=policy.timeout_seconds)
        except subprocess.TimeoutExpired:
            reap_notices = _reap(process)
            # Every process that could still hold the pipe write end shared the
            # group and has been signalled, so this drain cannot hang.
            stdout, stderr = process.communicate()
            timed_out = True
    except BaseException:
        _reap(process)
        raise
    finally:
        if getattr(_ACTIVE, "process", None) is process:
            _ACTIVE.process = None

    duration = round(time.monotonic() - started, 3)
    stdout_text, stdout_bytes, stdout_truncated = _bounded(stdout)
    stderr_text, stderr_bytes, stderr_truncated = _bounded(stderr)
    notices = list(reap_notices)
    if timed_out:
        notices.insert(
            0,
            f"setup hook timed out after {policy.timeout_seconds}s; its process "
            "group was terminated. Changes it already made are not undone",
        )
        announce(
            f"setup hook: timed out after {policy.timeout_seconds}s; process group "
            "terminated. Changes it already made are not undone"
        )
    elif process.returncode != 0:
        detail = escape_terminal_text(stderr_text.strip() or stdout_text.strip())
        suffix = f": {detail}" if detail else ""
        notices.insert(0, f"setup hook failed (exit {process.returncode}){suffix}")
        announce(
            f"setup hook: failed (exit {process.returncode}) in {duration}s; fork kept"
        )
    else:
        announce(f"setup hook: ok in {duration}s")
    return replace(
        base,
        eligibility=eligibility,
        status="ran",
        exit_code=process.returncode,
        timed_out=timed_out,
        duration_seconds=duration,
        stdout_tail=escape_terminal_text(stdout_text),
        stderr_tail=escape_terminal_text(stderr_text),
        stdout_bytes=stdout_bytes,
        stderr_bytes=stderr_bytes,
        truncated=stdout_truncated or stderr_truncated,
        notices=tuple(notices),
    )
