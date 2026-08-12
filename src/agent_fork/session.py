"""Agent-neutral session inspection and assertion service."""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from agent_fork.errors import SessionValidationError
from agent_fork.lineage import find_lineage

CLAUDE_TRANSCRIPT_LIMIT = 1_048_576
CLAUDE_RECORD_LIMIT = 10_000


@dataclass(frozen=True)
class SessionEvidence:
    id: str
    id_source: str
    name: str | None = None
    name_status: str = "not_found"
    name_source: str | None = None
    id_status: str = "observed"

    def document(self) -> dict[str, object]:
        return {
            "id": self.id,
            "id_source": self.id_source,
            "id_status": self.id_status,
            "name": self.name,
            "name_status": self.name_status,
            "name_source": self.name_source,
        }


@dataclass(frozen=True)
class SessionInspection:
    agent: str | None
    current_session: SessionEvidence | None
    parent_session: SessionEvidence | None
    lineage_status: str
    notices: tuple[str, ...] = ()

    def document(self) -> dict[str, object]:
        return {
            "agent": self.agent,
            "current_session": (
                self.current_session.document() if self.current_session else None
            ),
            "parent_session": (
                self.parent_session.document() if self.parent_session else None
            ),
            "lineage": {
                "has_parent_evidence": self.parent_session is not None,
                "status": self.lineage_status,
            },
            "notices": list(self.notices),
        }


@dataclass(frozen=True)
class SessionAssertions:
    agent: str | None = None
    session_id: str | None = None
    parent_session_id: str | None = None
    has_parent: bool | None = None


def _claude_transcript(env: Mapping[str, str], cwd: Path, session_id: str) -> Path:
    root = Path(env.get("CLAUDE_CONFIG_DIR", Path(env.get("HOME", "~")) / ".claude"))
    encoded = re.sub(r"[^a-zA-Z0-9]", "-", str(cwd.resolve()))
    return root / "projects" / encoded / f"{session_id}.jsonl"


def _claude_name(
    env: Mapping[str, str], cwd: Path, session_id: str
) -> tuple[str | None, str]:
    if re.fullmatch(r"[A-Za-z0-9-]+", session_id) is None:
        return None, "not_found"
    path = _claude_transcript(env, cwd, session_id)
    root = Path(
        env.get("CLAUDE_CONFIG_DIR", Path(env.get("HOME", "~")) / ".claude")
    ).resolve()
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError):
        return None, "not_found"
    if not resolved.is_file() or path.is_symlink():
        return None, "not_found"
    with resolved.open("rb") as stream:
        data = stream.read(CLAUDE_TRANSCRIPT_LIMIT + 1)
    if len(data) > CLAUDE_TRANSCRIPT_LIMIT:
        return None, "unavailable"
    name: str | None = None
    for index, raw in enumerate(data.splitlines()):
        if index >= CLAUDE_RECORD_LIMIT:
            return None, "unavailable"
        try:
            record = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(record, dict) or record.get("sessionId") != session_id:
            continue
        value = record.get("customTitle") or record.get("agentName")
        if isinstance(value, str):
            name = value
            if record.get("customTitle") is not None:
                break
    return name, "resolved" if name is not None else "not_found"


