"""Versioned XDG provenance claims for agent-created sessions."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

from agent_fork.registry import registry_lock

LINEAGE_VERSION = 1


@dataclass(frozen=True)
class LineageClaim:
    agent: str
    child_session_id: str
    parent_session_id: str
    created_at: str
    name: str | None = None
    branch: str | None = None
    worktree: str | None = None

    @classmethod
    def create(
        cls,
        *,
        agent: str,
        child_session_id: str,
        parent_session_id: str,
        name: str | None = None,
        branch: str | None = None,
        worktree: Path | None = None,
    ) -> LineageClaim:
        created = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        return cls(
            agent,
            child_session_id,
            parent_session_id,
            created,
            name,
            branch,
            str(worktree.resolve()) if worktree is not None else None,
        )


def lineage_path(env: Mapping[str, str] | None = None) -> Path:
    environment = os.environ if env is None else env
    base = environment.get("XDG_STATE_HOME")
    if base is None:
        base = str(Path(environment.get("HOME", "~")).expanduser() / ".local/state")
    return Path(base).expanduser() / "agent-fork" / "session-lineage.json"


def _decode(path: Path) -> list[LineageClaim]:
    if not path.exists():
        return []
    document = json.loads(path.read_text())
    if document.get("version") != LINEAGE_VERSION:
        raise ValueError(f"invalid agent-fork lineage store: {path}")
    return [LineageClaim(**item) for item in document["claims"]]


def read_lineage(*, env: Mapping[str, str] | None = None) -> tuple[LineageClaim, ...]:
    path = lineage_path(env)
    try:
        return tuple(
            sorted(
                _decode(path),
                key=lambda item: (item.created_at, item.agent, item.child_session_id),
            )
        )
    except (OSError, TypeError, KeyError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid agent-fork lineage store: {path}") from error


def add_lineage(claim: LineageClaim, *, env: Mapping[str, str] | None = None) -> None:
    path = lineage_path(env)
    with registry_lock(path):
        claims = [
            item
            for item in _decode(path)
            if not (
                item.agent == claim.agent
                and item.child_session_id == claim.child_session_id
            )
        ]
        claims.append(claim)
        claims.sort(
            key=lambda item: (item.created_at, item.agent, item.child_session_id)
        )
        document = {"version": LINEAGE_VERSION, "claims": [asdict(x) for x in claims]}
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_name: str | None = None
        try:
            with NamedTemporaryFile(
                "w", encoding="utf-8", dir=path.parent, prefix=".lineage-", delete=False
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


def find_lineage(
    agent: str, child_session_id: str, *, env: Mapping[str, str] | None = None
) -> LineageClaim | None:
    for claim in read_lineage(env=env):
        if claim.agent == agent and claim.child_session_id == child_session_id:
            return claim
    return None


def remove_lineage(
    agent: str,
    child_session_id: str,
    *,
    env: Mapping[str, str] | None = None,
) -> None:
    path = lineage_path(env)
    with registry_lock(path):
        claims = [
            item
            for item in _decode(path)
            if not (item.agent == agent and item.child_session_id == child_session_id)
        ]
        document = {"version": LINEAGE_VERSION, "claims": [asdict(x) for x in claims]}
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, prefix=".lineage-", delete=False
        ) as temporary:
            temporary_name = temporary.name
            json.dump(document, temporary, sort_keys=True, separators=(",", ":"))
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        try:
            os.replace(temporary_name, path)
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            Path(temporary_name).unlink(missing_ok=True)
