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
