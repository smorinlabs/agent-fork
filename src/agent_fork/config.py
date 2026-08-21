"""TOML discovery and deterministic multi-source configuration resolution."""

from __future__ import annotations

import os
import subprocess
import tomllib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_fork.errors import AgentForkError
from agent_fork.include import (
    DEFAULT_SETUP_HOOK_POLICY,
    DEFAULT_SETUP_HOOK_TIMEOUT,
    SETUP_HOOK_POLICIES,
)
from agent_fork.models import ConfigValues, ResolvedConfig
from agent_fork.text import escape_terminal_text
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
    "output",
    "setup_hook_policy",
    "setup_hook_timeout",
}
_BOOL_KEYS = {"with_state", "with_ignored", "verify", "copy"}
_GIT_REF_ILLEGAL_SUBSTRINGS = ("~", "^", ":", "?", "*", "[", "\\", "..", "@{")


class ConfigError(AgentForkError, ValueError):
    """A deterministic, user-actionable configuration failure."""

    code = "config_error"
    exit_code = 2


def branch_prefix_reason(prefix: str) -> str | None:
    """None if `prefix` composes into a Git-legal branch; else why not.

    ``naming.naming_plan()`` composes the fork branch by plain string
    concatenation (``prefix + sanitized_name``), so a prefix's legality is a
    property of the *composed* branch, not the prefix in isolation: a prefix
    can be legal alone yet compose into an illegal branch (a lone trailing
    dash), or illegal alone yet compose into a legal one (``"topic."`` is
    legal once suffixed, even though a bare trailing ``.`` looks like it
    should be rejected). This validates a representative composed sample
    (``prefix + "x"``) against ``git-check-ref-format(1)``'s rules, mirrored
    here rather than shelled out to Git so that `resolve_config()` stays pure
    — proved equivalent to real Git by a parity test in the pipeline tier.
    """
    composed = f"{prefix}x"
    if not composed:
        return None
    if composed[0] == "-":
        return "must not begin with -"
    if any(
        ord(character) < 0x20 or ord(character) == 0x7F or character == " "
        for character in composed
    ):
        return "must not contain control characters or spaces"
    for substring in _GIT_REF_ILLEGAL_SUBSTRINGS:
        if substring in composed:
            return f"must not contain {substring!r}"
    if composed.startswith("/") or "//" in composed:
        return "must not start with '/' or contain '//'"
    for component in composed.split("/"):
        if component.startswith("."):
            return "must not have a path component starting with '.'"
        if component.endswith(".lock"):
            return "must not have a path component ending in '.lock'"
    if composed.endswith("."):
        return "must not end with '.'"
    return None


@dataclass(frozen=True)
class KeySpec:
    """One configuration key's complete, declarative contract."""

    dotted: str
    field: str
    table: str  # "fork" | "agents.claude" | "agents.codex"
    kind: str  # "bool" | "enum" | "int" | "string" | "string-array"
    allowed: tuple[str, ...] = ()
    allowed_text: str | None = None
    env: str | None = None
    settable: bool = True
    validator: Callable[[str], str | None] | None = None

    def describe_allowed(self) -> str:
        if self.allowed_text is not None:
            return self.allowed_text
        if self.allowed:
            return ", ".join(self.allowed)
        return self.kind


@dataclass(frozen=True)
class ConfigFinding:
    """One semantic validation failure against the effective configuration."""

    key: str
    value: str
    reason: str
    allowed: str
    source: str

    def render(self) -> str:
        # `reason` and `source` can carry repository-controlled text too —
        # e.g. an unknown-placeholder name parsed out of a TOML template, or
        # a `--config`/discovered file path — not just `value`. All three
        # are escaped before reaching a diagnostic a human or a terminal
        # renders.
        escaped_value = escape_terminal_text(self.value)
        escaped_reason = escape_terminal_text(self.reason)
        escaped_source = escape_terminal_text(self.source)
        return (
            f"{self.key}: invalid value {escaped_value!r} ({escaped_reason}); "
            f"allowed: {self.allowed} (from {escaped_source})"
        )