def inspect_session(
    env: Mapping[str, str], *, cwd: Path | None = None
) -> SessionInspection:
    """Inspect ambient identity and bounded local evidence without mutation."""
    directory = Path.cwd() if cwd is None else cwd
    claude_id = env.get("CLAUDE_CODE_SESSION_ID")
    claude = env.get("CLAUDECODE") == "1" and bool(claude_id)
    codex_id = env.get("CODEX_THREAD_ID")
    codex = bool(codex_id)
    if claude and codex:
        return SessionInspection(
            None,
            None,
            None,
            "ambiguous",
            ("both Claude and Codex session signals are present",),
        )
    if not claude and not codex:
        return SessionInspection(None, None, None, "not_detected")
    notices: list[str] = []
    if claude:
        assert claude_id is not None
        name, name_status = _claude_name(env, directory, claude_id)
        try:
            claim = find_lineage("claude", claude_id, env=env)
        except ValueError as error:
            claim = None
            notices.append(str(error))
        inference = None
        if claim is None:
            try:
                from agent_fork.lineage_inference_store import (
                    find_inference,
                    inference_freshness,
                )

                inference = find_inference(claude_id, env=env)
                freshness = (
                    inference_freshness(inference, env=env)
                    if inference is not None
                    else None
                )
                if inference is not None and freshness != "current_at_last_analysis":
                    notices.append("recorded Claude parent inference is stale")
                    inference = None
                elif inference is not None:
                    notices.append(
                        "recorded Claude parent inference is current only at its last "
                        "explicit analysis"
                    )
            except ValueError as error:
                notices.append(str(error))
        if claim is not None and name is None and claim.name is not None:
            name = claim.name
            name_status = "claimed"
        current = SessionEvidence(
            claude_id,
            "CLAUDE_CODE_SESSION_ID",
            name,
            name_status,
            "claude-transcript"
            if name_status == "resolved"
            else "agent-fork-lineage"
            if name_status == "claimed"
            else None,
        )
        parent = (
            SessionEvidence(
                claim.parent_session_id,
                "agent-fork-lineage",
                id_status="claimed",
            )
            if claim is not None
            else SessionEvidence(
                inference.parent_session_id,
                "agent-fork-lineage-inference",
                id_status="inferred",
            )
            if inference is not None
            else None
        )
        return SessionInspection(
            "claude",
            current,
            parent,
            "claimed"
            if claim is not None
            else inference.status
            if inference
            else "not_found",
        )

    assert codex_id is not None
    binary = shutil.which("codex", path=env.get("PATH"))
    if binary is None:
        notices.append("Codex CLI is unavailable; name and lineage were not looked up")
        current = SessionEvidence(
            codex_id, "CODEX_THREAD_ID", name_status="unavailable"
        )
        return SessionInspection("codex", current, None, "unavailable", tuple(notices))
    try:
        from agent_fork.codex_app_server import read_thread

        thread = read_thread(binary, codex_id, env)
    except Exception as error:
        notices.append(str(error))
        current = SessionEvidence(
            codex_id, "CODEX_THREAD_ID", name_status="unavailable"
        )
        return SessionInspection("codex", current, None, "unavailable", tuple(notices))
    if thread is None:
        current = SessionEvidence(codex_id, "CODEX_THREAD_ID", name_status="not_found")
        return SessionInspection("codex", current, None, "not_found")
    current = SessionEvidence(
        codex_id,
        "CODEX_THREAD_ID",
        thread.name,
        "resolved" if thread.name is not None else "not_found",
        "codex-app-server",
    )
    parent: SessionEvidence | None = None
    if thread.forked_from_id is not None:
        parent_name: str | None = None
        parent_status = "not_found"
        try:
            parent_thread = read_thread(binary, thread.forked_from_id, env)
            if parent_thread is not None:
                parent_name = parent_thread.name
                parent_status = "resolved" if parent_name is not None else "not_found"
        except Exception as error:
            notices.append(str(error))
            parent_status = "unavailable"
        parent = SessionEvidence(
            thread.forked_from_id,
            "codex-app-server",
            parent_name,
            parent_status,
            "codex-app-server",
            "resolved",
        )
    return SessionInspection(
        "codex", current, parent, "resolved" if parent else "not_found", tuple(notices)
    )


def validate_session(
    inspection: SessionInspection, assertions: SessionAssertions
) -> dict[str, object]:
    """Assert requested facts, returning a stable success document."""
    checks: list[dict[str, object]] = []

    def check(name: str, expected: object, actual: object, passed: bool) -> None:
        checks.append(
            {"name": name, "expected": expected, "actual": actual, "passed": passed}
        )
        if not passed:
            raise SessionValidationError(
                f"session assertion {name} failed: expected {expected!r}, "
                f"got {actual!r}"
            )

    detected = inspection.current_session is not None and inspection.agent is not None
    check("session_detected", True, detected, detected)
    if assertions.agent is not None:
        check(
            "agent",
            assertions.agent,
            inspection.agent,
            inspection.agent == assertions.agent,
        )
    if assertions.session_id is not None:
        actual = inspection.current_session.id if inspection.current_session else None
        check(
            "session_id", assertions.session_id, actual, actual == assertions.session_id
        )
    if assertions.parent_session_id is not None:
        actual = inspection.parent_session.id if inspection.parent_session else None
        check(
            "parent_session_id",
            assertions.parent_session_id,
            actual,
            actual == assertions.parent_session_id,
        )
    if assertions.has_parent is not None:
        actual = inspection.parent_session is not None
        check(
            "has_parent", assertions.has_parent, actual, actual == assertions.has_parent
        )
    return {"valid": True, "assertions": checks, "session": inspection.document()}
