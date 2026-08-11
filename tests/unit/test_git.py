"""Unit regressions for Git subprocess cleanup."""

import signal

import pytest


@pytest.mark.matrix("T-RBK-07")
def test_interrupted_git_preserves_original_exception_after_group_exit(monkeypatch):
    """A redundant group signal must not mask the active interruption."""
    import agent_fork.git as module

    interrupted = KeyboardInterrupt()

    class ExitedProcess:
        pid = 12345
        returncode = -signal.SIGKILL

        def communicate(self, input=None):
            raise interrupted

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            return self.returncode

    process = ExitedProcess()
    monkeypatch.setattr(module.subprocess, "Popen", lambda *args, **kwargs: process)

    def redundant_signal(*args):
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(module.os, "killpg", redundant_signal)

    with pytest.raises(KeyboardInterrupt) as raised:
        module.run_git(module.Path.cwd(), ["status"])

    assert raised.value is interrupted
