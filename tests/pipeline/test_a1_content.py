"""G-VER — A1 content-level fork verification.

Design: docs/superpowers/plans/2026-08-16-p02-a1-content-verification.md

Before A1, `agent_fork.verify.verify_fork` compared only
`git status --porcelain=v1 -z` bytes, so content mutations that preserved
porcelain shape passed verification undetected. Each negative fixture below
pins one such vector: it asserts the same-porcelain precondition first —
proving the divergence is invisible to the `exact-copy-status` rung — and
then asserts that the `content-match` or `parent-content` rung fails and
rolls the fork back. Every one of them was RED before the rungs existed;
that state is preserved in the commit that introduced this file.

The exception is T-VER-12, whose vector is closed at the source by
`_apply_patch()`'s pinned `--whitespace=nowarn` rather than caught
downstream, so it is a faithful-transport guard instead.

Positive guards prove the inverse: these forks verify cleanly both before and
after the rungs landed, so the new comparison never produces a false rollback.

Hostile config for the negative fixtures is applied repo-locally on top of
the sealed environment's parent repo (`git config <key> <value>` inside the
scenario's own `parent_path`) — an A1-local fixture technique, not a general
unsealed-environment tier. This mirrors the design doc's gate-1 finding: the
real CLI forwards `os.environ` verbatim, so repo-local config only makes the
repro hermetic; it reaches the same code path ambient global config would.
"""

from __future__ import annotations

import subprocess

import pytest


def _git(world, repo, *args, input_bytes=None, check=True):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        env=world.env,
        input=input_bytes,
        capture_output=True,
        check=check,
    )


def _status(world, repo):
    return _git(world, repo, "status", "--porcelain=v1", "-z").stdout


def _create_and_materialize(world, name, *, with_state=True, with_ignored=False):
    from agent_fork.content import capture_state, collect_inventory
    from agent_fork.materialize import materialize
    from agent_fork.repository import create_worktree_at_anchor

    before = _status(world, world.parent_path)
    world.parent_state_before = capture_state(
        world.parent_path,
        collect_inventory(
            world.parent_path,
            with_state=with_state,
            with_ignored=with_ignored,
            env=world.env,
        ),
        env=world.env,
    )
    child = world.parent_path.parent / f"a1-{name}"
    creation = create_worktree_at_anchor(
        world.parent_path, f"fork/a1-{name}", child, env=world.env
    )
    materialize(
        world.parent_path,
        child,
        with_state=with_state,
        with_ignored=with_ignored,
        env=world.env,
    )
    world.child_path = child
    return creation, before


def _fork(repo_scenario, name, *, topology="plain@branch", states=(), mode="exact"):
    world = repo_scenario(topology, states=states)
    creation, before = _create_and_materialize(
        world,
        name,
        with_state=mode != "no-state",
        with_ignored=mode == "exact+ignored",
    )
    return world, creation, before


def _verify(world, creation, before, *, with_state=True, with_ignored=False):
    from agent_fork.verify import verify_fork

    verify_fork(
        creation,
        with_state=with_state,
        with_ignored=with_ignored,
        parent_status_before=before,
        parent_state_before=getattr(world, "parent_state_before", None),
        env=world.env,
    )


def _assert_rolls_back(
    world, creation, before, *, match, with_state=True, with_ignored=False
):
    """Same-porcelain precondition, then verify fails with `match`, then rollback.

    The precondition proves today's exact-copy-status rung (porcelain bytes,
    not content) already sees no divergence between parent and child — so the
    fixture's divergence is provably invisible to the existing ladder and can
    only be caught by a content-aware rung.
    """
    from agent_fork.errors import VerificationError
    from agent_fork.rollback import rollback_worktree

    assert _status(world, world.parent_path) == _status(world, world.child_path)

    with pytest.raises(VerificationError, match=match):
        _verify(
            world, creation, before, with_state=with_state, with_ignored=with_ignored
        )
    result = rollback_worktree(creation, env=world.env)
    assert result.cleaned
    assert not creation.path.exists()


# ---------------------------------------------------------------------------
# Negative fixtures (RED) — step 1
# ---------------------------------------------------------------------------


