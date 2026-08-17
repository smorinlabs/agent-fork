"""Post-verification .worktreeinclude and setup-hook support."""

from __future__ import annotations

import fnmatch
import os
import shutil
import stat
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from agent_fork.git import run_git
from agent_fork.text import escape_terminal_text


@dataclass(frozen=True)
class IncludeResult:
    copied: tuple[str, ...]
    notices: tuple[str, ...]


def _patterns(parent: Path) -> tuple[str, ...]:
    source = parent / ".worktreeinclude"
    if not source.is_file():
        return ()
    return tuple(
        line.strip()
        for line in source.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def _matches(path: str, patterns: tuple[str, ...]) -> bool:
    return any(
        fnmatch.fnmatchcase(path, pattern)
        or fnmatch.fnmatchcase(path, pattern.rstrip("/") + "/**")
        for pattern in patterns
    )


def copy_worktree_includes(
    parent: Path, child: Path, *, env: Mapping[str, str] | None = None
) -> IncludeResult:
    """Copy matching ignored files, without overwriting materialized destinations."""
    patterns = _patterns(parent)
    if not patterns:
        return IncludeResult((), ())
    ignored = run_git(
        parent,
        ["ls-files", "--others", "--ignored", "--exclude-standard", "-z"],
        env=env,
    ).stdout
    copied: list[str] = []
    notices: list[str] = []
    child_root = child.resolve()
    for raw in ignored.split(b"\0"):
        if not raw:
            continue
        relative = os.fsdecode(raw)
        if not _matches(relative, patterns):
            continue
        source = parent / relative
        destination = (child / relative).resolve(strict=False)
        if child_root not in destination.parents:
            notices.append(
                f"skipped unsafe .worktreeinclude path: "
                f"{escape_terminal_text(relative)}"
            )
            continue
        if destination.exists() or destination.is_symlink():
            continue
        info = source.lstat()
        destination.parent.mkdir(parents=True, exist_ok=True)
        if stat.S_ISLNK(info.st_mode):
            destination.symlink_to(os.readlink(source))
        elif stat.S_ISREG(info.st_mode):
            shutil.copy2(source, destination, follow_symlinks=False)
        else:
            notices.append(
                f"skipped unsupported .worktreeinclude path: "
                f"{escape_terminal_text(relative)}"
            )
            continue
        copied.append(relative)
    return IncludeResult(tuple(copied), tuple(notices))


def run_setup_hook(
    repo_root: Path,
    child: Path,
    *,
    env: Mapping[str, str] | None = None,
) -> tuple[str, ...]:
    hook = child / ".agent-fork/worktree-setup.sh"
    if not hook.is_file():
        return ()
    environment = dict(env or os.environ)
    environment.update(
        {
            "REPO_ROOT": str(repo_root.resolve()),
            "WORKTREE_PATH": str(child.resolve()),
        }
    )
    try:
        completed = subprocess.run(
            [str(hook)], cwd=child, env=environment, capture_output=True, text=True
        )
    except OSError as error:
        return (f"setup hook failed to start: {error}",)
    if completed.returncode == 0:
        return ()
    detail = completed.stderr.strip() or completed.stdout.strip()
    suffix = f": {detail}" if detail else ""
    return (f"setup hook failed (exit {completed.returncode}){suffix}",)
