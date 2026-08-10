"""Locked, atomic XDG registry for worktrees created by agent-fork."""

from __future__ import annotations

import fcntl
import json
import os
import time
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile

from agent_fork.errors import RegistryBusyError
from agent_fork.models import RegistryEntry

REGISTRY_VERSION = 1
DEFAULT_LOCK_TIMEOUT = 5.0


def registry_path(env: Mapping[str, str] | None = None) -> Path:
    environment = os.environ if env is None else env
    base = environment.get("XDG_STATE_HOME")
    if base is None:
        base = str(Path(environment.get("HOME", "~")).expanduser() / ".local/state")
    return Path(base).expanduser() / "agent-fork" / "forks.json"


def _decode(path: Path) -> list[RegistryEntry]:
    if not path.exists():
        return []
    try:
        document = json.loads(path.read_text())
        if document.get("version") != REGISTRY_VERSION:
            raise ValueError("unsupported registry version")
        return [RegistryEntry(**item) for item in document["forks"]]
    except (OSError, TypeError, KeyError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid agent-fork registry: {path}") from error


def _ordered(entries: list[RegistryEntry]) -> list[RegistryEntry]:
    return sorted(entries, key=lambda item: (item.created_at, item.name, item.branch))


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
        "forks": [item.to_dict() for item in _ordered(entries)],
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


def add_entry(
    entry: RegistryEntry,
    *,
    env: Mapping[str, str] | None = None,
    timeout: float = DEFAULT_LOCK_TIMEOUT,
) -> None:
    path = registry_path(env)
    with registry_lock(path, timeout=timeout):
        entries = _decode(path)
        entries = [item for item in entries if item.name != entry.name]
        entries.append(entry)
        _atomic_write(path, entries)


def remove_entry(
    name: str,
    *,
    env: Mapping[str, str] | None = None,
    timeout: float = DEFAULT_LOCK_TIMEOUT,
) -> None:
    path = registry_path(env)
    with registry_lock(path, timeout=timeout):
        _atomic_write(path, [item for item in _decode(path) if item.name != name])


def find_owned(
    target: str, *, env: Mapping[str, str] | None = None
) -> RegistryEntry | None:
    candidate = str(Path(target).expanduser().resolve())
    for entry in read_registry(env=env):
        if target in {entry.name, entry.branch} or candidate == str(
            Path(entry.worktree).resolve()
        ):
            return entry
    return None