@pytest.mark.matrix("T-VER-12")
def test_apply_whitespace_fix_cannot_rewrite_transported_hunk(repo_scenario):
    """(a) — ambient `apply.whitespace = fix` must not alter transported content.

    Config: `git config apply.whitespace fix` (repo-local, on the parent).
    Input:  parent unstaged `tracked.txt` = b"line one   \\nline two\\n" (trailing
            spaces on line one).

    Gate-1's empirical repro: before `_apply_patch()` pinned
    `--whitespace=nowarn`, the child ended up b"line one\\nline two\\n" (spaces
    stripped) while porcelain stayed ` M tracked.txt` on both sides — divergence
    invisible to the exact-copy-status rung, and the fork reported
    `verification: passed`. That RED state is preserved in the commit that
    introduced this file.

    The vector is closed at the source rather than caught downstream, so this is
    a faithful-transport regression guard, not a rollback fixture: remove
    `--whitespace=nowarn` from `_apply_patch()` and this test fails.
    """
    world = repo_scenario()
    _git(world, world.parent_path, "config", "apply.whitespace", "fix")
    (world.parent_path / "tracked.txt").write_bytes(b"line one   \nline two\n")

    creation, before = _create_and_materialize(world, "ws")

    assert (
        world.parent_path / "tracked.txt"
    ).read_bytes() == b"line one   \nline two\n"
    assert (world.child_path / "tracked.txt").read_bytes() == b"line one   \nline two\n"
    assert _status(world, world.parent_path) == _status(world, world.child_path)

    _verify(world, creation, before)


@pytest.mark.matrix("T-VER-13")
def test_negative_idempotent_clean_filter_diverges_raw_bytes(repo_scenario):
    """(b) — an idempotent clean filter masks a working-tree raw-byte divergence on
    a staged path: `_apply_patch()`'s cached `apply --index` writes the patch's
    already-clean plus-lines directly into the child's working tree, bypassing the
    smudge filter that a normal checkout would run. Since the filter is idempotent
    (`clean(clean(x)) == clean(x)`), `git status` never re-flags the child dirty —
    unlike a non-idempotent filter (T-VER-10's `A ` -> `AM`), which the existing
    porcelain-based rung already catches.

    Config: `.gitattributes` = "staged.txt filter=trimws\\n" (committed);
            `filter.trimws.clean` = `sed 's/[ \\t]*$//'` (strips trailing
            whitespace — idempotent); `filter.trimws.smudge` = `cat`.
    Input:  parent stages `staged.txt` = b"hello   \\nworld\\t\\t\\n".
    Empirically: parent worktree keeps the raw b"hello   \\nworld\\t\\t\\n"; child
    worktree ends up b"hello\\nworld\\t\\t\\n" (clean already applied, no smudge
    back) while both index blobs match and porcelain stays `A  staged.txt` on
    both sides. RED until step 4 lands the working-tree manifest rung.
    """
    world = repo_scenario()
    (world.parent_path / ".gitattributes").write_text("staged.txt filter=trimws\n")
    _git(
        world, world.parent_path, "config", "filter.trimws.clean", r"sed 's/[ \t]*$//'"
    )
    _git(world, world.parent_path, "config", "filter.trimws.smudge", "cat")
    _git(world, world.parent_path, "add", ".gitattributes")
    _git(world, world.parent_path, "commit", "-m", "configure filter")
    (world.parent_path / "staged.txt").write_bytes(b"hello   \nworld\t\t\n")
    _git(world, world.parent_path, "add", "staged.txt")

    creation, before = _create_and_materialize(world, "filter")

    parent_bytes = (world.parent_path / "staged.txt").read_bytes()
    child_bytes = (world.child_path / "staged.txt").read_bytes()
    assert parent_bytes == b"hello   \nworld\t\t\n"
    assert child_bytes != parent_bytes

    _assert_rolls_back(world, creation, before, match="content-match")


