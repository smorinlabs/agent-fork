"""G-REG unit rows for registry schema and ordering."""

from datetime import UTC, datetime

import pytest


@pytest.mark.matrix("T-REG-01")
def test_registry_write_populates_schema_fields(repo_scenario):
    from agent_fork.models import RegistryEntry
    from agent_fork.registry import add_entry, read_registry, registry_path

    world = repo_scenario()
    entry = RegistryEntry.create(
        name="review", branch="fork/review", worktree=world.parent_path, agent="codex"
    )
    add_entry(entry, env=world.env)
    [stored] = read_registry(env=world.env)
    assert stored == entry
    assert stored.to_dict() == {
        "name": "review",
        "branch": "fork/review",
        "worktree": str(world.parent_path),
        "agent": "codex",
        "created_at": entry.created_at,
    }
    parsed = datetime.fromisoformat(stored.created_at.replace("Z", "+00:00"))
    assert parsed.tzinfo == UTC
    assert registry_path(world.env).is_file()


@pytest.mark.matrix("T-REG-02")
def test_list_output_ordered_by_creation_time_deterministically(repo_scenario):
    from agent_fork.models import RegistryEntry
    from agent_fork.registry import add_entry, read_registry

    world = repo_scenario()
    entries = (
        RegistryEntry("z", "fork/z", "/z", "claude", "2026-01-02T00:00:00Z"),
        RegistryEntry("b", "fork/b", "/b", "codex", "2026-01-01T00:00:00Z"),
        RegistryEntry("a", "fork/a", "/a", "codex", "2026-01-01T00:00:00Z"),
    )
    for entry in entries:
        add_entry(entry, env=world.env)
    expected = ["a", "b", "z"]
    assert [item.name for item in read_registry(env=world.env)] == expected
    assert [item.name for item in read_registry(env=world.env)] == expected
