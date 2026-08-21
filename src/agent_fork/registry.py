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
    live: LivePairs = frozenset(),
    env: Mapping[str, str] | None = None,
    timeout: float = DEFAULT_LOCK_TIMEOUT,
) -> None:
    """Record a fork, refusing rather than displacing a live one.

    A record with this repository's identity and this name is replaced only
    when its worktree is **gone**, which orphans nothing. When that worktree
    is still there, the fork refuses: replacing the record would leave real
    work on disk with nothing pointing at it — A3's own fault, silent
    clobbering, surviving inside a single repository after scoping fixed it
    between them.

    `live` is used here to *refuse*, never to authorize, which is why a stale
    reading is safe: it can only make this refusal fire when it need not, and
    can never suppress it. Nothing is displaced, so nothing needs restoring
    if the caller later has to undo the fork.

    A record carrying no repository is never touched: matching a live worktree
    does not show it belongs here, since two repositories can hold one path on
    one branch name — ordinary under the `central` worktree layout, which keys
    on a repository's basename alone.
    """
    path = registry_path(env)
    with registry_lock(path, timeout=timeout):
        kept: list[RegistryEntry] = []
        for item in _decode(path):
            same_fork = (
                item.name == entry.name
                and item.repository is not None
                and entry.repository is not None
                and item.repository == entry.repository
            )
            if same_fork:
                # A record naming the same worktree and branch as the fork
                # being recorded describes this very slot, not a second fork.
                # Its liveness is the *new* worktree, which the caller just
                # created, so refusing here would block every re-fork of a
                # name whose worktree was removed outside agent-fork.
                same_slot = (
                    item.worktree == entry.worktree and item.branch == entry.branch
                )
                if not same_slot and is_live(item, live):
                    raise PreconditionError(
                        "conflict_fork_registered",
                        f"fork {item.name!r} is already registered for this "
                        f"repository at {item.worktree}; remove it first, or "
                        "choose another name",
                    )
                # Its worktree is gone, so the record describes nothing.
                continue
            kept.append(item)
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
