"""G-REG list command rendering."""

import json

import pytest


@pytest.mark.matrix("T-REG-07")
def test_list_renders_entries_and_json_schema(repo_scenario):
    from agent_fork.models import RegistryEntry
    from agent_fork.registry import add_entry
    from conftest import run_cli

    world = repo_scenario()
    missing = world.parent_path.parent / "missing"
    entries = (
        RegistryEntry(
            "later", "fork/later", str(missing), "claude", "2026-02-02T00:00:00Z"
        ),
        RegistryEntry(
            "first",
            "fork/first",
            str(world.parent_path),
            "codex",
            "2026-02-01T00:00:00Z",
        ),
    )
    for entry in entries:
        add_entry(entry, env=world.env)

    text = run_cli(["list"], world.env, world.parent_path)
    assert text.returncode == 0 and text.stderr == b""
    lines = text.stdout.decode().splitlines()
    assert lines[0].split("\t") == [
        "first",
        "fork/first",
        str(world.parent_path),
        "codex",
        "yes",
    ]
    assert lines[1].split("\t") == ["later", "fork/later", str(missing), "claude", "no"]

    machine = run_cli(["list", "-o", "json"], world.env, world.parent_path)
    assert machine.returncode == 0 and machine.stderr == b""
    document = json.loads(machine.stdout)
    assert document == {
        "version": 1,
        "forks": [
            {**entries[1].to_dict(), "worktree_exists": True},
            {**entries[0].to_dict(), "worktree_exists": False},
        ],
    }
