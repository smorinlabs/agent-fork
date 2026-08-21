"""G-MAT — A6b step 5: the carry recipe.

Design: docs/superpowers/plans/2026-08-17-p02-a6-dirty-submodules.md, "The
recipe, per gitlink, depth-first". Consumes the frozen snapshot (step 4);
does not yet consume the flag or wire into the pipeline — that is step 6.
"""

from __future__ import annotations

import subprocess

import pytest

from conftest import submodule


def _git(world, repo, *args, check=True):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        env=world.env,
        capture_output=True,
        check=check,
    )


def _status(world, repo):
    return _git(world, repo, "status", "--porcelain=v1", "-z").stdout


def _carry(world, child, *, with_state=True, with_ignored=False):
    from agent_fork.repository import create_worktree_at_anchor
    from agent_fork.submodules import carry_submodules, snapshot_submodules

    plans = snapshot_submodules(
        world.parent_path,
        with_state=with_state,
        with_ignored=with_ignored,
        env=world.env,
    )
    create_worktree_at_anchor(
        world.parent_path, f"fork/{child.name}", child, env=world.env
    )
    return carry_submodules(
        world.parent_path,
        child,
        plans,
        with_state=with_state,
        with_ignored=with_ignored,
        env=world.env,
    )


@pytest.mark.matrix("T-MAT-39")
def test_carry_leaves_no_submodules_carried_when_none_exist(repo_scenario):
    world = repo_scenario("plain@main")
    child = world.parent_path.parent / "a6b-none"
    result = _carry(world, child)
    assert result.carried == ()
    assert result.skipped == ()


@pytest.mark.matrix("T-MAT-40")
def test_carry_initializes_offline_and_matches_top_level_status(repo_scenario):
    """Cell `a` — a modified submodule carries and both statuses match exactly."""
    world = repo_scenario("plain@main", states=(submodule(dirty="modified"),))
    child = world.parent_path.parent / "a6b-modified"
    result = _carry(world, child)
    assert "vendor/submodule" in result.carried
    assert (child / "vendor/submodule/.git").exists()
    assert _status(world, child) == _status(world, world.parent_path)
    inner = _git(world, child / "vendor/submodule", "status", "--porcelain=v1").stdout
    assert inner == b" M tracked.txt\n"


@pytest.mark.matrix("T-MAT-41")
def test_carry_represents_an_unstaged_gitlink_advance(repo_scenario):
    """Cell `c` — the case A6a's guard refuses; carrying makes it representable.

    The parent's submodule sits at a commit its own index does not record.
    Checking the child out at the parent's *submodule* HEAD (not the gitlink
    OID in the index) is what makes this carriable at all.
    """
    world = repo_scenario("plain@main", states=(submodule(dirty="advanced"),))
    parent_sub_head = (
        _git(world, world.parent_path / "vendor/submodule", "rev-parse", "HEAD")
        .stdout.decode()
        .strip()
    )
    child = world.parent_path.parent / "a6b-advanced"
    result = _carry(world, child)
    assert "vendor/submodule" in result.carried
    child_sub_head = (
        _git(world, child / "vendor/submodule", "rev-parse", "HEAD")
        .stdout.decode()
        .strip()
    )
    assert child_sub_head == parent_sub_head
    assert _status(world, child) == _status(world, world.parent_path)


@pytest.mark.matrix("T-MAT-42")
def test_carry_never_runs_submodule_sync_in_the_child(repo_scenario):
    """Gate-4 pass 1 finding 1 — sync in a linked worktree corrupts the parent's
    shared config. A deliberate local override in the parent must survive.
    """
    world = repo_scenario("plain@main", states=(submodule(committed=True),))
    _git(
        world,
        world.parent_path,
        "config",
        "submodule.vendor/submodule.url",
        "/deliberately/overridden",
    )
    before = _git(
        world, world.parent_path, "config", "--get", "submodule.vendor/submodule.url"
    ).stdout
    child = world.parent_path.parent / "a6b-sync-safe"
    _carry(world, child)
    after = _git(
        world, world.parent_path, "config", "--get", "submodule.vendor/submodule.url"
    ).stdout
    assert after == before


