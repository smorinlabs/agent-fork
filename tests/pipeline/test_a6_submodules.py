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


# ---------------------------------------------------------------------------
# Gate-6 regressions
# ---------------------------------------------------------------------------


@pytest.mark.matrix("T-GRD-24")
def test_deleted_submodule_checkout_is_not_refused(repo_scenario):
    """Gate-6 finding 1 — a removed submodule directory is carriable, not refused.

    `--ignore-submodules=dirty` reports a missing submodule directory as a
    deletion, which the first guard intersected with the gitlink set and
    refused. The deletion is not an unrepresentable state: its patch is an
    ordinary `deleted file mode 160000` hunk that applies to the child cleanly,
    so the fork would have succeeded. Only a *modified* gitlink — the checkout
    sitting at a commit the index does not record — is unrepresentable.
    """
    import shutil

    from agent_fork.repository import validate_fork_guards

    world = repo_scenario("plain@main", states=(submodule(dirty="modified"),))
    shutil.rmtree(world.parent_path / "vendor/submodule")
    assert b" D vendor/submodule" in _status(world, world.parent_path)

    validate_fork_guards(
        world.parent_path,
        "fork/a6-deleted",
        world.parent_path.parent / "a6-deleted",
        env=world.env,
    )


@pytest.mark.matrix("T-GRD-25")
def test_unmerged_index_refusal_is_not_masked_by_the_submodule_guard(repo_scenario):
    """Gate-6 finding 3 — pre-existing refusals keep precedence over the new one.

    `gitlink_paths` reads mode-160000 entries from every index stage, so a
    submodule left unmerged by a conflicted merge could reach the guard's diff
    and raise `submodule_unrepresentable`. That code recommends staging or
    `--no-with-state`, and neither clears a conflicted index, so the advertised
    remedy could not work.

    Two changes close it, and the row pins both. `--diff-filter=M` excludes the
    conflicted gitlink, because Git reports an unmerged path as `U`. The guard
    also runs after the mid-operation and unmerged-index refusals, which name
    the state the user actually has — defence in depth, since the filter alone
    is what an unrelated change is most likely to disturb.
    """
    from agent_fork.errors import PreconditionError
    from agent_fork.repository import validate_fork_guards

    world = repo_scenario("plain@main", states=(submodule(),))
    parent = world.parent_path
    sub = parent / "vendor/submodule"
    _git(world, parent, "commit", "-qm", "record the gitlink")
    base = _git(world, sub, "rev-parse", "HEAD").stdout.decode().strip()

    # Advance the SUBMODULE differently on two branches, so the merge conflicts
    # on the gitlink itself and leaves mode-160000 at index stages 1-3. Each side
    # advances from `base`: checking out the parent branch does not rewind the
    # submodule, so without the reset both commits stack and Git fast-forwards
    # the gitlink instead of conflicting.
    _git(world, parent, "checkout", "-q", "-b", "other")
    (sub / "tracked.txt").write_text("other side\n")
    _git(world, sub, "commit", "-qam", "other advance")
    _git(world, parent, "commit", "-qam", "record other advance")

    _git(world, parent, "checkout", "-q", "main")
    _git(world, sub, "checkout", "-q", base)
    (sub / "tracked.txt").write_text("main side\n")
    _git(world, sub, "commit", "-qam", "main advance")
    _git(world, parent, "commit", "-qam", "record main advance")

    merge = _git(world, parent, "merge", "other", check=False)
    assert merge.returncode != 0, "fixture must leave a conflicted merge"
    staged = _git(world, parent, "ls-files", "--stage", "vendor/submodule").stdout
    assert staged.count(b"160000") > 1, "fixture must leave a conflicted gitlink"

    # Two independent defences, both pinned. First, `--diff-filter=M` excludes a
    # conflicted gitlink, which Git reports as unmerged (`U`) rather than
    # modified: drop that filter and this assertion goes red.
    from agent_fork.repository import _unrepresentable_submodules

    assert _unrepresentable_submodules(parent, env=world.env) == []

    with pytest.raises(PreconditionError) as raised:
        validate_fork_guards(
            parent, "fork/a6-unmerged", parent.parent / "a6-unmerged", env=world.env
        )
    # A conflicted merge leaves MERGE_HEAD, so the mid-operation guard is the one
    # that wins — and it names the state the user actually has to resolve.
    assert raised.value.code == "parent_mid_operation"


@pytest.mark.matrix("T-MAT-27")
def test_no_loss_notice_for_a_submodule_with_nothing_to_lose(repo_scenario):
    """Gate-6 finding 4 — the notice names suppressed state, not every submodule.

    The notice listed every indexed gitlink, so a repository whose submodules
    are all at their recorded commits was told its submodule working-tree
    changes were not carried. Nothing was dropped, and a false loss warning is
    worse than none: it trains the reader to ignore a real one.
    """
    from agent_fork.materialize import materialize
    from agent_fork.repository import create_worktree_at_anchor

    world = repo_scenario("plain@main", states=(submodule(),))
    child = world.parent_path.parent / "a6-clean-notice"
    create_worktree_at_anchor(
        world.parent_path, "fork/a6-clean-notice", child, env=world.env
    )
    result = materialize(world.parent_path, child, with_state=True, env=world.env)

    assert result.notices == ()


