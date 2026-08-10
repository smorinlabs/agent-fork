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
    parse_version,
)
from agent_fork.config import ConfigError, resolve_discovered_config
from agent_fork.git import PRODUCT_GIT_MIN


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    ok: bool
    detail: str


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


def run_doctor(cwd: Path, env: Mapping[str, str]) -> tuple[DoctorCheck, ...]:
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
    signals = DoctorCheck(
        "environment signals",
        True,
        "CLAUDECODE="
        f"{env.get('CLAUDECODE', '<absent>')}, CLAUDE_CODE_SESSION_ID="
        f"{'present' if env.get('CLAUDE_CODE_SESSION_ID') else 'absent'}, "
        f"CODEX_THREAD_ID={'present' if env.get('CODEX_THREAD_ID') else 'absent'}",
    )
    try:
        resolved = resolve_discovered_config(cwd, env)
        config = DoctorCheck(
            "config validity", True, f"valid ({resolved.config_path or 'defaults'})"
        )
    except ConfigError as error:
        config = DoctorCheck("config validity", False, str(error))
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
    return git, claude, codex, signals, config, xdg