@pytest.mark.matrix("T-MAT-43")
def test_carry_restores_only_the_childs_own_remote_url(repo_scenario):
    world = repo_scenario("plain@main", states=(submodule(committed=True),))
    child = world.parent_path.parent / "a6b-remote"
    _carry(world, child)
    child_remote = (
        _git(world, child / "vendor/submodule", "config", "--get", "remote.origin.url")
        .stdout.decode()
        .strip()
    )
    parent_remote = (
        _git(
            world,
            world.parent_path / "vendor/submodule",
            "config",
            "--get",
            "remote.origin.url",
        )
        .stdout.decode()
        .strip()
    )
    assert child_remote == parent_remote


@pytest.mark.matrix("T-MAT-44")
def test_carry_works_offline_with_a_renamed_submodule(repo_scenario):
    """Cell `j` — config name differs from path; the override must be name-keyed."""
    world = repo_scenario(
        "plain@main", states=(submodule(name="libfoo", committed=True),)
    )
    child = world.parent_path.parent / "a6b-renamed"
    result = _carry(world, child)
    assert "vendor/submodule" in result.carried
    assert (child / "vendor/submodule/.git").exists()


@pytest.mark.matrix("T-MAT-45")
def test_carry_works_offline_with_a_remote_unreachable_url(repo_scenario):
    """The offline override must engage even when `.gitmodules` names a real
    remote — proven with a genuinely unreachable URL, not a masked local one.
    """
    world = repo_scenario(
        "plain@main", states=(submodule(url_kind="remote-unreachable"),)
    )
    child = world.parent_path.parent / "a6b-unreachable"
    result = _carry(world, child)
    assert "vendor/submodule" in result.carried
    assert (child / "vendor/submodule/.git").exists()


@pytest.mark.matrix("T-MAT-46")
def test_carry_leaves_a_parent_cold_submodule_cold_in_the_child(repo_scenario):
    """Cell `g` — a fork must not initialize what the parent itself did not."""
    world = repo_scenario("plain@main", states=(submodule(dirty="uninit"),))
    child = world.parent_path.parent / "a6b-uninit"
    result = _carry(world, child)
    assert "vendor/submodule" in result.skipped
    assert result.carried == ()
    assert not (child / "vendor/submodule/.git").exists()


@pytest.mark.matrix("T-MAT-47")
def test_carry_honours_update_policy_none_via_the_checkout_flag(repo_scenario):
    """Gate-4 pass 1 finding 2 — `submodule.<name>.update=none` must not make
    the recipe's init step silently no-op.
    """
    world = repo_scenario(
        "plain@main", states=(submodule(update_policy="none", dirty="modified"),)
    )
    child = world.parent_path.parent / "a6b-updatenone"
    result = _carry(world, child)
    assert "vendor/submodule" in result.carried
    assert (child / "vendor/submodule/.git").exists()


@pytest.mark.matrix("T-MAT-48")
def test_carry_recurses_into_a_nested_submodule(repo_scenario):
    """Cell `h` — a submodule inside a submodule is carried too, not left cold."""
    world = repo_scenario(
        "plain@main", states=(submodule(nested=True, committed=True),)
    )
    child = world.parent_path.parent / "a6b-nested"
    result = _carry(world, child)
    assert "vendor/submodule" in result.carried
    assert (child / "vendor/submodule/vendor/submodule/inner/.git").exists() or (
        child / "vendor/submodule/inner/.git"
    ).exists()


@pytest.mark.matrix("T-MAT-49")
def test_carry_stages_a_change_in_the_submodules_own_index(repo_scenario):
    """Cell `i` — staged inside the submodule, HEAD unmoved; transport reuse
    (materialize, via config_pins) must carry the staged half."""
    world = repo_scenario(
        "plain@main", states=(submodule(dirty="staged-in-own-index"),)
    )
    child = world.parent_path.parent / "a6b-staged"
    result = _carry(world, child)
    assert "vendor/submodule" in result.carried
    inner = _git(world, child / "vendor/submodule", "status", "--porcelain=v1").stdout
    assert inner == b"M  tracked.txt\n"


@pytest.mark.matrix("T-MAT-50")
def test_carry_notices_name_the_configuration_fidelity_limit(repo_scenario):
    """Recipe step 3 — only remote.origin.url is restored; the notice must say so."""
    world = repo_scenario("plain@main", states=(submodule(committed=True),))
    child = world.parent_path.parent / "a6b-notice"
    result = _carry(world, child)
    assert any("remote.origin.url" in notice for notice in result.notices)
