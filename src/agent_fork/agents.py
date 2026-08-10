"""Agent identity detection and, later, native-fork preflight/templates."""

from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from agent_fork.errors import (
    AgentDetectionError,
    AgentPreflightError,
    PreconditionError,
)
from agent_fork.git import PRODUCT_GIT_MIN

AgentName = Literal["claude", "codex"]


@dataclass(frozen=True)
class AgentContext:
    agent: AgentName
    parent_session_id: str


@dataclass(frozen=True)
class PreflightResult:
    agent: AgentName
    version: tuple[int, int, int]
    notices: tuple[str, ...]
    verify: bool = True


CLAUDE_FORK_MIN = (2, 0, 73)
CLAUDE_RELIABLE_MIN = (2, 1, 100)
CODEX_FORK_MIN = (0, 81, 0)
CODEX_ENV_MIN = (0, 95, 0)
_VERSION = re.compile(r"(?<!\d)(\d+)\.(\d+)(?:\.(\d+))?")


def parse_version(output: str) -> tuple[int, int, int]:
    match = _VERSION.search(output)
    if match is None:
        raise ValueError(f"unable to parse version from {output!r}")
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch or 0)


def _render(version: tuple[int, int, int]) -> str:
    return ".".join(str(part) for part in version)


def _diagnosis(message: str) -> AgentPreflightError:
    return AgentPreflightError(f"{message}; run agent-fork doctor for diagnostics")


def _codex_home(env: Mapping[str, str]) -> Path:
    configured = env.get("CODEX_HOME")
    if configured:
        return Path(configured).expanduser()
    return Path(env.get("HOME", "~")).expanduser() / ".codex"


def codex_rollout_exists(context: AgentContext, env: Mapping[str, str]) -> bool:
    pattern = f"sessions/*/*/*/rollout-*-{context.parent_session_id}.jsonl"
    return any(_codex_home(env).glob(pattern))


def preflight_agent(
    context: AgentContext,
    env: Mapping[str, str],
    *,
    executable: str | None = None,
    version_output: str | None = None,
) -> PreflightResult:
    """Refuse unsupported native forks before any repository mutation."""
    binary = (
        executable
        if executable is not None
        else shutil.which(context.agent, path=env.get("PATH"))
    )
    if not binary:
        raise _diagnosis(
            f"detected agent={context.agent} session={context.parent_session_id}, "
            f"but required {context.agent} CLI is missing from PATH"
        )
    if version_output is None:
        completed = subprocess.run(
            [binary, "--version"], env=dict(env), capture_output=True, text=True
        )
        if completed.returncode != 0:
            raise _diagnosis(
                f"detected {context.agent} CLI at {binary}, but --version failed"
            )
        version_output = completed.stdout or completed.stderr
    try:
        version = parse_version(version_output)
    except ValueError as error:
        raise _diagnosis(
            f"detected {context.agent} CLI at {binary}, but its version was unreadable"
        ) from error

    notices: list[str] = []
    if context.agent == "claude":
        if version < CLAUDE_FORK_MIN:
            raise _diagnosis(
                f"detected Claude {_render(version)}; pinned-session fork requires "
                f">={_render(CLAUDE_FORK_MIN)}"
            )
        if version < CLAUDE_RELIABLE_MIN:
            notices.append(
                f"Claude {_render(version)} is below the reliable worktree-resume "
                f"band {_render(CLAUDE_RELIABLE_MIN)}"
            )
    else:
        if version < CODEX_FORK_MIN:
            raise _diagnosis(
                f"detected Codex {_render(version)}; fork requires "
                f">={_render(CODEX_FORK_MIN)}"
            )
        if version < CODEX_ENV_MIN:
            raise _diagnosis(
                f"detected Codex {_render(version)}; CODEX_THREAD_ID support requires "
                f">={_render(CODEX_ENV_MIN)}"
            )
        if not codex_rollout_exists(context, env):
            raise _diagnosis(
                f"detected Codex {_render(version)}, but parent rollout "
                f"{context.parent_session_id} is not flushed under {_codex_home(env)}"
            )
    return PreflightResult(context.agent, version, tuple(notices))


def preflight_git(
    version_output: str, *, force: bool = False, verify: bool = True
) -> tuple[str, ...]:
    """Enforce PRODUCT_GIT_MIN; --force overrides only this named check."""
    try:
        installed = parse_version(version_output)
    except ValueError as error:
        raise PreconditionError(
            "git_version_unsupported",
            "unable to determine installed Git version; upgrade Git and re-run",
        ) from error
    if installed >= PRODUCT_GIT_MIN:
        return ()
    message = (
        f"installed Git {_render(installed)} is below PRODUCT_GIT_MIN "
        f"{_render(PRODUCT_GIT_MIN)}; upgrade Git and re-run agent-fork"
    )
    if not force:
        raise PreconditionError("git_version_unsupported", message)
    if not verify:
        raise ValueError("Git-floor force override must not disable verification")
    return (f"warning: --force overrides Git floor only: {message}",)


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
