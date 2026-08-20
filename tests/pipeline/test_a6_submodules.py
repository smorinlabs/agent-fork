"""G-VER/G-GRD/G-MAT — A6a: a dirty submodule must not make a repo unforkable.

Design: docs/superpowers/plans/2026-08-17-p02-a6-dirty-submodules.md

`git worktree add` never initializes submodules, so a child worktree has no
submodule checkout. A parent whose submodule holds working-tree changes reports
` M <path>` that the child can never reproduce, and verification rolls the whole
fork back. A6a stops comparing what the design already decided not to carry:
`--ignore-submodules=dirty` suppresses submodule *working-tree* state on both
sides while still reporting *commit-level* gitlink differences, so the one
submodule case that transports today keeps being checked.

The negative rows here were RED before that filtering existed — each one
reproduced an end-to-end rollback. The positive guards were GREEN before and
must stay GREEN: they pin the state A6a must not stop checking.

A6a deliberately does not carry submodule contents. That is A6b.
"""

from __future__ import annotations

import subprocess

import pytest

from conftest import submodule, unstaged


def _git(world, repo, *args, check=True):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        env=world.env,
        capture_output=True,
        check=check,
    )


def _status(world, repo):
    return _git(world, repo, "status", "--porcelain=v1", "-z").stdout


def _fork_and_verify(repo_scenario, name, *, states):
    """Full pipeline slice: snapshot, create, materialize, verify.

    Returns the world so a caller can assert on what the child actually holds.
    Raises `VerificationError` if the fork does not verify, which is exactly the
    A6 failure being fixed.
    """
    from agent_fork.content import capture_state, collect_inventory
    from agent_fork.materialize import materialize
    from agent_fork.repository import create_worktree_at_anchor, validate_fork_guards
    from agent_fork.verify import verify_fork

    world = repo_scenario("plain@main", states=states)
    before = _status(world, world.parent_path)
    inventory = collect_inventory(
        world.parent_path, with_state=True, with_ignored=False, env=world.env
    )
    state_before = capture_state(world.parent_path, inventory, env=world.env)

    child = world.parent_path.parent / f"a6-{name}"
    branch = f"fork/a6-{name}"
    validate_fork_guards(world.parent_path, branch, child, env=world.env)
    creation = create_worktree_at_anchor(
        world.parent_path, branch, child, env=world.env
    )
    materialize(
        world.parent_path, child, with_state=True, inventory=inventory, env=world.env
    )
    world.child_path = child
    verify_fork(
        creation,
        with_state=True,
        parent_status_before=before,
        parent_state_before=state_before,
        env=world.env,
    )
    return world


# ---------------------------------------------------------------------------
# Negatives — each one rolled the fork back before A6a
# ---------------------------------------------------------------------------


@pytest.mark.matrix("T-VER-35")
def test_submodule_with_modified_tracked_file_still_forks(repo_scenario):
    """A6a — an edited tracked file inside a submodule no longer blocks the fork.

    Parent reports ` M vendor/submodule`; the child has no submodule checkout
    and reports nothing. Before A6a that difference failed `exact-copy-status`
    and `content-match` and rolled the fork back.
    """
    world = _fork_and_verify(
        repo_scenario, "modified", states=(submodule(dirty="modified"),)
    )
    assert b"vendor/submodule" in _status(world, world.parent_path)


@pytest.mark.matrix("T-VER-36")
def test_submodule_with_untracked_content_still_forks(repo_scenario):
    """A6a — untracked content inside a submodule no longer blocks the fork.

    Distinct from T-VER-35: Git's plain `diff` does not list a submodule dirtied
    only by untracked content, so this case failed `exact-copy-status` alone,
    while the modified-file case failed `content-match` as well.
    """
    world = _fork_and_verify(
        repo_scenario, "untracked", states=(submodule(dirty="untracked"),)
    )
    assert b"vendor/submodule" in _status(world, world.parent_path)


@pytest.mark.matrix("T-VER-37")
def test_ordinary_dirt_is_still_carried_alongside_a_dirty_submodule(repo_scenario):
    """A6a — the exemption is scoped to submodules and nothing else.

    The regression this guards against is over-broad filtering: a fork carrying
    both an ordinary modified file and a dirty submodule must still transport
    and verify the ordinary file. Before A6a the submodule's status line failed
    the whole fork and the ordinary file never got its verdict.
    """
    world = _fork_and_verify(
        repo_scenario,
        "mixed",
        states=(submodule(dirty="modified"), unstaged("carried.txt")),
    )
    child_status = _status(world, world.child_path)
    assert b"carried.txt" in child_status
    assert b"vendor/submodule" not in child_status


