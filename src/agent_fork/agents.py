"""Agent identity detection and, later, native-fork preflight/templates."""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from agent_fork.errors import (
    AgentDetectionError,
    AgentPreflightError,
    AgentSignalIncompleteError,
    PreconditionError,
    SessionNameAmbiguousError,
    SessionResolutionUnavailableError,
)
from agent_fork.git import PRODUCT_GIT_MIN
from agent_fork.text import BIDI_CONTROLS
from agent_fork.xdg import xdg_path

AgentName = Literal["claude", "codex", "muse"]
# Every supported agent, in the fixed order diagnostics and choices use.
AGENT_NAMES: tuple[AgentName, ...] = ("claude", "codex", "muse")
_AGENT_LABELS: dict[str, str] = {"claude": "Claude", "codex": "Codex", "muse": "Muse"}
# The environment variable that carries each agent's session ID.
_SESSION_ID_VARIABLES: dict[str, str] = {
    "claude": "CLAUDE_CODE_SESSION_ID",
    "codex": "CODEX_THREAD_ID",
    "muse": "MUSE_SESSION_ID",
}
AgentSignalStatus = Literal["absent", "incomplete", "detected", "ambiguous"]
AgentSignalName = Literal[
    "CLAUDECODE=1",
    "CLAUDE_CODE_SESSION_ID",
    "CODEX_THREAD_ID",
    "MUSE_SESSION_ID",
]


@dataclass(frozen=True)
class AgentContext:
    agent: AgentName
    parent_session_id: str


@dataclass(frozen=True)
class AgentSignalAssessment:
    status: AgentSignalStatus
    context: AgentContext | None
    present: tuple[AgentSignalName, ...]
    missing: tuple[AgentSignalName, ...]

    def document(self) -> dict[str, object]:
        return {
            "status": self.status,
            "present": list(self.present),
            "missing": list(self.missing),
        }

    def diagnosis(self) -> str:
        if self.status == "absent":
            return "no agent signal is present"
        if self.status == "incomplete":
            return f"incomplete Claude signal; missing {', '.join(self.missing)}"
        if self.status == "ambiguous":
            tools = [
                _AGENT_LABELS[agent]
                for agent, signals in (
                    ("claude", ("CLAUDECODE=1", "CLAUDE_CODE_SESSION_ID")),
                    ("codex", ("CODEX_THREAD_ID",)),
                    ("muse", ("MUSE_SESSION_ID",)),
                )
                if any(signal in self.present for signal in signals)
            ]
            listed = " and ".join(tools)
            if not self.missing:
                prefix = "both " if len(tools) == 2 else ""
                return f"{prefix}{listed} signals are present"
            return (
                f"{listed} signals are present; incomplete Claude signal is "
                f"missing {', '.join(self.missing)}"
            )
        assert self.context is not None
        return f"detected {self.context.agent} signal"


def assess_agent_signals(env: Mapping[str, str]) -> AgentSignalAssessment:
    """Classify supported ambient agent signals without performing I/O.

    Signals from more than one agent are ambiguous: presence alone cannot show
    which session is nested in which (P07, owner decision P08 Q4.A).
    """
    claude_marker = env.get("CLAUDECODE") == "1"
    claude_id = env.get("CLAUDE_CODE_SESSION_ID")
    claude_session = bool(claude_id)
    codex_id = env.get("CODEX_THREAD_ID")
    muse_id = env.get("MUSE_SESSION_ID")

    present_values: list[AgentSignalName] = []
    if claude_marker:
        present_values.append("CLAUDECODE=1")
    if claude_session:
        present_values.append("CLAUDE_CODE_SESSION_ID")
    if codex_id:
        present_values.append("CODEX_THREAD_ID")
    if muse_id:
        present_values.append("MUSE_SESSION_ID")

    missing_values: list[AgentSignalName] = []
    if claude_marker != claude_session:
        missing_values.append(
            "CLAUDE_CODE_SESSION_ID" if claude_marker else "CLAUDECODE=1"
        )

    # One entry per agent with any signal present; Claude counts when either
    # half of its pair is present, so a partial Claude signal still collides.
    candidates: list[AgentContext | None] = []
    if claude_marker or claude_session:
        candidates.append(
            AgentContext("claude", claude_id or "")
            if claude_marker and claude_session
            else None
        )
    if codex_id:
        candidates.append(AgentContext("codex", codex_id))
    if muse_id:
        candidates.append(AgentContext("muse", muse_id))

    status: AgentSignalStatus
    context: AgentContext | None = None
    if len(candidates) > 1:
        status = "ambiguous"
    elif claude_marker != claude_session:
        status = "incomplete"
    elif candidates:
        status = "detected"
        context = candidates[0]
    else:
        status = "absent"

    return AgentSignalAssessment(
        status=status,
        context=context,
        present=tuple(present_values),
        missing=tuple(missing_values),
    )


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
# Muse's recipe uses subcommands, not flags: `muse resume` in the paste
# command and `muse serve` (MSP) for the fork itself.
MUSE_RECIPE_COMMANDS = ("resume", "serve")
# Codex declares the recipe's flags on the `fork` subcommand, not the root, so
# the two agents are probed with different argument tails. Diagnostics name the
# tail that actually ran: for Codex, `codex --help` succeeds even when `fork`
# is gone, so reporting it would point the reader at a working command.
_HELP_ARGS: dict[str, tuple[str, ...]] = {
    "claude": ("--help",),
    "codex": ("fork", "--help"),
    "muse": ("--help",),
}
_VERSION = re.compile(r"(?<![\d.])(\d+)\.(\d+)(?:\.(\d+))?")


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
    if agent == "claude":
        return CLAUDE_RECIPE_FLAGS
    if agent == "codex":
        return CODEX_RECIPE_FLAGS
    if agent == "muse":
        return MUSE_RECIPE_COMMANDS
    raise ValueError(f"unsupported agent: {agent}")


