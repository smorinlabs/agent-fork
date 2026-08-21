"""G-FIX — A6b step 2: `config_pins` threaded through the transport/inventory
functions the recipe reuses. Still inert — no production caller passes pins
yet; these prove the parameter reaches Git when a test passes one directly.
"""

from __future__ import annotations

import pytest


@pytest.mark.matrix("T-FIX-33")
def test_collect_inventory_accepts_and_applies_config_pins(repo_scenario):
    """A pin that changes what Git reports as staged changes the inventory.

    `diff.ignoreSubmodules=all` (command-scoped) makes an otherwise-dirty
    staged submodule invisible to `git diff --cached --name-only`,
    distinguishing "the pin reached Git" from "the pin was accepted and
    silently ignored." The *staged* listing is the proving ground because it
    carries no `--ignore-submodules` flag of its own to compete with the pin —
    the unstaged listing does (A6a's `--ignore-submodules=dirty`), and a
    command-line flag beats a `-c` pin for the same axis, confirmed
    empirically before writing this assertion.
    """
    from agent_fork.content import collect_inventory
    from conftest import submodule

    world = repo_scenario("plain@main", states=(submodule(dirty="advanced-staged"),))
    unpinned = collect_inventory(
        world.parent_path, with_state=True, with_ignored=False, env=world.env
    )
    pinned = collect_inventory(
        world.parent_path,
        with_state=True,
        with_ignored=False,
        env=world.env,
        config_pins=(("diff.ignoreSubmodules", "all"),),
    )
    assert "vendor/submodule" in unpinned.staged
    assert "vendor/submodule" not in pinned.staged


@pytest.mark.matrix("T-FIX-34")
def test_materialize_accepts_config_pins_and_stays_inert_by_default(repo_scenario):
    """`materialize` takes the parameter; passing `()` changes nothing."""
    from agent_fork.materialize import materialize
    from agent_fork.repository import create_worktree_at_anchor
    from conftest import unstaged

    world = repo_scenario("plain@main", states=(unstaged("tracked.txt"),))
    child = world.parent_path.parent / "a6b-pins-inert"
    create_worktree_at_anchor(
        world.parent_path, "fork/a6b-pins-inert", child, env=world.env
    )
    result = materialize(
        world.parent_path, child, with_state=True, config_pins=(), env=world.env
    )
    assert result.unstaged_patch is True
    assert (child / "tracked.txt").read_text() == "unstaged\n"
