"""Aggregated environment and dependency diagnostics."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from agent_fork.agents import (
    CLAUDE_FORK_MIN,
    CODEX_ENV_MIN,
    assess_agent_signals,
    missing_recipe_flags,
    parse_version,
    read_help,
    recipe_flags,
)
from agent_fork.config import ConfigError, resolve_discovered_config
from agent_fork.git import PRODUCT_GIT_MIN


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    ok: bool
    detail: str


def _recipe_flag_check(env: Mapping[str, str], selected: str) -> DoctorCheck:
    """A4: report recipe flags the installed CLIs no longer document.

    This is where both preflight notices send the user, so it must actually
    answer the question they were warned about. An absent CLI or unreadable
    help is not evidence of drift and is reported as unverified, not failure.

    Only the selected agent's drift can fail the check. An unused CLI that
    happens to be installed must not fail an otherwise healthy diagnosis,
    matching how the version checks are made optional below.
    """
    name = "agent recipe flags"
    details: list[str] = []
    drifted = False
    for agent in ("claude", "codex"):
        binary = shutil.which(agent, path=env.get("PATH"))
        if binary is None:
            details.append(f"{agent}: not installed (skipped)")
            continue
        help_output = read_help(agent, binary, env)
        if help_output is None:
            details.append(f"{agent}: help unreadable (unverified)")
            continue
        absent = missing_recipe_flags(agent, help_output)
        if not absent:
            details.append(f"{agent}: {len(recipe_flags(agent))} documented")
            continue
        scope = "" if agent == selected else " (unselected)"
        drifted = drifted or agent == selected
        details.append(f"{agent}: undocumented {', '.join(absent)}{scope}")
    return DoctorCheck(name, not drifted, "; ".join(details))


def _version_check(
    name: str,
    executable: str | None,
    floor: tuple[int, int, int],
    env: Mapping[str, str],
) -> DoctorCheck:
    minimum = ".".join(map(str, floor))
    if executable is None:
        return DoctorCheck(name, False, f"missing; requires >= {minimum}")
    completed = subprocess.run(
        [executable, "--version"], env=dict(env), capture_output=True, text=True
    )
    output = (completed.stdout or completed.stderr).strip()
    try:
        version = parse_version(output)
    except ValueError:
        return DoctorCheck(name, False, f"unreadable version: {output}")
    return DoctorCheck(
        name,
        completed.returncode == 0 and version >= floor,
        f"{'.'.join(map(str, version))} (minimum {minimum})",
    )


def run_doctor(
    cwd: Path,
    env: Mapping[str, str],
    *,
    agent_mode: str | None = None,
    output: str | None = None,
) -> tuple[tuple[DoctorCheck, ...], str]:
    """Return the diagnostic checks plus the resolved `output` format.

    `agent_mode` and `output` are passed through as resolution flags, not
    just applied after the fact — an explicit `--require-agent`/`--no-agent`
    or `-o/--output` must be able to override an invalid lower-precedence
    `AGENT_FORK_AGENT_MODE`/`AGENT_FORK_OUTPUT`, the same as every other
    consumer. `output` falls back to `"text"` when configuration itself
    fails to resolve — the "config validity" check below already reports
    that failure; rendering the report still needs a format to render it in.
    """
    flags = {
        key: value
        for key, value in {"agent_mode": agent_mode, "output": output}.items()
        if value is not None
    }
    git = _version_check(
        "git PRODUCT_GIT_MIN",
        shutil.which("git", path=env.get("PATH")),
        PRODUCT_GIT_MIN,
        env,
    )
    claude = _version_check(
        "Claude CLI",
        shutil.which("claude", path=env.get("PATH")),
        CLAUDE_FORK_MIN,
        env,
    )
    codex = _version_check(
        "Codex CLI",
        shutil.which("codex", path=env.get("PATH")),
        CODEX_ENV_MIN,
        env,
    )
    try:
        resolved = resolve_discovered_config(cwd, env, flags=flags)
        selected_mode = agent_mode or resolved.agent_mode
        resolved_output = resolved.output
        config = DoctorCheck(
            "config validity", True, f"valid ({resolved.config_path or 'defaults'})"
        )
    except ConfigError as error:
        selected_mode = agent_mode or "auto"
        # An explicit -o/--output must still win even when a *different* key
        # is the one that failed to resolve; absent that, prefer a *valid*
        # AGENT_FORK_OUTPUT over the bare "text" default, so a JSON consumer
        # still gets a JSON report precisely when the config is broken —
        # the case it most needs to machine-read.
        env_output = env.get("AGENT_FORK_OUTPUT")
        resolved_output = output or (
            env_output if env_output in ("text", "json") else "text"
        )
        config = DoctorCheck("config validity", False, str(error))
    assessment = assess_agent_signals(env)
    if selected_mode == "git-only":
        selected = "git-only"
        signals_ok = True
    elif assessment.status == "incomplete":
        selected = "claude"
        signals_ok = False
    elif assessment.status == "ambiguous":
        selected = "ambiguous"
        signals_ok = False
    elif assessment.status == "absent":
        selected = "git-only"
        signals_ok = selected_mode == "auto"
    else:
        assert assessment.context is not None
        selected = assessment.context.agent
        signals_ok = True
    recipes = _recipe_flag_check(env, selected)
    present = ", ".join(assessment.present)
    missing = ", ".join(assessment.missing)
    signals = DoctorCheck(
        "environment signals",
        signals_ok,
        f"status={assessment.status}, present=[{present}], missing=[{missing}], "
        f"mode={selected_mode}, selected={selected}",
    )

    def optional(check: DoctorCheck) -> DoctorCheck:
        return DoctorCheck(check.name, True, f"{check.detail} (optional)")

    if selected_mode == "git-only" or assessment.status == "absent":
        claude, codex = optional(claude), optional(codex)
    elif assessment.status != "ambiguous":
        if selected == "claude":
            codex = optional(codex)
        else:
            claude = optional(claude)
    state = Path(
        env.get(
            "XDG_STATE_HOME",
            Path(env.get("HOME", "~")).expanduser() / ".local/state",
        )
    )
    data = Path(
        env.get(
            "XDG_DATA_HOME",
            Path(env.get("HOME", "~")).expanduser() / ".local/share",
        )
    )
    paths_ok = True
    details: list[str] = []
    for label, path in (("state", state), ("data", data)):
        try:
            path.mkdir(parents=True, exist_ok=True)
            ok = os.access(path, os.W_OK)
        except OSError:
            ok = False
        paths_ok &= ok
        details.append(f"{label}={path} ({'writable' if ok else 'not writable'})")
    xdg = DoctorCheck("XDG paths", paths_ok, ", ".join(details))
    return (git, claude, codex, recipes, signals, config, xdg), resolved_output