def _declared_commands(help_output: str) -> set[str]:
    """Subcommand names listed in a help text's `Commands:` section."""
    names: set[str] = set()
    inside = False
    for line in help_output.splitlines():
        if line.strip() == "Commands:":
            inside = True
            continue
        if inside:
            if not line.strip():
                break
            match = re.match(r"\s+([a-z][a-z0-9-]*)(?:\s|$)", line)
            if match:
                names.add(match.group(1))
    return names


def option_declarations(help_output: str) -> str:
    """The option-declaration part of each help line, description stripped.

    A bare token search treats prose as evidence: "this replaces
    --fork-session" would prove the flag still exists. Both CLIs declare
    options at the start of a line and separate the description with two or
    more spaces, so only that leading part counts.
    """
    declarations = []
    for line in help_output.splitlines():
        stripped = line.strip()
        if stripped.startswith("-"):
            declarations.append(re.split(r"\s{2,}", stripped, maxsplit=1)[0])
    return "\n".join(declarations)


def missing_recipe_flags(agent: AgentName, help_output: str) -> tuple[str, ...]:
    """Recipe flags absent from `help_output`, in declared order."""
    if agent == "muse":
        commands = _declared_commands(help_output)
        return tuple(name for name in MUSE_RECIPE_COMMANDS if name not in commands)
    declared = option_declarations(help_output)
    return tuple(
        flag
        for flag in recipe_flags(agent)
        if re.search(rf"(?<![\w-]){re.escape(flag)}(?![\w-])", declared) is None
    )


def help_invocation(agent: AgentName) -> str:
    """The help command as a reader would type it, for diagnostics."""
    return " ".join((agent, *_HELP_ARGS[agent]))


def read_help(agent: AgentName, binary: str, env: Mapping[str, str]) -> str | None:
    """Installed help text, or None when the capability is unverifiable.

    None is a third state, distinct from "flag present" and "flag absent":
    it means no evidence either way, which callers report rather than
    silently treat as success. Undecodable bytes land in that state too:
    `text=True` decodes inside `subprocess.run`, so UnicodeDecodeError must
    be caught here or it escapes a mechanism that promises never to refuse.
    Replacing the bad bytes instead would be worse — unreadable output would
    then be probed as if it were help, and report every flag as removed.
    """
    argv = [binary, *_HELP_ARGS[agent]]
    try:
        completed = subprocess.run(
            argv, env=dict(env), capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError, UnicodeDecodeError):
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


def codex_rollout_path(context: AgentContext, env: Mapping[str, str]) -> Path | None:
    """Locate one thread's rollout file; the newest match wins when several exist."""
    pattern = f"sessions/*/*/*/rollout-*-{context.parent_session_id}.jsonl"
    # Absolute is part of the reported contract and a configured CODEX_HOME (or
    # the HOME fallback) may be relative. Resolve here rather than in
    # _codex_home() so the preflight existence check keeps its exact behavior.
    root = _codex_home(env).resolve()
    matches = sorted(match for match in root.glob(pattern) if match.is_file())
    return matches[-1] if matches else None


