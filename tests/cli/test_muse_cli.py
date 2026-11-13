"""G-MUS — Muse as a full agent (P08), installed-CLI tier.

Matrix: docs/testing/TEST-MATRIX.md §G-MUS.
"""

from __future__ import annotations

import json
import os
import shlex
import sys
from pathlib import Path

import pytest

from muse_fake import FAKE_MUSE, FORK, PARENT


def _env(world, **extra: str) -> dict[str, str]:
    directory = world.parent_path.parent / "muse-bin"
    directory.mkdir(exist_ok=True)
    binary = directory / "muse"
    binary.write_text(FAKE_MUSE)
    binary.chmod(0o755)
    data = world.parent_path.parent / "muse-data"
    log = data / "muse/sessions/2026/11/13" / PARENT / "session.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("{}\n")
    return {
        **world.env,
        "PATH": f"{directory}{os.pathsep}{world.env['PATH']}",
        "XDG_DATA_HOME": str(data),
        **extra,
    }


def _executable() -> str:
    return str(Path(sys.executable).with_name("agent-fork"))


@pytest.mark.matrix("T-MUS-14")
def test_fork_agent_muse_dry_run_prints_the_paste_command(repo_scenario):
    from conftest import run_cli

    world = repo_scenario()
    completed = run_cli(
        [
            "fork",
            "try-muse",
            "--dry-run",
            "--json",
            "--agent",
            "muse",
            "--parent-session",
            PARENT,
        ],
        _env(world),
        world.parent_path,
    )
    assert completed.returncode == 0, completed.stderr
    document = json.loads(completed.stdout)
    worktree = document["plan"]["worktree"]["path"]
    q = shlex.quote
    assert document["command"] == (
        f"cd {q(worktree)} && muse resume "
        f'"$({q(_executable())} muse-fork {q(PARENT)})"'
    )


@pytest.mark.matrix("T-MUS-15")
def test_hidden_muse_fork_subcommand(repo_scenario):
    from conftest import run_cli

    world = repo_scenario()
    env = _env(world)
    help_text = run_cli(["--help"], env, world.parent_path)
    assert help_text.returncode == 0
    assert b"muse-fork" not in help_text.stdout
    elsewhere = world.parent_path.parent / "not-a-repo"
    elsewhere.mkdir()
    forked = run_cli(["muse-fork", PARENT], env, elsewhere)
    assert forked.returncode == 0, forked.stderr
    assert forked.stdout == f"{FORK}\n".encode()
    failed = run_cli(
        ["muse-fork", PARENT], {**env, "FAKE_MUSE_MODE": "error"}, elsewhere
    )
    assert failed.returncode == 3
    assert failed.stdout == b""
    assert b"session not found" in failed.stderr
    unsafe = run_cli(["muse-fork", "not-a-uuid"], env, elsewhere)
    assert unsafe.returncode == 3
    assert unsafe.stdout == b""


@pytest.mark.matrix("T-MUS-16")
def test_completion_offers_muse_but_not_the_hidden_command(repo_scenario):
    from conftest import run_cli

    world = repo_scenario()
    completed = run_cli(["completion", "bash"], world.env, world.parent_path)
    assert completed.returncode == 0
    assert b"muse" in completed.stdout
    assert b"muse-fork" not in completed.stdout


@pytest.mark.matrix("T-MUS-17")
def test_doctor_reports_muse(repo_scenario):
    from conftest import run_cli

    world = repo_scenario()
    env = _env(world, MUSE_SESSION_ID=PARENT, MUSE_THREAD_ID=PARENT)
    completed = run_cli(["doctor"], env, world.parent_path)
    output = completed.stdout.decode()
    assert "Muse CLI: 1.4.20" in output
    assert "environment signals: status=detected" in output
    assert "selected=muse" in output
    assert "muse: 2 documented" in output
