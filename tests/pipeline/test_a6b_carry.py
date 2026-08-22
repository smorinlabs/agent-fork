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


@pytest.mark.matrix("T-MAT-49")
def test_carry_leaves_no_submodules_carried_when_none_exist(repo_scenario):
    world = repo_scenario("plain@main")
    child = world.parent_path.parent / "a6b-none"
    result = _carry(world, child)
    assert result.carried == ()
    assert result.skipped == ()


@pytest.mark.matrix("T-MAT-50")
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


@pytest.mark.matrix("T-MAT-51")
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


@pytest.mark.matrix("T-MAT-52")
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


@pytest.mark.matrix("T-MAT-53")
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


@pytest.mark.matrix("T-MAT-54")
def test_carry_works_offline_with_a_renamed_submodule(repo_scenario):
    """Cell `j` — config name differs from path; the override must be name-keyed."""
    world = repo_scenario(
        "plain@main", states=(submodule(name="libfoo", committed=True),)
    )
    child = world.parent_path.parent / "a6b-renamed"
    result = _carry(world, child)
    assert "vendor/submodule" in result.carried
    assert (child / "vendor/submodule/.git").exists()


@pytest.mark.matrix("T-MAT-55")
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


@pytest.mark.matrix("T-MAT-56")
def test_carry_leaves_a_parent_cold_submodule_cold_in_the_child(repo_scenario):
    """Cell `g` — a fork must not initialize what the parent itself did not."""
    world = repo_scenario("plain@main", states=(submodule(dirty="uninit"),))
    child = world.parent_path.parent / "a6b-uninit"
    result = _carry(world, child)
    assert "vendor/submodule" in result.skipped
    assert result.carried == ()
    assert not (child / "vendor/submodule/.git").exists()


@pytest.mark.matrix("T-MAT-57")
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


@pytest.mark.matrix("T-MAT-58")
def test_carry_recurses_into_a_nested_submodule(repo_scenario):
    """Cell `h` — a submodule inside a submodule is carried too, not left cold."""
    world = repo_scenario(
        "plain@main", states=(submodule(nested=True, committed=True),)
    )
    child = world.parent_path.parent / "a6b-nested"
    result = _carry(world, child)
    assert "vendor/submodule" in result.carried
    assert (child / "vendor/submodule/inner/.git").exists()


@pytest.mark.matrix("T-MAT-59")
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


@pytest.mark.matrix("T-MAT-60")
def test_carry_notices_name_the_configuration_fidelity_limit(repo_scenario):
    """Recipe step 3 — only remote.origin.url is restored; the notice must say so."""
    world = repo_scenario("plain@main", states=(submodule(committed=True),))
    child = world.parent_path.parent / "a6b-notice"
    result = _carry(world, child)
    assert any("remote.origin.url" in notice for notice in result.notices)


@pytest.mark.matrix("T-MAT-61")
def test_carry_transports_untracked_content_inside_the_submodule(repo_scenario):
    """Cell `b` — untracked-only dirt inside a submodule is carried too."""
    world = repo_scenario("plain@main", states=(submodule(dirty="untracked"),))
    child = world.parent_path.parent / "a6b-untracked"
    result = _carry(world, child)
    assert "vendor/submodule" in result.carried
    inner = _git(world, child / "vendor/submodule", "status", "--porcelain=v1").stdout
    assert inner == b"?? loose.txt\n"
    assert (child / "vendor/submodule/loose.txt").read_text() == (
        "untracked inside the submodule\n"
    )


