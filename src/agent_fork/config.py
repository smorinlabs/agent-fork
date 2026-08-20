"""TOML discovery and deterministic multi-source configuration resolution."""

from __future__ import annotations

import os
import subprocess
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from agent_fork.errors import AgentForkError
from agent_fork.models import ConfigValues, ResolvedConfig
from agent_fork.xdg import xdg_path

DEFAULT_BRANCH_PREFIX = "fork/"
DEFAULT_WORKTREE_LOCATION = "sibling"
DEFAULT_AGENT_MODE = "auto"
CONFIG_RELATIVE_PATH = Path(".agent-fork/agent-fork_config.toml")
XDG_RELATIVE_PATH = Path("agent-fork/agent-fork_config.toml")

_FORK_KEYS = {
    "with_state",
    "with_ignored",
    "branch_prefix",
    "worktree_location",
    "agent_mode",
    "verify",
    "copy",
}
_BOOL_KEYS = {"with_state", "with_ignored", "verify", "copy"}


class ConfigError(AgentForkError, ValueError):
    """A deterministic, user-actionable configuration failure."""

    code = "config_error"
    exit_code = 2


def _coerce_source(source: ConfigValues | Mapping[str, Any] | None) -> ConfigValues:
    if source is None:
        return ConfigValues()
    if isinstance(source, ConfigValues):
        return source
    known = {
        field: source[field]
        for field in ConfigValues.__dataclass_fields__
        if field in source
    }
    return ConfigValues(**known)


def resolve_config(
    *,
    sources: Sequence[ConfigValues | Mapping[str, Any]] = (),
    flags: ConfigValues | Mapping[str, Any] | None = None,
    env: Mapping[str, str] | None = None,
) -> ResolvedConfig:
    """Resolve low-to-high sources, environment, then explicit flags."""
    environment = env or {}
    ordered = [_coerce_source(source) for source in sources]
    ordered.append(
        ConfigValues(
            output=environment.get("AGENT_FORK_OUTPUT"),
            agent_mode=environment.get("AGENT_FORK_AGENT_MODE"),
            config_path=(
                Path(environment["AGENT_FORK_CONFIG"]).expanduser()
                if environment.get("AGENT_FORK_CONFIG")
                else None
            ),
        )
    )
    ordered.append(_coerce_source(flags))

    with_state = True
    with_ignored = False
    branch_prefix = DEFAULT_BRANCH_PREFIX
    worktree_location = DEFAULT_WORKTREE_LOCATION
    worktree_location_explicit = False
    agent_mode = DEFAULT_AGENT_MODE
    verify = True
    copy = False
    output = "text"
    config_path: Path | None = None
    claude_extra_args: tuple[str, ...] = ()
    codex_extra_args: tuple[str, ...] = ()
    codex_session_name_resolution = True

    for source in ordered:
        if source.with_state is not None:
            with_state = source.with_state
            if not source.with_state:
                with_ignored = False
        if source.with_ignored is not None:
            with_ignored = source.with_ignored
            if source.with_ignored:
                with_state = True
        if source.branch_prefix is not None:
            branch_prefix = source.branch_prefix.strip() or DEFAULT_BRANCH_PREFIX
        if source.worktree_location is not None:
            worktree_location = source.worktree_location
            worktree_location_explicit = True
        if source.agent_mode is not None:
            agent_mode = source.agent_mode
        if source.verify is not None:
            verify = source.verify
        if source.copy is not None:
            copy = source.copy
        if source.output is not None:
            output = source.output
        if source.config_path is not None:
            config_path = source.config_path.resolve()
        if source.claude_extra_args is not None:
            claude_extra_args = source.claude_extra_args
        if source.codex_extra_args is not None:
            codex_extra_args = source.codex_extra_args
        if source.codex_session_name_resolution is not None:
            codex_session_name_resolution = source.codex_session_name_resolution

    if agent_mode not in {"auto", "strict", "git-only"}:
        raise ConfigError("agent_mode must be auto, strict, or git-only")
    if output not in {"text", "json"}:
        raise ConfigError("output must be text or json")

    return ResolvedConfig(
        with_state=with_state,
        with_ignored=with_ignored,
        branch_prefix=branch_prefix,
        worktree_location=worktree_location,
        worktree_location_explicit=worktree_location_explicit,
        agent_mode=agent_mode,
        verify=verify,
        copy=copy,
        output=output,
        config_path=config_path,
        claude_extra_args=claude_extra_args,
        codex_extra_args=codex_extra_args,
        codex_session_name_resolution=codex_session_name_resolution,
    )


