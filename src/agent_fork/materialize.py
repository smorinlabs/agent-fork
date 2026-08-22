"""Exact parent-state transport into a newly anchored Git worktree."""

from __future__ import annotations

import os
import shutil
import stat
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from agent_fork.content import (
    Inventory,
    SkipRecord,
    collect_inventory,
    sentinel_from_stat,
    suppressed_submodules,
)
from agent_fork.errors import EntryUnreadableError
from agent_fork.git import GitCommandError, run_git
from agent_fork.text import escape_terminal_text


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
    skipped: tuple[SkipRecord, ...] = ()


def _safe_destination(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve(strict=False)
    resolved_root = root.resolve()
    if candidate != resolved_root and resolved_root not in candidate.parents:
        raise MaterializeError(
            f"Git returned unsafe path outside worktree: {relative!r}"
        )
    return candidate


def _skip_copy(
    relative: str,
    reason: str,
    info: os.stat_result,
    deletion_blockers: tuple[str, ...],
) -> SkipRecord:
    if deletion_blockers:
        raise EntryUnreadableError(
            "cannot skip a carried entry while the fork carries a deletion: "
            f"{escape_terminal_text(relative)}",
            path=relative,
            reason="unreadable",
            phase="materialize",
            deletion_blockers=deletion_blockers,
        )
    return SkipRecord(relative, reason, "materialize", sentinel_from_stat(info))


def _prepare_destination(destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink() or destination.exists():
        if destination.is_dir() and not destination.is_symlink():
            shutil.rmtree(destination)
        else:
            destination.unlink()


def _open_classified_regular(source: Path, info: os.stat_result) -> BinaryIO | None:
    """Open exactly the regular file identified by the preceding ``lstat``.

    ``Path.open()`` follows a symlink substituted after classification. Open
    without following symlinks where the platform supports it, then compare
    the descriptor's identity and metadata with the observation. The
    descriptor pins that inode for the copy after this check.
    """
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(source, flags)
    except OSError:
        return None
    try:
        opened = os.fstat(descriptor)
    except OSError:
        os.close(descriptor)
        return None
    if not stat.S_ISREG(opened.st_mode) or sentinel_from_stat(
        opened
    ) != sentinel_from_stat(info):
        os.close(descriptor)
        return None
    try:
        return os.fdopen(descriptor, "rb")
    except (OSError, ValueError):
        os.close(descriptor)
        return None


def _copy_entry(
    parent: Path,
    child: Path,
    relative: str,
    *,
    deletion_blockers: tuple[str, ...],
) -> SkipRecord | None:
    source = parent / relative
    destination = _safe_destination(child, relative)
    try:
        info = source.lstat()
    except OSError as error:
        raise EntryUnreadableError(
            f"cannot stat carried entry: {escape_terminal_text(relative)}",
            path=relative,
            reason="lstat-failed",
            phase="materialize",
            deletion_blockers=deletion_blockers,
        ) from error
    if stat.S_ISLNK(info.st_mode):
        try:
            target = os.readlink(source)
        except OSError:
            return _skip_copy(relative, "unreadable", info, deletion_blockers)
        _prepare_destination(destination)
        destination.symlink_to(target)
        return None
    if not stat.S_ISREG(info.st_mode):
        return _skip_copy(relative, "unsupported-type", info, deletion_blockers)

    # Open and read the source separately from destination operations. A source
    # failure qualifies for the A5 skip; a child mkdir/open/write failure is a
    # materialization failure and must never be mislabeled as an unreadable
    # parent entry.
    source_file = _open_classified_regular(source, info)
    if source_file is None:
        return _skip_copy(relative, "unreadable", info, deletion_blockers)
    _prepare_destination(destination)
    source_error: OSError | None = None
    with source_file:
        with destination.open("wb") as destination_file:
            while True:
                try:
                    chunk = source_file.read(1 << 20)
                except OSError as error:
                    source_error = error
                    break
                if not chunk:
                    break
                destination_file.write(chunk)
    if source_error is not None:
        destination.unlink()
        return _skip_copy(relative, "unreadable", info, deletion_blockers)
    os.chmod(destination, stat.S_IMODE(info.st_mode), follow_symlinks=False)
    return None


def _apply_patch(
    child: Path,
    patch: bytes,
    args: Sequence[str],
    *,
    env: Mapping[str, str] | None,
    config_pins: Sequence[tuple[str, str]] = (),
) -> bool:
    if not patch:
        return False
    run_git(
        child,
        ["apply", "--binary", "--whitespace=nowarn", *args],
        env=env,
        input_bytes=patch,
        config_pins=config_pins,
    )
    return True


def submodule_loss_notices(
    parent: Path, *, env: Mapping[str, str] | None
) -> tuple[str, ...]:
    """Name what the fork leaves behind, rather than claiming a copy.

    The previous wording, "submodules copied opaquely", fired while the child's
    submodule directory was empty — `git worktree add` does not initialize
    submodules and nothing here populates them. Under `--no-verify` that message
    was the only thing a user saw before their submodule work went missing.

    It named every indexed gitlink, so a repository whose submodules all sat at
    their recorded commits was told its submodule changes were dropped. Nothing
    was dropped, and a false loss warning teaches the reader to ignore a real
    one, so this reports only the paths whose state verification stops seeing.
    """
    suppressed = suppressed_submodules(parent, env=env)
    if not suppressed:
        return ()
    listed = ", ".join(escape_terminal_text(path) for path in suppressed)
    return (f"submodule working-tree changes are not carried: {listed}",)


def skip_notices(skipped: tuple[object, ...]) -> tuple[str, ...]:
    """One notice per skipped entry, naming it.

    A count alone is not enough: the requirement is that the run says exactly
    which entries were not carried, so the user can judge whether the omission
    matters (P02 A5).
    """

    def key(record: object) -> bytes:
        return str(getattr(record, "path", record)).encode("utf-8", "surrogateescape")

    return tuple(
        "skipped entry, not carried: "
        + escape_terminal_text(str(getattr(record, "path", record)))
        for record in sorted(skipped, key=key)
    )


def materialize(
    parent: Path,
    child: Path,
    *,
    with_state: bool = True,
    with_ignored: bool = False,
    with_submodules: bool = False,
    inventory: Inventory | None = None,
    skipped: tuple[object, ...] = (),
    env: Mapping[str, str] | None = None,
    config_pins: Sequence[tuple[str, str]] = (),
) -> MaterializeResult:
    """Transport staged → ITA/unstaged → untracked → optional ignored state.

    ``inventory`` is the carried-state resolution taken before the worktree
    existed. Supplying it is what makes transport and verification operate on
    one fixed set of paths: without it this function re-resolves the paths now,
    and a file that appeared or vanished since the snapshot would be carried
    without being checked. The pipeline always supplies it; the parameter stays
    optional for callers transporting a tree they resolved themselves.

    ``config_pins`` is inert by default (A6b step 2). A6b reuses this function
    one level down for each carried submodule, and pins are what let that reuse
    stay "one added argument" rather than a second transport implementation —
    see the design doc's "Semantic pins on recursive commands".
    """
    if with_ignored and not with_state:
        raise ValueError("with_ignored requires with_state")
    if not with_state:
        return MaterializeResult(False, False, 0, 0, (), ())
    try:
        if inventory is None:
            inventory = collect_inventory(
                parent,
                with_state=with_state,
                with_ignored=with_ignored,
                env=env,
                config_pins=config_pins,
            )
        ita_paths = list(inventory.intent_to_add)
        staged_args = [
            "diff-index",
            "-p",
            "--binary",
            "--no-color",
            "--cached",
            "--ita-invisible-in-index",
        ]
        if with_submodules:
            # Mirrors collect_inventory's own flag: a local
            # `submodule.<name>.ignore` value suppresses this patch for a
            # staged gitlink advance and the `-c` pin cannot defeat it
            # (gate-6 round 2 findings 4+5).
            staged_args.append("--ignore-submodules=none")
        staged_args.append("HEAD")
        staged = run_git(
            parent,
            staged_args,
            env=env,
            config_pins=config_pins,
        ).stdout
        staged_applied = _apply_patch(
            child, staged, ["--index"], env=env, config_pins=config_pins
        )

        for path in ita_paths:
            ita_patch = run_git(
                parent,
                [
                    "diff-files",
                    "-p",
                    "--binary",
                    "--no-color",
                    "--ita-invisible-in-index",
                    "--",
                    f":(literal){path}",
                ],
                env=env,
                config_pins=config_pins,
            ).stdout
            _apply_patch(child, ita_patch, [], env=env, config_pins=config_pins)
            run_git(
                child,
                ["add", "--intent-to-add", "--", f":(literal){path}"],
                env=env,
                config_pins=config_pins,
            )

        unstaged_args = [
            "diff-files",
            "-p",
            "--binary",
            "--no-color",
            "--ita-invisible-in-index",
        ]
        if with_submodules:
            unstaged_args.append("--ignore-submodules=none")
        if ita_paths:
            unstaged_args.extend(
                [
                    "--",
                    ".",
                    *(f":(exclude,literal){path}" for path in ita_paths),
                ]
            )
        unstaged = run_git(
            parent, unstaged_args, env=env, config_pins=config_pins
        ).stdout
        unstaged_applied = _apply_patch(
            child, unstaged, [], env=env, config_pins=config_pins
        )

        skipped_paths = {getattr(record, "path", record) for record in skipped}
        newly_skipped: list[SkipRecord] = []
        untracked = [p for p in inventory.untracked if p not in skipped_paths]
        for path in untracked:
            record = _copy_entry(
                parent,
                child,
                path,
                deletion_blockers=inventory.deletions,
            )
            if record is not None:
                newly_skipped.append(record)

        ignored: list[str] = []
        if with_ignored:
            ignored = [p for p in inventory.ignored if p not in skipped_paths]
            untracked_set = set(untracked)
            for path in ignored:
                if path not in untracked_set:
                    record = _copy_entry(
                        parent,
                        child,
                        path,
                        deletion_blockers=inventory.deletions,
                    )
                    if record is not None:
                        newly_skipped.append(record)
    except (GitCommandError, OSError) as error:
        raise MaterializeError(str(error)) from error

    return MaterializeResult(
        staged_patch=staged_applied,
        unstaged_patch=unstaged_applied,
        copied_untracked=len(untracked)
        - sum(record.path in untracked for record in newly_skipped),
        copied_ignored=len(ignored)
        - sum(record.path in ignored for record in newly_skipped),
        intent_to_add=tuple(ita_paths),
        notices=(submodule_loss_notices(parent, env=env) if not with_submodules else ())
        + skip_notices((*skipped, *newly_skipped)),
        skipped=tuple(newly_skipped),
    )
