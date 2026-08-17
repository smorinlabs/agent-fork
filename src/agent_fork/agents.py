"""Agent identity detection and, later, native-fork preflight/templates."""

from __future__ import annotations

import re
import shlex
import shutil
import subprocess
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from agent_fork.errors import (
    AgentDetectionError,
    AgentPreflightError,
    PreconditionError,
    SessionNameAmbiguousError,
    SessionResolutionUnavailableError,
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
    context: AgentContext | None = None
    parent_session_name: str | None = None


@dataclass(frozen=True)
class LaunchCommand:
    command: str
    child_session_id: str | None
    extra_args: tuple[str, ...]

    def dry_run_text(self) -> str:
        rendered = ", ".join(repr(value) for value in self.extra_args) or "none"
        return (
            f"paste command: {self.command}\n"
            f"extra_args: {rendered}\n"
            "validation: local-only"
        )

    def json_fields(self) -> dict[str, object]:
        return {"command": self.command, "extra_args": list(self.extra_args)}


class UnsafeCommandInputError(ValueError):
    """A command input contains bytes that are unsafe to print to a terminal."""


CLAUDE_FORK_MIN = (2, 0, 73)
CLAUDE_RELIABLE_MIN = (2, 1, 100)
CODEX_FORK_MIN = (0, 81, 0)
CODEX_ENV_MIN = (0, 95, 0)
# A4: the flag tokens each rendered recipe emits. Version floors prove a flag
# arrived; they cannot prove it has since been removed, and neither vendor
# publishes a deprecation policy to reason from — so probe the installed help
# for these instead. T-PRE-26 keeps the lists in step with the renderer.
CLAUDE_RECIPE_FLAGS = ("--session-id", "--resume", "--fork-session", "-n")
CODEX_RECIPE_FLAGS = ("-C",)
_VERSION = re.compile(r"(?<![\d.])(\d+)\.(\d+)(?:\.(\d+))?")
_BIDI_CONTROLS = frozenset(
    {
        "\u061c",
        "\u200e",
        "\u200f",
        "\u202a",
        "\u202b",
        "\u202c",
        "\u202d",
        "\u202e",
        "\u2066",
        "\u2067",
        "\u2068",
        "\u2069",
    }
)


def parse_version(output: str) -> tuple[int, int, int]:
    match = _VERSION.search(output)
    if match is None:
        raise ValueError(f"unable to parse version from {output!r}")
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch or 0)


def version_tokens(output: str) -> tuple[tuple[int, int, int], ...]:
    """Every distinct version-like token in `output`, in order of appearance."""
    seen: list[tuple[int, int, int]] = []
    for match in _VERSION.finditer(output):
        major, minor, patch = match.groups()
        value = (int(major), int(minor), int(patch or 0))
        if value not in seen:
            seen.append(value)
    return tuple(seen)


def recipe_flags(agent: AgentName) -> tuple[str, ...]:
    return CLAUDE_RECIPE_FLAGS if agent == "claude" else CODEX_RECIPE_FLAGS


def missing_recipe_flags(agent: AgentName, help_output: str) -> tuple[str, ...]:
    """Recipe flags absent from `help_output`, in declared order."""
    return tuple(
        flag
        for flag in recipe_flags(agent)
        if re.search(rf"(?<![\w-]){re.escape(flag)}(?![\w-])", help_output) is None
    )