@pytest.mark.matrix("T-MAT-62")
def test_carry_transports_a_dirty_submodule_alongside_an_ordinary_dirty_file(
    repo_scenario,
):
    """Cell `f` — submodule dirt and ordinary file dirt both carry; neither
    masks the other. The plain file transports through the ordinary
    materialize() path, the submodule through carry_submodules() — proving
    the two mechanisms genuinely coexist rather than one starving the other.
    """
    from conftest import unstaged

    world = repo_scenario(
        "plain@main",
        states=(submodule(dirty="modified"), unstaged("carried.txt")),
    )
    child = world.parent_path.parent / "a6b-mixed"
    from agent_fork.content import collect_inventory
    from agent_fork.materialize import materialize
    from agent_fork.repository import create_worktree_at_anchor

    inventory = collect_inventory(
        world.parent_path, with_state=True, with_ignored=False, env=world.env
    )
    creation = create_worktree_at_anchor(
        world.parent_path, "fork/a6b-mixed", child, env=world.env
    )
    materialize(
        world.parent_path,
        creation.path,
        with_state=True,
        inventory=inventory,
        env=world.env,
    )
    from agent_fork.submodules import carry_submodules, snapshot_submodules

    plans = snapshot_submodules(world.parent_path, with_state=True, env=world.env)
    result = carry_submodules(
        world.parent_path, creation.path, plans, with_state=True, env=world.env
    )
    assert "vendor/submodule" in result.carried
    assert (child / "carried.txt").read_text() == "unstaged\n"
    inner = _git(world, child / "vendor/submodule", "status", "--porcelain=v1").stdout
    assert inner == b" M tracked.txt\n"


@pytest.mark.matrix("T-MAT-63")
def test_carry_offline_override_engages_for_a_relative_gitmodules_url(repo_scenario):
    """The offline URL override must engage at the carry layer too, not just
    the snapshot layer (T-MAT-47) — a relative URL resolved to an absolute
    value is what the recipe's init step actually consumes.
    """
    world = repo_scenario("plain@main", states=(submodule(url_kind="relative"),))
    child = world.parent_path.parent / "a6b-relative-carry"
    result = _carry(world, child)
    assert "vendor/submodule" in result.carried
    assert (child / "vendor/submodule/.git").exists()


@pytest.mark.matrix("T-MAT-64")
def test_carry_recurses_a_dirty_change_at_depth_two(repo_scenario):
    """Coverage audit — step 1's sixteen-cell commitment names "depth-2 dirt"
    as its own axis, distinct from cell `h` (a clean nested submodule, left
    cold at depth 1). Here the INNER submodule itself has a dirty tracked
    file, so the recursion in `_carry_one` must reach two levels deep, not
    just carry the outer submodule and stop.
    """
    world = repo_scenario(
        "plain@main", states=(submodule(nested=True, committed=True),)
    )
    outer = world.parent_path / "vendor/submodule"
    (outer / "inner" / "tracked.txt").write_text("dirty at depth two\n")

    child = world.parent_path.parent / "a6b-depth2"
    result = _carry(world, child)
    assert "vendor/submodule" in result.carried

    child_inner = child / "vendor/submodule" / "inner"
    assert child_inner.exists()
    inner_status = _git(world, child_inner, "status", "--porcelain=v1").stdout
    assert inner_status == b" M tracked.txt\n"
    assert (child_inner / "tracked.txt").read_text() == "dirty at depth two\n"
    assert _status(world, child) == _status(world, world.parent_path)


@pytest.mark.matrix("T-MAT-66")
def test_carry_works_offline_with_a_space_in_the_submodule_name(repo_scenario):
    """Gate-6 finding 5 -- `_gitmodules_names`'s naive `partition(" ")` broke on
    a config name containing its own space (a legal, realistic Git submodule
    name): `git config --get-regexp`'s output is `<key> <value>`
    space-separated, but the KEY itself also contains the name's embedded
    space, so a plain single-space split mis-parses the key/value boundary.
    The parser must use `--null` (`key\\nvalue\\0`) instead. Combined with a
    remote-unreachable URL, same as T-MAT-55, to prove the offline override
    actually engages under the fixed parser rather than being masked.
    """
    world = repo_scenario(
        "plain@main",
        states=(submodule(name="evil name", url_kind="remote-unreachable"),),
    )
    child = world.parent_path.parent / "a6b-spaced-name"
    result = _carry(world, child)
    assert "vendor/submodule" in result.carried
    assert (child / "vendor/submodule/.git").exists()