KEY_SPECS: tuple[KeySpec, ...] = (
    KeySpec("fork.with_state", "with_state", "fork", "bool"),
    KeySpec("fork.with_ignored", "with_ignored", "fork", "bool"),
    KeySpec(
        "fork.branch_prefix",
        "branch_prefix",
        "fork",
        "string",
        allowed_text="a prefix that composes into a valid Git branch name",
        validator=branch_prefix_reason,
    ),
    KeySpec(
        "fork.worktree_location",
        "worktree_location",
        "fork",
        "string",
        allowed_text=(
            "sibling, central, subdirectory, or a bare-placeholder template "
            "using {repo-name}, {repo-root}, {branch}, {branch-escaped}"
        ),
        validator=lambda value: (
            None
            if value in {"sibling", "central", "subdirectory"}
            else _worktree_location_reason(value)
        ),
    ),
    KeySpec(
        "fork.agent_mode",
        "agent_mode",
        "fork",
        "enum",
        allowed=("auto", "strict", "git-only"),
        env="AGENT_FORK_AGENT_MODE",
    ),
    KeySpec("fork.verify", "verify", "fork", "bool"),
    KeySpec("fork.copy", "copy", "fork", "bool"),
    KeySpec(
        "fork.output",
        "output",
        "fork",
        "enum",
        allowed=("text", "json"),
        env="AGENT_FORK_OUTPUT",
    ),
    KeySpec(
        "fork.setup_hook_policy",
        "setup_hook_policy",
        "fork",
        "enum",
        allowed=SETUP_HOOK_POLICIES,
    ),
    KeySpec(
        "fork.setup_hook_timeout",
        "setup_hook_timeout",
        "fork",
        "int",
        allowed_text="a whole number of seconds greater than zero",
    ),
    KeySpec(
        "agents.claude.extra_args",
        "claude_extra_args",
        "agents.claude",
        "string-array",
        settable=False,
    ),
    KeySpec(
        "agents.codex.extra_args",
        "codex_extra_args",
        "agents.codex",
        "string-array",
        settable=False,
    ),
    KeySpec(
        "agents.codex.session_name_resolution",
        "codex_session_name_resolution",
        "agents.codex",
        "bool",
    ),
)

_GET_KEYS_BY_DOTTED: dict[str, KeySpec] = {spec.dotted: spec for spec in KEY_SPECS}
_GET_KEYS_BY_BARE: dict[str, KeySpec] = {
    spec.field: spec for spec in KEY_SPECS if spec.table == "fork"
}
_ENV_BY_FIELD: dict[str, str] = {
    spec.field: spec.env for spec in KEY_SPECS if spec.env is not None
}
# Derived from the registry rather than hand-maintained, so a key added to
# KEY_SPECS is type-checked by `load_config()` without a second list to
# remember (A11's registry intent, extended to A12's `int` kind).
_STRING_KEYS: frozenset[str] = frozenset(
    spec.field
    for spec in KEY_SPECS
    if spec.table == "fork" and spec.kind in {"string", "enum"}
)
_ENUM_KEYS: dict[str, tuple[str, ...]] = {
    spec.field: spec.allowed
    for spec in KEY_SPECS
    if spec.table == "fork" and spec.kind == "enum"
}
_INT_KEYS: frozenset[str] = frozenset(
    spec.field for spec in KEY_SPECS if spec.table == "fork" and spec.kind == "int"
)


_TOML_SHORT_ESCAPES = {
    "\\": "\\\\",
    '"': '\\"',
    "\b": "\\b",
    "\t": "\\t",
    "\n": "\\n",
    "\f": "\\f",
    "\r": "\\r",
}


def _toml_string_literal(value: str) -> str:
    """A TOML basic string literal — a raw control character or DEL is not
    legal unescaped inside one, so both must be escaped for the emitted
    value to round-trip through a real TOML parser, not just match a
    fixed-string assertion."""
    characters = []
    for character in value:
        if character in _TOML_SHORT_ESCAPES:
            characters.append(_TOML_SHORT_ESCAPES[character])
        elif ord(character) < 0x20 or ord(character) == 0x7F:
            characters.append(f"\\u{ord(character):04x}")
        else:
            characters.append(character)
    return '"' + "".join(characters) + '"'


