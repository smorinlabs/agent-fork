"""G-MAT — A6b step 4: the recursive submodule snapshot.

Design: docs/superpowers/plans/2026-08-17-p02-a6-dirty-submodules.md, "The
recursive snapshot (finding 3)". Resolved once, before the worktree exists —
carry and verification both consume this same frozen plan, so a submodule
that changes between snapshot and carry cannot make either step see a
different world than the other. Read-only here: nothing consumes it yet.
"""

from __future__ import annotations

import pytest

from conftest import submodule


def _snapshot(world, **kwargs):
    from agent_fork.submodules import snapshot_submodules

    return snapshot_submodules(
        world.parent_path,
        with_state=kwargs.pop("with_state", True),
        with_ignored=kwargs.pop("with_ignored", False),
        env=world.env,
    )


@pytest.mark.matrix("T-MAT-40")
def test_no_gitlinks_snapshots_to_an_empty_tuple(repo_scenario):
    world = repo_scenario("plain@main")
    assert _snapshot(world) == ()


@pytest.mark.matrix("T-MAT-41")
def test_clean_submodule_snapshot_records_head_and_resolved_url(repo_scenario):
    world = repo_scenario("plain@main", states=(submodule(),))
    plans = _snapshot(world)
    assert len(plans) == 1
    plan = plans[0]
    assert plan.path == "vendor/submodule"
    assert plan.name == "vendor/submodule"
    assert plan.initialized is True
    assert plan.head is not None and len(plan.head) == 40
    assert plan.remote_url is not None
    assert plan.nested == ()


@pytest.mark.matrix("T-MAT-42")
def test_uninitialized_submodule_snapshots_as_cold_with_no_head_or_url(
    repo_scenario,
):
    """Cell `g` — the parent left it cold; the snapshot must say so plainly.

    A cold submodule cannot be walked for its own HEAD or remote, and it
    cannot be recursed into for nested plans — there is nothing there to read.
    """
    world = repo_scenario("plain@main", states=(submodule(dirty="uninit"),))
    plans = _snapshot(world)
    assert len(plans) == 1
    plan = plans[0]
    assert plan.initialized is False
    assert plan.head is None
    assert plan.remote_url is None
    assert plan.nested == ()


@pytest.mark.matrix("T-MAT-43")
def test_renamed_submodule_snapshot_carries_both_name_and_path(repo_scenario):
    """Cell `j` — config name and path differ; the plan must keep both."""
    world = repo_scenario("plain@main", states=(submodule(name="libfoo"),))
    plan = _snapshot(world)[0]
    assert plan.path == "vendor/submodule"
    assert plan.name == "libfoo"


@pytest.mark.matrix("T-MAT-44")
def test_nested_submodule_produces_a_nested_plan_entry(repo_scenario):
    """Cell `h` — the frozen plan recurses one level for a submodule-in-a-submodule."""
    world = repo_scenario("plain@main", states=(submodule(nested=True),))
    plan = _snapshot(world)[0]
    assert len(plan.nested) == 1
    inner = plan.nested[0]
    assert inner.path == "inner"
    assert inner.initialized is True
    assert inner.head is not None


@pytest.mark.matrix("T-MAT-45")
def test_snapshot_records_the_submodules_own_dirty_inventory(repo_scenario):
    """A dirty submodule's own carried-state facets are captured, not just its HEAD."""
    world = repo_scenario("plain@main", states=(submodule(dirty="modified"),))
    plan = _snapshot(world)[0]
    assert "tracked.txt" in plan.inventory.unstaged
    assert plan.content is not None
    assert "tracked.txt" in plan.content.paths


@pytest.mark.matrix("T-MAT-46")
def test_snapshot_with_no_state_returns_no_plans(repo_scenario):
    """`with_state=False` carries nothing, so there is nothing to snapshot either."""
    world = repo_scenario("plain@main", states=(submodule(dirty="modified"),))
    assert _snapshot(world, with_state=False) == ()


@pytest.mark.matrix("T-MAT-47")
def test_snapshot_resolves_a_relative_gitmodules_url_to_an_absolute_value(
    repo_scenario,
):
    """The recipe's own step 3 needs this resolved *before the fork* — this
    is the only place in the whole design that runs at that moment, so it is
    where the value must live (gate-4 pass 4 finding 4).
    """
    world = repo_scenario("plain@main", states=(submodule(url_kind="relative"),))
    plan = _snapshot(world)[0]
    assert plan.remote_url is not None
    assert not plan.remote_url.startswith("../")


@pytest.mark.matrix("T-MAT-48")
def test_snapshot_records_an_unreachable_remote_without_touching_the_network(
    repo_scenario,
):
    """Snapshotting reads local Git state only — it must never fetch."""
    world = repo_scenario(
        "plain@main", states=(submodule(url_kind="remote-unreachable"),)
    )
    plan = _snapshot(world)[0]
    assert plan.remote_url is not None
    assert "192.0.2.1" in plan.remote_url
