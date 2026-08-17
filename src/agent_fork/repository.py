"""Repository topology, pre-mutation guards, and atomic worktree creation."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from agent_fork.errors import PreconditionError
from agent_fork.git import GitCommandError, run_git
from agent_fork.text import escape_terminal_text


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
    result = run_git(parent, ["worktree", "list", "--porcelain"], env=env)
    branches: dict[str, Path] = {}
    current_path: Path | None = None
    for line in result.stdout.decode(errors="surrogateescape").splitlines():
        if line.startswith("worktree "):
            current_path = Path(line.removeprefix("worktree ")).resolve()
        elif line.startswith("branch refs/heads/") and current_path is not None:
            branches[line.removeprefix("branch refs/heads/")] = current_path
    return branches


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


def validate_fork_guards(
    parent: Path,
    branch: str,
    destination: Path,
    *,
    env: Mapping[str, str] | None = None,
) -> RepositoryInfo:
    """Run every refusal before filesystem or ref mutation."""
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