@pytest.mark.matrix("T-VER-14")
def test_negative_autocrlf_round_trip_diverges_mixed_line_endings(repo_scenario):
    """(c) — `core.autocrlf=true` normalizes a mixed-line-ending unstaged edit to
    uniform CRLF on re-apply, diverging from the parent's original mixed bytes.

    Config: `git config core.autocrlf true` (repo-local, shared by parent+child
            since they share the same repository).
    Input:  parent unstaged `tracked.txt` = b"line one\\r\\nline two\\nline
            three\\r\\n" (CRLF, LF, CRLF).
    Empirically: the diff `git diff` computes under autocrlf normalizes the
    patch text to LF-only; `git apply` (honoring the shared `core.autocrlf`)
    converts every LF back to CRLF on write, uniformly — losing the parent's
    original bare-LF middle line. Child ends up b"line one\\r\\nline
    two\\r\\nline three\\r\\n"; porcelain stays ` M tracked.txt` on both sides.
    RED until step 4 lands the working-tree manifest rung.
    """
    world = repo_scenario()
    _git(world, world.parent_path, "config", "core.autocrlf", "true")
    mixed = b"line one\r\nline two\nline three\r\n"
    (world.parent_path / "tracked.txt").write_bytes(mixed)

    creation, before = _create_and_materialize(world, "crlf")

    assert (world.parent_path / "tracked.txt").read_bytes() == mixed
    assert (world.child_path / "tracked.txt").read_bytes() != mixed

    _assert_rolls_back(world, creation, before, match="content-match")


@pytest.mark.matrix("T-VER-15")
def test_negative_staged_index_blob_diverges_post_transport(repo_scenario):
    """(d) — the child's staged index blob diverges from the parent's after
    transport while porcelain stays `A ` on both sides (index/mode divergence,
    not caught by the porcelain-only ladder). Simulates the shape of failure a
    materialize defect could produce; verify must catch it independently of
    materialize's own correctness.

    Input: parent stages `staged.txt` = b"staged add\\n" (via the `staged(add=...)`
           fixture helper). After transport, the child's working file is
           overwritten with b"different content\\n" and re-`git add`-ed, so the
           child's own index stays self-consistent (still `A `) but now points
           at a different blob than the parent's.
    """
    from conftest import staged

    world, creation, before = _fork(
        repo_scenario, "staged-idx", states=(staged(add="staged.txt"),)
    )

    parent_blob = _git(world, world.parent_path, "rev-parse", ":staged.txt").stdout
    (world.child_path / "staged.txt").write_bytes(b"different content\n")
    _git(world, world.child_path, "add", "staged.txt")
    child_blob = _git(world, world.child_path, "rev-parse", ":staged.txt").stdout
    assert parent_blob != child_blob

    _assert_rolls_back(world, creation, before, match="content-match")


@pytest.mark.matrix("T-VER-16")
def test_negative_parent_working_tree_edit_after_materialize(repo_scenario):
    """(e) — the parent's working tree is edited after materialize has already
    captured the transported bytes (a race window between transport and verify),
    status-preserving throughout: the edit keeps the same tracked file in the
    same unstaged-modified shape, so both the existing `parent-untouched` and
    `exact-copy-status` rungs (porcelain-only) see no difference.

    Input: parent unstaged `tracked.txt` = b"unstaged\\n" (the `unstaged()`
           fixture default) at materialize time; edited again to
           b"unstaged two\\n" afterward, before verify runs.
    RED until step 4 lands parent-manifest bracketing (parent-before vs
    parent-after, on top of the existing porcelain-only parent-untouched check).
    """
    from conftest import unstaged

    world, creation, before = _fork(
        repo_scenario, "parent-edit", states=(unstaged("tracked.txt"),)
    )

    assert (world.child_path / "tracked.txt").read_bytes() == b"unstaged\n"
    (world.parent_path / "tracked.txt").write_bytes(b"unstaged two\n")

    assert (
        _status(world, world.parent_path) == before
    )  # parent-untouched (porcelain) still passes

    _assert_rolls_back(world, creation, before, match="parent-content")


@pytest.mark.matrix("T-VER-17")
def test_negative_parent_index_swap_after_materialize_mm_path(repo_scenario):
    """(f) — the parent's staged INDEX blob is swapped (re-staged) after materialize
    on an `MM` path, then the working tree is restored to its original unstaged
    content — so porcelain stays `MM tracked.txt` throughout even though the
    parent's index no longer matches what was transported into the child.

    Input: parent staged `tracked.txt` = b"staged\\n" (the `staged(modify=...)`
           default), unstaged on top = b"unstaged\\n" (the `unstaged()` default),
           giving `MM`. After transport: parent's `tracked.txt` is rewritten to
           b"reindexed\\n" and re-`git add`-ed (index blob A -> B), then rewritten
           back to b"unstaged\\n" (restoring the pre-swap working tree exactly).
    RED until step 4 lands parent-index bracketing (parent-before vs
    parent-after on `git ls-files --stage`).
    """
    from conftest import staged, unstaged

    world, creation, before = _fork(
        repo_scenario,
        "parent-idx-swap",
        states=(staged(modify="tracked.txt"), unstaged("tracked.txt")),
    )
    assert before == b"MM tracked.txt\0"
    assert (world.child_path / "tracked.txt").read_bytes() == b"unstaged\n"

    (world.parent_path / "tracked.txt").write_bytes(b"reindexed\n")
    _git(world, world.parent_path, "add", "tracked.txt")
    (world.parent_path / "tracked.txt").write_bytes(b"unstaged\n")

    assert (
        _status(world, world.parent_path) == before
    )  # parent-untouched (porcelain) still passes

    _assert_rolls_back(world, creation, before, match="parent-content")


