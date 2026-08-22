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
    assert caught.value.details is not None
    assert cast(dict, caught.value.details["entry"])["reason"] == "tracked"


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

    details = caught.value.details
    assert details is not None
    entry = cast(dict, details["entry"])
    assert entry["reason"] == "unreadable"
    assert details["deletion_blockers"] == ["tracked.txt"]


@pytest.mark.matrix("T-MAT-36")
def test_staged_cached_deletion_blocks_an_untracked_replacement_skip(repo_scenario):
    """A cached deletion is a blocker even though its working file exists."""
    world = repo_scenario()
    subprocess.run(
        ["git", "-C", str(world.parent_path), "rm", "--cached", "tracked.txt"],
        env=world.env,
        capture_output=True,
        check=True,
    )
    target = world.parent_path / "tracked.txt"
    os.chmod(target, 0)
    try:
        with pytest.raises(EntryUnreadableError) as caught:
            capture_state(world.parent_path, _inventory(world), env=world.env)
    finally:
        os.chmod(target, 0o644)

    assert caught.value.details is not None
    assert caught.value.details == {
        "entry": {
            "path": "tracked.txt",
            "reason": "unreadable",
            "phase": "capture",
        },
        "deletion_blockers": ["tracked.txt"],
    }


@pytest.mark.matrix("T-MAT-32")
def test_nonregular_entry_at_the_transport_seam_is_skipped(repo_scenario):
    """The defensive non-regular branch returns a skip and notice."""
    from agent_fork.content import Inventory
    from agent_fork.materialize import materialize
    from agent_fork.repository import create_worktree_at_anchor

    world = repo_scenario()
    fifo = world.parent_path / "transport.fifo"
    os.mkfifo(fifo)
    child = world.parent_path.parent / "a5-nonregular"
    creation = create_worktree_at_anchor(
        world.parent_path, "fork/a5-nonregular", child, env=world.env
    )
    try:
        result = materialize(
            world.parent_path,
            creation.path,
            inventory=Inventory(untracked=("transport.fifo",)),
            env=world.env,
        )
    finally:
        fifo.unlink()

    assert len(result.skipped) == 1
    record = result.skipped[0]
    assert (record.path, record.reason, record.phase) == (
        "transport.fifo",
        "unsupported-type",
        "materialize",
    )
    assert sum("transport.fifo" in notice for notice in result.notices) == 1
    assert not (creation.path / "transport.fifo").exists()


@pytest.mark.matrix("T-MAT-31")
def test_strict_refusal_aggregates_every_capture_skip_in_byte_order(repo_scenario):
    """One strict error names every capture skip rather than stopping at one."""
    from agent_fork.errors import StrictSkipRefusedError
    from agent_fork.pipeline import ForkRequest, fork

    world = repo_scenario()
    locked = [world.parent_path / name for name in ("z-last.txt", "a-first.txt")]
    for path in locked:
        path.write_text("secret\n")
        os.chmod(path, 0)

    destination = world.parent_path.parent / "a5-strict-capture"
    try:
        with pytest.raises(StrictSkipRefusedError) as caught:
            fork(
                ForkRequest(
                    parent=world.parent_path,
                    destination=destination,
                    name="a5-strict-capture",
                    branch="fork/a5-strict-capture",
                    agent=None,
                    strict=True,
                    git_version_output="git version 2.43.0",
                ),
                env=world.env,
            )
    finally:
        for path in locked:
            os.chmod(path, 0o644)

    details = caught.value.details
    assert details is not None
    assert details == {
        "skipped": [
            {"path": "a-first.txt", "reason": "unreadable", "phase": "capture"},
            {"path": "z-last.txt", "reason": "unreadable", "phase": "capture"},
        ],
        "count": 2,
    }
    assert "a-first.txt" in str(caught.value)
    assert "z-last.txt" in str(caught.value)
    assert not destination.exists(), "strict refusal rolls the worktree back"


