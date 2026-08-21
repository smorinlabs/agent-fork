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
from agent_fork.config import ConfigError, resolve_discovered_config, worktree_root
from agent_fork.git import PRODUCT_GIT_MIN
from agent_fork.include import SETUP_HOOK_RELATIVE_PATH, setup_hook_eligibility


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


def _setup_hook_check(
    cwd: Path, env: Mapping[str, str], policy: str | None, timeout: int
) -> DoctorCheck:
    """A12: report whether this repository's setup hook would actually run.

    Unlike every other row here, this one describes the repository's working
    tree rather than machine readiness, and it is allowed to fail: a hook that
    is present but ineligible under the default `tracked` policy will silently
    not run, which the owner chose to surface as a hard failure rather than a
    note. It stays `ok` under `any` (the hook is explicitly allowed to run),
    under `off` (it is not evaluated), and when no hook is present.

    Evaluated against `HEAD`, which the detail says explicitly: `fork` resolves
    its own anchor and on a detached HEAD the two can differ.
    """
    name = "repository setup hook"
    if policy is None:
        return DoctorCheck(name, True, "not evaluated: configuration is invalid")
    if policy == "off":
        return DoctorCheck(name, True, "disabled by config (setup_hook_policy = off)")
    try:
        root = worktree_root(cwd, env)
    except ConfigError:
        return DoctorCheck(name, True, f"not evaluated: {cwd} is not a worktree")
    eligibility, reason = setup_hook_eligibility(
        root, "HEAD", reference_label="HEAD", env=env
    )
    if eligibility == "absent":
        return DoctorCheck(name, True, f"none in {root}")
    if eligibility == "eligible":
        return DoctorCheck(
            name,
            True,
            f"{SETUP_HOOK_RELATIVE_PATH} present, eligible at HEAD, "
            f"policy={policy}, timeout={timeout}s",
        )
    if policy == "any":
        return DoctorCheck(
            name,
            True,
            f"{SETUP_HOOK_RELATIVE_PATH} {reason} (allowed to run under policy=any)",
        )
    return DoctorCheck(
        name,
        False,
        f"{SETUP_HOOK_RELATIVE_PATH} {reason} (blocked under policy=tracked; "
        "override --setup-hook-policy any)",
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
    hook_policy: str | None = None
    hook_timeout = 0
    try:
        resolved = resolve_discovered_config(cwd, env)
        selected_mode = agent_mode or resolved.agent_mode
        hook_policy = resolved.setup_hook_policy
        hook_timeout = resolved.setup_hook_timeout
        config = DoctorCheck(
            "config validity", True, f"valid ({resolved.config_path or 'defaults'})"
        )
    except ConfigError as error:
        selected_mode = agent_mode or "auto"
        config = DoctorCheck("config validity", False, str(error))
    setup_hook = _setup_hook_check(cwd, env, hook_policy, hook_timeout)
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
    return git, claude, codex, recipes, signals, config, xdg, setup_hook
