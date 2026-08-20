"""Registry-scoped cleanup planning, guards, and mutation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from agent_fork.errors import AgentForkError, PreconditionError
from agent_fork.git import run_git
from agent_fork.models import RegistryEntry
from agent_fork.registry import (
    find_candidates,
    is_live,
    registry_lock,
    registry_path,
    remove_locked,
    require_single,
)
from agent_fork.repository import inspect_repository, live_worktree_pairs
from agent_fork.text import escape_terminal_text as _escape_terminal_text
from agent_fork.worktree_list import list_worktrees

DETAIL_LIMIT = 10


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
    # Working directory the repository was identified from, kept so the plan
    # can be revalidated against the same repository it was built against.
    # `git_root` is a Git common directory and cannot enumerate worktrees.
    anchor: Path | None = None

    def render(self, *, keep_branch: bool = False) -> str:
        branch = (
            "preserve"
            if keep_branch
            else f"delete {_escape_terminal_text(self.branch)}"
        )
        return (
            f"remove worktree {_escape_terminal_text(str(self.worktree))}; "
            f"branch: {branch}; registry: {_escape_terminal_text(self.entry.name)}"
        )


@dataclass(frozen=True)
class DirtyPath:
    status: str
    path: str

    def document(self) -> dict[str, str]:
        return {"status": self.status, "path": self.path}


@dataclass(frozen=True)
class UnpushedCommit:
    sha: str
    subject: str

    def document(self) -> dict[str, str]:
        return {"sha": self.sha, "subject": self.subject}


@dataclass(frozen=True)
class CleanupDetails:
    dirty: tuple[DirtyPath, ...]
    dirty_count: int
    unpushed: tuple[UnpushedCommit, ...]
    unpushed_count: int

    @property
    def has_risk(self) -> bool:
        return bool(self.dirty_count or self.unpushed_count)

    def document(self) -> dict[str, object]:
        return {
            "dirty": [entry.document() for entry in self.dirty],
            "dirty_count": self.dirty_count,
            "dirty_truncated": self.dirty_count > len(self.dirty),
            "unpushed": [entry.document() for entry in self.unpushed],
            "unpushed_count": self.unpushed_count,
            "unpushed_truncated": self.unpushed_count > len(self.unpushed),
        }

    def render_preview(self, branch: str) -> str:
        blocks: list[str] = []
        if self.dirty_count:
            change = "change" if self.dirty_count == 1 else "changes"
            blocks.append(
                "\n".join(
                    _dirty_lines(
                        self,
                        f"⚠ WOULD DESTROY {self.dirty_count} uncommitted {change}:",
                    )
                )
            )
        if self.unpushed_count:
            commit = "commit" if self.unpushed_count == 1 else "commits"
            blocks.append(
                "\n".join(
                    _unpushed_lines(
                        self,
                        f"⚠ branch {_escape_terminal_text(branch)} has "
                        f"{self.unpushed_count} {commit} "
                        "not reachable from any remote:",
                    )
                )
            )
        return "\n\n".join(blocks)


@dataclass(frozen=True)
class CleanupResult:
    plan: CleanupPlan
    removed: bool
    notices: tuple[str, ...]
    details: CleanupDetails


def _git_root(worktree: Path, *, env: Mapping[str, str]) -> Path:
    result = run_git(worktree, ["rev-parse", "--git-common-dir"], env=env)
    value = Path(result.stdout.decode().strip())
    if not value.is_absolute():
        value = worktree / value
    return value.resolve()


def _worktrees(cwd: Path, *, env: Mapping[str, str]) -> list[tuple[Path, str | None]]:
    return [(record.path, record.branch) for record in list_worktrees(cwd, env=env)]


def _anchor(
    target: str, *, cwd: Path, env: Mapping[str, str]
) -> tuple[Path | None, Path | None]:
    """The repository every command in this cleanup will be aimed at.

    Taken from the invoking directory. Failing that, from the target when the
    user typed an existing path: an argument is fresh input, unlike a path read
    back out of a registry record. The repository is never taken from a
    record's stored path, which may since have been reused by another
    repository — aiming the deletions there would destroy that repository's
    work.
    """
    for source in (cwd, Path(target).expanduser()):
        try:
            if not source.exists():
                continue
            return source, inspect_repository(source, env=env).common_dir
        except Exception:
            continue
    return None, None


def _owns(entry: RegistryEntry, anchor_common_dir: Path | None) -> bool:
    """Whether a record's own repository permits acting on it here.

    A stored value may *veto* an action but may never *authorize* one. It
    cannot prove the fork still exists — that is what the live predicate is
    for — but a record naming repository A is reason enough to decline acting
    on it from repository B, because a stale value can only make this refusal
    more conservative. Selection ignores stored identity; this does not.

    A record migrated from a v1 registry names no repository and so vetoes
    nothing. Under exact path-and-branch reuse it remains indistinguishable
    from a record of this repository's own; `prune` is the remedy.
    """
    if entry.repository is None:
        return True
    return anchor_common_dir is not None and entry.repository == str(anchor_common_dir)


def resolve_cleanup_target(
    target: str,
    *,
    cwd: Path,
    env: Mapping[str, str],
    force: bool = False,
) -> CleanupPlan:
    """Select a fork to remove, confirming every candidate against live state.

    A registry row proposes a target; the invoking repository's worktree list
    decides whether that proposal still describes reality. A row that names a
    worktree this repository does not currently have is refused, whether it
    belongs to another repository or to a fork that no longer exists.
    """
    candidates = find_candidates(target, env=env)
    anchor_path, anchor_common_dir = _anchor(target, cwd=cwd, env=env)
    live: frozenset[tuple[str, str]] = frozenset()
    if anchor_path is not None:
        live = live_worktree_pairs(anchor_path, env=env)
    actionable = [
        entry
        for entry in candidates
        if is_live(entry, live) and _owns(entry, anchor_common_dir)
    ]
    if len(actionable) > 1:
        paths = ", ".join(_escape_terminal_text(entry.worktree) for entry in actionable)
        raise PreconditionError(
            "cleanup_registry_ambiguous",
            f"several registry records claim {_escape_terminal_text(target)}: {paths}",
        )
    if actionable:
        owned = actionable[0]
        worktree = Path(owned.worktree).resolve()
        # The mutation root is the anchor, never the record's stored path.
        assert anchor_common_dir is not None
        return CleanupPlan(
            owned, worktree, owned.branch, anchor_common_dir, True, anchor_path
        )
    if candidates:
        # Not overridable by --force: this is the only evidence that the
        # worktree still belongs to the repository its record names, and
        # --force is routinely passed for the unrelated dirty/unpushed guards.
        stale = candidates[0]
        raise PreconditionError(
            "cleanup_registry_stale",
            f"registry records {_escape_terminal_text(stale.worktree)} on "
            f"{_escape_terminal_text(stale.branch)}, which is not a worktree of "
            f"this repository; run 'agent-fork prune' if the fork is gone",
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
    raise CleanupTargetError(f"cleanup target not found: {target!r}")


def _dirty_paths(
    plan: CleanupPlan, *, env: Mapping[str, str]
) -> tuple[list[DirtyPath], int]:
    output = run_git(plan.worktree, ["status", "--porcelain=v1", "-z"], env=env).stdout
    records = output.split(b"\0")
    entries: list[DirtyPath] = []
    index = 0
    while index < len(records):
        record = records[index]
        if not record:
            index += 1
            continue
        status = record[:2].decode("ascii")
        path = record[3:].decode(errors="surrogateescape")
        entries.append(DirtyPath(status, path))
        index += 2 if "R" in status or "C" in status else 1
    modifications = [entry for entry in entries if entry.status != "??"]
    untracked = [entry for entry in entries if entry.status == "??"]
    ordered = [*modifications, *untracked]
    if len(ordered) <= DETAIL_LIMIT or not (modifications and untracked):
        return ordered[:DETAIL_LIMIT], len(ordered)
    modification_count = min(len(modifications), DETAIL_LIMIT - 1)
    untracked_count = DETAIL_LIMIT - modification_count
    return (
        [*modifications[:modification_count], *untracked[:untracked_count]],
        len(ordered),
    )


def _unpushed_commits(
    plan: CleanupPlan, *, env: Mapping[str, str]
) -> tuple[list[UnpushedCommit], int]:
    count_output = run_git(
        plan.worktree,
        ["rev-list", "--count", "HEAD", "--not", "--remotes"],
        env=env,
    ).stdout
    count = int(count_output.decode().strip())
    if count == 0:
        return [], 0
    output = run_git(
        plan.worktree,
        [
            "log",
            "-z",
            f"--max-count={DETAIL_LIMIT}",
            "--format=%h%x00%s",
            "HEAD",
            "--not",
            "--remotes",
        ],
        env=env,
    ).stdout
    fields = output.split(b"\0")
    if fields and not fields[-1]:
        fields.pop()
    entries = [
        UnpushedCommit(
            fields[index].decode(errors="surrogateescape"),
            fields[index + 1].decode(errors="surrogateescape"),
        )
        for index in range(0, len(fields), 2)
    ]
    return entries, count


def _has_configured_remotes(plan: CleanupPlan, *, env: Mapping[str, str]) -> bool:
    output = run_git(plan.worktree, ["remote"], env=env).stdout
    return bool(output.strip())


def _inspect(plan: CleanupPlan, *, env: Mapping[str, str]) -> CleanupDetails:
    dirty, dirty_count = _dirty_paths(plan, env=env)
    unpushed, unpushed_count = _unpushed_commits(plan, env=env)
    return CleanupDetails(
        dirty=tuple(dirty),
        dirty_count=dirty_count,
        unpushed=tuple(unpushed),
        unpushed_count=unpushed_count,
    )


def _dirty_lines(details: CleanupDetails, heading: str) -> list[str]:
    lines = [heading]
    has_modifications = any(entry.status != "??" for entry in details.dirty)
    untracked_started = False
    for entry in details.dirty:
        if entry.status == "??" and has_modifications and not untracked_started:
            lines.append("")
            untracked_started = True
        lines.append(f"    {entry.status} {_escape_terminal_text(entry.path)}")
    if details.dirty_count > len(details.dirty):
        lines.append(f"    … and {details.dirty_count - len(details.dirty)} more")
    return lines


def _unpushed_lines(details: CleanupDetails, heading: str) -> list[str]:
    lines = [heading]
    lines.extend(
        f"    {entry.sha}  {_escape_terminal_text(entry.subject)}"
        for entry in details.unpushed
    )
    if details.unpushed_count > len(details.unpushed):
        lines.append(f"    … and {details.unpushed_count - len(details.unpushed)} more")
    return lines


def _refusal_message(
    plan: CleanupPlan,
    details: CleanupDetails,
    *,
    code: str,
    has_configured_remotes: bool = True,
) -> tuple[str, str]:
    if code == "cleanup_dirty_worktree":
        message = f"refusing to remove {plan.worktree}"
        human_message = (
            f"refusing to remove {_escape_terminal_text(str(plan.worktree))}"
        )
        next_step = (
            "  Override with --allow-dirty (destroys them), or commit/stash first."
        )
    else:
        message = f"refusing to remove {plan.branch}"
        human_message = f"refusing to remove {_escape_terminal_text(plan.branch)}"
        if has_configured_remotes:
            next_step = (
                "  Override with --allow-unpushed (destroys them), or push first."
            )
        else:
            next_step = (
                "  No Git remote is configured. Configure one before pushing these "
                "commits (for example: git remote add REMOTE-NAME REMOTE-URL), or "
                "override with --allow-unpushed (destroys them)."
            )
    blocks = [human_message]
    if details.dirty_count:
        change = "change" if details.dirty_count == 1 else "changes"
        blocks.append(
            "\n".join(
                _dirty_lines(details, f"  {details.dirty_count} uncommitted {change}:")
            )
        )
    if details.unpushed_count:
        commit = "commit" if details.unpushed_count == 1 else "commits"
        heading = f"  {details.unpushed_count} {commit} not reachable from any remote:"
        blocks.append(
            "\n".join(
                _unpushed_lines(
                    details,
                    heading,
                )
            )
        )
    blocks.append(next_step)
    return message, "\n\n".join(blocks)


def _validate(
    plan: CleanupPlan,
    *,
    cwd: Path,
    env: Mapping[str, str],
    force: bool,
    allow_dirty: bool,
    allow_unpushed: bool,
) -> CleanupDetails:
    invoking = cwd.resolve()
    if invoking == plan.worktree or plan.worktree in invoking.parents:
        raise PreconditionError(
            "cleanup_target_is_cwd", "refusing to remove the invoking working directory"
        )
    details = _inspect(plan, env=env)
    if details.dirty_count and not (force or allow_dirty):
        message, human_message = _refusal_message(
            plan, details, code="cleanup_dirty_worktree"
        )
        raise PreconditionError(
            "cleanup_dirty_worktree",
            message,
            details=details.document(),
            human_message=human_message,
        )
    if details.unpushed_count and not (force or allow_unpushed):
        message, human_message = _refusal_message(
            plan,
            details,
            code="cleanup_unpushed_commits",
            has_configured_remotes=_has_configured_remotes(plan, env=env),
        )
        raise PreconditionError(
            "cleanup_unpushed_commits",
            message,
            details=details.document(),
            human_message=human_message,
        )
    return details


def cleanup(
    plan: CleanupPlan,
    *,
    cwd: Path,
    env: Mapping[str, str],
    force: bool = False,
    allow_dirty: bool = False,
    allow_unpushed: bool = False,
    keep_branch: bool = False,
    dry_run: bool = False,
) -> CleanupResult:
    details = _validate(
        plan,
        cwd=cwd,
        env=env,
        force=force,
        allow_dirty=allow_dirty,
        allow_unpushed=allow_unpushed,
    )
    notices = (
        "agent session files were not deleted; the fork session remains resumable "
        "and may be archived with the agent CLI",
    )
    if dry_run:
        return CleanupResult(plan, False, notices, details)

    def destroy() -> None:
        run_git(
            plan.git_root,
            ["worktree", "remove", "--force", str(plan.worktree)],
            env=env,
        )
        run_git(plan.git_root, ["worktree", "prune"], env=env)
        if not keep_branch:
            run_git(plan.git_root, ["branch", "-D", plan.branch], env=env)

    if not plan.owned:
        destroy()
        return CleanupResult(plan, True, notices, details)

    # The plan was built before consent, which has no time bound. Hold the
    # registry lock across revalidation, destruction, and removal so a record
    # that changed while the user was deciding refuses here, with nothing
    # destroyed, rather than after the worktree is already gone.
    token = plan.entry.token()
    with registry_lock(registry_path(env)):
        require_single(token, env=env)
        # Revalidate against the same repository the plan was anchored to, not
        # the invoking directory, which need not be inside one.
        anchor = plan.anchor or cwd
        if not is_live(plan.entry, live_worktree_pairs(anchor, env=env)):
            raise PreconditionError(
                "cleanup_registry_stale",
                "the fork changed while the removal was awaiting confirmation; "
                "nothing was removed",
            )
        destroy()
        remove_locked(token, env=env)
    return CleanupResult(plan, True, notices, details)