def read_help(agent: AgentName, binary: str, env: Mapping[str, str]) -> str | None:
    """Installed help text, or None when it cannot be read.

    Unreadable help is not evidence that a flag is gone, so callers stay
    silent on None rather than warning on a transient failure.
    """
    argv = [binary, "--help"] if agent == "claude" else [binary, "fork", "--help"]
    try:
        completed = subprocess.run(
            argv, env=dict(env), capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout or None


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
    help_output: str | None = None,
    codex_session_name_resolution: bool = True,
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
    tokens = version_tokens(version_output)
    # A misparse is most damaging when it causes a floor refusal, and an
    # exception discards `notices` — so the refusals carry the hint too.
    hint = (
        f" (ambiguous version output: {len(tokens)} tokens)" if len(tokens) > 1 else ""
    )
    if len(tokens) > 1:
        notices.append(
            f"{context.agent} version output carried {len(tokens)} version-like "
            f"tokens and was ambiguous; read as {_render(version)} — run "
            "agent-fork doctor if that is not the installed version"
        )
    resolved_context = context
    resolved_name: str | None = None
    if context.agent == "claude":
        if version < CLAUDE_FORK_MIN:
            raise _diagnosis(
                f"detected Claude {_render(version)}; pinned-session fork requires "
                f">={_render(CLAUDE_FORK_MIN)}{hint}"
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
                f">={_render(CODEX_FORK_MIN)}{hint}"
            )
        if version < CODEX_ENV_MIN:
            raise _diagnosis(
                f"detected Codex {_render(version)}; CODEX_THREAD_ID support requires "
                f">={_render(CODEX_ENV_MIN)}{hint}"
            )
        try:
            canonical = str(uuid.UUID(context.parent_session_id))
            is_uuid = canonical.lower() == context.parent_session_id.lower()
        except ValueError:
            is_uuid = False
        if not is_uuid:
            if not codex_session_name_resolution:
                raise SessionResolutionUnavailableError(
                    "Codex session-name resolution is disabled; pass the canonical "
                    "UUID or enable --codex-session-name-resolution"
                )
            from agent_fork.codex_app_server import list_named_threads

            candidates = list_named_threads(binary, context.parent_session_id, env)
            canonical_ids: list[str] = []
            for candidate in candidates:
                try:
                    candidate_id = str(uuid.UUID(candidate.id))
                except ValueError:
                    continue
                if candidate_id.lower() == candidate.id.lower():
                    canonical_ids.append(candidate_id)
            canonical_ids = sorted(set(canonical_ids))
            if not canonical_ids:
                raise AgentPreflightError(
                    f"Codex session name {context.parent_session_id!r} was not found; "
                    "pass the canonical UUID or run codex resume --all"
                )
            if len(canonical_ids) > 1:
                shown = ", ".join(canonical_ids[:5])
                omitted = len(canonical_ids) - 5
                suffix = f" (+{omitted} more)" if omitted > 0 else ""
                raise SessionNameAmbiguousError(
                    f"Codex session name {context.parent_session_id!r} matches "
                    f"multiple sessions: {shown}{suffix}; pass a canonical UUID"
                )
            resolved_name = context.parent_session_id
            resolved_context = AgentContext("codex", canonical_ids[0])
            notices.append(
                f"resolved Codex session {resolved_name!r} to "
                f"{resolved_context.parent_session_id}"
            )
        if not codex_rollout_exists(resolved_context, env):
            raise _diagnosis(
                f"detected Codex {_render(version)}, but parent rollout "
                f"{resolved_context.parent_session_id} is not flushed under "
                f"{_codex_home(env)}"
            )
    help_text = (
        help_output
        if help_output is not None
        else read_help(context.agent, binary, env)
    )
    if help_text:
        absent = missing_recipe_flags(context.agent, help_text)
        if absent:
            notices.append(
                f"installed {context.agent} CLI no longer documents "
                f"{', '.join(absent)}; the paste command may fail — run "
                "agent-fork doctor"
            )
    return PreflightResult(
        context.agent,
        version,
        tuple(notices),
        context=resolved_context,
        parent_session_name=resolved_name,
    )


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


def _terminal_safe(value: str) -> bool:
    return all(
        not (ord(character) < 0x20 or 0x7F <= ord(character) <= 0x9F)
        and character not in _BIDI_CONTROLS
        for character in value
    )


def _render_native_command(
    context: AgentContext,
    *,
    directory: Path,
    child_session_id: str | None,
    name: str | None,
    extra_args: tuple[str, ...],
) -> str:
    """Render the shared native-command grammar with one quoting boundary."""
    values = [str(directory), context.parent_session_id, *extra_args]
    if child_session_id is not None:
        values.append(child_session_id)
    if name is not None:
        values.append(name)
    if not all(_terminal_safe(value) for value in values):
        raise UnsafeCommandInputError(
            "session identity or directory contains terminal-unsafe controls"
        )

    quote = shlex.quote
    suffix = "".join(f" {quote(value)}" for value in extra_args)
    if context.agent == "claude":
        if child_session_id is None:
            raise ValueError("Claude native command requires a child session ID")
        command = (
            f"cd {quote(str(directory))} && claude --session-id "
            f"{quote(child_session_id)} "
            f"--resume {quote(context.parent_session_id)} --fork-session "
        )
        if name is not None:
            command += f"-n {quote(name)}"
        command += suffix
        return command.rstrip()
    return (
        f"codex fork {quote(context.parent_session_id)} "
        f"-C {quote(str(directory))}{suffix}"
    )


def build_launch_command(
    context: AgentContext,
    *,
    worktree: Path,
    name: str,
    extra_args: tuple[str, ...] = (),
    child_session_id: str | None = None,
) -> LaunchCommand:
    """Build the locked REQ-28 template without splitting configured arguments."""
    child = None
    if context.agent == "claude":
        child = child_session_id or str(uuid.uuid4())
    command = _render_native_command(
        context,
        directory=worktree,
        child_session_id=child,
        name=name,
        extra_args=extra_args,
    )
    return LaunchCommand(command, child, extra_args)


def build_session_fork_command(
    context: AgentContext,
    *,
    directory: Path,
    child_session_id: str | None = None,
) -> LaunchCommand:
    """Construct the read-only D21 command without preflight or configuration."""
    child = None
    if context.agent == "claude":
        child = child_session_id or str(uuid.uuid4())
    command = _render_native_command(
        context,
        directory=directory,
        child_session_id=child,
        name=None,
        extra_args=(),
    )
    return LaunchCommand(command, child, ())


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


def resolve_agent_mode(
    mode: str,
    env: Mapping[str, str],
    *,
    explicit_agent: str | None = None,
    explicit_parent_session: str | None = None,
) -> AgentContext | None:
    """Select managed-agent or Git-only behavior without unsafe fallback."""
    if mode not in {"auto", "strict", "git-only"}:
        raise ValueError(f"unknown agent mode: {mode}")
    explicit = explicit_agent is not None or explicit_parent_session is not None
    if mode == "git-only":
        if explicit:
            raise AgentDetectionError(
                "--no-agent cannot be combined with --agent or --parent-session"
            )
        return None
    if explicit:
        return detect_agent(
            env,
            explicit_agent=explicit_agent,
            explicit_parent_session=explicit_parent_session,
        )
    claude = env.get("CLAUDECODE") == "1" and bool(env.get("CLAUDE_CODE_SESSION_ID"))
    codex = bool(env.get("CODEX_THREAD_ID"))
    if mode == "auto" and not claude and not codex:
        return None
    return detect_agent(env)
