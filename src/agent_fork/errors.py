"""Typed domain failures with stable codes and process exit mappings."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorSpec:
    exit_code: int
    meaning: str


ERROR_CATALOG: dict[str, ErrorSpec] = {
    "runtime_error": ErrorSpec(1, "unexpected runtime or materialization failure"),
    "verify_failed": ErrorSpec(1, "fork verification failed"),
    "registry_busy": ErrorSpec(1, "registry lock wait expired"),
    "config_error": ErrorSpec(2, "configuration is invalid or unsupported"),
    "agent_not_detected": ErrorSpec(3, "agent identity is missing or ambiguous"),
    "session_not_found": ErrorSpec(3, "agent session or rollout is unavailable"),
    "session_name_ambiguous": ErrorSpec(3, "session name matches multiple sessions"),
    "session_resolution_unavailable": ErrorSpec(
        3, "session-name resolver is unavailable"
    ),
    "session_validation_failed": ErrorSpec(3, "session assertions did not match"),
    "claude_parent_unavailable": ErrorSpec(3, "Claude parent inference is unavailable"),
    "claude_parent_not_recordable": ErrorSpec(
        3, "Claude parent inference result is not recordable"
    ),
    "claude_parent_partial_record": ErrorSpec(
        3, "one or more Claude parent results were not recordable"
    ),
    "cleanup_target_unknown": ErrorSpec(3, "cleanup target is not registered or found"),
    "conflict_branch_exists": ErrorSpec(5, "fork branch already exists"),
    "conflict_branch_worktree": ErrorSpec(5, "branch is attached to a worktree"),
    "conflict_worktree_path": ErrorSpec(5, "worktree destination already exists"),
    "parent_mid_operation": ErrorSpec(5, "parent repository is mid-operation"),
    "repo_no_commits": ErrorSpec(5, "repository has no commit to fork"),
    "unmerged_index": ErrorSpec(5, "repository index has unresolved conflicts"),
    "not_git_repository": ErrorSpec(5, "invocation path is not a Git repository"),
    "git_version_unsupported": ErrorSpec(5, "installed Git is below the product floor"),
    "invalid_branch": ErrorSpec(5, "explicit branch name is invalid"),
    "invalid_worktree_base": ErrorSpec(5, "worktree base is not an existing directory"),
    "invalid_worktree_name": ErrorSpec(5, "worktree leaf is not one safe component"),
    "cleanup_target_is_cwd": ErrorSpec(5, "cleanup target contains the invoking cwd"),
    "cleanup_dirty_worktree": ErrorSpec(5, "cleanup target has uncommitted changes"),
    "cleanup_unpushed_commits": ErrorSpec(5, "cleanup target has unpushed commits"),
}


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

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, object] | None = None,
        human_message: str | None = None,
    ):
        if code not in ERROR_CATALOG:
            raise ValueError(f"uncataloged precondition error code: {code}")
        super().__init__(message)
        self.code = code
        self.details = details
        self.human_message = human_message


class VerificationError(AgentForkError):
    """A created fork failed one or more post-materialization checks."""

    code = "verify_failed"
    exit_code = 1


class RegistryBusyError(AgentForkError):
    """The XDG registry lock could not be acquired within its bounded wait."""

    code = "registry_busy"
    exit_code = 1


class AgentPreflightError(AgentForkError):
    """The detected agent cannot safely fork the requested parent session."""

    code = "session_not_found"
    exit_code = 3


class SessionNameAmbiguousError(AgentForkError):
    code = "session_name_ambiguous"
    exit_code = 3


class SessionResolutionUnavailableError(AgentForkError):
    code = "session_resolution_unavailable"
    exit_code = 3


class SessionValidationError(AgentForkError):
    code = "session_validation_failed"
    exit_code = 3


class ClaudeParentError(AgentForkError):
    code = "claude_parent_unavailable"
    exit_code = 3

    def __init__(
        self,
        message: str,
        *,
        code: str = "claude_parent_unavailable",
        details: dict[str, object] | None = None,
        human_message: str | None = None,
    ):
        if code not in ERROR_CATALOG:
            raise ValueError(f"uncataloged Claude parent error code: {code}")
        super().__init__(message)
        self.code = code
        self.details = details
        self.human_message = human_message


class ClaudeParentNotRecordableError(ClaudeParentError):
    code = "claude_parent_not_recordable"

    def __init__(self, message: str, **kwargs):
        super().__init__(message, code=self.code, **kwargs)


class ClaudeParentPartialRecordError(ClaudeParentError):
    code = "claude_parent_partial_record"

    def __init__(self, message: str, **kwargs):
        super().__init__(message, code=self.code, **kwargs)
