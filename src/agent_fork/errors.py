"""Typed domain failures with stable codes and process exit mappings."""

from __future__ import annotations


class AgentForkError(Exception):
    """Base class for failures intended to cross the CLI boundary."""

    code = "runtime_error"
    exit_code = 1


class AgentDetectionError(AgentForkError):
    """Agent/session identity is absent, ambiguous, or invalid."""

    code = "agent_not_detected"
    exit_code = 3


class ConflictError(AgentForkError):
    """A branch, worktree, or other precondition collision."""

    code = "conflict_branch_exists"
    exit_code = 5


class PreconditionError(AgentForkError):
    """A stable-code refusal raised before an unsafe mutation."""

    exit_code = 5

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