def codex_rollout_exists(context: AgentContext, env: Mapping[str, str]) -> bool:
    return codex_rollout_path(context, env) is not None


# The first record of a session log is small; a fork's is
# `session.fork.created`. Read no more than this to find it.
MUSE_FIRST_RECORD_LIMIT = 1_048_576


def _muse_home(env: Mapping[str, str]) -> Path:
    """Muse's data directory: `$XDG_DATA_HOME/muse`, else `~/.local/share/muse`."""
    return xdg_path(env, "XDG_DATA_HOME", ".local/share", "muse")


def muse_session_log(session_id: str, env: Mapping[str, str]) -> Path | None:
    """Locate one session's `session.jsonl`; the newest match wins."""
    if not _is_canonical_uuid(session_id):
        return None
    root = _muse_home(env).resolve()
    pattern = f"sessions/*/*/*/{session_id}/session.jsonl"
    matches = sorted(match for match in root.glob(pattern) if match.is_file())
    return matches[-1] if matches else None


def muse_forked_from(log: Path) -> str | None:
    """The source session ID a fork's log records first, or None."""
    try:
        with log.open("rb") as handle:
            first = handle.readline(MUSE_FIRST_RECORD_LIMIT)
    except OSError:
        return None
    try:
        record = json.loads(first)
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None
    if not isinstance(record, dict) or record.get("payload_type") != (
        "session.fork.created"
    ):
        return None
    payload = record.get("payload")
    source = payload.get("source_session_id") if isinstance(payload, dict) else None
    return source if isinstance(source, str) and _is_canonical_uuid(source) else None


def agent_fork_executable() -> tuple[str, ...]:
    """The argv that runs this `agent-fork`, for Muse's paste command.

    The paste command runs `agent-fork muse-fork` later, possibly where
    `agent-fork` is not on PATH (the skill can run it through `uvx`), so it
    names this installation: the absolute console script, or this interpreter
    with `-m agent_fork.cli` when started that way. Never a bare name, which
    could resolve to a different installation.
    """
    argv0 = sys.argv[0] if sys.argv else ""
    if argv0 and Path(argv0).name == "agent-fork" and Path(argv0).exists():
        return (os.path.abspath(argv0),)
    return (os.path.abspath(sys.executable), "-m", "agent_fork.cli")


def _is_canonical_uuid(value: str) -> bool:
    try:
        return str(uuid.UUID(value)) == value.lower()
    except ValueError:
        return False


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
        # Ambiguity can straddle the streams: a CLI may print its version on
        # stdout and an updater banner on stderr, so count tokens across both
        # even though only one stream is parsed.
        token_source = f"{completed.stdout}\n{completed.stderr}"
    else:
        token_source = version_output
    if context.agent == "muse":
        # Muse prints its version twice plus a build number, as in
        # "Muse Code 1.4.20 (1.4.20-R8619.1)"; the parenthesized build is not
        # a second version.
        version_output = version_output.split(" (", 1)[0]
        token_source = token_source.split(" (", 1)[0]
    try:
        version = parse_version(version_output)
    except ValueError as error:
        raise _diagnosis(
            f"detected {context.agent} CLI at {binary}, but its version was unreadable"
        ) from error

    notices: list[str] = []
    tokens = version_tokens(token_source)
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
    if context.agent == "muse":
        _preflight_muse(context, env, version)
    elif context.agent == "claude":
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
    elif context.agent == "codex":
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
    else:
        raise ValueError(f"unsupported agent: {context.agent}")
    help_text = (
        help_output
        if help_output is not None
        else read_help(context.agent, binary, env)
    )
    if not help_text:
        # Third state: unverified. Silence here would make "no evidence"
        # indistinguishable from "verified", and would hide removal of the
        # Codex `fork` subcommand entirely, since that makes help unreadable.
        notices.append(
            f"could not read the output of {help_invocation(context.agent)}, so "
            "the paste command's flags are unverified; run agent-fork doctor"
        )
    else:
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


