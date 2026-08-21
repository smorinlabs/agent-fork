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

from agent_fork.git import GitCommandError, run_git
from agent_fork.text import escape_terminal_text

SETUP_HOOK_RELATIVE_PATH = ".agent-fork/worktree-setup.sh"
SETUP_HOOK_POLICIES = ("tracked", "any", "off")
DEFAULT_SETUP_HOOK_POLICY = "tracked"
DEFAULT_SETUP_HOOK_TIMEOUT = 300
OUTPUT_TAIL_BYTES = 4096
OVERRIDE_HINT = "run it anyway with --setup-hook-policy any"
# How long the hook's output pipes may stay open after the hook's own process
# has exited. Only something the hook started can still hold them, and one that
# left the process group cannot be killed, so this is the bound on waiting.
SETUP_HOOK_DRAIN_SECONDS = 2.0
LEFTOVER_NOTICE = (
    "setup hook left at least one process running; agent-fork stopped waiting "
    "for it and did not terminate it"
)
_REAP_GRACE_SECONDS = 1.0
_POLL_SLICE_SECONDS = 0.05
# Exactly the signals `rollback.run_with_rollback()` handles, blocked around
# the spawn so an interrupt cannot land between the hook starting and the
# record that makes it reachable. Blocking is per-thread and this runs on the
# main thread, which is where CPython runs Python-level handlers.
_HANDLED_SIGNALS = frozenset({signal.SIGINT, signal.SIGTERM})

# The active hook group, mirroring `git._ACTIVE` so `rollback.interrupt()`
# can reach a running hook's process group during signal cleanup.
_ACTIVE = threading.local()


@dataclass
class _HookGroup:
    """One spawned hook, plus the one-way fact that its group has emptied.

    ``emptied`` is a latch, never cleared. A PID is reserved as its process
    group's id only while the group still holds a member; once the last one
    exits the kernel may reuse that PID for an unrelated process, and a
    ``killpg`` issued afterwards would signal a stranger. Every signalling path
    — the reap ladder's SIGKILL escalation and
    ``terminate_active_setup_hook()`` — reads this one record, so a single
    observation of emptiness retires the PID for all of them.
    """

    process: subprocess.Popen[bytes]
    emptied: bool = False


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
    # False when the hook outlived itself: a process still in its group, or one
    # that left the group and still held its output open when agent-fork
    # stopped waiting. Never a failure — the fork keeps going — but never
    # silent either, because the group is the unit this step can bound.
    descendants_cleared: bool = True
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
            "descendants_cleared": self.descendants_cleared,
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


def _signal_hook_group(group: _HookGroup, signum: signal.Signals) -> None:
    """Signal the hook's whole process group, whether or not its leader is alive.

    Deliberately narrower than ``git.signal_process_group()``, which returns
    before ``killpg`` whenever ``process.poll()`` shows the leader has exited.
    That gate is right for Git, whose children do not outlive it, and wrong
    here: a hook that backgrounds a process and returns leaves a group whose
    leader is gone and whose remaining members are exactly what needs the
    signal.

    Addressing the group by the leader's pid stays safe *while the group still
    holds a member*: the kernel reserves that pid as the group id for exactly
    that long, and no longer. Once the group has emptied the pid is free to
    name something unrelated, so ``_group_is_empty()`` runs first — both to
    honour the latch, which makes emptiness permanent, and to shrink the
    unavoidable check-to-signal gap to a single syscall.
    """
    if _group_is_empty(group):
        return
    process = group.process
    try:
        os.killpg(process.pid, signum)
    except ProcessLookupError:
        group.emptied = True
    except PermissionError:
        # macOS can report EPERM in the window between a member's exit and its
        # reaping. Cleanup stays best-effort so the original timeout or
        # interruption remains the observable outcome.
        if process.poll() is None:
            try:
                process.send_signal(signum)
            except (ProcessLookupError, PermissionError):
                pass


def _group_is_empty(group: _HookGroup) -> bool:
    """Report whether the hook's process group still holds any process.

    The latch is read before anything else: after the group has been seen
    empty, a probe that answers "alive" is a reused pid rather than a survivor,
    and believing it would put an unrelated process group back in range of the
    reap ladder.

    ``poll()`` runs before the probe so an unreaped leader — a zombie is still
    a group member as far as ``killpg`` is concerned — does not read as a
    survivor.
    """
    if group.emptied:
        return True
    group.process.poll()
    try:
        os.killpg(group.process.pid, 0)
    except ProcessLookupError:
        group.emptied = True
        return True
    except PermissionError:
        return False
    return False