@pytest.mark.matrix("T-MAT-37")
def test_strict_with_ignored_aggregates_capture_materialize_and_include_skips(
    repo_scenario, monkeypatch
):
    """All three skip-producing phases reach one strict refusal."""
    from agent_fork import pipeline
    from agent_fork.errors import StrictSkipRefusedError
    from agent_fork.pipeline import ForkRequest, fork

    world = repo_scenario()
    (world.parent_path / ".gitignore").write_text("*.env\n")
    (world.parent_path / ".worktreeinclude").write_text("include-only.env\n")
    subprocess.run(
        ["git", "-C", str(world.parent_path), "add", "."],
        env=world.env,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(world.parent_path), "commit", "-m", "configure includes"],
        env=world.env,
        capture_output=True,
        check=True,
    )

    capture_path = world.parent_path / "capture.env"
    materialize_path = world.parent_path / "transport.env"
    include_path = world.parent_path / "include-only.env"
    capture_path.write_text("capture\n")
    materialize_path.write_text("materialize\n")
    os.chmod(capture_path, 0)

    real_materialize = pipeline.materialize

    def gate_materialize(*args, **kwargs):
        os.chmod(materialize_path, 0)
        result = real_materialize(*args, **kwargs)
        include_path.write_text("include\n")
        os.chmod(include_path, 0)
        return result

    monkeypatch.setattr(pipeline, "materialize", gate_materialize)
    # This row isolates cross-phase aggregation. The materialize-time chmod is
    # an intentional parent mutation, whose verification refusal is covered by
    # G-VER; allowing the run to reach include proves the aggregator's third
    # input without weakening production verification.
    monkeypatch.setattr(pipeline, "verify_fork", lambda *args, **kwargs: None)
    request = ForkRequest(
        parent=world.parent_path,
        destination=world.parent_path.parent / "a5-three-phases",
        name="a5-three-phases",
        branch="fork/a5-three-phases",
        agent=None,
        with_ignored=True,
        strict=True,
        git_version_output="git version 2.43.0",
    )
    try:
        with pytest.raises(StrictSkipRefusedError) as caught:
            fork(request, env=world.env)
    finally:
        for path in (capture_path, materialize_path, include_path):
            if path.exists():
                os.chmod(path, 0o644)

    assert caught.value.details == {
        "skipped": [
            {"path": "capture.env", "reason": "unreadable", "phase": "capture"},
            {
                "path": "include-only.env",
                "reason": "unreadable",
                "phase": "include",
            },
            {
                "path": "transport.env",
                "reason": "unreadable",
                "phase": "materialize",
            },
        ],
        "count": 3,
    }
    assert not request.destination.exists()


@pytest.mark.matrix("T-MAT-38")
def test_no_verify_can_skip_an_entry_first_read_during_materialize(repo_scenario):
    """Capture is absent under ``--no-verify``; transport still skips safely."""
    from agent_fork.pipeline import ForkRequest, fork

    world = repo_scenario()
    locked = world.parent_path / "materialize-only.txt"
    locked.write_text("secret\n")
    os.chmod(locked, 0)
    try:
        result = fork(
            ForkRequest(
                parent=world.parent_path,
                destination=world.parent_path.parent / "a5-no-verify",
                name="a5-no-verify",
                branch="fork/a5-no-verify",
                agent=None,
                verify=False,
                git_version_output="git version 2.43.0",
            ),
            env=world.env,
        )
    finally:
        os.chmod(locked, 0o644)

    assert result.verification is False
    assert result.skipped == (
        {
            "path": "materialize-only.txt",
            "reason": "unreadable",
            "phase": "materialize",
        },
    )
    assert not (result.creation.path / "materialize-only.txt").exists()
    assert sum("materialize-only.txt" in notice for notice in result.notices) == 1


