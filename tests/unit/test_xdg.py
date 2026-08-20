"""Unit tests for XDG path resolution."""

from pathlib import Path

import pytest

from agent_fork.xdg import xdg_path


@pytest.mark.matrix("T-CFG-19")
def test_xdg_path_uses_explicit_base_without_home():
    resolved = xdg_path(
        {"XDG_DATA_HOME": "/tmp/data"},
        "XDG_DATA_HOME",
        ".local/share",
        "agent-fork",
    )
    assert resolved == Path("/tmp/data/agent-fork")


@pytest.mark.matrix("T-CFG-20")
def test_xdg_path_expands_home_default():
    resolved = xdg_path({}, "XDG_CACHE_HOME", ".cache", "agent-fork")
    assert str(resolved).endswith("/.cache/agent-fork")
    assert not str(resolved).startswith("~")


@pytest.mark.matrix("T-CFG-21")
def test_xdg_path_does_not_require_home_when_var_is_set():
    assert xdg_path(
        {"XDG_DATA_HOME": "/tmp/data"},
        "XDG_DATA_HOME",
        ".local/share",
    ) == Path("/tmp/data")


@pytest.mark.matrix("T-CFG-22")
def test_empty_xdg_value_is_treated_as_unset():
    """An empty value must not resolve the store relative to the cwd.

    The XDG Base Directory specification treats an empty variable as unset.
    Accepting an empty base would place state wherever the process happened
    to be running.
    """
    resolved = xdg_path(
        {"XDG_STATE_HOME": "", "HOME": "/home/example"},
        "XDG_STATE_HOME",
        ".local/state",
        "agent-fork",
    )
    assert resolved == Path("/home/example/.local/state/agent-fork")
    assert resolved.is_absolute()