def _await_empty_group(group: _HookGroup, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while True:
        if _group_is_empty(group):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(_POLL_SLICE_SECONDS)


def terminate_active_setup_hook() -> None:
    """Terminate the current setup-hook process group during signal cleanup."""
    group = getattr(_ACTIVE, "group", None)
    if group is None:
        return
    _signal_hook_group(group, signal.SIGKILL)


def _reap(group: _HookGroup) -> tuple[str, ...]:
    """Escalate SIGTERM then SIGKILL over the hook's whole process group.

    Escalation is decided by probing the group, not by waiting on the leader:
    ``process.wait()`` returns the moment the hook's own shell exits, which
    would skip the SIGKILL that its surviving children still need. Cleanup
    stays best-effort so the original timeout or interruption remains the
    observable outcome.
    """
    _signal_hook_group(group, signal.SIGTERM)
    if _await_empty_group(group, _REAP_GRACE_SECONDS):
        return ()
    _signal_hook_group(group, signal.SIGKILL)
    if _await_empty_group(group, _REAP_GRACE_SECONDS):
        return ()
    return (
        f"setup hook process group {group.process.pid} did not exit after "
        "SIGKILL; surviving processes may need manual cleanup",
    )


def _collect_output(
    process: subprocess.Popen[bytes],
    *,
    leader_deadline: float,
    drain_seconds: float,
) -> tuple[bytes, bytes, str]:
    """Read both of the hook's pipes to EOF under two independent bounds.

    ``leader_deadline`` is an absolute ``time.monotonic()`` value bounding how
    long the hook's own process may run. ``drain_seconds`` separately bounds how
    long its pipes may stay open *after* that process has exited.

    The bounds have to be separate because a pipe outlives the writer's parent.
    Reading "the pipes are still open" as "the hook is still running" reports a
    hook that finished in milliseconds as a timeout, and waiting for EOF with no
    bound at all never returns at all once a process has called ``setsid()`` and
    left the group where ``killpg`` could reach it.

    Returns ``(stdout, stderr, outcome)``, where outcome is ``"completed"``
    (both pipes reached EOF), ``"timed_out"`` (the hook was still running at
    ``leader_deadline``), or ``"detached"`` (the hook exited but its output
    stayed open past ``drain_seconds``). Re-calling ``communicate()`` after a
    ``TimeoutExpired`` is the documented retry pattern: the buffers accumulate
    across calls, and the exception carries what has been read so far.
    """
    stdout = stderr = b""
    drain_deadline: float | None = None
    while True:
        limit = leader_deadline if drain_deadline is None else drain_deadline
        try:
            stdout, stderr = process.communicate(
                timeout=max(0.0, min(_POLL_SLICE_SECONDS, limit - time.monotonic()))
            )
            return stdout, stderr, "completed"
        except subprocess.TimeoutExpired as expired:
            stdout = expired.stdout or stdout
            stderr = expired.stderr or stderr
        if drain_deadline is None and process.poll() is not None:
            drain_deadline = time.monotonic() + drain_seconds
        elif time.monotonic() >= limit:
            return (
                stdout,
                stderr,
                "timed_out" if drain_deadline is None else "detached",
            )


def _abandon_pipes(process: subprocess.Popen[bytes]) -> None:
    """Let go of pipes a process outside the hook's group is holding open.

    Nothing else can close them. Once the writer has left the process group it
    is unreachable by ``killpg``, so releasing this end is the only bound
    available on this side.
    """
    for pipe in (process.stdout, process.stderr):
        if pipe is not None:
            try:
                pipe.close()
            except OSError:
                pass


def setup_hook_eligibility(
    worktree: Path,
    reference: str,
    *,
    reference_label: str = "the fork anchor",
    env: Mapping[str, str] | None = None,
) -> tuple[str, str | None]:
    """Compare the bytes that would execute against those committed at ``reference``.

    Evaluated in the worktree that would run the hook, because ``materialize()``
    carries the parent's uncommitted state across: a parent-side check would
    clear a committed copy while the child executes a modified one.

    Raw blob bytes are compared rather than ``git hash-object`` output, which
    applies the path's clean filter and could make differing bytes hash equal.

    ``reference_label`` names ``reference`` in the returned reason. ``fork``
    resolves its own anchor while ``doctor`` reads ``HEAD``, and on a detached
    HEAD those differ, so neither surface may borrow the other's wording.
    """
    hook = worktree / SETUP_HOOK_RELATIVE_PATH
    try:
        info = hook.lstat()
    except OSError:
        return "absent", None
    if not stat.S_ISREG(info.st_mode):
        return "not_a_regular_blob", "present but not a regular file on disk"
    try:
        listed = run_git(
            worktree,
            ["ls-tree", "-z", reference, "--", SETUP_HOOK_RELATIVE_PATH],
            env=env,
        ).stdout
    except (GitCommandError, OSError):
        return "unchecked", f"{reference_label} could not be read"
    entry = listed.split(b"\0")[0]
    if not entry:
        return "untracked", f"present but not committed at {reference_label}"
    header = entry.partition(b"\t")[0].split(b" ")
    if len(header) != 3:
        return "unchecked", f"the {reference_label} entry could not be parsed"
    mode, _, oid = header
    if mode not in (b"100644", b"100755"):
        return (
            "not_a_regular_blob",
            f"recorded at {reference_label} as a symlink or submodule, not a file",
        )
    try:
        committed = run_git(
            worktree, ["cat-file", "blob", oid.decode()], env=env
        ).stdout
        on_disk = hook.read_bytes()
    except (GitCommandError, OSError):
        return "unchecked", "the committed hook bytes could not be read"
    if hashlib.sha256(committed).digest() != hashlib.sha256(on_disk).digest():
        return "modified", f"present but modified since {reference_label}"
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
    eligibility, reason = setup_hook_eligibility(child, anchor, env=env)
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
    process: subprocess.Popen[bytes] | None = None
    group: _HookGroup | None = None
    spawn_error: OSError | None = None
    timed_out = False
    reap_notices: tuple[str, ...] = ()
    stdout = stderr = b""
    outcome = "completed"
    try:
        # The spawn and the registration are one critical section, held under a
        # blocked mask. `process = Popen(...)` evaluates the spawn before
        # binding the name, and CPython runs signal handlers between bytecodes,
        # so a handler firing in that gap would find a running hook registered
        # nowhere — reachable by neither `rollback.interrupt()` nor the ladder
        # below. Blocking defers such a signal to the `SIG_SETMASK` below,
        # which restores whatever mask the caller had rather than assuming it
        # was empty.
        restore_mask = signal.pthread_sigmask(signal.SIG_BLOCK, _HANDLED_SIGNALS)
        try:
            process = subprocess.Popen(
                [str(hook)],
                cwd=child,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                # A new session is what makes `killpg` reach the hook's own
                # children; it also removes the controlling terminal, so stdin
                # is DEVNULL rather than an inherited TTY the hook would block
                # on.
                start_new_session=True,
                # A signal mask is inherited across fork and survives exec, so
                # without this the hook would run unable to receive the reap
                # ladder's SIGTERM at all — only the SIGKILL escalation would
                # land, and a hook trapping SIGTERM to shut down in order would
                # never see it. `preexec_fn` runs in the forked child before
                # exec; its documented hazard is other threads holding locks at
                # fork time, and agent-fork spawns hooks from a single-threaded
                # CLI.
                preexec_fn=lambda: signal.pthread_sigmask(
                    signal.SIG_SETMASK, restore_mask
                ),
            )
        except OSError as error:
            spawn_error = error
        else:
            group = _HookGroup(process)
            _ACTIVE.group = group
        finally:
            # Inside the `except BaseException` block, so the signal delivered
            # right here lands on the reap path with the group registered.
            signal.pthread_sigmask(signal.SIG_SETMASK, restore_mask)
        if process is not None and group is not None:
            stdout, stderr, outcome = _collect_output(
                process,
                leader_deadline=started + policy.timeout_seconds,
                drain_seconds=SETUP_HOOK_DRAIN_SECONDS,
            )
            if outcome == "timed_out":
                timed_out = True
                reap_notices = _reap(group)
                # The hook itself is now dead, so only the drain bound applies.
                stdout, stderr, outcome = _collect_output(
                    process,
                    leader_deadline=time.monotonic(),
                    drain_seconds=SETUP_HOOK_DRAIN_SECONDS,
                )
    except BaseException:
        if group is not None:
            _reap(group)
        raise
    finally:
        if group is not None and getattr(_ACTIVE, "group", None) is group:
            _ACTIVE.group = None

    if spawn_error is not None:
        detail = escape_terminal_text(str(spawn_error))
        announce(f"setup hook: failed to start: {detail}")
        return replace(
            base,
            eligibility=eligibility,
            status="failed_to_start",
            reason=detail,
            notices=(f"setup hook failed to start: {detail}",),
        )
    assert process is not None
    assert group is not None

    if outcome == "detached":
        _abandon_pipes(process)
    descendants_cleared = outcome != "detached" and _group_is_empty(group)
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
    if not descendants_cleared:
        # Reported rather than escalated: the hook's own outcome above is still
        # the outcome, and killing a process the hook deliberately started is
        # not this step's call to make.
        if not reap_notices:
            notices.append(LEFTOVER_NOTICE)
        announce(f"setup hook: {LEFTOVER_NOTICE.removeprefix('setup hook ')}")
    return replace(
        base,
        eligibility=eligibility,
        status="ran",
        exit_code=process.returncode,
        timed_out=timed_out,
        descendants_cleared=descendants_cleared,
        duration_seconds=duration,
        stdout_tail=escape_terminal_text(stdout_text),
        stderr_tail=escape_terminal_text(stderr_text),
        stdout_bytes=stdout_bytes,
        stderr_bytes=stderr_bytes,
        truncated=stdout_truncated or stderr_truncated,
        notices=tuple(notices),
    )