@pytest.mark.matrix("T-VER-42")
def test_setup_hook_mutation_of_a_skipped_entry_fails_at_finalization(repo_scenario):
    """The hook runs after verification, so the sentinel is checked later."""
    from agent_fork.errors import VerificationError
    from agent_fork.pipeline import ForkRequest, fork
    from agent_fork.registry import find_candidates

    world = repo_scenario()
    hook = world.parent_path / ".agent-fork/worktree-setup.sh"
    hook.parent.mkdir(parents=True)
    hook.write_text('#!/bin/sh\nchmod 644 "$REPO_ROOT/locked.txt"\n')
    hook.chmod(0o755)
    subprocess.run(
        ["git", "-C", str(world.parent_path), "add", "."],
        env=world.env,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(world.parent_path), "commit", "-m", "add setup hook"],
        env=world.env,
        capture_output=True,
        check=True,
    )
    locked = world.parent_path / "locked.txt"
    locked.write_text("secret\n")
    os.chmod(locked, 0)
    request = ForkRequest(
        parent=world.parent_path,
        destination=world.parent_path.parent / "a5-hook-sentinel",
        name="a5-hook-sentinel",
        branch="fork/a5-hook-sentinel",
        agent=None,
        git_version_output="git version 2.43.0",
    )
    try:
        with pytest.raises(VerificationError) as caught:
            fork(request, env=world.env)
    finally:
        os.chmod(locked, 0o644)

    details = caught.value.details
    assert details is not None
    assert details["failed_checks"] == [
        {
            "check": "skip-sentinel",
            "primary": True,
            "total": 1,
            "differences": [
                {
                    "path": "locked.txt",
                    "kind": "skip-sentinel",
                    "detail": "changed after observation",
                }
            ],
        }
    ]
    assert not request.destination.exists()
    assert not find_candidates("a5-hook-sentinel", env=world.env)


def _status_filter_probe(world, name, skipped_name, sibling_name):
    """Delete one non-skipped child path, then run only the status oracle."""
    from agent_fork.errors import VerificationError
    from agent_fork.materialize import materialize
    from agent_fork.repository import create_worktree_at_anchor
    from agent_fork.verify import verify_fork

    before = subprocess.run(
        ["git", "-C", str(world.parent_path), "status", "--porcelain=v1", "-z"],
        env=world.env,
        capture_output=True,
        check=True,
    ).stdout
    inventory = _inventory(world)
    state = capture_state(world.parent_path, inventory, env=world.env)
    child = world.parent_path.parent / f"a5-{name}"
    creation = create_worktree_at_anchor(
        world.parent_path, f"fork/a5-{name}", child, env=world.env
    )
    materialize(
        world.parent_path,
        child,
        inventory=inventory,
        skipped=state.skipped,
        env=world.env,
    )
    (child / sibling_name).unlink()
    with pytest.raises(VerificationError, match="exact-copy-status"):
        verify_fork(
            creation,
            parent_status_before=before,
            parent_state_before=None,
            skipped=state.skipped,
            env=world.env,
        )
    assert [record.path for record in state.skipped] == [skipped_name]


@pytest.mark.matrix("T-VER-40")
def test_status_skip_exclusion_does_not_hide_a_sibling(repo_scenario):
    """Excluding one nested skip cannot exclude its directory or sibling."""
    world = repo_scenario()
    directory = world.parent_path / "nested"
    directory.mkdir()
    locked = directory / "locked.txt"
    sibling = directory / "sibling.txt"
    locked.write_text("secret\n")
    sibling.write_text("carried\n")
    os.chmod(locked, 0)
    try:
        _status_filter_probe(
            world, "narrow-filter", "nested/locked.txt", "nested/sibling.txt"
        )
    finally:
        os.chmod(locked, 0o644)


@pytest.mark.matrix("T-VER-43")
def test_status_skip_exclusion_treats_pathspec_characters_literally(repo_scenario):
    """A skipped filename containing `*` cannot exclude a matching sibling."""
    world = repo_scenario()
    locked = world.parent_path / "wild*"
    sibling = world.parent_path / "wild-one"
    locked.write_text("secret\n")
    sibling.write_text("carried\n")
    os.chmod(locked, 0)
    try:
        _status_filter_probe(world, "literal-filter", "wild*", "wild-one")
    finally:
        os.chmod(locked, 0o644)


