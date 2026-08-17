"""Locked, atomic XDG registry for worktrees created by agent-fork."""

from __future__ import annotations

import fcntl
import json
import os
import time
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from tempfile import NamedTemporaryFile

from agent_fork.errors import PreconditionError, RegistryBusyError
from agent_fork.models import RegistryEntry

REGISTRY_VERSION = 2
SUPPORTED_REGISTRY_VERSIONS = (1, 2)
DEFAULT_LOCK_TIMEOUT = 5.0

# A (worktree, branch) pair observed live in a repository. Rows are confirmed
# against these; a row alone never authorizes anything.
LivePairs = frozenset[tuple[str, str]]


def registry_path(env: Mapping[str, str] | None = None) -> Path:
    environment = os.environ if env is None else env
    base = environment.get("XDG_STATE_HOME")
    if base is None:
        base = str(Path(environment.get("HOME", "~")).expanduser() / ".local/state")
    return Path(base).expanduser() / "agent-fork" / "forks.json"


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
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, prefix=".forks-", delete=False
        ) as temporary:
            temporary_name = temporary.name
            json.dump(document, temporary, sort_keys=True, separators=(",", ":"))
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, path)
        temporary_name = None
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


def read_registry(*, env: Mapping[str, str] | None = None) -> list[RegistryEntry]:
    return _ordered(_decode(registry_path(env)))


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
    """Record a fork, replacing only rows this repository provably owns.

    `live` is the invoking repository's worktree list. A same-named row is
    replaced when it carries this repository's identity, or when the predicate
    confirms it; a row that merely stores a matching path string is left alone,
    because that path may since have been taken by an unrelated repository.
    """
    path = registry_path(env)
    with registry_lock(path, timeout=timeout):
        kept: list[RegistryEntry] = []
        for item in _decode(path):
            same_repository = (
                item.repository is not None
                and entry.repository is not None
                and item.repository == entry.repository
            )
            confirmed = is_live(item, live)
            if item.name == entry.name and (same_repository or confirmed):
                continue
            # Backfill an identity onto a row this repository demonstrably
            # owns. The evidence is the live list, not the row's own path.
            if item.repository is None and confirmed and entry.repository:
                item = replace(item, repository=entry.repository)
            kept.append(item)
        kept.append(entry)
        _atomic_write(path, kept)


def remove_entry(
    token: tuple[str, ...],
    *,
    env: Mapping[str, str] | None = None,
    timeout: float = DEFAULT_LOCK_TIMEOUT,
) -> None:
    """Compare-and-swap removal: delete exactly the row that was selected.

    Refuses rather than removing when the registry no longer holds exactly one
    row matching the token, which means it changed after the caller chose.
    """
    path = registry_path(env)
    with registry_lock(path, timeout=timeout):
        entries = _decode(path)
        matches = [item for item in entries if item.token() == token]
        if len(matches) != 1:
            code = (
                "cleanup_registry_stale"
                if not matches
                else ("cleanup_registry_ambiguous")
            )
            raise PreconditionError(
                code,
                f"registry holds {len(matches)} records matching the selected "
                f"fork; expected exactly one",
            )
        _atomic_write(path, [item for item in entries if item.token() != token])


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
