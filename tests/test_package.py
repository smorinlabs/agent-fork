"""Scaffold smoke tests: the package imports and exposes its metadata."""

import tomllib
from importlib.metadata import version
from pathlib import Path

import agent_fork
from agent_fork.cli import main


def test_version_matches_metadata() -> None:
    assert agent_fork.__version__ == version("agent-fork")


def test_console_entry_point_is_callable() -> None:
    assert callable(main)


def test_flox_environment_uses_host_managed_agent_clis() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    manifest = tomllib.loads((repo_root / ".flox/env/manifest.toml").read_text())

    installed = manifest["install"]
    assert "claude-code" not in installed
    assert "codex" not in installed
