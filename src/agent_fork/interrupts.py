"""Shared SIGINT/SIGTERM handling for owned child process groups."""

from __future__ import annotations

import signal
from collections.abc import Callable
from types import FrameType
from typing import TypeVar

from agent_fork.git import terminate_active_git

_T = TypeVar("_T")


class OperationInterrupted(BaseException):
    """An operation stopped after its active child process groups were killed."""

    def __init__(self, signum: int, message: str | None = None):
        self.signum = signum
        self.signal_name = signal.Signals(signum).name
        self.exit_code = 128 + signum
        super().__init__(message or f"operation interrupted by {self.signal_name}")


def run_with_interruption_handler(
    operation: Callable[[], _T], *, message: str | None = None
) -> _T:
    """Run one mutation while forwarding terminal signals to owned children."""
    previous: dict[
        signal.Signals, Callable[[int, FrameType | None], object] | int | None
    ] = {}

    def interrupt(signum: int, _frame: FrameType | None) -> None:
        from agent_fork.include import terminate_active_setup_hook

        terminate_active_git()
        # The setup hook is the second owned process group. This call is a no-op
        # on cleanup's Git-only path, while preserving rollback's guarantee that
        # hook descendants are stopped before the worktree is removed.
        terminate_active_setup_hook()
        raise OperationInterrupted(signum, message)

    for signum in (signal.SIGINT, signal.SIGTERM):
        previous[signum] = signal.signal(signum, interrupt)
    try:
        return operation()
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)
