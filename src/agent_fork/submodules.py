"""Recursive submodule carry for A6b — snapshot, then (recipe) transport.

A fork's whole correctness rests on resolving carried state once, before the
worktree exists, so transport and verification share one fixed domain
(``content.py``'s module docstring). Submodules break that if carry reads live
state afterward: a gitlink contributes only its index entry to the top-level
inventory, and its working tree is excluded from the manifest, so inner bytes
can change between worktree creation and submodule carry while every
top-level bracket — status, inventory, manifest — reports no difference. This
module's snapshot is what closes that gap one level down: walked recursively,
before the worktree exists, and consumed unchanged by both carry and
verification.

See ``docs/superpowers/plans/2026-08-17-p02-a6-dirty-submodules.md``, "The
recursive snapshot".
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from agent_fork.content import (
    CarriedState,
    Inventory,
    capture_state,
    collect_inventory,
    gitlink_paths,
)
from agent_fork.git import run_git


@dataclass(frozen=True)
class SubmoduleSnapshot:
    """One frozen submodule plan node.

    ``name`` is the submodule's config name; ``path`` is where it lives in its
    parent. They coincide only by convention — a renamed submodule (cell `j`)
    is exactly the case where they diverge, and every config lookup for this
    submodule must be keyed by ``name`` while every Git pathspec must use
    ``path``, never the other way around.

    ``initialized``, ``head``, and ``remote_url`` are all ``None``/``False``
    together when the parent itself left the submodule uninitialized (cell
    `g`) — there is nothing to read inside a checkout that does not exist, and
    a fork must not initialize what the parent itself did not.
    """

    name: str
    path: str
    initialized: bool
    head: str | None
    remote_url: str | None
    inventory: Inventory
    content: CarriedState | None
    nested: tuple[SubmoduleSnapshot, ...]


def _gitmodules_names(parent: Path, *, env: Mapping[str, str] | None) -> dict[str, str]:
    """Map each submodule's path to its config name, from `.gitmodules`.

    Absent when the parent has no `.gitmodules` (a gitlink with no matching
    entry, or an unborn/pre-init state that `gitlink_paths` would not
    return anyway).
    """
    if not (parent / ".gitmodules").exists():
        return {}
    result = run_git(
        parent,
        ["config", "-f", ".gitmodules", "--get-regexp", r"^submodule\..*\.path$"],
        env=env,
        check=False,
    )
    mapping: dict[str, str] = {}
    for line in result.stdout.decode(errors="surrogateescape").splitlines():
        key, _, value = line.partition(" ")
        if not key.endswith(".path"):
            continue
        name = key.removeprefix("submodule.").removesuffix(".path")
        mapping[value] = name
    return mapping


def _resolve_remote_url(checkout: Path, *, env: Mapping[str, str] | None) -> str | None:
    """The submodule's own effective `remote.origin.url`, already resolved.

    "Resolved" matters for a relative `.gitmodules` URL: Git expands it
    against the parent's remote when the submodule was added, and the
    submodule's own local config already holds that expansion — reading it
    here, rather than the literal string in `.gitmodules`, is what recipe
    step 3 needs "before the fork" and what this snapshot exists to capture
    at exactly that moment.
    """
    result = run_git(
        checkout, ["config", "--get", "remote.origin.url"], env=env, check=False
    )
    if result.returncode != 0:
        return None
    return result.stdout.decode(errors="surrogateescape").strip() or None


def _snapshot_one(
    parent: Path,
    path: str,
    name: str,
    *,
    with_state: bool,
    with_ignored: bool,
    env: Mapping[str, str] | None,
) -> SubmoduleSnapshot:
    checkout = parent / path
    initialized = (checkout / ".git").exists()
    if not initialized:
        return SubmoduleSnapshot(
            name=name,
            path=path,
            initialized=False,
            head=None,
            remote_url=None,
            inventory=Inventory(),
            content=None,
            nested=(),
        )
    head = run_git(checkout, ["rev-parse", "HEAD"], env=env).stdout.decode().strip()
    remote_url = _resolve_remote_url(checkout, env=env)
    inventory = collect_inventory(
        checkout, with_state=with_state, with_ignored=with_ignored, env=env
    )
    content = capture_state(checkout, inventory, env=env) if with_state else None
    nested = _snapshot_recursive(
        checkout, with_state=with_state, with_ignored=with_ignored, env=env
    )
    return SubmoduleSnapshot(
        name=name,
        path=path,
        initialized=True,
        head=head,
        remote_url=remote_url,
        inventory=inventory,
        content=content,
        nested=nested,
    )


def _snapshot_recursive(
    root: Path,
    *,
    with_state: bool,
    with_ignored: bool,
    env: Mapping[str, str] | None,
) -> tuple[SubmoduleSnapshot, ...]:
    paths = gitlink_paths(root, env=env)
    if not paths:
        return ()
    names = _gitmodules_names(root, env=env)
    return tuple(
        _snapshot_one(
            root,
            path,
            names.get(path, path),
            with_state=with_state,
            with_ignored=with_ignored,
            env=env,
        )
        for path in paths
    )


def snapshot_submodules(
    parent: Path,
    *,
    with_state: bool,
    with_ignored: bool = False,
    env: Mapping[str, str] | None = None,
) -> tuple[SubmoduleSnapshot, ...]:
    """Recursively freeze every submodule under ``parent``, before the fork.

    Must be called before the worktree exists — this is what makes it a
    snapshot rather than a live read. Empty when ``with_state`` is false: a
    fork carrying no state has nothing to snapshot either.
    """
    if not with_state:
        return ()
    return _snapshot_recursive(
        parent, with_state=with_state, with_ignored=with_ignored, env=env
    )
