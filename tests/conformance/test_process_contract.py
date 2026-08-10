"""R9.6/R9.14 process-boundary checks outside the row matrix."""

from __future__ import annotations

import signal
import subprocess
import sys
from pathlib import Path


def _entrypoint() -> Path:
    return Path(sys.executable).with_name("agent-fork")


def test_closed_stdout_terminates_cleanly_with_sigpipe():
    process = subprocess.Popen(
        [_entrypoint(), "--help"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    assert process.stdout is not None
    process.stdout.close()
    assert process.wait(timeout=5) == -signal.SIGPIPE


def test_closed_stderr_on_usage_error_has_no_traceback_or_hang():
    process = subprocess.Popen(
        [_entrypoint(), "cleanup"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    assert process.stderr is not None
    process.stderr.close()
    assert process.wait(timeout=5) == -signal.SIGPIPE
