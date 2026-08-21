"""Normative preflight-to-emission fork orchestration."""

from __future__ import annotations

import shlex
import subprocess
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from agent_fork.agents import (
    AgentContext,
    LaunchCommand,
    build_launch_command,
    preflight_agent,
    preflight_git,
)
from agent_fork.content import capture_state, collect_inventory
from agent_fork.git import run_git
from agent_fork.include import copy_worktree_includes, run_setup_hook
from agent_fork.lineage import LineageClaim, add_lineage
from agent_fork.materialize import materialize
from agent_fork.models import RegistryEntry
from agent_fork.registry import add_entry, remove_entry
from agent_fork.repository import (
    WorktreeCreation,
    create_worktree_at_anchor,
    validate_fork_guards,
)
from agent_fork.rollback import run_with_rollback
from agent_fork.submodules import SEMANTIC_PINS, carry_submodules, snapshot_submodules
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
    agent: AgentContext | None = None
    parent_session_name: str | None = None


def _git_version(env: Mapping[str, str]) -> str:
    completed = subprocess.run(
        ["git", "--version"], env=dict(env), capture_output=True, text=True
    )
    return completed.stdout or completed.stderr


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
    validate_fork_guards(
        request.parent,
        request.branch,
        request.destination,
        with_state=request.with_state,
        with_submodules=request.with_submodules,
        env=env,
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

    def finish() -> tuple[tuple[str, ...], tuple[str, ...]]:
        materialized = materialize(
            request.parent,
            creation.path,
            with_state=request.with_state,
            with_ignored=request.with_ignored,
            with_submodules=request.with_submodules,
            inventory=inventory,
            env=env,
        )
        notices.extend(materialized.notices)
        submodule_skipped: tuple[str, ...] = ()
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
                env=env,
            )
        included = copy_worktree_includes(request.parent, creation.path, env=env)
        notices.extend(included.notices)
        hook_notices = run_setup_hook(request.parent, creation.path, env=env)
        notices.extend(hook_notices)
        add_entry(
            RegistryEntry.create(
                name=request.name,
                branch=request.branch,
                worktree=creation.path,
                agent=resolved_agent.agent if resolved_agent is not None else None,
                mode="agent" if resolved_agent is not None else "git-only",
            ),
            env=env,
        )
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
                remove_entry(request.name, env=env)
                raise
        return included.copied, hook_notices

    included, _ = run_with_rollback(creation, finish, env=env)
    return ForkResult(
        creation,
        launch,
        tuple(notices),
        request.verify,
        included,
        resolved_agent,
        agent_check.parent_session_name if agent_check is not None else None,
    )
