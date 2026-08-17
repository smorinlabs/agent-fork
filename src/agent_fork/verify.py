"""Post-materialization verification ladder for a newly created fork."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from agent_fork.content import (
    CarriedState,
    capture_state,
    collect_inventory,
    compare_states,
)
from agent_fork.errors import VerificationError
from agent_fork.git import run_git
from agent_fork.repository import WorktreeCreation

DETAIL_LIMIT = 5


def _text(value: bytes) -> str:
    return value.decode(errors="surrogateescape").strip()


def _labelled(label: str, differences: Sequence[str]) -> str:
    shown = list(differences[:DETAIL_LIMIT])
    if len(differences) > DETAIL_LIMIT:
        shown.append(f"and {len(differences) - DETAIL_LIMIT} more")
    return f"{label} ({'; '.join(shown)})"


def _worktree_pairs(creation: WorktreeCreation, *, env: Mapping[str, str] | None):
    output = run_git(
        creation.parent_path, ["worktree", "list", "--porcelain"], env=env
    ).stdout
    pairs: set[tuple[str, str]] = set()
    path: str | None = None
    for line in output.decode(errors="surrogateescape").splitlines():
        if line.startswith("worktree "):
            path = line.removeprefix("worktree ")
        elif line.startswith("branch refs/heads/") and path is not None:
            pairs.add((path, line.removeprefix("branch refs/heads/")))
    return pairs


def verify_fork(
    creation: WorktreeCreation,
    *,
    with_state: bool = True,
    with_ignored: bool = False,
    parent_status_before: bytes,
    parent_state_before: CarriedState | None = None,
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
    if (str(creation.path), creation.branch) not in _worktree_pairs(creation, env=env):
        failures.append("worktree-list")

    status_args = ["status", "--porcelain=v1", "-z", "--untracked-files=all"]
    if with_ignored:
        status_args.append("--ignored")
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
            env=env,
        )
        content = compare_states(parent_state_before, child_state)
        if drift:
            failures.append(_labelled("parent-content", drift))
        if content:
            failures.append(_labelled("content-match", content))

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
        raise VerificationError("verification failed: " + ", ".join(failures))
