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

from collections.abc import Mapping, Sequence
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
from agent_fork.materialize import materialize


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


@dataclass(frozen=True)
class CarryResult:
    """What one `carry_submodules` call actually did, recursively flattened."""

    carried: tuple[str, ...]
    skipped: tuple[str, ...]
    notices: tuple[str, ...]


def _carry_one(
    parent: Path,
    child: Path,
    plan: SubmoduleSnapshot,
    *,
    with_state: bool,
    with_ignored: bool,
    config_pins: Sequence[tuple[str, str]],
    env: Mapping[str, str] | None,
) -> tuple[list[str], list[str], list[str]]:
    """Carry one submodule per the recipe, then recurse into its own nested plan.

    Steps below are numbered to match the design doc's "recipe, per gitlink,
    depth-first" (step 0, name/path resolution, already happened at snapshot
    time — the frozen ``plan`` already carries both).
    """
    carried: list[str] = []
    skipped: list[str] = []
    notices: list[str] = []

    # Step 1 — skip what the parent left cold.
    if not plan.initialized:
        skipped.append(plan.path)
        return carried, skipped, notices

    child_checkout = child / plan.path
    literal_path = f":(literal){plan.path}"

    # Step 2 — initialize from the parent's own checkout, never the remote.
    # protocol.file.allow and the URL override are command-scoped pins, never
    # ambient; the URL is keyed by name, never path (step 0). --checkout is
    # required so submodule.<name>.update=none cannot make this silently no-op.
    run_git(
        child,
        ["submodule", "update", "--init", "--checkout", "--", literal_path],
        env=env,
        config_pins=(
            ("protocol.file.allow", "always"),
            (f"submodule.{plan.name}.url", str(parent / plan.path)),
            *config_pins,
        ),
    )
    if not (child_checkout / ".git").exists():
        raise RuntimeError(
            f"submodule {plan.path!r} did not initialize; "
            "submodule.<name>.update policy may have blocked --checkout"
        )

    # Step 3 — restore only the child's own remote.origin.url. Never
    # `git submodule sync`: the child is a linked worktree sharing .git/config
    # with the parent, so top-level sync would corrupt the parent's config.
    if plan.remote_url is not None:
        run_git(
            child_checkout,
            ["config", "remote.origin.url", plan.remote_url],
            env=env,
            config_pins=config_pins,
        )

    # Step 4 — match the checked-out commit. This is what makes an unstaged
    # gitlink advance (cell `c`) representable at all.
    if plan.head is not None:
        run_git(
            child_checkout,
            ["checkout", "--detach", plan.head],
            env=env,
            config_pins=config_pins,
        )

    # Step 5 — reuse transport through the config_pins seam, not verbatim.
    materialize(
        parent / plan.path,
        child_checkout,
        with_state=with_state,
        with_ignored=with_ignored,
        inventory=plan.inventory,
        config_pins=config_pins,
        env=env,
    )
    carried.append(plan.path)
    notices.append(
        f"submodule carried: {plan.path} "
        "(only remote.origin.url restored, not fetch refspecs or "
        f"submodule.{plan.name}.active)"
    )

    # Step 6 — recurse for nested submodules, carrying the frozen plan for
    # that depth. The outer submodule's own checkout becomes the "parent" and
    # "child" for its own nested submodules.
    for nested_plan in plan.nested:
        nested_carried, nested_skipped, nested_notices = _carry_one(
            parent / plan.path,
            child_checkout,
            nested_plan,
            with_state=with_state,
            with_ignored=with_ignored,
            config_pins=config_pins,
            env=env,
        )
        carried.extend(f"{plan.path}/{item}" for item in nested_carried)
        skipped.extend(f"{plan.path}/{item}" for item in nested_skipped)
        notices.extend(nested_notices)

    return carried, skipped, notices


def carry_submodules(
    parent: Path,
    child: Path,
    plans: tuple[SubmoduleSnapshot, ...],
    *,
    with_state: bool,
    with_ignored: bool = False,
    config_pins: Sequence[tuple[str, str]] = (),
    env: Mapping[str, str] | None = None,
) -> CarryResult:
    """Carry every submodule in ``plans`` from ``parent`` into ``child``.

    ``plans`` is the frozen snapshot from `snapshot_submodules`, resolved
    before the worktree existed. ``child`` must already exist as a worktree of
    ``parent`` — this function does not create it.
    """
    carried: list[str] = []
    skipped: list[str] = []
    notices: list[str] = []
    for plan in plans:
        plan_carried, plan_skipped, plan_notices = _carry_one(
            parent,
            child,
            plan,
            with_state=with_state,
            with_ignored=with_ignored,
            config_pins=config_pins,
            env=env,
        )
        carried.extend(plan_carried)
        skipped.extend(plan_skipped)
        notices.extend(plan_notices)
    return CarryResult(tuple(carried), tuple(skipped), tuple(notices))
