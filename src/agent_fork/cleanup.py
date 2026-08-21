"""Registry-scoped cleanup planning, guards, and mutation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from agent_fork.errors import AgentForkError, PreconditionError
from agent_fork.git import run_git
from agent_fork.models import RegistryEntry
from agent_fork.registry import find_owned, remove_entry
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
    retained_metadata: dict[str, object]


def _git_root(worktree: Path, *, env: Mapping[str, str]) -> Path:
    result = run_git(worktree, ["rev-parse", "--git-common-dir"], env=env)
    value = Path(result.stdout.decode().strip())
    if not value.is_absolute():
        value = worktree / value
    return value.resolve()


def _worktrees(cwd: Path, *, env: Mapping[str, str]) -> list[tuple[Path, str | None]]:
    return [(record.path, record.branch) for record in list_worktrees(cwd, env=env)]


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


_EMPTY_RETAINED_METADATA: dict[str, object] = {
    "lineage_claims": [],
    "inferred_records": [],
    "freshness_entries": [],
    "removal_commands": [],
}


def _retained_metadata(
    plan: CleanupPlan, *, env: Mapping[str, str]
) -> tuple[dict[str, object], tuple[str, ...]]:
    """Read-only disclosure of lineage/inference/freshness metadata this cleanup
    does not touch: which child sessions retain evidence, where the stores live,
    and the exact source-qualified command to remove each retained record."""
    try:
        from agent_fork.lineage import lineage_path, read_lineage
        from agent_fork.lineage_inference_store import (
            _legacy_index_freshness_path,
            _read_targets,
            index_freshness_path,
            inference_path,
            read_inferences,
        )

        resolved_worktree = str(plan.worktree.resolve())
        claims = [
            claim
            for claim in read_lineage(env=env)
            if claim.worktree is not None
            and str(Path(claim.worktree).resolve()) == resolved_worktree
        ]
        if not claims:
            return dict(_EMPTY_RETAINED_METADATA), ()

        inferred_by_child = {
            record.child_session_id for record in read_inferences(env=env)
        }
        state_targets = _read_targets(index_freshness_path(env))
        legacy_targets = _read_targets(_legacy_index_freshness_path(env))
        if state_targets is None or legacy_targets is None:
            # A structurally invalid store is a fault to disclose, not a
            # cache miss to paper over as "no freshness evidence retained" —
            # degrade to the same neutral shape as an unreadable lineage
            # store, per the design's "disclosure must never fail a
            # cleanup" guarantee, with an honest notice instead of silence.
            return dict(_EMPTY_RETAINED_METADATA), (
                "could not read Claude parent freshness metadata; nothing "
                "disclosed for it",
            )

        lineage_claims: list[str] = []
        inferred_records: list[str] = []
        freshness_entries: list[str] = []
        freshness_entries_state: list[str] = []
        freshness_entries_legacy: list[str] = []
        removal_commands: list[dict[str, str]] = []
        for claim in sorted(claims, key=lambda item: item.child_session_id):
            # Raw values in every machine-readable field below: JSON encoding
            # already represents control characters safely, and escaping
            # here would corrupt a session ID a script pastes back into a
            # command. Escaping applies only to the human `notices` text.
            child = claim.child_session_id
            lineage_claims.append(child)
            removal_commands.append(
                {
                    "session_id": child,
                    "source": "planned",
                    "command": (
                        "agent-fork session claude-parent delete --session-id "
                        f"{child} --source planned --yes"
                    ),
                }
            )
            if child in inferred_by_child:
                inferred_records.append(child)
                removal_commands.append(
                    {
                        "session_id": child,
                        "source": "inferred",
                        "command": (
                            "agent-fork session claude-parent delete --session-id "
                            f"{child} --source inferred --yes"
                        ),
                    }
                )
            in_state = child in state_targets
            in_legacy = child in legacy_targets
            if in_state or in_legacy:
                freshness_entries.append(child)
                if in_state:
                    freshness_entries_state.append(child)
                else:
                    freshness_entries_legacy.append(child)

        metadata = {
            "lineage_claims": lineage_claims,
            "inferred_records": inferred_records,
            "freshness_entries": freshness_entries,
            "removal_commands": removal_commands,
        }
        notices = (
            "retained planned lineage claim(s) for: "
            + ", ".join(_escape_terminal_text(item) for item in lineage_claims)
            + f"; store: {_escape_terminal_text(str(lineage_path(env)))}",
        )
        if inferred_records:
            notices += (
                "retained inferred record(s) for: "
                + ", ".join(_escape_terminal_text(item) for item in inferred_records)
                + f"; store: {_escape_terminal_text(str(inference_path(env)))}",
            )
        if freshness_entries_state:
            notices += (
                "retained freshness corroboration for: "
                + ", ".join(
                    _escape_terminal_text(item) for item in freshness_entries_state
                )
                + f"; store: {_escape_terminal_text(str(index_freshness_path(env)))}",
            )
        if freshness_entries_legacy:
            notices += (
                "retained freshness corroboration (not yet migrated) for: "
                + ", ".join(
                    _escape_terminal_text(item) for item in freshness_entries_legacy
                )
                + "; store: "
                + _escape_terminal_text(str(_legacy_index_freshness_path(env))),
            )
        notices += (
            "these are kept because the forked agent session remains resumable "
            "and this is Agent Fork's strongest local parent evidence",
            "shared transcript screen cache shards hold no parent conclusion, are "
            "rebuilt on demand, and are reclaimed by the bounded cache sweep "
            "rather than by cleanup",
        )
        return metadata, notices
    except (OSError, ValueError):
        return dict(_EMPTY_RETAINED_METADATA), (
            "could not read Claude parent lineage/inference metadata; "
            "nothing disclosed",
        )


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
    retained_metadata, retained_notices = _retained_metadata(plan, env=env)
    notices = (
        "agent session files were not deleted; the fork session remains resumable "
        "and may be archived with the agent CLI",
        *retained_notices,
    )
    if dry_run:
        return CleanupResult(plan, False, notices, details, retained_metadata)
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
    return CleanupResult(plan, True, notices, details, retained_metadata)
