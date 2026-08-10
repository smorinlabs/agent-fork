"""Precise cleanup for failures after a worktree has been created."""

from __future__ import annotations

import signal
from collections.abc import Mapping
from dataclasses import dataclass

from agent_fork.git import GitCommandError, run_git
from agent_fork.repository import WorktreeCreation


@dataclass(frozen=True)
class RollbackResult:
    cleaned: bool
    manual_recovery: str | None = None


class OperationInterrupted(BaseException):
    def __init__(self, signum: int):
        self.signum = signum
        self.exit_code = 128 + signum


def run_with_rollback(creation, operation, *, env=None):
    """Run a post-create mutation with rollback on failure or termination signal."""
    previous = {}

    def interrupt(signum, _frame):
        from agent_fork.git import terminate_active_git

        terminate_active_git()
        raise OperationInterrupted(signum)

    for signum in (signal.SIGINT, signal.SIGTERM):
        previous[signum] = signal.signal(signum, interrupt)
    try:
        return operation()
    except BaseException:
        rollback_worktree(creation, env=env)
        raise
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def manual_recovery_command(creation: WorktreeCreation) -> str:
    def quoted(value: str) -> str:
        return (
            '"'
            + value.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("$", "\\$")
            .replace("`", "\\`")
            + '"'
        )

    return (
        f"rm -rf {quoted(str(creation.path))} && "
        f"git -C {quoted(str(creation.parent_path))} branch -D "
        f"{quoted(creation.branch)}"
    )


def rollback_worktree(
    creation: WorktreeCreation, *, env: Mapping[str, str] | None = None
) -> RollbackResult:
    """Remove exactly this call's worktree and, when created here, its branch."""
    try:
        if creation.path.exists():
            run_git(
                creation.parent_path,
                ["worktree", "remove", "--force", str(creation.path)],
                env=env,
            )
        if creation.branch_created:
            run_git(
                creation.parent_path,
                ["branch", "-D", creation.branch],
                env=env,
            )
        run_git(creation.parent_path, ["worktree", "prune"], env=env)
    except (GitCommandError, OSError):
        return RollbackResult(False, manual_recovery_command(creation))
    return RollbackResult(True)
