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
