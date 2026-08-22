"""Post-materialization verification ladder for a newly created fork."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from agent_fork.content import (
    CarriedState,
    Difference,
    capture_state,
    collect_inventory,
    compare_states,
)
from agent_fork.errors import VerificationError
from agent_fork.git import run_git
from agent_fork.repository import WorktreeCreation
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


def verify_fork(
    creation: WorktreeCreation,
    *,
    with_state: bool = True,
    with_ignored: bool = False,
    parent_status_before: bytes,
    parent_state_before: CarriedState | None = None,
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
    # which a fork does not carry — `git worktree add` never initializes
    # submodules, so the child cannot reproduce the parent's ` M <path>`. It
    # still reports commit-level gitlink differences, so a submodule advance
    # staged in the parent, which does travel in the staged patch, keeps being
    # compared. `=all` would hide that too (A6a).
    status_args = [
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        "--ignore-submodules=dirty",
    ]
    if with_ignored:
        status_args.append("--ignored")
    # A skipped entry is in the parent and absent from the child by design, so
    # an unfiltered comparison would fail every skipping fork. Excluded at the
    # query boundary rather than by post-processing porcelain, following A6a's
    # shape, with `literal` magic so a filename containing pathspec characters
    # cannot act as a pattern. The `parent-untouched` bracket below is
    # deliberately NOT filtered: it compares the parent against itself, where a
    # skipped path appears identically on both sides, and filtering it would
    # hide a real mid-fork transition (P02 A5).
    if skipped:
        status_args.extend(["--", "."])
        status_args.extend(
            ":(exclude,literal)" + str(getattr(r, "path", r)) for r in skipped
        )
    child_status = run_git(creation.path, status_args, env=env).stdout
    if with_state:
        parent_status = run_git(creation.parent_path, status_args, env=env).stdout
        if child_status != parent_status:
            failures.append("exact-copy-status")
    elif child_status:
        failures.append("clean-from-head")

    if with_state and parent_state_before is not None:
        parent_after = capture_state(
            creation.parent_path,
            collect_inventory(
                creation.parent_path,
                with_state=with_state,
                with_ignored=with_ignored,
                env=env,
            ),
            known_skipped=skipped,
            env=env,
        )
        drift = compare_states(parent_state_before, parent_after)
        child_state = capture_state(
            creation.path,
            collect_inventory(
                creation.path,
                with_state=with_state,
                with_ignored=with_ignored,
                env=env,
            ),
            known_skipped=skipped,
            env=env,
        )
        content = compare_states(parent_state_before, child_state)
        if drift:
            failures.append(_labelled("parent-content", drift))
            failed_checks.append(_failed_check("parent-content", drift, primary=True))
        if content:
            failures.append(_labelled("content-match", content))
            failed_checks.append(
                _failed_check("content-match", content, primary=not drift)
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
