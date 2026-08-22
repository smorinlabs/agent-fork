"""Registry-scoped cleanup planning, guards, and mutation."""

from __future__ import annotations

import shlex
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from agent_fork.errors import AgentForkError, PreconditionError
from agent_fork.git import run_git
from agent_fork.models import RegistryEntry
from agent_fork.registry import (
    find_candidates,
    match_live,
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
class ConfirmedFork:
    """A fork that was observed to exist, with the values Git will be given.

    Every field here comes from a fresh observation, never from a registry
    record. `confirm_fork` is the only way to build one, and it cannot do so
    without having enumerated the repository's live worktrees — so a caller
    that holds this type is holding evidence, not a claim.

    This exists because seven separate defects in this item had one shape: a
    check confirmed a record, and then a destructive command was handed a
    value read back out of that record. Keeping the two apart by discipline
    failed repeatedly; keeping them apart by construction is what this type
    is for. Nothing below should reintroduce a field sourced from a record.
    """

    worktree: Path
    branch: str
    #: Git common directory of the anchor repository — where commands run.
    git_root: Path
    #: A working directory inside the anchor, for re-enumerating later. The
    #: common directory cannot enumerate worktrees, so it cannot serve here.
    anchor: Path

    @classmethod
    def from_observation(
        cls, observed: tuple[str, str], *, anchor: Path, git_root: Path
    ) -> ConfirmedFork:
        """Build from one element of a live worktree listing."""
        path, branch = observed
        return cls(Path(path), branch, git_root, anchor)


@dataclass(frozen=True)
class CleanupPlan:
    entry: RegistryEntry
    fork: ConfirmedFork
    owned: bool

    @property
    def worktree(self) -> Path:
        return self.fork.worktree

    @property
    def branch(self) -> str:
        return self.fork.branch

    @property
    def git_root(self) -> Path:
        return self.fork.git_root

    @property
    def anchor(self) -> Path:
        return self.fork.anchor

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

    A record migrated from a v1 registry names no repository, so it can never
    show that it belongs here — and it authorizes nothing (owner decision
    2026-08-20). An earlier revision permitted such records, reasoning that
    the live predicate was proof enough. It is not: two repositories can hold
    the same worktree path on the same branch name, which the `central`
    worktree layout makes ordinary rather than exotic, because that layout
    keys on a repository's basename alone. `prune` clears these records; an
    older fork is still removable by explicit path.
    """
    if entry.repository is None:
        return False
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
    # Each surviving candidate is paired with what was actually observed, so
    # the values below can only have come from the observation.
    actionable = [
        (entry, observed)
        for entry in candidates
        for observed in [match_live(entry, live)]
        if observed is not None and _owns(entry, anchor_common_dir)
    ]
    if len(actionable) > 1:
        paths = ", ".join(
            _escape_terminal_text(observed[0]) for _, observed in actionable
        )
        raise PreconditionError(
            "cleanup_registry_ambiguous",
            f"several registry records claim {_escape_terminal_text(target)}: {paths}",
        )
    if actionable:
        owned, observed = actionable[0]
        assert anchor_path is not None and anchor_common_dir is not None
        return CleanupPlan(
            owned,
            ConfirmedFork.from_observation(
                observed, anchor=anchor_path, git_root=anchor_common_dir
            ),
            True,
        )
    # A record carrying no repository is inert in both directions: it cannot
    # authorize and it does not veto. It is therefore dropped here rather than
    # given a say.
    #
    # An earlier revision let an explicit existing path slip past such a
    # record, to keep the pre-v2 recovery in one step. That inferred the
    # selector from the filesystem — `Path(target).exists()` — which misreads
    # a bare fork name as a path whenever a directory of that name happens to
    # sit in the invoking directory, and let the mere presence of a null
    # record waive the unregistered-target gate. Recovery is two steps
    # instead: `prune` clears the inert records, after which the worktree is
    # genuinely unregistered and `cleanup <path> --force` applies, exactly as
    # for any worktree agent-fork did not create.
    identified = [entry for entry in candidates if entry.repository is not None]
    if identified:
        # Not overridable by --force: a record naming a repository is the only
        # evidence that the worktree still belongs to it, and --force is
        # routinely passed for the unrelated dirty and unpushed guards.
        stale = identified[0]
        raise PreconditionError(
            "cleanup_registry_stale",
            f"registry records {_escape_terminal_text(stale.worktree)} on "
            f"{_escape_terminal_text(stale.branch)}, which is not a worktree of "
            f"this repository; run 'agent-fork prune' if the fork is gone",
        )
    if not force:
        if candidates:
            # Records exist, but every one predates the repository field and
            # so cannot show the fork is this repository's. Saying "not
            # created by agent-fork" would be false and unhelpful.
            raise CleanupTargetError(
                f"cleanup target {_escape_terminal_text(target)} matches only "
                "registry records written before agent-fork recorded which "
                "repository a fork belongs to, so they cannot identify it; "
                "run 'agent-fork prune' to clear them, then target the "
                "worktree by path with --force"
            )
        raise CleanupTargetError(
            f"cleanup target {target!r} was not created by agent-fork; "
            "use --force to extend targeting"
        )
    # Unregistered targeting still confirms. `list_worktrees` reports what a
    # repository has *recorded*, which includes a path whose directory was
    # since replaced by another repository's worktree; only `live_worktree_pairs`
    # asks each directory what it currently is. Taking the raw listing here
    # would let `--force` aim deletions at whoever occupies the path now.
    if anchor_path is None or anchor_common_dir is None:
        raise CleanupTargetError(f"cleanup target not found: {target!r}")
    confirmed = live_worktree_pairs(anchor_path, env=env)
    resolved = str(Path(target).expanduser().resolve())
    for observed_path, observed_branch in sorted(confirmed):
        if resolved == observed_path or target == observed_branch:
            entry = RegistryEntry.create(
                name=Path(observed_path).name,
                branch=observed_branch,
                worktree=Path(observed_path),
                agent="unknown",
            )
            # The synthesized record is for display only; the fork's fields
            # come from the confirmed observation, same as the owned path.
            return CleanupPlan(
                entry,
                ConfirmedFork.from_observation(
                    (observed_path, observed_branch),
                    anchor=anchor_path,
                    git_root=anchor_common_dir,
                ),
                False,
            )
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
        # A structurally invalid freshness store is a fault to disclose, not
        # a cache miss to paper over as "no freshness evidence retained" —
        # but it is a fault ONLY about freshness. An unrelated, independently
        # readable lineage claim or inferred record must still be disclosed;
        # nulling the whole result would suppress real information the user
        # needs, per the design's "disclosure must never fail a cleanup"
        # guarantee, with an honest notice instead of silence.
        freshness_unreadable = state_targets is None or legacy_targets is None
        if state_targets is None:
            state_targets = {}
        if legacy_targets is None:
            legacy_targets = {}

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
            quoted_child = shlex.quote(child)
            lineage_claims.append(child)
            removal_commands.append(
                {
                    "session_id": child,
                    "source": "planned",
                    "command": (
                        "agent-fork session claude-parent delete --session-id "
                        f"{quoted_child} --source planned --yes"
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
                            f"{quoted_child} --source inferred --yes"
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
        if freshness_unreadable:
            notices += (
                "could not read Claude parent freshness metadata; freshness "
                "corroboration for retained records could not be disclosed",
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
        return CleanupResult(plan, True, notices, details, retained_metadata)

    # The plan was built before consent, which has no time bound. Hold the
    # registry lock across revalidation, destruction, and removal so a record
    # that changed while the user was deciding refuses here, with nothing
    # destroyed, rather than after the worktree is already gone.
    token = plan.entry.token()
    stale = PreconditionError(
        "cleanup_registry_stale",
        "the fork changed while the removal was awaiting confirmation; "
        "nothing was removed",
    )
    with registry_lock(registry_path(env)):
        require_single(token, env=env)
        # Everything the plan was built on is re-established here, not just
        # the record. Consent has no time bound, so the anchor directory can
        # have become a different repository in the interval — checking only
        # that the pair is live would then confirm against the newcomer and
        # destroy its work.
        anchor = plan.anchor
        try:
            anchor_common_dir = inspect_repository(anchor, env=env).common_dir
            observed = live_worktree_pairs(anchor, env=env)
        except Exception as error:
            # The anchor can stop being a repository while consent is pending.
            # That is the same fact the checks below establish — the plan no
            # longer describes reality — so it reads as the same refusal
            # rather than as a probe failure the user has to interpret.
            raise stale from error
        if anchor_common_dir != plan.git_root:
            raise stale
        if not _owns(plan.entry, plan.git_root):
            raise stale
        if match_live(plan.entry, observed) is None:
            raise stale
        destroy()
        remove_locked(token, env=env)
    return CleanupResult(plan, True, notices, details, retained_metadata)
