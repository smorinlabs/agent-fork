"""Registry-scoped cleanup planning, guards, and mutation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from agent_fork.errors import AgentForkError, PreconditionError
from agent_fork.git import run_git
from agent_fork.models import RegistryEntry
from agent_fork.registry import find_owned, remove_entry


class CleanupTargetError(AgentForkError):
    code = "cleanup_target_unknown"
    exit_code = 3


@dataclass(frozen=True)
class CleanupPlan:
    entry: RegistryEntry
    worktree: Path
    branch: str
    git_root: Path
    owned: bool

    def render(self, *, keep_branch: bool = False) -> str:
        branch = "preserve" if keep_branch else f"delete {self.branch}"
        return (
            f"remove worktree {self.worktree}; branch: {branch}; "
            f"registry: {self.entry.name}"
        )


@dataclass(frozen=True)
class CleanupResult:
    plan: CleanupPlan
    removed: bool
    notices: tuple[str, ...]


def _git_root(worktree: Path, *, env: Mapping[str, str]) -> Path:
    result = run_git(worktree, ["rev-parse", "--git-common-dir"], env=env)
    value = Path(result.stdout.decode().strip())
    if not value.is_absolute():
        value = worktree / value
    return value.resolve()


def _worktrees(cwd: Path, *, env: Mapping[str, str]) -> list[tuple[Path, str | None]]:
    output = run_git(cwd, ["worktree", "list", "--porcelain"], env=env).stdout
    records: list[tuple[Path, str | None]] = []
    path: Path | None = None
    branch: str | None = None
    for line in output.decode(errors="surrogateescape").splitlines() + [""]:
        if line.startswith("worktree "):
            if path is not None:
                records.append((path, branch))
            path = Path(line.removeprefix("worktree ")).resolve()
            branch = None
        elif line.startswith("branch refs/heads/"):
            branch = line.removeprefix("branch refs/heads/")
        elif not line and path is not None:
            records.append((path, branch))
            path = None
            branch = None
    return records


def resolve_cleanup_target(
    target: str,
    *,
    cwd: Path,
    env: Mapping[str, str],
    force: bool = False,
) -> CleanupPlan:
    owned = find_owned(target, env=env)
    if owned is not None:
        worktree = Path(owned.worktree).resolve()
        return CleanupPlan(
            owned, worktree, owned.branch, _git_root(worktree, env=env), True
        )
    if not force:
        raise CleanupTargetError(
            f"cleanup target {target!r} was not created by agent-fork; "
            "use --force to extend targeting"
        )
    candidate = Path(target).expanduser()
    matches: list[tuple[Path, str | None]] = []
    try:
        matches = _worktrees(cwd, env=env)
    except Exception:
        if candidate.exists():
            matches = _worktrees(candidate.resolve(), env=env)
    resolved = candidate.resolve()
    for path, branch in matches:
        if resolved == path or target == branch:
            if branch is None:
                raise CleanupTargetError("cannot clean a detached worktree by branch")
            entry = RegistryEntry.create(
                name=path.name, branch=branch, worktree=path, agent="unknown"
            )
            return CleanupPlan(entry, path, branch, _git_root(path, env=env), False)
    raise CleanupTargetError(f"cleanup target not found: {target}")


def _validate(
    plan: CleanupPlan, *, cwd: Path, env: Mapping[str, str], force: bool
) -> None:
    invoking = cwd.resolve()
    if invoking == plan.worktree or plan.worktree in invoking.parents:
        raise PreconditionError(
            "cleanup_target_is_cwd", "refusing to remove the invoking working directory"
        )
    if force:
        return
    status = run_git(plan.worktree, ["status", "--porcelain=v1", "-z"], env=env).stdout
    if status:
        raise PreconditionError(
            "cleanup_dirty_worktree", f"cleanup target is dirty: {plan.worktree}"
        )
    upstream = run_git(
        plan.worktree,
        ["for-each-ref", "--format=%(refname)", "--contains", "HEAD", "refs/remotes"],
        env=env,
    ).stdout
    if not upstream.strip():
        raise PreconditionError(
            "cleanup_unpushed_commits",
            "cleanup target has commits not reachable from any upstream: "
            f"{plan.branch}",
        )


def cleanup(
    plan: CleanupPlan,
    *,
    cwd: Path,
    env: Mapping[str, str],
    force: bool = False,
    keep_branch: bool = False,
    dry_run: bool = False,
) -> CleanupResult:
    _validate(plan, cwd=cwd, env=env, force=force)
    notices = (
        "agent session files were not deleted; the fork session remains resumable "
        "and may be archived with the agent CLI",
    )
    if dry_run:
        return CleanupResult(plan, False, notices)
    run_git(
        plan.git_root,
        ["worktree", "remove", "--force", str(plan.worktree)],
        env=env,
    )
    run_git(plan.git_root, ["worktree", "prune"], env=env)
    if not keep_branch:
        run_git(plan.git_root, ["branch", "-D", plan.branch], env=env)
    if plan.owned:
        remove_entry(plan.entry.name, env=env)
    return CleanupResult(plan, True, notices)