@pytest.mark.matrix("T-CLI-36")
def test_cli_forwards_the_no_state_mode_to_the_submodule_guard(repo_scenario):
    """Gate-6 finding 5 — prove the wiring, not just the function's parameter.

    T-GRD-23 calls `validate_fork_guards(with_state=False)` directly, so it stays
    green even if neither the CLI nor the pipeline forwards the mode. This row
    runs the real console script, so removing either forwarding turns it red.
    """
    from conftest import run_cli

    world = repo_scenario("plain@main", states=(submodule(dirty="advanced"),))
    refused = run_cli(
        ["fork", "guarded", "--no-agent", "-o", "json"], world.env, world.parent_path
    )
    assert refused.returncode == 5
    assert b"submodule_unrepresentable" in refused.stderr

    allowed = run_cli(
        ["fork", "nostate", "--no-agent", "--no-with-state", "-o", "json"],
        world.env,
        world.parent_path,
    )
    assert allowed.returncode == 0, allowed.stderr.decode()


@pytest.mark.matrix("T-CLI-37")
def test_dry_run_counts_and_notices_match_what_the_fork_will_carry(repo_scenario):
    """Gate-6 finding 2 — the preview must describe the fork that will happen.

    The dry-run counts came from an unfiltered `git diff --name-only` while the
    real inventory filters submodule working-tree state, so a dirty submodule
    was previewed as one unstaged path that the fork then did not carry, with no
    warning. A preview that over-reports is worse than a bare count: it is the
    one place a user checks before committing to the operation.
    """
    import json

    from conftest import run_cli

    world = repo_scenario("plain@main", states=(submodule(dirty="modified"),))
    completed = run_cli(
        ["fork", "preview", "--no-agent", "--dry-run", "-o", "json"],
        world.env,
        world.parent_path,
    )
    assert completed.returncode == 0, completed.stderr.decode()
    document = json.loads(completed.stdout)

    assert document["plan"]["files_to_carry"]["unstaged"] == 0
    assert any("vendor/submodule" in notice for notice in document["notices"])


@pytest.mark.matrix("T-CLI-38")
def test_the_new_error_code_is_published_in_its_own_exit_row():
    """Gate-6 finding 7 — a stable identifier nobody published is not stable.

    README calls error codes compatibility identifiers, so a client may switch
    on them, and `submodule_unrepresentable` was added to the catalog without
    being listed. The assertion reads the exit-code table and requires the code
    in the row for its own configured exit status: a passing mention anywhere
    else in the prose would satisfy a whole-file search while still leaving a
    client unable to map the code to an exit status.

    Scoped to this item's code by the gate-6 routing rule. Whole-catalog parity,
    and the three pre-existing codes it exposed, are routed to their own work.
    """
    from pathlib import Path as _Path

    from agent_fork.errors import ERROR_CATALOG

    code = "submodule_unrepresentable"
    exit_code = ERROR_CATALOG[code].exit_code
    readme = (_Path(__file__).resolve().parents[2] / "README.md").read_text()
    rows = [line for line in readme.splitlines() if line.startswith(f"| {exit_code} |")]
    assert len(rows) == 1, f"expected one exit-{exit_code} row, found {len(rows)}"
    assert f"`{code}`" in rows[0]


@pytest.mark.matrix("T-MAT-28")
def test_a_submodule_both_staged_and_dirty_still_reports_its_loss(repo_scenario):
    """Gate-6 pass-2 — the loss notice compares status codes, not path membership.

    A submodule can be staged at a new commit and dirty inside at the same time.
    Git reports that as `MM`, and the filter reduces it to `M `: the path is
    present on both sides, so a membership comparison sees no difference and
    stays silent — while the staged commit is carried and the inner edit is not.
    """
    from agent_fork.content import suppressed_submodules

    world = repo_scenario("plain@main", states=(submodule(dirty="advanced-staged"),))
    sub = world.parent_path / "vendor/submodule"
    (sub / "tracked.txt").write_text("dirty on top of the staged advance\n")

    assert b"MM vendor/submodule" in _status(world, world.parent_path)
    assert suppressed_submodules(world.parent_path, env=world.env) == [
        "vendor/submodule"
    ]


@pytest.mark.matrix("T-MAT-29")
def test_a_rename_source_record_cannot_mask_a_dirty_submodule(repo_scenario):
    """Gate-6 pass-2 — porcelain rename records carry a second, prefixless path.

    `--porcelain=v1 -z` emits a rename as two records: the entry, then a bare
    source path with no status prefix. Slicing a prefix off that second record
    fabricates a path, and a source of `abcvendor/submodule` yields exactly
    `vendor/submodule` — which then appears on both sides of the comparison and
    hides the real submodule's suppressed state.
    """
    from agent_fork.content import suppressed_submodules

    world = repo_scenario("plain@main", states=(submodule(dirty="modified"),))
    parent = world.parent_path
    decoy = parent / "abcvendor"
    decoy.mkdir()
    (decoy / "submodule").write_text("payload\n")
    _git(world, parent, "add", "abcvendor/submodule")
    _git(world, parent, "commit", "-qm", "add the decoy")
    _git(world, parent, "mv", "abcvendor/submodule", "renamed.txt")

    records = _status(world, parent).split(b"\0")
    assert b"abcvendor/submodule" in records, "fixture must emit a rename source"
    assert suppressed_submodules(parent, env=world.env) == ["vendor/submodule"]


@pytest.mark.matrix("T-GRD-26")
def test_a_deleted_submodule_checkout_forks_end_to_end(repo_scenario):
    """Gate-6 pass-2 — T-GRD-24 proved the guard allows it; this proves it works.

    Passing the guard is not the same as transporting: the deletion still has to
    survive materialization and verification. Driving the console script pins the
    whole path, so a later transport regression cannot hide behind a guard-only
    assertion.
    """
    import shutil

    from conftest import run_cli

    world = repo_scenario("plain@main", states=(submodule(dirty="modified"),))
    shutil.rmtree(world.parent_path / "vendor/submodule")

    completed = run_cli(
        ["fork", "deleted", "--no-agent", "-o", "json"], world.env, world.parent_path
    )
    assert completed.returncode == 0, completed.stderr.decode()
