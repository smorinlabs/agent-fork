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
    Difference,
    Inventory,
    capture_state,
    collect_inventory,
    compare_states,
    gitlink_paths,
)
from agent_fork.git import run_git
from agent_fork.materialize import materialize
from agent_fork.text import escape_terminal_text

# Local configuration inside a parent's submodule is not cloned into the
# child's copy, so identical nested working trees can be *reported*
# differently on the two sides (gate-4 pass 1 finding 4, reproduced at depth
# 2 with `diff.ignoreSubmodules=all` set inside the parent's outer
# submodule). Every recursive status, inventory, and diff call below pins
# this, command-scoped, on top of whatever a caller's own `config_pins`
# supplies — a caller should not have to know this internal detail to get a
# correct comparison.
SEMANTIC_PINS: tuple[tuple[str, str], ...] = (("diff.ignoreSubmodules", "none"),)


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
        [
            "config",
            "-f",
            ".gitmodules",
            "--null",
            "--get-regexp",
            r"^submodule\..*\.path$",
        ],
        env=env,
        check=False,
    )
    mapping: dict[str, str] = {}
    text = result.stdout.decode(errors="surrogateescape")
    for record in text.split("\0"):
        if not record:
            continue
        # `--null` emits `key\nvalue`, not `key value` -- a plain single-space
        # split breaks the moment the config NAME itself contains a space,
        # which Git permits (gate-6 finding 5): the key becomes
        # indistinguishable from the value at the wrong boundary.
        key, _, value = record.partition("\n")
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
    config_pins: Sequence[tuple[str, str]],
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
    head = (
        run_git(checkout, ["rev-parse", "HEAD"], env=env, config_pins=config_pins)
        .stdout.decode()
        .strip()
    )
    remote_url = _resolve_remote_url(checkout, env=env)
    # with_submodules=True unconditionally: a submodule's own nested gitlinks
    # are represented via `nested` below regardless of the top-level flag —
    # the opt-out only governs whether *this* submodule is carried at all, not
    # whether collect_inventory hides one of its own children behind the
    # hardcoded `--ignore-submodules=dirty` filter (which would otherwise beat
    # the semantic pin on the same axis, since a command-line flag always
    # outranks a `-c` pin — confirmed empirically). config_pins carries the
    # SEMANTIC_PINS forward from the snapshot's own entry point (gate-6
    # finding 2): without them here, the snapshot could see LESS than what
    # carry and verify -- both pinned -- see later, producing a false
    # "newly carried" difference purely from the domain mismatch, not from
    # anything carry actually did wrong.
    inventory = collect_inventory(
        checkout,
        with_state=with_state,
        with_ignored=with_ignored,
        with_submodules=True,
        env=env,
        config_pins=config_pins,
    )
    content = (
        capture_state(checkout, inventory, env=env, config_pins=config_pins)
        if with_state
        else None
    )
    nested = _snapshot_recursive(
        checkout,
        with_state=with_state,
        with_ignored=with_ignored,
        config_pins=config_pins,
        env=env,
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
    config_pins: Sequence[tuple[str, str]],
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
            config_pins=config_pins,
            env=env,
        )
        for path in paths
    )


def snapshot_submodules(
    parent: Path,
    *,
    with_state: bool,
    with_ignored: bool = False,
    config_pins: Sequence[tuple[str, str]] = (),
    env: Mapping[str, str] | None = None,
) -> tuple[SubmoduleSnapshot, ...]:
    """Recursively freeze every submodule under ``parent``, before the fork.

    Must be called before the worktree exists — this is what makes it a
    snapshot rather than a live read. Empty when ``with_state`` is false: a
    fork carrying no state has nothing to snapshot either. The semantic pins
    (module docstring above ``SEMANTIC_PINS``) apply automatically on top of
    whatever ``config_pins`` the caller supplies, matching `carry_submodules`
    and `verify_submodules` -- a snapshot resolved without them could see
    less than what carry and verify, both pinned, see afterward.
    """
    if not with_state:
        return ()
    config_pins = (*SEMANTIC_PINS, *config_pins)
    return _snapshot_recursive(
        parent,
        with_state=with_state,
        with_ignored=with_ignored,
        config_pins=config_pins,
        env=env,
    )