def config_get(resolved: ResolvedConfig, key: str) -> str:
    """Render one effective configuration value by its canonical key.

    Accepts both bare `[fork]` names (e.g. ``branch_prefix``) and fully
    dotted forms (e.g. ``fork.branch_prefix``, ``agents.claude.extra_args``).
    Rejects every other attribute — including internal-only ones an earlier
    `hasattr` fallback used to leak: `config_path`, `mode`,
    `worktree_location_explicit`, `claude_extra_args`, `codex_extra_args`,
    and the bare `codex_session_name_resolution` (only its dotted
    `agents.codex.session_name_resolution` form is a documented key).

    An array renders as a TOML array literal (``["--model", "opus"]``, or
    ``[]`` when empty) so it pastes directly into the file `config set`'s
    refusal for that same key names.
    """
    spec = _GET_KEYS_BY_DOTTED.get(key) or _GET_KEYS_BY_BARE.get(key)
    if spec is None:
        # `key` is a raw CLI argument, echoed verbatim; escape it like every
        # other diagnostic in this codebase (`ConfigFinding.render()`).
        raise ConfigError(f"unknown config key: {escape_terminal_text(key)}")
    value = getattr(resolved, spec.field)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, tuple):
        return "[" + ", ".join(_toml_string_literal(item) for item in value) + "]"
    return str(value)


def _worktree_location_reason(value: str) -> str | None:
    from agent_fork.location import worktree_location_reason

    return worktree_location_reason(value)


