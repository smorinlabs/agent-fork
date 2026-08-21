"""Locked, atomic XDG registry for worktrees created by agent-fork."""

from __future__ import annotations

import fcntl
import json
import os
import time
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path

from agent_fork.errors import PreconditionError, RegistryBusyError
from agent_fork.models import RegistryEntry
from agent_fork.storage import atomic_write_json
from agent_fork.text import escape_terminal_text
from agent_fork.xdg import xdg_path

REGISTRY_VERSION = 2
SUPPORTED_REGISTRY_VERSIONS = (1, 2)
DEFAULT_LOCK_TIMEOUT = 5.0

# A (worktree, branch) pair observed live in a repository. Rows are confirmed
# against these; a row alone never authorizes anything.
LivePairs = frozenset[tuple[str, str]]


def registry_path(env: Mapping[str, str] | None = None) -> Path:
    environment = os.environ if env is None else env
    return xdg_path(
        environment, "XDG_STATE_HOME", ".local/state", "agent-fork", "forks.json"
    )


def _decode(path: Path) -> list[RegistryEntry]:
    """Decode v1 or v2 structurally. Never runs a subprocess.

    A v1 row has no repository, and none is inferred here: the only path it
    records is where its worktree was when the row was written, which is not
    evidence about what is there now.
    """
    if not path.exists():
        return []
    try:
        document = json.loads(path.read_text())
        if document.get("version") not in SUPPORTED_REGISTRY_VERSIONS:
            raise ValueError("unsupported registry version")
        return [RegistryEntry(**item) for item in document["forks"]]
    except (OSError, TypeError, KeyError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid agent-fork registry: {path}") from error


def _ordered(entries: list[RegistryEntry]) -> list[RegistryEntry]:
    # `repository` is nullable, so it is wrapped rather than sorted directly:
    # a bare None beside a str raises TypeError inside a sort key tuple.
    return sorted(
        entries,
        key=lambda item: (
            item.created_at,
            item.name,
            item.branch,
            item.repository is None,
            item.repository or "",
            item.worktree,
        ),
    )


@contextmanager
def registry_lock(path: Path, *, timeout: float = DEFAULT_LOCK_TIMEOUT):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError as error:
                if time.monotonic() >= deadline:
                    raise RegistryBusyError(
                        f"registry lock busy after {timeout:g}s: {lock_path}"
                    ) from error
                time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _atomic_write(path: Path, entries: list[RegistryEntry]) -> None:
    document = {
        "version": REGISTRY_VERSION,
        "forks": [item.to_registry_dict() for item in _ordered(entries)],
    }
    atomic_write_json(path, document, prefix=".forks-")


def read_registry(*, env: Mapping[str, str] | None = None) -> list[RegistryEntry]:
    return _ordered(_decode(registry_path(env)))


def match_live(entry: RegistryEntry, live: LivePairs) -> tuple[str, str] | None:
    """The observed pair this record corresponds to, or None.

    Returns the element *from the observation* rather than a boolean, so a
    caller that needs the worktree and branch takes them from what was seen
    rather than from the record. That is the whole difference between a
    confirmed fork and a remembered one.
    """
    wanted = (str(Path(entry.worktree).resolve()), entry.branch)
    for observed in live:
        if observed == wanted:
            return observed
    return None


def is_live(entry: RegistryEntry, live: LivePairs) -> bool:
    """The actionability predicate.

    A row is actionable only when its (worktree, branch) pair is present in a
    freshly observed worktree list. The row says what to look for; only the
    observation says whether it is still there.
    """
    return (str(Path(entry.worktree).resolve()), entry.branch) in live


def occupied_fork(
    name: str,
    repository: Path | str,
    *,
    env: Mapping[str, str] | None = None,
    entries: list[RegistryEntry] | None = None,
) -> RegistryEntry | None:
    """A record of this repository and name whose worktree is still on disk.

    Existence of the directory, not a Git probe, is the test. That is
    deliberate on three counts. It needs no subprocess, so it is cheap enough
    to evaluate inside the registry lock, which is what closes the window in
    which two forks of one name could each miss the other. It cannot produce a
    false negative for a worktree that is merely detached, on an unavailable
    mount, or switched to another branch — all cases a probe reports as "not
    live", and all cases where real work is sitting in that directory. And it
    errs toward refusing: a path occupied by something unrelated refuses too,
    which costs the user a rename and costs nobody their work.

    A record with no repository is never a match: it cannot show it belongs
    here, since two repositories can hold one path under one name.
    """
    records = _decode(registry_path(env)) if entries is None else entries
    for item in records:
        if (
            item.name == name
            and item.repository is not None
            and item.repository == str(repository)
            and Path(item.worktree).exists()
        ):
            return item
    return None


def add_entry(
    entry: RegistryEntry,
    *,
    env: Mapping[str, str] | None = None,
    timeout: float = DEFAULT_LOCK_TIMEOUT,
) -> None:
    """Record a fork, refusing rather than displacing one that still exists.

    A record of this repository and name is replaced only when its worktree is
    **gone**, which orphans nothing. When that directory is still there the
    fork refuses: replacing the record would leave real work on disk with
    nothing naming it — A3's own fault, silent clobbering, surviving inside a
    single repository after scoping fixed it between them.

    Callers should refuse earlier, at preflight, so nothing has been created
    when a conflict is reported. This check exists because preflight cannot be
    the last word: another fork can register between it and here. Evaluating
    it under the lock is what makes that window closed rather than narrow.
    """
    path = registry_path(env)
    with registry_lock(path, timeout=timeout):
        entries = _decode(path)
        occupied = occupied_fork(entry.name, entry.repository or "", entries=entries)
        # A record naming the same worktree and branch as the entry being
        # written describes this very slot, not a second fork — the directory
        # it points at is the one the caller just created.
        if occupied is not None and (
            occupied.worktree != entry.worktree or occupied.branch != entry.branch
        ):
            raise PreconditionError(
                "conflict_fork_registered",
                f"fork {entry.name!r} is already registered for this repository "
                f"at {escape_terminal_text(occupied.worktree)}; remove it "
                "first, or choose another name",
            )
        kept = [
            item
            for item in entries
            if not (
                item.name == entry.name
                and item.repository is not None
                and entry.repository is not None
                and item.repository == entry.repository
            )
        ]
        kept.append(entry)
        _atomic_write(path, kept)


def require_single(token: tuple[object, ...], *, env: Mapping[str, str] | None) -> None:
    """Assert the registry still holds exactly one record with this token.

    Call inside a held registry lock. Advisory locks are per open file
    description, so a helper that took the lock itself would contend with its
    own caller and fail after the bounded wait.
    """
    matches = [item for item in _decode(registry_path(env)) if item.token() == token]
    if len(matches) != 1:
        raise PreconditionError(
            "cleanup_registry_stale" if not matches else "cleanup_registry_ambiguous",
            f"registry holds {len(matches)} records matching the selected fork; "
            "expected exactly one",
        )


def remove_locked(token: tuple[object, ...], *, env: Mapping[str, str] | None) -> None:
    """Remove exactly one record. Call inside a held registry lock."""
    path = registry_path(env)
    require_single(token, env=env)
    _atomic_write(path, [item for item in _decode(path) if item.token() != token])


def remove_entry(
    token: tuple[object, ...],
    *,
    env: Mapping[str, str] | None = None,
    timeout: float = DEFAULT_LOCK_TIMEOUT,
) -> None:
    """Compare-and-swap removal for callers not already holding the lock."""
    with registry_lock(registry_path(env), timeout=timeout):
        remove_locked(token, env=env)


def find_candidates(
    target: str, *, env: Mapping[str, str] | None = None
) -> list[RegistryEntry]:
    """Every row a target could name, by fork name, branch, or worktree path.

    Deliberately unfiltered by repository: narrowing here would mean trusting a
    stored identity. The caller confirms candidates against live state.
    """
    candidate = str(Path(target).expanduser().resolve())
    return [
        entry
        for entry in read_registry(env=env)
        if target in {entry.name, entry.branch}
        or candidate == str(Path(entry.worktree).resolve())
    ]