@dataclass(frozen=True)
class CarryResult:
    """What one `carry_submodules` call actually did, recursively flattened."""

    carried: tuple[str, ...]
    skipped: tuple[str, ...]
    notices: tuple[str, ...]
    reasoned_skipped: tuple[str, ...]


def _carry_one(
    parent: Path,
    child: Path,
    plan: SubmoduleSnapshot,
    *,
    with_state: bool,
    with_ignored: bool,
    config_pins: Sequence[tuple[str, str]],
    env: Mapping[str, str] | None,
    _path_prefix: str = "",
) -> tuple[list[str], list[str], list[str], list[str]]:
    """Carry one submodule per the recipe, then recurse into its own nested plan.

    Steps below are numbered to match the design doc's "recipe, per gitlink,
    depth-first" (step 0, name/path resolution, already happened at snapshot
    time — the frozen ``plan`` already carries both).

    ``_path_prefix`` is internal recursion state, not a caller-facing
    parameter (mirrors ``verify_submodules``'s own): every path this call
    reports (``carried``/``skipped``/``reasoned_skipped`` entries and notice
    text) is qualified with it at depths below the top, so two different
    outer submodules that both happen to contain a nested submodule with the
    same name still produce attributable, distinguishable reports (gate-6
    round 2 finding 8). Filesystem-path uses (``child / plan.path`` etc.)
    stay unqualified -- those are relative to this level's own ``child``.
    """
    carried: list[str] = []
    skipped: list[str] = []
    notices: list[str] = []
    reasoned_skipped: list[str] = []
    qualified_path = f"{_path_prefix}{plan.path}" if _path_prefix else plan.path

    # Step 1 — skip what the parent left cold. Named, not silent: a cold
    # submodule at any nesting depth must not read as full recursion having
    # happened (design doc, "Notices"). Not "reasoned" in the sense below:
    # rung 6 already exempts this case via `plan.initialized is False`.
    if not plan.initialized:
        skipped.append(qualified_path)
        notices.append(
            f"submodule left cold: {escape_terminal_text(qualified_path)} "
            "(the parent itself never initialized it)"
        )
        return carried, skipped, notices, reasoned_skipped

    # A config name containing `=` cannot be expressed as a command-scoped
    # `-c submodule.<name>.url=...` override: Git's own `-c key=value` syntax
    # has no way to distinguish the name's own `=` from the pin's separator
    # (gate-6 finding 5). Applying the override anyway would silently do
    # nothing, falling through to whatever `.gitmodules` itself names as the
    # URL -- exactly the uncontrolled remote this recipe exists to avoid.
    # Skip rather than risk that. This is a REASONED skip (gate-6 round 2
    # finding 1): unlike an unexpected/silent skip, it must not fail
    # recursive verification -- the submodule was initialized in the parent
    # (`plan.initialized` is True) but is deliberately left cold here, so
    # both rung 1 (init parity) and rung 6 (nested-plan completeness) need to
    # know it was excused, not missed.
    if "=" in plan.name:
        skipped.append(qualified_path)
        reasoned_skipped.append(qualified_path)
        notices.append(
            f"submodule skipped: {escape_terminal_text(qualified_path)} "
            f"(its config name {escape_terminal_text(plan.name)!r} contains "
            "'=', which cannot be expressed as a command-scoped -c override; "
            "carrying it could otherwise contact its real remote)"
        )
        return carried, skipped, notices, reasoned_skipped

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
    else:
        # `submodule update --init` always writes a persistent
        # remote.origin.url into the child, pointed at whatever the
        # init-scoped `-c submodule.<name>.url` pin named -- the parent's
        # own local checkout path (gate-6 round 2 finding 7, confirmed
        # empirically). When the parent's own submodule had no origin at
        # all, that synthetic, machine-local origin must not survive: the
        # child should match the parent exactly, with none.
        run_git(
            child_checkout,
            ["remote", "remove", "origin"],
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
    # with_submodules=True: this submodule's own nested gitlinks are carried
    # too, via step 6's recursion below -- materialize's default loss notice
    # would otherwise wrongly claim they were not.
    materialize(
        parent / plan.path,
        child_checkout,
        with_state=with_state,
        with_ignored=with_ignored,
        with_submodules=True,
        inventory=plan.inventory,
        config_pins=config_pins,
        env=env,
    )
    carried.append(qualified_path)
    remote_note = (
        "only remote.origin.url restored"
        if plan.remote_url is not None
        else "no remote.origin.url to restore, origin removed"
    )
    notices.append(
        f"submodule carried: {escape_terminal_text(qualified_path)} "
        f"({remote_note}, not fetch refspecs or "
        f"submodule.{escape_terminal_text(plan.name)}.active)"
    )

    # Step 6 — recurse for nested submodules, carrying the frozen plan for
    # that depth. The outer submodule's own checkout becomes the "parent" and
    # "child" for its own nested submodules. `_path_prefix` qualification
    # happens inside the recursive call itself now, so its results arrive
    # already qualified -- no more post-hoc string-prefixing here.
    for nested_plan in plan.nested:
        nested_carried, nested_skipped, nested_notices, nested_reasoned = _carry_one(
            parent / plan.path,
            child_checkout,
            nested_plan,
            with_state=with_state,
            with_ignored=with_ignored,
            config_pins=config_pins,
            env=env,
            _path_prefix=f"{qualified_path}/",
        )
        carried.extend(nested_carried)
        skipped.extend(nested_skipped)
        notices.extend(nested_notices)
        reasoned_skipped.extend(nested_reasoned)

    return carried, skipped, notices, reasoned_skipped


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
    ``parent`` — this function does not create it. The semantic pins (module
    docstring above `SEMANTIC_PINS`) apply automatically on top of whatever
    ``config_pins`` the caller supplies.
    """
    config_pins = (*SEMANTIC_PINS, *config_pins)
    carried: list[str] = []
    skipped: list[str] = []
    notices: list[str] = []
    reasoned_skipped: list[str] = []
    for plan in plans:
        plan_carried, plan_skipped, plan_notices, plan_reasoned = _carry_one(
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
        reasoned_skipped.extend(plan_reasoned)
    return CarryResult(
        tuple(carried), tuple(skipped), tuple(notices), tuple(reasoned_skipped)
    )


def verify_submodules(
    parent: Path,
    child: Path,
    plans: tuple[SubmoduleSnapshot, ...],
    *,
    with_ignored: bool = False,
    skipped: tuple[str, ...] = (),
    reasoned_skipped: tuple[str, ...] = (),
    config_pins: Sequence[tuple[str, str]] = (),
    env: Mapping[str, str] | None = None,
    _path_prefix: str = "",
) -> list[Difference]:
    """The seven recursive verification rungs, per carried submodule.

    Two forks can agree on every top-level signal — status, inventory,
    manifest — while a submodule inside them is verifiably wrong (gate-4 pass
    3 finding 2). These rungs are what a top-level check cannot see: each is
    independently triggerable by an injected defect, per "Recursive
    verification" in the design doc. Recurses through ``plans[*].nested``. The
    semantic pins (module docstring above ``SEMANTIC_PINS``) apply
    automatically on top of whatever ``config_pins`` the caller supplies.

    ``_path_prefix`` is internal recursion state, not a caller-facing
    parameter: it is what qualifies every path this call reports (and every
    entry of ``skipped`` it checks against) at depths below the top, since
    ``carry_submodules`` itself qualifies a nested skip as ``outer/inner``
    (gate-6 finding 7) -- comparing against the bare ``plan.path`` at every
    recursion depth could never match that qualified shape.
    """
    config_pins = (*SEMANTIC_PINS, *config_pins)
    differences: list[Difference] = []
    for plan in plans:
        child_checkout = child / plan.path
        qualified_path = f"{_path_prefix}{plan.path}" if _path_prefix else plan.path

        # A reasoned skip (gate-6 round 2 finding 1, e.g. the `=`-in-name
        # case) is a deliberate decision, not a defect: it must not fail
        # rung 6 the way a silent/unexpected skip does. The one thing still
        # worth asserting is that the child actually stayed cold, the same
        # shape as the "parent left it cold" case below.
        if qualified_path in reasoned_skipped:
            if (child_checkout / ".git").exists():
                differences.append(
                    Difference(
                        qualified_path,
                        "submodule-reasoned-skip-initialized",
                        "expected the submodule to stay cold (reasoned skip), "
                        "but the child initialized it",
                    )
                )
            continue

        # Rung 6 — nested-plan completeness: the frozen plan expected this
        # submodule to be carried, but the carry step's own report says it
        # was skipped. Distinct from the ordinary "parent left it cold" case
        # (plan.initialized is False), which is not a failure.
        if plan.initialized and qualified_path in skipped:
            differences.append(
                Difference(
                    qualified_path,
                    "submodule-skipped",
                    "carried plan entry was silently skipped",
                )
            )
            continue

        # Rung 1 — initialized/cold parity.
        child_initialized = (child_checkout / ".git").exists()
        if child_initialized != plan.initialized:
            differences.append(
                Difference(
                    qualified_path,
                    "submodule-init-parity",
                    f"expected initialized={plan.initialized}, got {child_initialized}",
                )
            )
            continue
        if not plan.initialized:
            continue

        # Rung 2 — HEAD identity. This is the rung that catches a submodule
        # detached at the wrong commit while every top-level signal agrees.
        child_head = (
            run_git(
                child_checkout, ["rev-parse", "HEAD"], env=env, config_pins=config_pins
            )
            .stdout.decode()
            .strip()
        )
        if child_head != plan.head:
            differences.append(
                Difference(
                    qualified_path,
                    "submodule-head",
                    f"expected HEAD {plan.head}, got {child_head}",
                )
            )

        # Rung 3 — detached state, not attached to a branch that could
        # diverge from the pinned commit later.
        symbolic = run_git(
            child_checkout,
            ["symbolic-ref", "--quiet", "--short", "HEAD"],
            env=env,
            config_pins=config_pins,
            check=False,
        )
        if symbolic.returncode == 0:
            branch_name = symbolic.stdout.decode().strip()
            differences.append(
                Difference(
                    qualified_path,
                    "submodule-detached",
                    f"HEAD is attached to branch {branch_name!r}, expected detached",
                )
            )

        # Rungs 4+5 — status and content parity, via the same comparison the
        # top-level content-match rung already uses, one level down.
        if plan.content is not None:
            child_inventory = collect_inventory(
                child_checkout,
                with_state=True,
                with_ignored=with_ignored,
                with_submodules=True,
                env=env,
                config_pins=config_pins,
            )
            child_content = capture_state(
                child_checkout, child_inventory, env=env, config_pins=config_pins
            )
            for difference in compare_states(plan.content, child_content):
                differences.append(
                    Difference(
                        f"{qualified_path}/{difference.path}",
                        difference.check,
                        difference.detail,
                    )
                )

            # Rung 7 — recursive parent-untouched, extending the top-level
            # bracket one level down: carry must not be what dirties the
            # parent's own submodule checkout. A clean commit-to-commit move
            # (gate-6 finding 1) leaves the inventory-derived content
            # identical at both commits -- content comparison alone cannot
            # see it -- so the parent's HEAD is checked directly too,
            # mirroring rung 2's identity check for the child.
            parent_checkout = parent / plan.path
            parent_head = (
                run_git(
                    parent_checkout,
                    ["rev-parse", "HEAD"],
                    env=env,
                    config_pins=config_pins,
                )
                .stdout.decode()
                .strip()
            )
            if parent_head != plan.head:
                differences.append(
                    Difference(
                        qualified_path,
                        "submodule-parent-head",
                        f"expected parent HEAD {plan.head}, got {parent_head}",
                    )
                )
            parent_inventory = collect_inventory(
                parent_checkout,
                with_state=True,
                with_ignored=with_ignored,
                with_submodules=True,
                env=env,
                config_pins=config_pins,
            )
            parent_after = capture_state(
                parent_checkout, parent_inventory, env=env, config_pins=config_pins
            )
            for difference in compare_states(plan.content, parent_after):
                differences.append(
                    Difference(
                        f"{qualified_path}/{difference.path}",
                        "submodule-parent-untouched",
                        difference.detail,
                    )
                )

        differences.extend(
            verify_submodules(
                parent / plan.path,
                child_checkout,
                plan.nested,
                with_ignored=with_ignored,
                skipped=skipped,
                reasoned_skipped=reasoned_skipped,
                config_pins=config_pins,
                env=env,
                _path_prefix=f"{qualified_path}/",
            )
        )
    return differences
