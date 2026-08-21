"""Normative preflight-to-emission fork orchestration."""

from __future__ import annotations

import shlex
import subprocess
import uuid
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from agent_fork.agents import (
    AgentContext,
    LaunchCommand,
    build_launch_command,
    preflight_agent,
    preflight_git,
)
from agent_fork.content import capture_state, collect_inventory, sentinel_for
from agent_fork.errors import PreconditionError, VerificationError
from agent_fork.git import run_git
from agent_fork.include import copy_worktree_includes, run_setup_hook
from agent_fork.lineage import LineageClaim, add_lineage
from agent_fork.materialize import materialize
from agent_fork.models import RegistryEntry
from agent_fork.registry import add_entry, occupied_fork, remove_entry
from agent_fork.repository import (
    WorktreeCreation,
    create_worktree_at_anchor,
    validate_fork_guards,
)
from agent_fork.rollback import run_with_rollback
from agent_fork.text import escape_terminal_text
from agent_fork.verify import verify_fork


@dataclass(frozen=True)
class ForkRequest:
    parent: Path
    destination: Path
    name: str
    branch: str
    agent: AgentContext | None
    with_state: bool = True
    with_ignored: bool = False
    verify: bool = True
    force: bool = False
    extra_args: tuple[str, ...] = ()
    agent_executable: str | None = None
    agent_version_output: str | None = None
    git_version_output: str | None = None
    child_session_id: str | None = None
    codex_session_name_resolution: bool = True


@dataclass(frozen=True)
class ForkResult:
    creation: WorktreeCreation
    launch: LaunchCommand
    notices: tuple[str, ...]
    verification: bool
    included: tuple[str, ...]
    skipped: tuple[dict[str, str], ...] = ()
    agent: AgentContext | None = None
    parent_session_name: str | None = None


def _git_version(env: Mapping[str, str]) -> str:
    completed = subprocess.run(
        ["git", "--version"], env=dict(env), capture_output=True, text=True
    )
    return completed.stdout or completed.stderr


def _recheck_skips(parent: Path, skipped: tuple[object, ...]) -> None:
    """Fail the fork if a skipped entry changed after it was observed.

    Skipped paths are excluded from every content comparison, so this is the
    only thing standing between a mid-fork mutation and a successful fork that
    quietly omitted it.
    """
    for record in skipped:
        relative = str(getattr(record, "path", record))
        try:
            now = sentinel_for(parent, relative)
        except OSError:
            now = None
        if now != getattr(record, "sentinel", None):
            raise VerificationError(
                "a skipped entry changed during the fork: "
                f"{escape_terminal_text(relative)}",
                details={
                    "failed_checks": [
                        {
                            "check": "skip-sentinel",
                            "primary": True,
                            "total": 1,
                            "differences": [
                                {
                                    "path": escape_terminal_text(relative),
                                    "kind": "skip-sentinel",
                                    "detail": "changed after observation",
                                }
                            ],
                        }
                    ]
                },
            )