@pytest.mark.matrix("T-VER-41")
def test_verification_does_not_reopen_a_known_skipped_path(repo_scenario, monkeypatch):
    """The verification re-capture consumes the known skip set directly."""
    from agent_fork import content
    from agent_fork.materialize import materialize
    from agent_fork.repository import create_worktree_at_anchor
    from agent_fork.verify import verify_fork

    world = repo_scenario()
    locked = world.parent_path / "locked.txt"
    locked.write_text("secret\n")
    os.chmod(locked, 0)
    before = subprocess.run(
        ["git", "-C", str(world.parent_path), "status", "--porcelain=v1", "-z"],
        env=world.env,
        capture_output=True,
        check=True,
    ).stdout
    inventory = _inventory(world)
    state = capture_state(world.parent_path, inventory, env=world.env)
    child = world.parent_path.parent / "a5-no-reopen"
    creation = create_worktree_at_anchor(
        world.parent_path, "fork/a5-no-reopen", child, env=world.env
    )
    materialize(
        world.parent_path,
        child,
        inventory=inventory,
        skipped=state.skipped,
        env=world.env,
    )
    real_manifest_entry = content._manifest_entry

    def guarded_manifest_entry(root, relative, *, tracked):
        if root == world.parent_path and relative == "locked.txt":
            raise AssertionError("verification reopened a known skipped path")
        return real_manifest_entry(root, relative, tracked=tracked)

    monkeypatch.setattr(content, "_manifest_entry", guarded_manifest_entry)
    try:
        verify_fork(
            creation,
            parent_status_before=before,
            parent_state_before=state,
            skipped=state.skipped,
            env=world.env,
        )
    finally:
        os.chmod(locked, 0o644)


@pytest.mark.matrix("T-VER-44")
def test_capture_sentinel_uses_the_lstat_that_preceded_the_failed_read(
    repo_scenario, monkeypatch
):
    """A target swap cannot replace the observation-time sentinel."""
    from agent_fork import content

    world = repo_scenario()
    target = world.parent_path / "raced.txt"
    target.write_text("before\n")
    inventory = _inventory(world)
    observed = content.sentinel_for(world.parent_path, "raced.txt")

    def swap_then_fail(path):
        replacement = path.with_name("replacement")
        replacement.write_text("after!\n")
        os.chmod(replacement, 0)
        os.replace(replacement, path)
        raise PermissionError("simulated read race")

    monkeypatch.setattr(content, "_digest", swap_then_fail)
    try:
        state = capture_state(world.parent_path, inventory, env=world.env)
        current = content.sentinel_for(world.parent_path, "raced.txt")
    finally:
        os.chmod(target, 0o644)

    assert state.skipped[0].sentinel == observed
    assert state.skipped[0].sentinel != current


@pytest.mark.matrix("T-VER-45")
def test_same_size_rewrite_with_restored_mtime_is_caught_by_ctime(repo_scenario):
    """Mode, inode, size, and mtime can match while ctime proves mutation."""
    from agent_fork.errors import VerificationError
    from agent_fork.pipeline import ForkRequest, fork

    world = repo_scenario()
    reference = world.parent_path / "reference.txt"
    reference.write_text("secret\n")
    hook = world.parent_path / ".agent-fork/worktree-setup.sh"
    hook.parent.mkdir(parents=True)
    hook.write_text(
        "#!/bin/sh\n"
        'chmod 600 "$REPO_ROOT/locked.txt"\n'
        'printf "change\\n" > "$REPO_ROOT/locked.txt"\n'
        'touch -r "$REPO_ROOT/reference.txt" "$REPO_ROOT/locked.txt"\n'
        'chmod 000 "$REPO_ROOT/locked.txt"\n'
    )
    hook.chmod(0o755)
    subprocess.run(
        ["git", "-C", str(world.parent_path), "add", "."],
        env=world.env,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(world.parent_path), "commit", "-m", "add ctime hook"],
        env=world.env,
        capture_output=True,
        check=True,
    )
    locked = world.parent_path / "locked.txt"
    locked.write_text("secret\n")
    reference_stat = reference.stat()
    os.utime(
        locked,
        ns=(reference_stat.st_atime_ns, reference_stat.st_mtime_ns),
    )
    os.chmod(locked, 0)
    before = locked.lstat()
    request = ForkRequest(
        parent=world.parent_path,
        destination=world.parent_path.parent / "a5-ctime",
        name="a5-ctime",
        branch="fork/a5-ctime",
        agent=None,
        git_version_output="git version 2.43.0",
    )
    try:
        with pytest.raises(VerificationError, match="skipped entry changed"):
            fork(request, env=world.env)
        after = locked.lstat()
    finally:
        os.chmod(locked, 0o644)

    assert (before.st_ino, before.st_mode, before.st_size, before.st_mtime_ns) == (
        after.st_ino,
        after.st_mode,
        after.st_size,
        after.st_mtime_ns,
    )
    assert before.st_ctime_ns != after.st_ctime_ns