@pytest.mark.matrix("T-MAT-67")
def test_carry_skips_a_submodule_whose_name_contains_equals(repo_scenario):
    """Gate-6 finding 5 -- a config name containing `=` cannot be expressed as
    a command-scoped `-c submodule.<name>.url=...` pin: git's `-c key=value`
    syntax has no way to distinguish the name's own `=` from the pin's
    separator. Rather than silently apply a broken pin (which would fall
    through to Git contacting the real, uncontrolled `.gitmodules` remote --
    exactly the offline guarantee this recipe exists to provide), the
    submodule must be skipped, with a notice naming why. Remote-unreachable
    proves this: if carry attempted the remote fallback, it would hang or
    fail against 192.0.2.1 rather than skip cleanly.
    """
    world = repo_scenario(
        "plain@main",
        states=(submodule(name="eq=name", url_kind="remote-unreachable"),),
    )
    child = world.parent_path.parent / "a6b-eq-name"
    result = _carry(world, child)
    assert "vendor/submodule" in result.skipped
    assert "vendor/submodule" not in result.carried
    assert any(
        "vendor/submodule" in notice and "=" in notice for notice in result.notices
    )
    assert not (child / "vendor/submodule/.git").exists()


@pytest.mark.matrix("T-MAT-70")
def test_carried_notice_escapes_a_hostile_submodule_name(repo_scenario):
    """Gate-6 round 2 finding 10 -- round-1 finding 6 (terminal injection,
    absorbed in commit bf81d94) added `escape_terminal_text()` around both
    `plan.path` and `plan.name` in the "submodule carried" notice, but no
    test actually proved the escaping happens: T-MAT-56 checks only skip
    state and T-MAT-60 checks only the remote-fidelity wording, neither
    with a hostile string in play. A submodule config name containing an
    ANSI erase-screen sequence (the same hostile shape `test_a1_content.py`
    uses for a filename, minus the embedded newline that hostile shape also
    carries -- `git submodule add --name` rejects a literal newline in the
    name outright, confirmed empirically) must not reach the notice
    literally -- it must come back escaped and terminal-safe.
    """
    hostile = "bad\x1b[2Jname"
    world = repo_scenario(
        "plain@main", states=(submodule(name=hostile, committed=True),)
    )
    child = world.parent_path.parent / "a6b-hostile-name"
    result = _carry(world, child)

    assert "vendor/submodule" in result.carried
    carried_notice = next(
        notice for notice in result.notices if notice.startswith("submodule carried")
    )
    assert "\x1b" not in carried_notice
    assert "\\x1b" in carried_notice


@pytest.mark.matrix("T-MAT-68")
def test_carry_removes_the_synthetic_origin_when_the_parent_submodule_has_none(
    repo_scenario,
):
    """Gate-6 round 2 finding 7. `submodule update --init` always writes a
    persistent `remote.origin.url` into the child submodule's own config,
    pointed at whatever the init-scoped `-c submodule.<name>.url` pin named
    (the parent's own local checkout path) -- confirmed empirically: even
    with the pin only process-scoped, `git config --get remote.origin.url`
    inside the freshly-initialized child submodule returns that path,
    persisted to disk. When the parent's own submodule has NO
    `remote.origin.url` at all (`plan.remote_url is None`), step 3's
    restore is a no-op (`if plan.remote_url is not None`), so this synthetic,
    machine-local origin silently survives in the child -- an origin the
    parent never had, pointing at a path that only exists on this machine.
    The carried child must match the parent: no origin remote at all.
    """
    world = repo_scenario("plain@main", states=(submodule(committed=True),))
    outer = world.parent_path / "vendor/submodule"
    _git(world, outer, "config", "--unset", "remote.origin.url")

    child = world.parent_path.parent / "a6b-no-origin"
    _carry(world, child)

    remotes = _git(world, child / "vendor/submodule", "remote").stdout.decode().split()
    assert remotes == []


