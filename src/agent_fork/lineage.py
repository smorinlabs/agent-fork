"""Versioned XDG provenance claims for agent-created sessions."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from agent_fork.registry import registry_lock
from agent_fork.storage import atomic_write_json
from agent_fork.xdg import xdg_path

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
    return xdg_path(
        environment,
        "XDG_STATE_HOME",
        ".local/state",
        "agent-fork",
        "session-lineage.json",
    )


def _decode(path: Path) -> list[LineageClaim]:
    if not path.exists():
        return []
    try:
        document = json.loads(path.read_text())
        if document.get("version") != LINEAGE_VERSION:
            raise ValueError(f"invalid agent-fork lineage store: {path}")
        return [LineageClaim(**item) for item in document["claims"]]
    except (OSError, TypeError, KeyError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid agent-fork lineage store: {path}") from error


def read_lineage(*, env: Mapping[str, str] | None = None) -> tuple[LineageClaim, ...]:
    path = lineage_path(env)
    return tuple(
        sorted(
            _decode(path),
            key=lambda item: (item.created_at, item.agent, item.child_session_id),
        )
    )


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
        atomic_write_json(path, document, prefix=".lineage-")


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
        atomic_write_json(path, document, prefix=".lineage-")
