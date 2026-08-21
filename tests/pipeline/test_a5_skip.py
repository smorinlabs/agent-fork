"""G-MAT — A5 skip detection.

Design: docs/superpowers/plans/2026-08-20-p02-a5-skip-and-race-policy.md

A5's governing rule is that a fork must not refuse to work because of one
entry it cannot copy. Detection comes first: every unreadable carried entry
must surface as the typed `entry_unreadable`, never as a raw `runtime_error`
carrying an errno string. Converting the qualifying cases into skips is a
later slice; this module pins the classification.

The `lstat` row matters beyond ergonomics. `_manifest_entry` catches every
`OSError` and reports kind `absent`, so a `PermissionError` from an
untraversable parent directory currently masquerades as a deletion. A5's rule
that absence is legitimate would then silently swallow it, which is issue #59's
failure mode arriving through the back door. Only `ENOENT` and `ENOTDIR` may
mean absent.
"""

from __future__ import annotations

import os
import subprocess
from typing import cast

import pytest

from agent_fork.content import capture_state, collect_inventory
from agent_fork.errors import EntryUnreadableError


def _inventory(world):
    return collect_inventory(
        world.parent_path, with_state=True, with_ignored=False, env=world.env
    )


@pytest.mark.matrix("T-MAT-33")
def test_unreadable_tracked_file_raises_entry_unreadable(repo_scenario):
    """A tracked, modified file whose content cannot be read is a typed
    failure naming the path — never a raw runtime_error, and never a skip:
    tracked paths cannot skip, because a rename's endpoints land in different
    listings and dropping one would lose the other."""
    world = repo_scenario()
    target = world.parent_path / "tracked.txt"
    target.write_text("modified\n")
    os.chmod(target, 0)
    try:
        with pytest.raises(EntryUnreadableError) as caught:
            capture_state(world.parent_path, _inventory(world), env=world.env)
    finally:
        os.chmod(target, 0o644)

    assert caught.value.code == "entry_unreadable"
    assert caught.value.exit_code == 1
    assert "tracked.txt" in str(caught.value)


@pytest.mark.matrix("T-MAT-34")
def test_lstat_failure_is_never_reported_as_absent(repo_scenario):
    """An `lstat` that fails for any reason other than ENOENT/ENOTDIR raises
    rather than reporting kind `absent`. A path that cannot be stat'd yields
    no stability sentinel, so it could never be proven unchanged; reporting it
    as absent would make it indistinguishable from a legitimate deletion."""
    world = repo_scenario()
    holder = world.parent_path / "holder"
    holder.mkdir()
    (holder / "buried.txt").write_text("untracked\n")
    inventory = _inventory(world)
    assert "holder/buried.txt" in inventory.untracked, "precondition: Git saw it"

    os.chmod(holder, 0)
    try:
        with pytest.raises(EntryUnreadableError) as caught:
            capture_state(world.parent_path, inventory, env=world.env)
    finally:
        os.chmod(holder, 0o755)

    assert caught.value.code == "entry_unreadable"
    assert "holder/buried.txt" in str(caught.value)


def _fork_through(world, name, *, with_ignored=False):
    """Capture → create → materialize → verify, the pipeline's own order."""
    from agent_fork.content import capture_state, collect_inventory
    from agent_fork.materialize import materialize
    from agent_fork.repository import create_worktree_at_anchor
    from agent_fork.verify import verify_fork

    before = subprocess.run(
        ["git", "-C", str(world.parent_path), "status", "--porcelain=v1", "-z"],
        env=world.env,
        capture_output=True,
    ).stdout
    inventory = collect_inventory(
        world.parent_path, with_state=True, with_ignored=with_ignored, env=world.env
    )
    state = capture_state(world.parent_path, inventory, env=world.env)
    child = world.parent_path.parent / f"a5-{name}"
    creation = create_worktree_at_anchor(
        world.parent_path, f"fork/a5-{name}", child, env=world.env
    )
    result = materialize(
        world.parent_path,
        child,
        with_state=True,
        with_ignored=with_ignored,
        inventory=inventory,
        skipped=state.skipped,
        env=world.env,
    )
    verify_fork(
        creation,
        with_state=True,
        with_ignored=with_ignored,
        parent_status_before=before,
        parent_state_before=state,
        skipped=state.skipped,
        env=world.env,
    )
    return child, state, result


@pytest.mark.matrix("T-MAT-30")
def test_unreadable_untracked_file_is_skipped_and_the_fork_succeeds(repo_scenario):
    """The fault A5 exists to fix: one unreadable untracked entry must not
    destroy the fork. It is skipped, named, and everything else is carried."""
    world = repo_scenario()
    (world.parent_path / "keep.txt").write_text("carried\n")
    locked = world.parent_path / "locked.txt"
    locked.write_text("secret\n")
    os.chmod(locked, 0)
    try:
        child, state, result = _fork_through(world, "skip")
    finally:
        os.chmod(locked, 0o644)

    assert [r.path for r in state.skipped] == ["locked.txt"]
    assert state.skipped[0].reason == "unreadable"
    assert (child / "keep.txt").read_text() == "carried\n", "the rest is carried"
    assert not (child / "locked.txt").exists(), "the skipped entry is not carried"
    assert any("locked.txt" in n for n in result.notices), "the skip is named"


@pytest.mark.matrix("T-MAT-35")
def test_a_carried_deletion_refuses_the_skip(repo_scenario):
    """A skip is refused while the fork carries any deletion. `mv old new`
    without `git mv` splits into an unstaged deletion of `old` and an untracked
    `new`; skipping an unreadable `new` would drop `old` too, leaving the child
    with neither endpoint while the warning named only `new`."""
    world = repo_scenario()
    (world.parent_path / "tracked.txt").unlink()  # unstaged deletion
    moved = world.parent_path / "moved.txt"
    moved.write_text("renamed content\n")
    os.chmod(moved, 0)
    try:
        with pytest.raises(EntryUnreadableError) as caught:
            _fork_through(world, "deletion-blocks")
    finally:
        os.chmod(moved, 0o644)

    entry = cast(dict, caught.value.details["entry"])
    assert entry["reason"] == "skip-blocked-by-deletion"
    assert caught.value.details["deletion_blockers"] == ["tracked.txt"]