@pytest.mark.matrix("T-VER-18")
def test_negative_manifest_existence_type_untracked_symlink_becomes_file(
    repo_scenario,
):
    """(g1) — manifest dimension: existence/type. An untracked symlink is
    replaced by an untracked regular file at the same path in the child after
    transport. Untracked paths show as `?? path` in porcelain regardless of
    type, so the divergence is invisible to the existing ladder.

    Input: parent untracked symlink `loose` -> `tracked.txt` (the
           `untracked(symlink=...)` fixture). After transport, the child's
           `loose` is deleted and replaced with a regular file containing
           b"not a symlink\\n".
    """
    from conftest import untracked

    world, creation, before = _fork(
        repo_scenario,
        "manifest-type",
        states=(untracked(symlink="loose", target="tracked.txt"),),
    )
    assert (world.child_path / "loose").is_symlink()
    (world.child_path / "loose").unlink()
    (world.child_path / "loose").write_bytes(b"not a symlink\n")
    assert not (world.child_path / "loose").is_symlink()

    _assert_rolls_back(world, creation, before, match="content-match")


@pytest.mark.matrix("T-VER-19")
def test_negative_manifest_mode_untracked_file_mode_diverges(repo_scenario):
    """(g2) — manifest dimension: mode. An untracked file's POSIX mode is changed
    in the child after transport. Untracked-file porcelain never reflects mode,
    so the divergence is invisible to the existing ladder.

    Input: parent untracked `loose.sh` (mode 0o644, the `untracked()` default).
           After transport, the child's `loose.sh` mode is changed to 0o755.
    """
    import stat

    from conftest import untracked

    world, creation, before = _fork(
        repo_scenario, "manifest-mode", states=(untracked("loose.sh"),)
    )
    parent_mode = stat.S_IMODE((world.parent_path / "loose.sh").stat().st_mode)
    child_mode_before = stat.S_IMODE((world.child_path / "loose.sh").stat().st_mode)
    assert parent_mode == child_mode_before
    (world.child_path / "loose.sh").chmod(0o755)
    assert stat.S_IMODE((world.child_path / "loose.sh").stat().st_mode) != parent_mode

    _assert_rolls_back(world, creation, before, match="content-match")


@pytest.mark.matrix("T-VER-20")
def test_negative_manifest_symlink_target_untracked_symlink_target_diverges(
    repo_scenario,
):
    """(g3) — manifest dimension: symlink target. An untracked symlink's target is
    changed in the child after transport, path unchanged. Untracked-symlink
    porcelain never reflects the target, so the divergence is invisible to the
    existing ladder.

    Input: parent untracked symlink `loose-link` -> `tracked.txt` (the
           `untracked(symlink=...)` fixture). After transport, the child's
           `loose-link` is repointed to `elsewhere.txt`.
    """
    import os

    from conftest import untracked

    world, creation, before = _fork(
        repo_scenario,
        "manifest-target",
        states=(untracked(symlink="loose-link", target="tracked.txt"),),
    )
    assert os.readlink(world.child_path / "loose-link") == "tracked.txt"
    (world.child_path / "loose-link").unlink()
    (world.child_path / "loose-link").symlink_to("elsewhere.txt")
    assert os.readlink(world.child_path / "loose-link") == "elsewhere.txt"

    _assert_rolls_back(world, creation, before, match="content-match")


