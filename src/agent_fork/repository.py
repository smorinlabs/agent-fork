"""Repository topology, pre-mutation guards, and atomic worktree creation."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from agent_fork.content import gitlink_paths, nul_paths
from agent_fork.errors import PreconditionError
from agent_fork.git import GitCommandError, run_git
from agent_fork.text import escape_terminal_text
from agent_fork.worktree_list import list_worktrees


@dataclass(frozen=True)
class RepositoryInfo:
    parent_path: Path
    git_dir: Path
    common_dir: Path
    worktree_root: Path | None
    bare: bool

    @property
    def linked_worktree(self) -> bool:
        return self.git_dir != self.common_dir


@dataclass(frozen=True)
class WorktreeCreation:
    path: Path
    branch: str
    anchor: str
    branch_created: bool
    parent_path: Path
    common_dir: Path
    parent_branch: str | None
    parent_detached: bool
    parent_on_default: bool


@dataclass(frozen=True)
class DefaultBranchClassification:
    remote_default_branch: str | None
    candidates: tuple[str, ...]


@dataclass(frozen=True)
class WorkingTreeStatus:
    staged: int
    unstaged: int
    untracked: int
    unmerged: int
    operation: str | None

    @property
    def clean(self) -> bool:
        return (
            self.staged == 0
            and self.unstaged == 0
            and self.untracked == 0
            and self.unmerged == 0
            and self.operation is None
        )

    def document(self) -> dict[str, object]:
        return {
            "clean": self.clean,
            "staged": self.staged,
            "unstaged": self.unstaged,
            "untracked": self.untracked,
            "unmerged": self.unmerged,
            "operation": self.operation,
        }


def _resolve_git_path(parent: Path, value: str) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = parent / candidate
    return candidate.resolve()


def inspect_repository(
    parent: Path, *, env: Mapping[str, str] | None = None
) -> RepositoryInfo:
    """Resolve Git metadata for plain, linked, and bare invocation paths."""
    resolved_parent = parent.resolve()
    probe = run_git(
        resolved_parent,
        ["rev-parse", "--git-dir", "--git-common-dir", "--is-bare-repository"],
        env=env,
        check=False,
    )
    if probe.returncode != 0:
        raise PreconditionError(
            "not_git_repository", f"{resolved_parent} is not a Git repository"
        )
    lines = probe.stdout.decode().splitlines()
    if len(lines) != 3:
        raise PreconditionError(
            "not_git_repository", "unable to resolve Git repository"
        )
    git_dir = _resolve_git_path(resolved_parent, lines[0])
    common_dir = _resolve_git_path(resolved_parent, lines[1])
    bare = lines[2] == "true"
    worktree_root: Path | None = None
    if not bare:
        root = run_git(resolved_parent, ["rev-parse", "--show-toplevel"], env=env)
        worktree_root = Path(root.stdout.decode().strip()).resolve()
    return RepositoryInfo(
        parent_path=resolved_parent,
        git_dir=git_dir,
        common_dir=common_dir,
        worktree_root=worktree_root,
        bare=bare,
    )


def _worktree_branches(
    parent: Path, *, env: Mapping[str, str] | None
) -> dict[str, Path]:
    branches: dict[str, Path] = {}
    for record in list_worktrees(parent, env=env):
        if record.branch is not None:
            branches[record.branch] = record.path
    return branches


def live_worktree_pairs(
    parent: Path, *, env: Mapping[str, str] | None = None
) -> frozenset[tuple[str, str]]:
    """Freshly observed (worktree path, branch) pairs for one repository.

    This is the evidence registry records are checked against, so it reports
    only what is demonstrably there *now*. Enumeration comes from
    `list_worktrees`, and every listed path is then asked directly which
    repository it belongs to and which branch it is on, because being listed
    is not the same as being present:

    - Git keeps listing a worktree whose directory was deleted, marking it
      `prunable`, until someone runs `git worktree prune`;
    - a directory can be replaced by an unrelated repository's worktree while
      the original repository still lists the path.

    Both are excluded by the probe rather than by parsing list metadata, which
    is why this does not need the `prunable` field. Detached worktrees are
    excluded too: a fork always has a branch, so a record matching nothing
    here is not one of this repository's forks.
    """
    own_common_dir = inspect_repository(parent, env=env).common_dir
    pairs: set[tuple[str, str]] = set()
    for record in list_worktrees(parent, env=env):
        current = _current_worktree_identity(record.path, env=env)
        if current is None:
            continue
        common_dir, branch = current
        if common_dir == own_common_dir:
            pairs.add((str(record.path), branch))
    return frozenset(pairs)


def _current_worktree_identity(
    path: Path, *, env: Mapping[str, str] | None
) -> tuple[Path, str] | None:
    """The repository and branch a directory belongs to right now.

    Returns None when the path is not a usable worktree or has no branch: a
    fork always has one, so a detached or broken directory can never confirm a
    registry record.
    """
    probe = run_git(
        path,
        ["rev-parse", "--git-common-dir", "--abbrev-ref", "HEAD"],
        env=env,
        check=False,
    )
    if probe.returncode != 0:
        return None
    lines = probe.stdout.decode(errors="surrogateescape").splitlines()
    if len(lines) != 2 or lines[1] == "HEAD":
        return None
    return _resolve_git_path(path, lines[0]), lines[1]


_OPERATION_SENTINELS = {
    "rebase": ("rebase-merge", "rebase-apply"),
    "merge": ("MERGE_HEAD",),
    "cherry-pick": ("CHERRY_PICK_HEAD",),
    "revert": ("REVERT_HEAD",),
    "bisect": ("BISECT_LOG",),
}


def mid_operation(info: RepositoryInfo) -> str | None:
    for operation, sentinels in _OPERATION_SENTINELS.items():
        if any((info.git_dir / sentinel).exists() for sentinel in sentinels):
            return operation
    return None


def current_branch(parent: Path, *, env: Mapping[str, str] | None = None) -> str | None:
    result = run_git(
        parent,
        ["symbolic-ref", "--quiet", "--short", "HEAD"],
        env=env,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.decode(errors="replace").strip()


def classify_default_branches(
    parent: Path, *, env: Mapping[str, str] | None = None
) -> DefaultBranchClassification:
    remote_default: str | None = None
    remote = run_git(
        parent,
        ["symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"],
        env=env,
        check=False,
    )
    if remote.returncode == 0:
        remote_default = (
            remote.stdout.decode(errors="replace").strip().removeprefix("origin/")
        )

    candidates: list[str] = []
    if remote_default:
        candidates.append(remote_default)
    for fallback in ("main", "master"):
        present = run_git(
            parent,
            ["show-ref", "--verify", "--quiet", f"refs/heads/{fallback}"],
            env=env,
            check=False,
        )
        if present.returncode == 0 and fallback not in candidates:
            candidates.append(fallback)
    return DefaultBranchClassification(remote_default, tuple(candidates))


def count_paths(
    parent: Path,
    arguments: list[str],
    *,
    env: Mapping[str, str] | None = None,
) -> int:
    data = run_git(parent, arguments, env=env).stdout
    return len({value for value in data.split(b"\0") if value})


def inspect_working_tree_status(
    info: RepositoryInfo, *, env: Mapping[str, str] | None = None
) -> WorkingTreeStatus | None:
    if info.bare:
        return None
    assert info.worktree_root is not None
    parent = info.worktree_root
    unmerged = run_git(parent, ["ls-files", "-u", "-z"], env=env).stdout
    unmerged_paths = {
        record.split(b"\t", 1)[1] for record in unmerged.split(b"\0") if b"\t" in record
    }
    return WorkingTreeStatus(
        staged=count_paths(
            parent,
            ["diff", "--cached", "--name-only", "-z", "--no-renames"],
            env=env,
        ),
        unstaged=count_paths(
            parent, ["diff", "--name-only", "-z", "--no-renames"], env=env
        ),
        untracked=count_paths(
            parent,
            ["ls-files", "--others", "--exclude-standard", "-z"],
            env=env,
        ),
        unmerged=len(unmerged_paths),
        operation=mid_operation(info),
    )


def _abort_hint(operation: str, parent: Path) -> str:
    command = (
        "git bisect reset" if operation == "bisect" else f"git {operation} --abort"
    )
    return f'cd "{parent}" && {command}'


def _unrepresentable_submodules(
    parent: Path, *, env: Mapping[str, str] | None
) -> list[str]:
    """Submodules checked out at a commit the parent's index does not record.

    A fork carries submodule state only as the gitlink in the parent's index, so
    a checkout sitting at some other commit is a fact the child cannot express:
    saying it would require a submodule checkout, and the child has none.
    `--ignore-submodules=dirty` keeps reporting that case while suppressing
    working-tree dirt, so it survives to be refused here rather than failing
    verification after a worktree has been built and destroyed.

    `--diff-filter=M` narrows it to exactly that case. A removed submodule
    directory also reports as an unstaged gitlink change, but it transports as an
    ordinary `deleted file mode 160000` hunk like any other deletion, and a
    conflicted gitlink reports as unmerged rather than modified. Refusing either
    would block a fork that works.

    A6b removes this limitation for the default path: once the child's submodule
    is initialized and detached at the parent's submodule HEAD, the state is
    representable and this guard must not fire.
    """
    gitlinks = set(gitlink_paths(parent, env=env))
    if not gitlinks:
        return []
    changed = run_git(
        parent,
        [
            "diff",
            "--name-only",
            "-z",
            "--no-renames",
            "--diff-filter=M",
            "--ignore-submodules=dirty",
        ],
        env=env,
    )
    return sorted(gitlinks.intersection(nul_paths(changed.stdout)))


def validate_fork_guards(
    parent: Path,
    branch: str,
    destination: Path,
    *,
    with_state: bool = True,
    with_submodules: bool = False,
    env: Mapping[str, str] | None = None,
) -> RepositoryInfo:
    """Run every refusal before filesystem or ref mutation.

    The submodule refusal fires on ``with_state and not with_submodules``
    (A6b step 6). A fork that carries no state reproduces nothing about the
    parent's submodules, so there is no divergence to refuse — and refusing
    anyway would block the remedy the error itself recommends. A fork that
    carries submodules identically can represent an unstaged gitlink advance,
    because the child gets a real submodule checkout to detach at the
    parent's submodule HEAD — so the refusal must not fire there either.
    ``with_submodules`` defaults false so a caller that predates A6b, or that
    never resolved the flag, keeps A6a's original unconditional-on-with_state
    behaviour.
    """
    info = inspect_repository(parent, env=env)
    attached = _worktree_branches(info.parent_path, env=env)
    if branch in attached:
        raise PreconditionError(
            "conflict_branch_worktree",
            f"branch {branch!r} already has a worktree at "
            f"{escape_terminal_text(str(attached[branch]))}",
        )
    branch_probe = run_git(
        info.parent_path,
        ["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
        env=env,
        check=False,
    )
    if branch_probe.returncode == 0:
        raise PreconditionError(
            "conflict_branch_exists", f"branch {branch!r} already exists"
        )
    if destination.exists() or destination.is_symlink():
        raise PreconditionError(
            "conflict_worktree_path", f"worktree path already exists: {destination}"
        )
    operation = mid_operation(info)
    if operation is not None:
        raise PreconditionError(
            "parent_mid_operation",
            f"parent is mid-{operation}; finish or abort it: "
            f"{_abort_hint(operation, info.parent_path)}",
        )
    head = run_git(
        info.parent_path,
        ["rev-parse", "--verify", "HEAD^{commit}"],
        env=env,
        check=False,
    )
    if head.returncode != 0:
        raise PreconditionError(
            "repo_no_commits",
            "repository has no commits; make an initial commit and re-run agent-fork",
        )
    unmerged = run_git(info.parent_path, ["ls-files", "-u", "-z"], env=env)
    paths: set[str] = set()
    for record in unmerged.stdout.split(b"\0"):
        if b"\t" in record:
            paths.add(os.fsdecode(record.split(b"\t", 1)[1]))
    if paths:
        rendered = ", ".join(escape_terminal_text(path) for path in sorted(paths))
        raise PreconditionError(
            "unmerged_index",
            f"unmerged index paths: {rendered}; resolve conflicts and re-run",
        )
    # Last, because every guard above names a state the user can act on directly.
    # `gitlink_paths` reads mode-160000 entries from every index stage, so a
    # conflicted submodule would otherwise be refused here first, with a remedy
    # -- stage it, or --no-with-state -- that cannot clear a conflicted index.
    unrepresentable = (
        _unrepresentable_submodules(info.parent_path, env=env)
        if with_state and not with_submodules
        else []
    )
    if unrepresentable:
        listed = ", ".join(escape_terminal_text(path) for path in unrepresentable)
        raise PreconditionError(
            "submodule_unrepresentable",
            f"submodule checkout differs from the recorded commit: {listed}; "
            "a fork carries submodules only as the commit recorded in the index. "
            "Stage it (git add -- <path>), or fork without carrying state "
            "(--no-with-state)",
        )
    return info


def resolve_anchor(parent: Path, *, env: Mapping[str, str] | None = None) -> str:
    result = run_git(parent, ["rev-parse", "--verify", "HEAD^{commit}"], env=env)
    return result.stdout.decode().strip()


def create_worktree_at_anchor(
    parent: Path,
    branch: str,
    destination: Path,
    *,
    anchor: str | None = None,
    env: Mapping[str, str] | None = None,
) -> WorktreeCreation:
    """Atomically ask Git to create branch+worktree and classify race losses."""
    info = inspect_repository(parent, env=env)
    resolved_anchor = anchor or resolve_anchor(parent, env=env)
    parent_branch = current_branch(parent, env=env)
    default_branches = classify_default_branches(parent, env=env)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        run_git(
            parent,
            ["worktree", "add", "-b", branch, str(destination), resolved_anchor],
            env=env,
        )
    except GitCommandError as error:
        branch_now_exists = (
            run_git(
                parent,
                ["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
                env=env,
                check=False,
            ).returncode
            == 0
        )
        if branch_now_exists:
            raise PreconditionError(
                "conflict_branch_exists",
                f"branch {branch!r} won a concurrent creation race; "
                "nothing was created",
            ) from error
        raise
    return WorktreeCreation(
        path=destination.resolve(),
        branch=branch,
        anchor=resolved_anchor,
        branch_created=True,
        parent_path=info.parent_path,
        common_dir=info.common_dir,
        parent_branch=parent_branch,
        parent_detached=parent_branch is None,
        parent_on_default=parent_branch in default_branches.candidates,
    )
