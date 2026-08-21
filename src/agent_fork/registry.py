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


def add_entry(
    entry: RegistryEntry,
    *,
    env: Mapping[str, str] | None = None,
    timeout: float = DEFAULT_LOCK_TIMEOUT,
) -> list[RegistryEntry]:
    """Record a fork, replacing only records this repository provably owns.

    A same-named record is replaced when it carries this repository's
    identity, and otherwise left alone. Nothing here consults live worktrees:
    a record that merely stores a matching path and branch has not shown it
    belongs here, because two repositories can hold that same pair.

    Returns the records this call displaced, so a caller that has to undo the
    fork can put them back rather than leaving the user's earlier fork
    unregistered.
    """
    path = registry_path(env)
    displaced: list[RegistryEntry] = []
    with registry_lock(path, timeout=timeout):
        kept: list[RegistryEntry] = []
        for item in _decode(path):
            same_repository = (
                item.repository is not None
                and entry.repository is not None
                and item.repository == entry.repository
            )
            if item.name == entry.name and same_repository:
                displaced.append(item)
                continue
            # A record carrying no repository is not backfilled and is not
            # replaced (owner decision 2026-08-20). Matching a live worktree
            # does not show the record belongs to this repository: two
            # repositories can hold the same path on the same branch name,
            # which the `central` worktree layout makes ordinary because it
            # keys on a repository's basename alone. Writing an identity on
            # that evidence would manufacture the ownership it cannot prove.
            kept.append(item)
        kept.append(entry)
        _atomic_write(path, kept)
    return displaced


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


def undo_add(
    inserted: RegistryEntry,
    displaced: list[RegistryEntry],
    *,
    env: Mapping[str, str] | None = None,
    timeout: float = DEFAULT_LOCK_TIMEOUT,
) -> None:
    """Reverse one `add_entry` in a single locked step.

    Removes the record identified by `token` and puts back exactly the records
    that call displaced. Deliberately does not reuse the replacement rule:
    re-adding through `add_entry` would apply it a second time and could
    delete a record another process registered in the meantime. Records added
    concurrently under other names are preserved untouched.

    Absence of the inserted record has two very different causes, and they are
    distinguished by whether a *successor* exists — another record with the
    same repository and name:

    - **Superseded.** Another fork took the name while this one was failing.
      That record is the live one now, and putting back what this call
      displaced would leave two records under one name, making a later cleanup
      ambiguous rather than repairing anything. Do nothing.
    - **Cleaned up.** Someone removed the fork this call inserted. No
      successor holds the name, so the record this call displaced is still the
      right one to restore, and skipping it would silently unregister a
      worktree that still exists.
    """
    path = registry_path(env)
    token = inserted.token()
    with registry_lock(path, timeout=timeout):
        entries = _decode(path)
        if not any(item.token() == token for item in entries):
            superseded = any(
                item.name == inserted.name
                and item.repository is not None
                and item.repository == inserted.repository
                for item in entries
            )
            if superseded:
                return
        remaining = [item for item in entries if item.token() != token]
        present = {item.token() for item in remaining}
        remaining.extend(item for item in displaced if item.token() not in present)
        _atomic_write(path, remaining)


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