def load_config(path: Path) -> ConfigValues:
    """Load and validate one agent-fork TOML file."""
    try:
        document = tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"invalid config {path}: {error}") from None
    unknown_top = set(document) - {"fork", "agents"}
    if unknown_top:
        raise ConfigError(
            f"invalid config {path}: unknown table {sorted(unknown_top)[0]}"
        )
    fork = document.get("fork", {})
    if not isinstance(fork, dict):
        raise ConfigError(f"invalid config {path}: [fork] must be a table")
    unknown = set(fork) - _FORK_KEYS
    if unknown:
        raise ConfigError(
            f"invalid config {path}: unknown key fork.{sorted(unknown)[0]}"
        )
    for key in _BOOL_KEYS:
        if key in fork and not isinstance(fork[key], bool):
            raise ConfigError(f"invalid config {path}: fork.{key} must be boolean")
    for key in {"branch_prefix", "worktree_location", "agent_mode"}:
        if key in fork and not isinstance(fork[key], str):
            raise ConfigError(f"invalid config {path}: fork.{key} must be a string")
    if "agent_mode" in fork and fork["agent_mode"] not in {
        "auto",
        "strict",
        "git-only",
    }:
        raise ConfigError(
            f"invalid config {path}: fork.agent_mode must be auto, strict, or git-only"
        )
    agents = document.get("agents", {})
    if not isinstance(agents, dict):
        raise ConfigError(f"invalid config {path}: [agents] must be a table")
    unknown_agents = set(agents) - {"claude", "codex"}
    if unknown_agents:
        raise ConfigError(
            f"invalid config {path}: unknown agent {sorted(unknown_agents)[0]}"
        )
    agent_values: dict[str, object] = {}
    for agent, values in agents.items():
        allowed = {"extra_args"}
        if agent == "codex":
            allowed.add("session_name_resolution")
        if not isinstance(values, dict) or set(values) - allowed:
            raise ConfigError(f"invalid config {path}: [agents.{agent}] is invalid")
        raw = values.get("extra_args", [])
        if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
            raise ConfigError(
                f"invalid config {path}: agents.{agent}.extra_args must be strings"
            )
        agent_values[f"{agent}_extra_args"] = tuple(raw)
        if agent == "codex" and "session_name_resolution" in values:
            resolution = values["session_name_resolution"]
            if not isinstance(resolution, bool):
                raise ConfigError(
                    f"invalid config {path}: "
                    "agents.codex.session_name_resolution must be boolean"
                )
            agent_values["codex_session_name_resolution"] = resolution
    return ConfigValues(config_path=path.resolve(), **fork, **agent_values)


