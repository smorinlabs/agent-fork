"""Scaffold smoke tests: the package imports and exposes its metadata."""

from importlib.metadata import version

import agent_fork
from agent_fork.cli import main


def test_version_matches_metadata() -> None:
    assert agent_fork.__version__ == version("agent-fork")


def test_console_entry_point_is_callable() -> None:
    assert callable(main)