@pytest.mark.matrix("T-MAT-69")
def test_nested_cold_notice_is_qualified_with_its_outer_path(repo_scenario):
    """Gate-6 round 2 finding 8. `carry_submodules` qualifies nested `carried`
    and `skipped` PATHS with their outer prefix (``outer/inner``, gate-6
    finding 7's own fix for rung 6), but nested NOTICE TEXT is appended
    unchanged (`notices.extend(nested_notices)`), still naming only the bare
    nested path (``inner``). Two different outer submodules that each happen
    to contain a nested submodule named the same thing would produce two
    identical, unattributable "left cold: inner" notices with no way to
    tell which outer's `inner` either one refers to.
    """
    world = repo_scenario(
        "plain@main", states=(submodule(nested=True, committed=True),)
    )
    outer = world.parent_path / "vendor/submodule"
    _git(world, outer, "submodule", "deinit", "-f", "--", "inner")

    child = world.parent_path.parent / "a6b-nested-cold-notice"
    result = _carry(world, child)

    assert any("vendor/submodule/inner" in notice for notice in result.notices), (
        result.notices
    )


@pytest.mark.matrix("T-VER-53")
def test_rung_7_catches_the_parent_submodule_cleanly_moving_head(repo_scenario):
    """Gate-6 finding 1 -- rung 7 ("recursive parent-untouched") compared only
    dirty-inventory-derived content, never the parent submodule's own HEAD.
    A clean commit-to-commit move (R -> S) between snapshot and verify leaves
    the inventory empty at both R and S -- content comparison alone sees
    nothing -- so without a HEAD check this passes even though the parent
    changed. Mirrors rung 2's child HEAD-identity check, one side over.
    """
    from agent_fork.submodules import snapshot_submodules, verify_submodules

    world = repo_scenario("plain@main", states=(submodule(committed=True),))
    outer = world.parent_path / "vendor/submodule"
    plans = snapshot_submodules(world.parent_path, with_state=True, env=world.env)
    assert plans[0].head is not None

    # The race: the parent submodule cleanly moves to a NEW commit after the
    # snapshot was taken -- not a dirty change, a clean checkout elsewhere.
    (outer / "tracked.txt").write_text("moved to a new commit\n")
    _git(world, outer, "commit", "-qam", "advance cleanly")
    new_head = _git(world, outer, "rev-parse", "HEAD").stdout.decode().strip()
    assert new_head != plans[0].head

    child = world.parent_path.parent / "a6b-parent-head-race"
    from agent_fork.repository import create_worktree_at_anchor
    from agent_fork.submodules import carry_submodules

    create_worktree_at_anchor(
        world.parent_path, "fork/a6b-parent-head-race", child, env=world.env
    )
    carry_submodules(world.parent_path, child, plans, with_state=True, env=world.env)

    differences = verify_submodules(world.parent_path, child, plans, env=world.env)
    assert differences, (
        "the parent submodule's HEAD moved between snapshot and verify; "
        "rung 7 must catch it even though the working tree stayed clean "
        "at both commits"
    )


@pytest.mark.matrix("T-VER-54")
def test_rung_6_detects_a_skipped_nested_submodule_via_its_qualified_path(
    repo_scenario,
):
    """Gate-6 finding 7 -- carry_submodules qualifies a nested skipped path
    with its outer prefix (`outer/inner`, T-MAT-58's own recursion pattern),
    but verify_submodules compared the bare, unqualified `plan.path`
    ("inner") against that globally-prefixed tuple at every recursion depth.
    Rung 6 could never detect a skipped NESTED plan as a result -- only a
    skip at the top level, where no prefix exists to mismatch. Direct
    injection, per the design's own fault-injection style: fabricate exactly
    the `skipped` shape carry_submodules would have produced.
    """
    from agent_fork.submodules import snapshot_submodules, verify_submodules

    world = repo_scenario(
        "plain@main", states=(submodule(nested=True, committed=True),)
    )
    plans = snapshot_submodules(world.parent_path, with_state=True, env=world.env)
    inner_plan = plans[0].nested[0]
    assert inner_plan.path == "inner"

    differences = verify_submodules(
        world.parent_path,
        world.parent_path,  # child is irrelevant; rung 6 short-circuits
        plans,
        skipped=("vendor/submodule/inner",),
        env=world.env,
    )
    skip_findings = [d for d in differences if d.check == "submodule-skipped"]
    assert skip_findings, (
        "rung 6 must catch a skipped NESTED plan, not just a top-level one"
    )
    assert skip_findings[0].path == "vendor/submodule/inner", (
        "the difference itself must carry the qualified path -- a bare "
        "'inner' is ambiguous when more than one submodule could have one"
    )