def worktree_root(cwd: Path, env: Mapping[str, str] | None = None) -> Path:
    """Resolve the current worktree's own root through PATH-resolved Git."""
    from agent_fork.git import without_config_injection

    result = subprocess.run(
        ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
        env=without_config_injection(env),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ConfigError(f"cannot discover project config: {cwd} is not a worktree")
    return Path(result.stdout.strip()).resolve()


def find_project_config(cwd: Path, env: Mapping[str, str] | None = None) -> Path | None:
    """Walk from cwd to its own worktree root, never above that boundary."""
    boundary = worktree_root(cwd, env)
    current = cwd.resolve()
    if current != boundary and boundary not in current.parents:
        raise ConfigError(
            f"cannot discover project config outside worktree root {boundary}"
        )
    while True:
        candidate = current / CONFIG_RELATIVE_PATH
        if candidate.is_file():
            return candidate
        if current == boundary:
            return None
        current = current.parent


def discover_config_paths(cwd: Path, env: Mapping[str, str]) -> list[Path]:
    """Return existing config paths in low-to-high precedence order."""
    explicit = env.get("AGENT_FORK_CONFIG")
    if explicit:
        return [Path(explicit).expanduser().resolve()]
    paths: list[Path] = []
    system_dirs = [
        Path(value)
        for value in env.get("XDG_CONFIG_DIRS", "/etc/xdg").split(os.pathsep)
    ]
    for directory in reversed(system_dirs):
        candidate = directory / XDG_RELATIVE_PATH
        if candidate.is_file():
            paths.append(candidate.resolve())
    user = xdg_path(env, "XDG_CONFIG_HOME", ".config")
    user_candidate = user / XDG_RELATIVE_PATH
    if user_candidate.is_file():
        paths.append(user_candidate.resolve())
    project = find_project_config(cwd, env)
    if project is not None:
        paths.append(project.resolve())
    return paths


def resolve_discovered_config(
    cwd: Path,
    env: Mapping[str, str],
    *,
    explicit_path: Path | None = None,
    flags: ConfigValues | Mapping[str, Any] | None = None,
) -> ResolvedConfig:
    """Load discovery or one explicit path, then apply env and flags."""
    paths = (
        [explicit_path.resolve()]
        if explicit_path is not None
        else discover_config_paths(cwd, env)
    )
    sources = [load_config(path) for path in paths]
    effective_env = dict(env)
    if explicit_path is not None:
        effective_env["AGENT_FORK_CONFIG"] = str(explicit_path.resolve())
    return resolve_config(sources=sources, flags=flags, env=effective_env)


def set_user_value(path: Path, key: str, value: str) -> None:
    """Write one supported `[fork]` value for the config CLI."""
    codex_resolution_key = "agents.codex.session_name_resolution"
    if key != codex_resolution_key and key not in _FORK_KEYS:
        raise ConfigError(f"unknown config key: {key}")
    if key in _BOOL_KEYS or key == codex_resolution_key:
        lowered = value.lower()
        if lowered not in {"true", "false"}:
            raise ConfigError(f"{key} expects true or false")
    if key == "agent_mode" and value not in {"auto", "strict", "git-only"}:
        raise ConfigError("agent_mode expects auto, strict, or git-only")
    existing = load_config(path) if path.exists() else ConfigValues()
    values = {
        field: getattr(existing, field)
        for field in _FORK_KEYS
        if getattr(existing, field) is not None
    }
    if key == codex_resolution_key:
        existing = ConfigValues(
            **{
                field: getattr(existing, field)
                for field in ConfigValues.__dataclass_fields__
                if field != "codex_session_name_resolution"
            },
            codex_session_name_resolution=value.lower() == "true",
        )
    else:
        values[key] = value.lower() == "true" if key in _BOOL_KEYS else value
    lines = ["[fork]"]
    for name in sorted(values):
        item = values[name]
        if isinstance(item, bool):
            text = "true" if item else "false"
        else:
            text = '"' + str(item).replace("\\", "\\\\").replace('"', '\\"') + '"'
        lines.append(f"{name} = {text}")
    for agent, extra_args in (
        ("claude", existing.claude_extra_args),
        ("codex", existing.codex_extra_args),
    ):
        if extra_args is None and not (
            agent == "codex" and existing.codex_session_name_resolution is not None
        ):
            continue
        quoted = ", ".join(
            '"' + item.replace("\\", "\\\\").replace('"', '\\"') + '"'
            for item in (extra_args or ())
        )
        lines.extend(("", f"[agents.{agent}]", f"extra_args = [{quoted}]"))
        if agent == "codex" and existing.codex_session_name_resolution is not None:
            lines.append(
                "session_name_resolution = "
                + ("true" if existing.codex_session_name_resolution else "false")
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