def fork(request: ForkRequest, *, env: Mapping[str, str]) -> ForkResult:
    """Execute the locked preflight-through-registry fork sequence."""
    agent_check = (
        preflight_agent(
            request.agent,
            env,
            executable=request.agent_executable,
            version_output=request.agent_version_output,
            codex_session_name_resolution=request.codex_session_name_resolution,
        )
        if request.agent is not None
        else None
    )
    notices = list(
        preflight_git(
            request.git_version_output or _git_version(env),
            force=request.force,
            verify=request.verify,
        )
    )
    if agent_check is not None:
        notices.extend(agent_check.notices)
    resolved_agent = agent_check.context if agent_check is not None else request.agent
    info = validate_fork_guards(
        request.parent,
        request.branch,
        request.destination,
        with_state=request.with_state,
        env=env,
    )
    # Refuse a name this repository already has a fork of, here — before any
    # worktree, include copy, or setup hook has run. `add_entry` checks again
    # under the registry lock, because another fork can register in between,
    # but by then the hook has already had its side effects, which a rollback
    # cannot reverse. A refusal the user can act on has to come first.
    occupied = occupied_fork(request.name, info.common_dir, env=env)
    if occupied is not None:
        raise PreconditionError(
            "conflict_fork_registered",
            f"fork {request.name!r} is already registered for this repository "
            f"at {escape_terminal_text(occupied.worktree)}; remove it first, "
            "or choose another name",
        )
    planned_child_id = (
        request.child_session_id or str(uuid.uuid4())
        if resolved_agent is not None and resolved_agent.agent == "claude"
        else None
    )
    launch_directory = request.destination.resolve()
    launch = (
        build_launch_command(
            resolved_agent,
            worktree=launch_directory,
            name=request.name,
            extra_args=request.extra_args,
            child_session_id=planned_child_id,
        )
        if resolved_agent is not None
        else LaunchCommand(f"cd {shlex.quote(str(launch_directory))}", None, ())
    )
    parent_status = run_git(
        request.parent, ["status", "--porcelain=v1", "-z"], env=env
    ).stdout
    inventory = collect_inventory(
        request.parent,
        with_state=request.with_state,
        with_ignored=request.with_ignored,
        env=env,
    )
    parent_state = (
        capture_state(request.parent, inventory, env=env)
        if request.verify and request.with_state
        else None
    )
    creation = create_worktree_at_anchor(
        request.parent, request.branch, request.destination, env=env
    )

    skipped = parent_state.skipped if parent_state is not None else ()

    def finish() -> tuple[tuple[str, ...], tuple[str, ...]]:
        materialized = materialize(
            request.parent,
            creation.path,
            with_state=request.with_state,
            with_ignored=request.with_ignored,
            inventory=inventory,
            skipped=skipped,
            env=env,
        )
        notices.extend(materialized.notices)
        if request.verify:
            verify_fork(
                creation,
                with_state=request.with_state,
                with_ignored=request.with_ignored,
                parent_status_before=parent_status,
                parent_state_before=parent_state,
                skipped=skipped,
                env=env,
            )
        included = copy_worktree_includes(request.parent, creation.path, env=env)
        notices.extend(included.notices)
        hook_notices = run_setup_hook(request.parent, creation.path, env=env)
        notices.extend(hook_notices)
        # Finalization, not verification: include copying and the setup hook
        # run after the ladder, and the hook receives REPO_ROOT and can mutate
        # the parent. A sentinel checked earlier would leave a window in which
        # a skipped entry changes and the fork is still registered successful
        # (P02 A5).
        _recheck_skips(request.parent, skipped)
        entry = RegistryEntry.create(
            name=request.name,
            branch=request.branch,
            worktree=creation.path,
            agent=resolved_agent.agent if resolved_agent is not None else None,
            mode="agent" if resolved_agent is not None else "git-only",
            repository=creation.common_dir,
        )
        add_entry(entry, env=env)
        if (
            resolved_agent is not None
            and resolved_agent.agent == "claude"
            and planned_child_id is not None
        ):
            try:
                add_lineage(
                    LineageClaim.create(
                        agent="claude",
                        child_session_id=planned_child_id,
                        parent_session_id=resolved_agent.parent_session_id,
                        name=request.name,
                        branch=request.branch,
                        worktree=creation.path,
                    ),
                    env=env,
                )
            except Exception:
                # Remove exactly the record this call wrote. Nothing else is
                # needed: `add_entry` refuses rather than displacing a live
                # fork, so there is no earlier record to put back. Removal is
                # a compare-and-swap, so a record already taken by a cleanup
                # or replaced by a later fork is left alone. Compensation is
                # best-effort by design — whatever goes wrong here, the
                # failure that triggered it is the one worth reporting.
                with suppress(Exception):
                    remove_entry(entry.token(), env=env)
                raise
        return included.copied, hook_notices

    included, _ = run_with_rollback(creation, finish, env=env)
    return ForkResult(
        creation,
        launch,
        tuple(notices),
        request.verify,
        included,
        tuple({"path": r.path, "reason": r.reason, "phase": r.phase} for r in skipped),
        resolved_agent,
        agent_check.parent_session_name if agent_check is not None else None,
    )
