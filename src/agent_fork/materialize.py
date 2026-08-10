"""Exact parent-state transport into a newly anchored Git worktree."""

from __future__ import annotations

import os
import shutil
import stat
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from agent_fork.git import GitCommandError, run_git


class MaterializeError(RuntimeError):
    """State transport failed; callers must roll back the created worktree."""


@dataclass(frozen=True)
class MaterializeResult:
    staged_patch: bool
    unstaged_patch: bool
    copied_untracked: int
    copied_ignored: int
    intent_to_add: tuple[str, ...]
    notices: tuple[str, ...]


def _nul_paths(data: bytes) -> list[str]:
    return [os.fsdecode(value) for value in data.split(b"\0") if value]


def _safe_destination(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve(strict=False)
    resolved_root = root.resolve()
    if candidate != resolved_root and resolved_root not in candidate.parents:
        raise MaterializeError(
            f"Git returned unsafe path outside worktree: {relative!r}"
        )
    return candidate


def _copy_entry(parent: Path, child: Path, relative: str) -> None:
    source = parent / relative
    destination = _safe_destination(child, relative)
    info = source.lstat()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink() or destination.exists():
        if destination.is_dir() and not destination.is_symlink():
            shutil.rmtree(destination)
        else:
            destination.unlink()
    if stat.S_ISLNK(info.st_mode):
        destination.symlink_to(os.readlink(source))
    elif stat.S_ISREG(info.st_mode):
        shutil.copyfile(source, destination, follow_symlinks=False)
        os.chmod(destination, stat.S_IMODE(info.st_mode), follow_symlinks=False)
    else:
        raise MaterializeError(f"unsupported untracked file type: {relative}")


def _apply_patch(
    child: Path,
    patch: bytes,
    args: Sequence[str],
    *,
    env: Mapping[str, str] | None,
) -> bool:
    if not patch:
        return False
    run_git(child, ["apply", "--binary", *args], env=env, input_bytes=patch)
    return True


def _intent_to_add_paths(parent: Path, *, env: Mapping[str, str] | None) -> list[str]:
    visible = run_git(
        parent,
        ["diff", "--cached", "--ita-visible-in-index", "--name-only", "-z"],
        env=env,
    )
    hidden = run_git(
        parent,
        ["diff", "--cached", "--ita-invisible-in-index", "--name-only", "-z"],
        env=env,
    )
    return sorted(set(_nul_paths(visible.stdout)) - set(_nul_paths(hidden.stdout)))


def _submodule_notices(
    parent: Path, *, env: Mapping[str, str] | None
) -> tuple[str, ...]:
    result = run_git(parent, ["ls-files", "--stage", "-z"], env=env)
    paths: list[str] = []
    for record in result.stdout.split(b"\0"):
        if record.startswith(b"160000 ") and b"\t" in record:
            paths.append(os.fsdecode(record.split(b"\t", 1)[1]))
    if not paths:
        return ()
    return (f"submodules copied opaquely: {', '.join(sorted(paths))}",)


def materialize(
    parent: Path,
    child: Path,
    *,
    with_state: bool = True,
    with_ignored: bool = False,
    env: Mapping[str, str] | None = None,
) -> MaterializeResult:
    """Transport staged → ITA/unstaged → untracked → optional ignored state."""
    if with_ignored and not with_state:
        raise ValueError("with_ignored requires with_state")
    if not with_state:
        return MaterializeResult(False, False, 0, 0, (), ())

    try:
        ita_paths = _intent_to_add_paths(parent, env=env)
        staged = run_git(
            parent,
            ["diff", "--binary", "--no-color", "--cached", "--ita-invisible-in-index"],
            env=env,
        ).stdout
        staged_applied = _apply_patch(child, staged, ["--index"], env=env)

        for path in ita_paths:
            ita_patch = run_git(
                parent,
                [
                    "diff",
                    "--binary",
                    "--no-color",
                    "--ita-invisible-in-index",
                    "--",
                    path,
                ],
                env=env,
            ).stdout
            _apply_patch(child, ita_patch, ["--intent-to-add"], env=env)

        unstaged_args = ["diff", "--binary", "--no-color", "--ita-invisible-in-index"]
        if ita_paths:
            unstaged_args.extend(
                ["--", ".", *(f":(exclude){path}" for path in ita_paths)]
            )
        unstaged = run_git(parent, unstaged_args, env=env).stdout
        unstaged_applied = _apply_patch(child, unstaged, [], env=env)

        untracked = _nul_paths(
            run_git(
                parent,
                ["ls-files", "--others", "-z", "--exclude-standard"],
                env=env,
            ).stdout
        )
        for path in untracked:
            _copy_entry(parent, child, path)

        ignored: list[str] = []
        if with_ignored:
            ignored = _nul_paths(
                run_git(
                    parent,
                    [
                        "ls-files",
                        "--others",
                        "-z",
                        "--ignored",
                        "--exclude-standard",
                    ],
                    env=env,
                ).stdout
            )
            for path in ignored:
                if path not in untracked:
                    _copy_entry(parent, child, path)
    except (GitCommandError, OSError) as error:
        raise MaterializeError(str(error)) from error

    return MaterializeResult(
        staged_patch=staged_applied,
        unstaged_patch=unstaged_applied,
        copied_untracked=len(untracked),
        copied_ignored=len(ignored),
        intent_to_add=tuple(ita_paths),
        notices=_submodule_notices(parent, env=env),
    )