@pytest.mark.matrix("T-VER-21")
def test_negative_manifest_raw_bytes_untracked_file_content_diverges(repo_scenario):
    """(g4) — manifest dimension: raw bytes. An untracked file's content is
    changed in the child after transport, path/type/mode unchanged.
    Untracked-file porcelain never reflects content, so the divergence is
    invisible to the existing ladder.

    Input: parent untracked `loose.txt` = b"untracked\\n" (the `untracked()`
           default). After transport, the child's `loose.txt` is overwritten
           with b"tampered bytes\\n".
    """
    from conftest import untracked

    world, creation, before = _fork(
        repo_scenario, "manifest-bytes", states=(untracked("loose.txt"),)
    )
    assert (world.child_path / "loose.txt").read_bytes() == b"untracked\n"
    (world.child_path / "loose.txt").write_bytes(b"tampered bytes\n")

    _assert_rolls_back(world, creation, before, match="content-match")


# ---------------------------------------------------------------------------
# Positive guards (false-rollback protection) — step 2
# ---------------------------------------------------------------------------


@pytest.mark.matrix("T-VER-22")
def test_positive_symmetric_autocrlf_conversion_verifies(repo_scenario):
    """Symmetric conversion guard — `core.autocrlf=true` applied identically to
    parent and child (they share one repository/config) on a uniform-CRLF
    (non-mixed) unstaged edit transports byte-identical. Contrast with T-VER-14's
    mixed-line-ending negative fixture, which the same config does NOT preserve.

    Input: parent unstaged `tracked.txt` = b"line one\\r\\nline two\\r\\n"
    (uniform CRLF). Must keep verifying cleanly after step 4 lands.
    """
    world = repo_scenario()
    _git(world, world.parent_path, "config", "core.autocrlf", "true")
    uniform = b"line one\r\nline two\r\n"
    (world.parent_path / "tracked.txt").write_bytes(uniform)

    creation, before = _create_and_materialize(world, "symm-crlf")

    assert (world.child_path / "tracked.txt").read_bytes() == uniform
    _verify(world, creation, before)


@pytest.mark.matrix("T-VER-23")
def test_positive_staged_and_unstaged_same_path_verifies(repo_scenario):
    """Positive guard — staged+unstaged edits on the same path (`MM`) transport
    correctly and verify cleanly. Must keep verifying after step 4 lands.
    """
    from conftest import staged, unstaged

    world, creation, before = _fork(
        repo_scenario,
        "mm-guard",
        states=(staged(modify="tracked.txt"), unstaged("tracked.txt")),
    )
    _verify(world, creation, before)


@pytest.mark.matrix("T-VER-24")
def test_positive_intent_to_add_verifies(repo_scenario):
    """Positive guard — an intent-to-add entry transports correctly and verifies
    cleanly. Must keep verifying after step 4 lands.
    """
    from conftest import intent_to_add

    world, creation, before = _fork(
        repo_scenario, "ita-guard", states=(intent_to_add("intent.txt"),)
    )
    _verify(world, creation, before)


@pytest.mark.matrix("T-VER-25")
def test_positive_rename_verifies(repo_scenario):
    """Positive guard — a renamed-and-edited file transports correctly and
    verifies cleanly. Must keep verifying after step 4 lands.
    """
    from conftest import rename_edit

    world, creation, before = _fork(
        repo_scenario, "rename-guard", states=(rename_edit("old-name.txt"),)
    )
    _verify(world, creation, before)


@pytest.mark.matrix("T-VER-26")
def test_positive_deletion_verifies(repo_scenario):
    """Positive guard — an unstaged deletion of a tracked file transports
    correctly and verifies cleanly. Must keep verifying after step 4 lands.

    conftest's StateSpec vocabulary has no dedicated "deletion" helper, so this
    is built directly: the seeded `tracked.txt` is removed from the parent
    worktree without staging the removal (` D tracked.txt`).
    """
    world = repo_scenario()
    (world.parent_path / "tracked.txt").unlink()

    creation, before = _create_and_materialize(world, "deletion-guard")

    assert before == b" D tracked.txt\0"
    assert not (world.child_path / "tracked.txt").exists()
    _verify(world, creation, before)


@pytest.mark.matrix("T-VER-27")
def test_positive_untracked_verifies(repo_scenario):
    """Positive guard — an untracked file transports correctly and verifies
    cleanly. Must keep verifying after step 4 lands.
    """
    from conftest import untracked

    world, creation, before = _fork(
        repo_scenario, "untracked-guard", states=(untracked("loose.txt"),)
    )
    _verify(world, creation, before)