# ---------------------------------------------------------------------------
# Positive guards — GREEN before A6a, must stay GREEN
# ---------------------------------------------------------------------------


@pytest.mark.matrix("T-VER-38")
def test_staged_gitlink_advance_is_still_carried_and_verified(repo_scenario):
    """A6a guard — a submodule advance staged in the parent keeps its check.

    This is the case that already works: the gitlink OID travels in the parent's
    staged patch and the child reproduces `M  vendor/submodule` exactly. It is
    why the filter is `--ignore-submodules=dirty` and not `=all` — `=all` would
    hide this difference, so verification would stop checking state the fork
    genuinely transports.
    """
    world = _fork_and_verify(
        repo_scenario, "staged-advance", states=(submodule(dirty="advanced-staged"),)
    )
    assert _status(world, world.child_path) == _status(world, world.parent_path)
    assert b"M  vendor/submodule" in _status(world, world.child_path)


@pytest.mark.matrix("T-VER-39")
def test_clean_submodule_still_verifies(repo_scenario):
    """A6a guard — the clean-submodule case is unaffected by the filter."""
    world = _fork_and_verify(repo_scenario, "clean", states=(submodule(),))
    assert _status(world, world.child_path) == _status(world, world.parent_path)


# ---------------------------------------------------------------------------
# Refusal — the case A6a cannot carry, refused before any mutation
# ---------------------------------------------------------------------------


@pytest.mark.matrix("T-GRD-22")
def test_unstaged_gitlink_advance_is_refused_before_any_mutation(repo_scenario):
    """A6a — an unstaged submodule advance refuses up front instead of rolling back.

    The parent's submodule sits at a commit its own index does not record. A
    child with no submodule checkout cannot represent that, and
    `--ignore-submodules=dirty` reports it by design, so the fork would fail
    verification after building and destroying a worktree. A6a refuses first,
    at exit 5, naming the remedy.

    The guard is deliberately conditional on submodules not being carried: A6b
    initializes the child's submodule and detaches it at the parent's submodule
    HEAD, which makes this case representable and this refusal wrong. A6b gates
    it rather than deleting it.
    """
    from agent_fork.errors import PreconditionError
    from agent_fork.repository import validate_fork_guards

    world = repo_scenario("plain@main", states=(submodule(dirty="advanced"),))
    child = world.parent_path.parent / "a6-advance"

    with pytest.raises(PreconditionError) as raised:
        validate_fork_guards(world.parent_path, "fork/a6-advance", child, env=world.env)

    assert raised.value.code == "submodule_unrepresentable"
    assert "vendor/submodule" in str(raised.value)
    assert not child.exists()
    assert (
        b"fork/a6-advance"
        not in _git(world, world.parent_path, "branch", "--list").stdout
    )


# ---------------------------------------------------------------------------
# Notice — say what was not carried, not that it was copied
# ---------------------------------------------------------------------------


@pytest.mark.matrix("T-MAT-26")
def test_notice_names_uncarried_submodule_state_instead_of_claiming_a_copy(
    repo_scenario,
):
    """A6a — the notice stops claiming submodules were copied.

    `materialize` announced `submodules copied opaquely: <path>` while the
    child's submodule directory was empty. Nothing was copied, and under
    `--no-verify` that message was the only thing a user saw before their
    submodule work went missing.
    """
    from agent_fork.materialize import materialize
    from agent_fork.repository import create_worktree_at_anchor

    world = repo_scenario("plain@main", states=(submodule(dirty="modified"),))
    child = world.parent_path.parent / "a6-notice"
    create_worktree_at_anchor(world.parent_path, "fork/a6-notice", child, env=world.env)
    result = materialize(world.parent_path, child, with_state=True, env=world.env)

    joined = " ".join(result.notices)
    assert "vendor/submodule" in joined
    assert "copied" not in joined
    assert "not carried" in joined


@pytest.mark.matrix("T-GRD-23")
def test_unstaged_gitlink_advance_is_not_refused_when_no_state_is_carried(
    repo_scenario,
):
    """A6a — the refusal must not block the remedy it recommends.

    `submodule_unrepresentable` tells the user to fork without carrying state.
    The guard therefore must not fire in that mode: with `--no-with-state` the
    child is a clean checkout of the anchor commit, nothing about the parent's
    submodule is being reproduced, and there is no divergence to refuse.
    """
    from agent_fork.repository import validate_fork_guards

    world = repo_scenario("plain@main", states=(submodule(dirty="advanced"),))
    child = world.parent_path.parent / "a6-nostate"

    validate_fork_guards(
        world.parent_path,
        "fork/a6-nostate",
        child,
        with_state=False,
        env=world.env,
    )