def validate_values(
    values: ResolvedConfig,
    *,
    provenance: Mapping[str, str] | None = None,
) -> tuple[ConfigFinding, ...]:
    """Every semantic defect in the merged, effective configuration.

    Pure: no filesystem, subprocess, or network access. Checks every key the
    registry declares a rule for and returns *every* finding, not just the
    first, so one `config validate` run reports every bad key at once.
    """
    provenance = provenance or {}
    findings: list[ConfigFinding] = []
    for spec in KEY_SPECS:
        if spec.validator is None and spec.kind not in {"enum", "int"}:
            continue
        value = getattr(values, spec.field)
        if value is None:
            continue
        reason: str | None = None
        if spec.kind == "enum" and value not in spec.allowed:
            reason = "not one of the allowed values"
        elif spec.kind == "int":
            # `isinstance(True, int)` is true in Python, so booleans need their
            # own rejection. There is deliberately no "no timeout" sentinel: an
            # unbounded hook is the fault A12 exists to close.
            if isinstance(value, bool) or not isinstance(value, int):
                reason = "not a whole number of seconds"
            elif value <= 0:
                reason = "not greater than zero seconds"
        elif spec.validator is not None:
            reason = spec.validator(value)
        if reason is not None:
            findings.append(
                ConfigFinding(
                    key=spec.dotted,
                    value=str(value),
                    reason=reason,
                    allowed=spec.describe_allowed(),
                    source=provenance.get(spec.field, "default"),
                )
            )
    return tuple(findings)


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
    labels = [
        str(source.config_path) if source.config_path is not None else "config"
        for source in ordered
    ]
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
    labels.append("env")
    ordered.append(_coerce_source(flags))
    labels.append("flag")
    provenance: dict[str, str] = {}

    with_state = True
    with_ignored = False
    branch_prefix = DEFAULT_BRANCH_PREFIX
    worktree_location = DEFAULT_WORKTREE_LOCATION
    worktree_location_explicit = False
    agent_mode = DEFAULT_AGENT_MODE
    verify = True
    copy = False
    setup_hook_policy = DEFAULT_SETUP_HOOK_POLICY
    setup_hook_timeout = DEFAULT_SETUP_HOOK_TIMEOUT
    output = "text"
    config_path: Path | None = None
    claude_extra_args: tuple[str, ...] = ()
    codex_extra_args: tuple[str, ...] = ()
    codex_session_name_resolution = True

    for source, label in zip(ordered, labels, strict=True):
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
            provenance["branch_prefix"] = label
        if source.worktree_location is not None:
            worktree_location = source.worktree_location
            worktree_location_explicit = True
            provenance["worktree_location"] = label
        if source.agent_mode is not None:
            agent_mode = source.agent_mode
            provenance["agent_mode"] = (
                _ENV_BY_FIELD.get("agent_mode", label) if label == "env" else label
            )
        if source.verify is not None:
            verify = source.verify
        if source.copy is not None:
            copy = source.copy
        if source.setup_hook_policy is not None:
            setup_hook_policy = source.setup_hook_policy
        if source.setup_hook_timeout is not None:
            setup_hook_timeout = source.setup_hook_timeout
        if source.output is not None:
            output = source.output
            provenance["output"] = (
                _ENV_BY_FIELD.get("output", label) if label == "env" else label
            )
        if source.config_path is not None:
            config_path = source.config_path.resolve()
        if source.claude_extra_args is not None:
            claude_extra_args = source.claude_extra_args
        if source.codex_extra_args is not None:
            codex_extra_args = source.codex_extra_args
        if source.codex_session_name_resolution is not None:
            codex_session_name_resolution = source.codex_session_name_resolution

    resolved = ResolvedConfig(
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
        setup_hook_policy=setup_hook_policy,
        setup_hook_timeout=setup_hook_timeout,
    )
    findings = validate_values(resolved, provenance=provenance)
    if findings:
        raise ConfigError("; ".join(finding.render() for finding in findings))
    return resolved


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
    for key in _STRING_KEYS:
        if key in fork and not isinstance(fork[key], str):
            raise ConfigError(f"invalid config {path}: fork.{key} must be a string")
    # A11's lesson: a key that passes `config validate` and later crashes `fork`
    # is the exact defect that item found, so every new key is rejected here.
    for key, allowed in _ENUM_KEYS.items():
        if key in fork and fork[key] not in allowed:
            raise ConfigError(
                f"invalid config {path}: fork.{key} must be "
                f"{', '.join(allowed[:-1])}, or {allowed[-1]}"
            )
    for key in _INT_KEYS:
        if key not in fork:
            continue
        value = fork[key]
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigError(
                f"invalid config {path}: fork.{key} must be a whole number of seconds"
            )
        if value <= 0:
            raise ConfigError(
                f"invalid config {path}: fork.{key} must be greater than zero seconds"
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


def discover_config_paths(
    cwd: Path, env: Mapping[str, str], *, require_repo: bool = True
) -> list[Path]:
    """Return existing config paths in low-to-high precedence order.

    ``require_repo=False`` skips project-config discovery gracefully when
    `cwd` is not inside a Git worktree, instead of raising — for commands
    that are usable outside a repository (`list`, `session`, `cleanup`) but
    still need `AGENT_FORK_OUTPUT`/`[fork].output` to resolve.
    """
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
    if require_repo:
        project = find_project_config(cwd, env)
    else:
        try:
            project = find_project_config(cwd, env)
        except ConfigError:
            project = None
    if project is not None:
        paths.append(project.resolve())
    return paths


def resolve_discovered_config(
    cwd: Path,
    env: Mapping[str, str],
    *,
    explicit_path: Path | None = None,
    flags: ConfigValues | Mapping[str, Any] | None = None,
    require_repo: bool = True,
) -> ResolvedConfig:
    """Load discovery or one explicit path, then apply env and flags."""
    paths = (
        [explicit_path.resolve()]
        if explicit_path is not None
        else discover_config_paths(cwd, env, require_repo=require_repo)
    )
    sources = [load_config(path) for path in paths]
    effective_env = dict(env)
    if explicit_path is not None:
        effective_env["AGENT_FORK_CONFIG"] = str(explicit_path.resolve())
    return resolve_config(sources=sources, flags=flags, env=effective_env)


def set_user_value(path: Path, key: str, value: str) -> None:
    """Write one supported configuration value for the config CLI.

    Driven by the same `KEY_SPECS` registry as `config_get()` and
    `validate_values()` — a key added to the registry gets `get`, semantic
    validation, and (if `settable`) `set` support all at once, rather than
    needing a fourth hand-maintained list to remember.
    """
    resolved_path = path.resolve()
    spec = _GET_KEYS_BY_BARE.get(key) or _GET_KEYS_BY_DOTTED.get(key)
    if spec is None:
        raise ConfigError(f"unknown config key: {escape_terminal_text(key)}")
    if not spec.settable:
        raise ConfigError(
            f"{spec.dotted} is an array and cannot be set from the CLI; edit "
            f"[{spec.table}] extra_args in {resolved_path}"
        )
    if spec.kind == "bool":
        if value.lower() not in {"true", "false"}:
            raise ConfigError(
                ConfigFinding(
                    key=spec.dotted,
                    value=value,
                    reason="not a boolean",
                    allowed="true, false",
                    source=str(resolved_path),
                ).render()
            )
    elif spec.kind == "enum" and value not in spec.allowed:
        raise ConfigError(
            ConfigFinding(
                key=spec.dotted,
                value=value,
                reason="not one of the allowed values",
                allowed=spec.describe_allowed(),
                source=str(resolved_path),
            ).render()
        )
    elif spec.kind == "int":
        # Digits only, before `int()` sees it: `int("1_000")` is 1000, so
        # `config set setup_hook_timeout 1_000` used to write a value the user
        # never typed.
        reason = (
            "not a whole number of seconds"
            if not (value.isascii() and value.isdigit())
            else "not greater than zero seconds"
            if int(value) <= 0
            else None
        )
        if reason is not None:
            raise ConfigError(
                ConfigFinding(
                    key=spec.dotted,
                    value=value,
                    reason=reason,
                    allowed=spec.describe_allowed(),
                    source=str(resolved_path),
                ).render()
            )
    elif spec.validator is not None:
        # Normalize identically to resolve_config() before validating, so a
        # whitespace-only branch_prefix (which resolves to the default) is
        # not spuriously refused; the raw value is still what gets written.
        normalized = (
            value.strip() or DEFAULT_BRANCH_PREFIX
            if spec.field == "branch_prefix"
            else value
        )
        reason = spec.validator(normalized)
        if reason is not None:
            raise ConfigError(
                ConfigFinding(
                    key=spec.dotted,
                    value=value,
                    reason=reason,
                    allowed=spec.describe_allowed(),
                    source=str(resolved_path),
                ).render()
            )
    # Everything above must run, and raise, before any filesystem mutation
    # below — including path.parent.mkdir() at the end of this function, not
    # merely before the write. An invalid value must leave the target file
    # (and its parent directories) untouched.
    existing = load_config(path) if path.exists() else ConfigValues()
    values = {
        field: getattr(existing, field)
        for field in _FORK_KEYS
        if getattr(existing, field) is not None
    }
    if spec.field == "codex_session_name_resolution":
        existing = ConfigValues(
            **{
                field: getattr(existing, field)
                for field in ConfigValues.__dataclass_fields__
                if field != "codex_session_name_resolution"
            },
            codex_session_name_resolution=value.lower() == "true",
        )
    elif spec.kind == "bool":
        values[spec.field] = value.lower() == "true"
    elif spec.kind == "int":
        values[spec.field] = int(value)
    else:
        values[spec.field] = value
    lines = ["[fork]"]
    for name in sorted(values):
        item = values[name]
        if isinstance(item, bool):
            text = "true" if item else "false"
        elif isinstance(item, int):
            text = str(item)
        else:
            text = _toml_string_literal(str(item))
        lines.append(f"{name} = {text}")
    for agent, extra_args in (
        ("claude", existing.claude_extra_args),
        ("codex", existing.codex_extra_args),
    ):
        if extra_args is None and not (
            agent == "codex" and existing.codex_session_name_resolution is not None
        ):
            continue
        quoted = ", ".join(_toml_string_literal(item) for item in (extra_args or ()))
        lines.extend(("", f"[agents.{agent}]", f"extra_args = [{quoted}]"))
        if agent == "codex" and existing.codex_session_name_resolution is not None:
            lines.append(
                "session_name_resolution = "
                + ("true" if existing.codex_session_name_resolution else "false")
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
