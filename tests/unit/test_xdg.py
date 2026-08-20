"""Unit tests for XDG path resolution."""

from pathlib import Path

from agent_fork.xdg import xdg_path


def test_xdg_path_uses_explicit_base_without_home():
    resolved = xdg_path(
        {"XDG_DATA_HOME": "/tmp/data"},
        "XDG_DATA_HOME",
        ".local/share",
        "agent-fork",
    )
    assert resolved == Path("/tmp/data/agent-fork")


def test_xdg_path_expands_home_default():
    resolved = xdg_path({}, "XDG_CACHE_HOME", ".cache", "agent-fork")
    assert str(resolved).endswith("/.cache/agent-fork")
    assert not str(resolved).startswith("~")


def test_xdg_path_does_not_require_home_when_var_is_set():
    assert xdg_path(
        {"XDG_DATA_HOME": "/tmp/data"},
        "XDG_DATA_HOME",
        ".local/share",
    ) == Path("/tmp/data")