@pytest.mark.matrix("T-VER-28")
def test_positive_ignored_under_with_ignored_verifies(repo_scenario):
    """Positive guard — an ignored file transports correctly under
    `--with-ignored` (mode=exact+ignored) and verifies cleanly with
    `with_ignored=True`. Must keep verifying after step 4 lands.
    """
    from conftest import ignored

    world, creation, before = _fork(
        repo_scenario,
        "ignored-guard",
        states=(ignored("secret.env"),),
        mode="exact+ignored",
    )
    _verify(world, creation, before, with_ignored=True)


@pytest.mark.matrix("T-VER-29")
def test_positive_exec_bit_verifies(repo_scenario):
    """Positive guard — an exec-bit-only change transports correctly and
    verifies cleanly. Must keep verifying after step 4 lands.
    """
    from conftest import exec_bit

    world, creation, before = _fork(
        repo_scenario, "exec-bit-guard", states=(exec_bit("script.sh"),)
    )
    _verify(world, creation, before)


@pytest.mark.matrix("T-VER-30")
def test_positive_clean_submodule_gitlink_verifies(repo_scenario):
    """Positive guard — a clean submodule gitlink (index-only, mode-160000)
    verifies without traversing its working tree. Must keep verifying after
    step 4 lands (the future manifest rung must prune gitlink dirs the same
    way the test-side manifest oracle already does).
    """
    from conftest import submodule

    world, creation, before = _fork(
        repo_scenario, "gitlink-guard", states=(submodule("vendor/module"),)
    )
    _verify(world, creation, before)


# ---------------------------------------------------------------------------
# Cost gate — step 5
# ---------------------------------------------------------------------------


@pytest.mark.matrix("T-VER-31")
def test_verification_hashes_each_carried_file_once_per_snapshot(
    repo_scenario, monkeypatch
):
    """Cost gate — content verification stays proportional to the carried set.

    A wall-clock bound would be flaky under CI load, so the contract pinned here
    is structural: one `verify_fork` takes exactly two content snapshots (the
    parent bracket and the child), and each snapshot digests every carried
    regular file exactly once. A regression that re-walks the inventory, adds a
    snapshot, or rehashes per comparison fails this test rather than quietly
    multiplying the cost of every fork.

    Measured for reference on a 201-entry carried set: 1.08s representative,
    1.89s with --with-ignored over 2000 ignored files (REQ-40 budget ~2s).
    """
    from agent_fork import content
    from conftest import untracked

    states = tuple(untracked(f"loose{index}.txt") for index in range(5))
    world, creation, before = _fork(repo_scenario, "cost", states=states)

    digested: list[str] = []
    snapshots: list[int] = []
    real_digest = content._digest
    real_capture = content.capture_state

    def counting_digest(path):
        digested.append(str(path))
        return real_digest(path)

    def counting_capture(root, inventory, **kwargs):
        snapshots.append(1)
        return real_capture(root, inventory, **kwargs)

    monkeypatch.setattr(content, "_digest", counting_digest)
    monkeypatch.setattr("agent_fork.verify.capture_state", counting_capture)

    _verify(world, creation, before)

    assert len(snapshots) == 2
    assert len(digested) == len(set(digested)), (
        "a file was digested more than once during one verification"
    )
    carried = len(world.parent_state_before.paths)
    assert carried >= len(states)
    assert len(digested) <= 2 * carried


@pytest.mark.matrix("T-VER-32")
def test_negative_child_carries_a_path_the_parent_does_not(repo_scenario):
    """(h) — a path present in the child but not the parent must be caught.

    Config: `status.showUntrackedFiles=no` on both worktrees, which suppresses
    untracked paths from `git status` entirely, so the porcelain rung is blind
    to the extra file. `ls-files --others` is unaffected by that setting, so the
    inventory still sees it.

    This pins the child-membership comparison specifically. An earlier
    implementation handed the parent's own path list to the child snapshot, so
    the missing/extra comparison compared a list against itself and could never
    fire; the child now collects its own inventory.
    """
    world, creation, before = _fork(repo_scenario, "child-extra")
    _git(world, world.parent_path, "config", "status.showUntrackedFiles", "no")
    _git(world, world.child_path, "config", "status.showUntrackedFiles", "no")
    (world.child_path / "smuggled.txt").write_bytes(b"not from the parent\n")

    _assert_rolls_back(world, creation, before, match="content-match")
