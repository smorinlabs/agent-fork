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


def _recipe_flag_check(env: Mapping[str, str]) -> DoctorCheck:
    """A4: report recipe flags the installed CLIs no longer document.

    This is where both preflight notices send the user, so it must actually
    answer the question they were warned about. An absent CLI or unreadable
    help is not evidence of drift and is reported as a skip, not a failure.
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
            details.append(f"{agent}: help unreadable (skipped)")
            continue
        absent = missing_recipe_flags(agent, help_output)
        if absent:
            drifted = True
            details.append(f"{agent}: undocumented {', '.join(absent)}")
        else:
            details.append(f"{agent}: {len(recipe_flags(agent))} documented")
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
    cwd: Path, env: Mapping[str, str], *, agent_mode: str | None = None
) -> tuple[DoctorCheck, ...]:
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
    recipes = _recipe_flag_check(env)
    try:
        resolved = resolve_discovered_config(cwd, env)
        selected_mode = agent_mode or resolved.agent_mode
        config = DoctorCheck(
            "config validity", True, f"valid ({resolved.config_path or 'defaults'})"
        )
    except ConfigError as error:
        selected_mode = agent_mode or "auto"
        config = DoctorCheck("config validity", False, str(error))
    claude_signal = env.get("CLAUDECODE") == "1" and bool(
        env.get("CLAUDE_CODE_SESSION_ID")
    )
    codex_signal = bool(env.get("CODEX_THREAD_ID"))
    ambiguous = claude_signal and codex_signal
    missing_strict = selected_mode == "strict" and not (claude_signal or codex_signal)
    signals_ok = selected_mode == "git-only" or not (ambiguous or missing_strict)
    selected = (
        "git-only"
        if selected_mode == "git-only" or not (claude_signal or codex_signal)
        else "ambiguous"
        if ambiguous
        else "claude"
        if claude_signal
        else "codex"
    )
    signals = DoctorCheck(
        "environment signals",
        signals_ok,
        f"CLAUDECODE={env.get('CLAUDECODE', '<absent>')}, CLAUDE_CODE_SESSION_ID="
        f"{'present' if env.get('CLAUDE_CODE_SESSION_ID') else 'absent'}, "
        f"CODEX_THREAD_ID={'present' if env.get('CODEX_THREAD_ID') else 'absent'}, "
        f"mode={selected_mode}, selected={selected}",
    )

    def optional(check: DoctorCheck) -> DoctorCheck:
        return DoctorCheck(check.name, True, f"{check.detail} (optional)")

    if selected_mode == "git-only" or not (claude_signal or codex_signal):
        claude, codex = optional(claude), optional(codex)
    elif not ambiguous:
        if claude_signal:
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
    return git, claude, codex, recipes, signals, config, xdg