@pytest.mark.matrix("T-VER-49")
def test_a_mixed_time_race_is_caught_by_verification_not_silently_carried(
    repo_scenario,
):
    """Gate-4 pass 1 finding 3 — the whole reason the snapshot is frozen
    before the worktree exists. Mutate the submodule's dirty content AFTER
    the snapshot is taken but BEFORE carry runs: the snapshot's stale bytes
    predict one thing, the live filesystem contains another, and this must
    surface as a verification failure — not a silent pass with mismatched
    content, and not a silent overwrite of what the snapshot recorded.
    """
    from agent_fork.content import capture_state, collect_inventory, compare_states
    from agent_fork.repository import create_worktree_at_anchor
    from agent_fork.submodules import carry_submodules, snapshot_submodules

    world = repo_scenario("plain@main", states=(submodule(dirty="modified"),))
    plans = snapshot_submodules(world.parent_path, with_state=True, env=world.env)
    frozen_content = plans[0].content
    assert frozen_content is not None

    # The race: content changes after the snapshot, before carry.
    (world.parent_path / "vendor/submodule/tracked.txt").write_text(
        "submodule modified AGAIN after the snapshot\n"
    )

    child = world.parent_path.parent / "a6b-race"
    create_worktree_at_anchor(world.parent_path, "fork/a6b-race", child, env=world.env)
    carry_submodules(world.parent_path, child, plans, with_state=True, env=world.env)

    # Carry transported the LIVE (post-race) bytes, since materialize's diff
    # runs live against the parent's current working tree at carry time.
    live = (child / "vendor/submodule/tracked.txt").read_text()
    assert live == "submodule modified AGAIN after the snapshot\n"

    # Verification compares against the FROZEN snapshot, so it must catch the
    # divergence rather than silently accept whatever carry actually moved.
    child_inventory = collect_inventory(
        child / "vendor/submodule", with_state=True, with_ignored=False, env=world.env
    )
    child_content = capture_state(
        child / "vendor/submodule", child_inventory, env=world.env
    )
    diff = compare_states(frozen_content, child_content)
    assert diff, "a mixed-time race must be visible to compare_states, not silent"


@pytest.mark.matrix("T-VER-50")
def test_semantic_pin_reaches_a_recursive_collect_inventory_call(repo_scenario):
    """Gate-4 pass 1 finding 4 — semantics that reach a recursive
    `collect_inventory` call must actually change its output, not just be
    present as an unused parameter. Reproduced directly against
    `collect_inventory` on a submodule checkout, the same call
    `verify_submodules` and `_carry_one` make: ambient `diff.ignoreSubmodules=
    all`, set inside *that checkout's own* local config (not global, not
    passed by agent-fork — whatever a user of that submodule happened to
    configure for themselves), would otherwise hide a nested gitlink's
    working-tree state from the unstaged listing.

    Gate-6 round 2 findings 4+5 hardened this further: a `-c` config pin
    cannot defeat every axis a user's local config can set (concretely,
    `submodule.<name>.ignore`, confirmed empirically — the pin left the
    listing empty, only the explicit command-line flag restored it), so
    `collect_inventory` now adds `--ignore-submodules=none` itself whenever
    `with_submodules=True`, unconditionally of `config_pins`. This test now
    proves that stronger, caller-independent guarantee: the ambient config
    never hides the advance even when no pin is threaded through at all.
    """
    from agent_fork.content import collect_inventory

    world = repo_scenario(
        "plain@main", states=(submodule(nested=True, committed=True),)
    )
    outer = world.parent_path / "vendor/submodule"
    _git(world, outer, "config", "diff.ignoreSubmodules", "all")
    (outer / "inner" / "tracked.txt").write_text("advanced\n")
    _git(world, outer / "inner", "commit", "-qam", "advance the inner submodule")

    carrying_no_pins = collect_inventory(
        outer, with_state=True, with_ignored=False, with_submodules=True, env=world.env
    )
    assert "inner" in carrying_no_pins.unstaged
