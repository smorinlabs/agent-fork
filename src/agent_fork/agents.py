"""Agent identity detection and, later, native-fork preflight/templates."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from agent_fork.errors import AgentDetectionError

AgentName = Literal["claude", "codex"]


@dataclass(frozen=True)
class AgentContext:
    agent: AgentName
    parent_session_id: str


def detect_agent(
    env: Mapping[str, str],
    *,
    explicit_agent: str | None = None,
    explicit_parent_session: str | None = None,
) -> AgentContext:
    """Resolve explicit identity first, otherwise use only the locked env signals."""
    if explicit_agent is not None:
        if explicit_agent not in {"claude", "codex"}:
            raise AgentDetectionError(
                f"unknown agent {explicit_agent!r}; choose --agent claude or codex"
            )
        parent = explicit_parent_session
        if parent is None:
            parent = (
                env.get("CLAUDE_CODE_SESSION_ID")
                if explicit_agent == "claude"
                else env.get("CODEX_THREAD_ID")
            )
        if not parent:
            raise AgentDetectionError(
                f"--agent {explicit_agent} requires --parent-session "
                "or its matching environment signal"
            )
        agent: AgentName = "claude" if explicit_agent == "claude" else "codex"
        return AgentContext(agent=agent, parent_session_id=parent)

    if explicit_parent_session is not None:
        raise AgentDetectionError("--parent-session requires an explicit --agent")

    claude_id = env.get("CLAUDE_CODE_SESSION_ID")
    claude = env.get("CLAUDECODE") == "1" and bool(claude_id)
    codex_id = env.get("CODEX_THREAD_ID")
    codex = bool(codex_id)

    if claude == codex:
        state = (
            "both Claude and Codex signals are present"
            if claude
            else "no agent signal is present"
        )
        raise AgentDetectionError(
            f"{state}; pass --agent and --parent-session explicitly"
        )
    if claude:
        return AgentContext(agent="claude", parent_session_id=claude_id or "")
    return AgentContext(agent="codex", parent_session_id=codex_id or "")
