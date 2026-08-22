"""Normative preflight-to-emission fork orchestration."""

from __future__ import annotations

import shlex
import subprocess
import uuid
from collections.abc import Callable, Mapping
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
from agent_fork.errors import (
    PreconditionError,
    StrictSkipRefusedError,
    VerificationError,
)
from agent_fork.git import run_git
from agent_fork.include import (
    DEFAULT_SETUP_HOOK_POLICY,
    DEFAULT_SETUP_HOOK_TIMEOUT,
    SetupHookPolicy,
    SetupHookResult,
    copy_worktree_includes,
    run_setup_hook,
)
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
from agent_fork.submodules import SEMANTIC_PINS, carry_submodules, snapshot_submodules
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
    with_submodules: bool = True
    verify: bool = True
    force: bool = False
    strict: bool = False
    extra_args: tuple[str, ...] = ()
    agent_executable: str | None = None
    agent_version_output: str | None = None
    git_version_output: str | None = None
    child_session_id: str | None = None
    codex_session_name_resolution: bool = True
    setup_hook_policy: str = DEFAULT_SETUP_HOOK_POLICY
    setup_hook_timeout: int = DEFAULT_SETUP_HOOK_TIMEOUT
    progress: Callable[[str], None] | None = None


@dataclass(frozen=True)
class ForkResult:
    creation: WorktreeCreation
    launch: LaunchCommand
    notices: tuple[str, ...]
    verification: bool
    included: tuple[str, ...]
    setup_hook: SetupHookResult
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
        with_submodules=request.with_submodules,
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
    # SEMANTIC_PINS applies to the top-level capture too, not just the
    # recursive submodule calls, whenever submodules are carried (gate-6
    # finding 2): ambient config anywhere in a carried submodule's tree can
    # otherwise make the top-level inventory see less than what carry and
    # verify -- both pinned -- see afterward, producing a false difference.
    top_level_pins = SEMANTIC_PINS if request.with_submodules else ()
    inventory = collect_inventory(
        request.parent,
        with_state=request.with_state,
        with_ignored=request.with_ignored,
        with_submodules=request.with_submodules,
        env=env,
        config_pins=top_level_pins,
    )
    parent_state = (
        capture_state(request.parent, inventory, env=env, config_pins=top_level_pins)
        if request.verify and request.with_state
        else None
    )
    # Resolved before the worktree exists — this is what makes it a snapshot
    # rather than a live read (A6b step 4). Empty whenever submodules are not
    # being carried, so carry and verification both stay no-ops below.
    submodule_plans = (
        snapshot_submodules(
            request.parent,
            with_state=request.with_state,
            with_ignored=request.with_ignored,
            env=env,
        )
        if request.with_state and request.with_submodules
        else ()
    )
    creation = create_worktree_at_anchor(
        request.parent, request.branch, request.destination, env=env
    )

    skipped = list(parent_state.skipped if parent_state is not None else ())

    def finish() -> tuple[tuple[str, ...], SetupHookResult]:
        materialized = materialize(
            request.parent,
            creation.path,
            with_state=request.with_state,
            with_ignored=request.with_ignored,
            with_submodules=request.with_submodules,
            inventory=inventory,
            config_pins=top_level_pins,
            skipped=tuple(skipped),
            env=env,
        )
        notices.extend(materialized.notices)
        skipped.extend(materialized.skipped)
        submodule_skipped: tuple[str, ...] = ()
        submodule_reasoned_skipped: tuple[str, ...] = ()
        if request.with_state and request.with_submodules:
            carried = carry_submodules(
                request.parent,
                creation.path,
                submodule_plans,
                with_state=request.with_state,
                with_ignored=request.with_ignored,
                env=env,
            )
            notices.extend(carried.notices)
            submodule_skipped = carried.skipped
            submodule_reasoned_skipped = carried.reasoned_skipped
        if request.verify:
            verify_fork(
                creation,
                with_state=request.with_state,
                with_ignored=request.with_ignored,
                with_submodules=request.with_submodules,
                parent_status_before=parent_status,
                parent_state_before=parent_state,
                submodule_plans=submodule_plans,
                submodule_skipped=submodule_skipped,
                submodule_reasoned_skipped=submodule_reasoned_skipped,
                skipped=tuple(skipped),
                env=env,
            )
        included = copy_worktree_includes(
            request.parent,
            creation.path,
            deletion_blockers=inventory.deletions,
            known_skipped=tuple(skipped),
            env=env,
        )
        notices.extend(included.notices)
        skipped.extend(included.skipped)
        if request.strict and skipped:
            # Includes are the final skip-producing phase. Refuse here, before
            # the setup hook can have external side effects and before the
            # registry write, while still reporting capture + materialize +
            # include skips in one error (P02 A5).
            raise StrictSkipRefusedError(skipped)
        setup_hook = run_setup_hook(
            request.parent,
            creation.path,
            anchor=creation.anchor,
            policy=SetupHookPolicy(
                mode=request.setup_hook_policy,
                timeout_seconds=request.setup_hook_timeout,
            ),
            env=env,
            progress=request.progress,
        )
        notices.extend(setup_hook.notices)
        # Finalization, not verification: include copying and the setup hook
        # run after the ladder, and the hook receives REPO_ROOT and can mutate
        # the parent. A sentinel checked earlier would leave a window in which
        # a skipped entry changes and the fork is still registered successful
        # (P02 A5).
        _recheck_skips(request.parent, tuple(skipped))
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
        return included.copied, setup_hook

    included, setup_hook = run_with_rollback(creation, finish, env=env)
    return ForkResult(
        creation,
        launch,
        tuple(notices),
        request.verify,
        included,
        setup_hook,
        tuple(
            {"path": r.path, "reason": r.reason, "phase": r.phase}
            for r in sorted(
                skipped,
                key=lambda record: record.path.encode("utf-8", "surrogateescape"),
            )
        ),
        resolved_agent,
        agent_check.parent_session_name if agent_check is not None else None,
    )