def _preflight_muse(
    context: AgentContext, env: Mapping[str, str], version: tuple[int, int, int]
) -> None:
    """Muse has no version floor (1.4.20 is observed, not required): check the
    parent session instead. `session/fork` takes only a session UUID."""
    if not _is_canonical_uuid(context.parent_session_id):
        raise _diagnosis(
            f"Muse parent {context.parent_session_id!r} is not a session UUID; "
            "pass the UUID from MUSE_SESSION_ID"
        )
    if muse_session_log(context.parent_session_id, env) is None:
        raise _diagnosis(
            f"detected Muse {_render(version)}, but parent session "
            f"{context.parent_session_id} was not found under "
            f"{_muse_home(env)}/sessions"
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
    """Reject command inputs that carry controls or bidi overrides.

    Intentionally separate from ``output.terminal_text`` and
    ``text.escape_terminal_text``: this is a predicate for native command
    construction, not a renderer, and it also rejects bidi controls neither
    escaper handles.
    """
    return all(
        not (ord(character) < 0x20 or 0x7F <= ord(character) <= 0x9F)
        and character not in BIDI_CONTROLS
        for character in value
    )


def _render_native_command(
    context: AgentContext,
    *,
    directory: Path,
    child_session_id: str | None,
    name: str | None,
    extra_args: tuple[str, ...],
    mode: Literal["fork", "resume"] = "fork",
) -> str:
    """Render the shared native-command grammar with one quoting boundary."""
    executable = agent_fork_executable() if context.agent == "muse" else ()
    values = [str(directory), context.parent_session_id, *extra_args, *executable]
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
    if context.agent == "muse":
        # Muse forks only over MSP, so the paste command forks when it runs:
        # `agent-fork muse-fork` prints the new session ID, and an empty ID
        # (a failed fork) makes `muse resume ""` refuse. The resume runs in
        # the worktree, which binds the fork's workspace to it.
        if child_session_id is not None:
            raise ValueError("Muse native command must not carry a child session ID")
        if mode == "resume":
            return (
                f"cd {quote(str(directory))} && muse resume "
                f"{quote(context.parent_session_id)}{suffix}"
            )
        launcher = " ".join(quote(part) for part in executable)
        return (
            f"cd {quote(str(directory))} && muse resume "
            f'"$({launcher} muse-fork {quote(context.parent_session_id)})"'
            f"{suffix}"
        )
    if context.agent not in ("claude", "codex"):
        raise ValueError(f"unsupported agent: {context.agent}")
    if mode == "resume":
        if child_session_id is not None:
            raise ValueError("resume command must not carry a child session ID")
        if context.agent == "claude":
            command = (
                f"cd {quote(str(directory))} && claude "
                f"--resume {quote(context.parent_session_id)}{suffix}"
            )
            return command.rstrip()
        return (
            f"codex resume {quote(context.parent_session_id)} "
            f"-C {quote(str(directory))}{suffix}"
        )
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


def build_session_resume_command(
    context: AgentContext, *, directory: Path
) -> LaunchCommand:
    """Construct the read-only in-place resume command: no fork, no new session."""
    command = _render_native_command(
        context,
        directory=directory,
        child_session_id=None,
        name=None,
        extra_args=(),
        mode="resume",
    )
    return LaunchCommand(command, None, ())


def detect_agent(
    env: Mapping[str, str],
    *,
    explicit_agent: str | None = None,
    explicit_parent_session: str | None = None,
) -> AgentContext:
    """Resolve explicit identity first, otherwise use only the locked env signals."""
    if explicit_agent is not None:
        agent = next((name for name in AGENT_NAMES if name == explicit_agent), None)
        if agent is None:
            raise AgentDetectionError(
                f"unknown agent {explicit_agent!r}; choose --agent claude, codex, "
                "or muse"
            )
        parent = explicit_parent_session
        if parent is None:
            parent = env.get(_SESSION_ID_VARIABLES[agent])
        if not parent:
            raise AgentDetectionError(
                f"--agent {explicit_agent} requires --parent-session "
                "or its matching environment signal"
            )
        return AgentContext(agent=agent, parent_session_id=parent)

    if explicit_parent_session is not None:
        raise AgentDetectionError("--parent-session requires an explicit --agent")

    assessment = assess_agent_signals(env)
    if assessment.status == "incomplete":
        raise AgentSignalIncompleteError(assessment.present, assessment.missing)
    if assessment.context is None:
        raise AgentDetectionError(
            f"{assessment.diagnosis()}; pass --agent and --parent-session explicitly"
        )
    return assessment.context


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
    assessment = assess_agent_signals(env)
    if mode == "auto" and assessment.status == "absent":
        return None
    if assessment.status == "incomplete":
        raise AgentSignalIncompleteError(
            assessment.present,
            assessment.missing,
            allow_git_only=True,
        )
    if assessment.context is None:
        raise AgentDetectionError(
            f"{assessment.diagnosis()}; pass --agent and --parent-session explicitly"
        )
    return assessment.context
