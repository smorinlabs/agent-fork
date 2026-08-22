"""Post-materialization verification ladder for a newly created fork."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from agent_fork.content import (
    CarriedState,
    Difference,
    SkipRecord,
    capture_state,
    collect_inventory,
    compare_states,
)
from agent_fork.errors import VerificationError
from agent_fork.git import run_git
from agent_fork.repository import WorktreeCreation
from agent_fork.submodules import SEMANTIC_PINS, SubmoduleSnapshot, verify_submodules
from agent_fork.text import escape_terminal_text
from agent_fork.worktree_list import list_worktrees

DETAIL_LIMIT = 5


def _text(value: bytes) -> str:
    return value.decode(errors="surrogateescape").strip()


def _labelled(label: str, differences: Sequence[Difference]) -> str:
    shown = [
        f"{escape_terminal_text(item.path)}: {item.detail}"
        for item in differences[:DETAIL_LIMIT]
    ]
    if len(differences) > DETAIL_LIMIT:
        shown.append(f"and {len(differences) - DETAIL_LIMIT} more")
    return f"{label} ({'; '.join(shown)})"


def _failed_check(
    label: str, differences: Sequence[Difference], *, primary: bool
) -> dict[str, object]:
    """Structured record for ``error.details.failed_checks``.

    Paths are escaped here as well as in the message: a filename may contain
    bytes that are not valid UTF-8, which would otherwise raise on encoding
    when the machine document is written.
    """
    return {
        "check": label,
        "primary": primary,
        "total": len(differences),
        "differences": [
            {
                "path": escape_terminal_text(item.path),
                "kind": item.check,
                "detail": item.detail,
            }
            for item in differences[:DETAIL_LIMIT]
        ],
    }


def _worktree_pairs(creation: WorktreeCreation, *, env: Mapping[str, str] | None):
    return {
        (str(record.path), record.branch)
        for record in list_worktrees(creation.parent_path, env=env)
        if record.branch is not None
    }


def _submodule_roots_with_entry_skips(
    plans: tuple[SubmoduleSnapshot, ...], skipped: tuple[SkipRecord, ...]
) -> tuple[str, ...]:
    """Name top-level gitlinks whose recursive content has an allowed skip."""
    skipped_paths = tuple(str(getattr(record, "path", record)) for record in skipped)
    return tuple(
        plan.path
        for plan in plans
        if any(path.startswith(f"{plan.path}/") for path in skipped_paths)
    )


def _without_top_level_paths(
    state: CarriedState, omitted: tuple[str, ...]
) -> CarriedState:
    """Remove exact top-level paths delegated to recursive verification."""
    omitted_set = set(omitted)
    return CarriedState(
        paths=tuple(path for path in state.paths if path not in omitted_set),
        index=tuple(entry for entry in state.index if entry.path not in omitted_set),
        manifest=tuple(
            entry for entry in state.manifest if entry.path not in omitted_set
        ),
        skipped=tuple(
            record for record in state.skipped if record.path not in omitted_set
        ),
    )


def verify_fork(
    creation: WorktreeCreation,
    *,
    with_state: bool = True,
    with_ignored: bool = False,
    with_submodules: bool = False,
    parent_status_before: bytes,
    parent_state_before: CarriedState | None = None,
    submodule_plans: tuple[SubmoduleSnapshot, ...] = (),
    submodule_skipped: tuple[str, ...] = (),
    submodule_reasoned_skipped: tuple[str, ...] = (),
    submodule_entry_skips: tuple[SkipRecord, ...] = (),
    skipped: tuple[object, ...] = (),
    env: Mapping[str, str] | None = None,
) -> None:
    """Run the complete base ladder and topology-dependent assertions.

    ``parent_state_before`` is the carried-state snapshot taken in the parent
    before the worktree existed. It is the reference for both content rungs:
    the child must reproduce it, and the parent must still match it afterwards.
    Content rungs are skipped when it is absent, so callers that only exercise
    the topology ladder need not build one.
    """
    failures: list[str] = []
    failed_checks: list[dict[str, object]] = []
    recursive_skip_roots = _submodule_roots_with_entry_skips(
        submodule_plans, submodule_entry_skips
    )
    head = _text(
        run_git(creation.path, ["rev-parse", "--verify", "HEAD"], env=env).stdout
    )
    if head != creation.anchor:
        failures.append("anchor")
    branch = _text(
        run_git(creation.path, ["rev-parse", "--abbrev-ref", "HEAD"], env=env).stdout
    )
    if branch != creation.branch:
        failures.append("branch")
    if (str(creation.path.resolve()), creation.branch) not in _worktree_pairs(
        creation, env=env
    ):
        failures.append("worktree-list")

    # `--ignore-submodules=dirty` suppresses submodule *working-tree* state,
    # which an opted-out fork does not carry — `git worktree add` never
    # initializes submodules, so the child cannot reproduce the parent's
    # ` M <path>`. It still reports commit-level gitlink differences, so a
    # submodule advance staged in the parent, which does travel in the staged
    # patch, keeps being compared. `=all` would hide that too (A6a). Dropped
    # entirely when `with_submodules` is true (A6b step 6): a fork that
    # carries submodules identically should match the parent exactly, with no
    # exemption — the recursive rungs below carry the real weight of proving
    # that, but the top-level status comparison stays strict too.
    status_args = [
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    ]
    if not with_submodules:
        status_args.append("--ignore-submodules=dirty")
    if with_ignored:
        status_args.append("--ignored")
    # A skipped entry is in the parent and absent from the child by design, so
    # exclude it at the query boundary. Literal pathspecs keep metacharacters
    # in a filename from acting as patterns (P02 A5).
    status_exclusions = tuple(
        sorted(
            {
                *(str(getattr(record, "path", record)) for record in skipped),
                *recursive_skip_roots,
            },
            key=lambda path: path.encode("utf-8", "surrogateescape"),
        )
    )
    if status_exclusions:
        status_args.extend(["--", "."])
        status_args.extend(":(exclude,literal)" + path for path in status_exclusions)

    # The child's carried submodule is a fresh `submodule update --init`, so
    # it never inherits the parent's own submodule's local git config
    # (nothing copies arbitrary config, only tracked/working-tree state) --
    # an ambient setting like `diff.ignoreSubmodules` inside the PARENT's
    # submodule can therefore make the two raw `git status` outputs
    # genuinely differ even though carry transported the content correctly
    # (gate-6 finding 2, same root cause one more layer up). Pinning both
    # sides to the same semantic policy is what makes the comparison
    # apples-to-apples.
    status_pins = SEMANTIC_PINS if with_submodules else ()
    child_status = run_git(
        creation.path, status_args, env=env, config_pins=status_pins
    ).stdout
    if with_state:
        parent_status = run_git(
            creation.parent_path, status_args, env=env, config_pins=status_pins
        ).stdout
        if child_status != parent_status:
            failures.append("exact-copy-status")
    elif child_status:
        failures.append("clean-from-head")

    if with_state and parent_state_before is not None:
        # SEMANTIC_PINS matches the pins pipeline.py applies to the snapshot
        # it captured before the fork (gate-6 finding 2): recomputing here
        # without them would create the same false-difference domain
        # mismatch one more time, symmetrically, at the top level.
        top_level_pins = SEMANTIC_PINS if with_submodules else ()
        parent_after = capture_state(
            creation.parent_path,
            collect_inventory(
                creation.parent_path,
                with_state=with_state,
                with_ignored=with_ignored,
                with_submodules=with_submodules,
                env=env,
                config_pins=top_level_pins,
            ),
            known_skipped=skipped,
            env=env,
            config_pins=top_level_pins,
        )
        expected_state = _without_top_level_paths(
            parent_state_before, recursive_skip_roots
        )
        parent_after = _without_top_level_paths(parent_after, recursive_skip_roots)
        drift = compare_states(expected_state, parent_after)
        child_state = capture_state(
            creation.path,
            collect_inventory(
                creation.path,
                with_state=with_state,
                with_ignored=with_ignored,
                with_submodules=with_submodules,
                env=env,
                config_pins=top_level_pins,
            ),
            known_skipped=skipped,
            env=env,
            config_pins=top_level_pins,
        )
        child_state = _without_top_level_paths(child_state, recursive_skip_roots)
        content = compare_states(expected_state, child_state)
        if drift:
            failures.append(_labelled("parent-content", drift))
            failed_checks.append(_failed_check("parent-content", drift, primary=True))
        if content:
            failures.append(_labelled("content-match", content))
            failed_checks.append(
                _failed_check("content-match", content, primary=not drift)
            )

    if with_state and with_submodules and submodule_plans:
        submodule_differences = verify_submodules(
            creation.parent_path,
            creation.path,
            submodule_plans,
            with_ignored=with_ignored,
            skipped=submodule_skipped,
            reasoned_skipped=submodule_reasoned_skipped,
            env=env,
        )
        if submodule_differences:
            first_failure = not failures
            failures.append(_labelled("submodule-content-match", submodule_differences))
            failed_checks.append(
                _failed_check(
                    "submodule-content-match",
                    submodule_differences,
                    primary=first_failure,
                )
            )

    parent_status_after = run_git(
        creation.parent_path, ["status", "--porcelain=v1", "-z"], env=env
    ).stdout
    if parent_status_after != parent_status_before:
        failures.append("parent-untouched")
    if creation.parent_on_default and creation.branch == creation.parent_branch:
        failures.append("branch-is-default")
    child_common = _text(
        run_git(creation.path, ["rev-parse", "--git-common-dir"], env=env).stdout
    )
    from pathlib import Path

    common_path = Path(child_common)
    if not common_path.is_absolute():
        common_path = creation.path / common_path
    if common_path.resolve() != creation.common_dir.resolve():
        failures.append("common-dir")
    if creation.parent_detached:
        symbolic = run_git(
            creation.parent_path,
            ["symbolic-ref", "--quiet", "--short", "HEAD"],
            env=env,
            check=False,
        )
        if creation.parent_branch is not None or symbolic.returncode == 0:
            failures.append("detached-record")
    if failures:
        raise VerificationError(
            "verification failed: " + ", ".join(failures),
            details={"failed_checks": failed_checks} if failed_checks else None,
        )
