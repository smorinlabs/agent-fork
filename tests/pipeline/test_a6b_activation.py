"""G-MAT/G-VER/G-GRD — A6b step 6: activation.

Design: docs/superpowers/plans/2026-08-17-p02-a6-dirty-submodules.md,
"Activation — the one step where default behaviour changes". Four things
land together: A6a's existing protection gates off (`with_state and not
with_submodules`), carry gates on (`with_state and with_submodules`),
recursive verification runs the seven rungs, and the notice is gated and
extended. Drives the real `fork()` pipeline end to end, not the recipe in
isolation — this is the step that makes the sixteen cells from step 1
flip from red to green.
"""

from __future__ import annotations

import subprocess
from typing import cast

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


def _fork(world, name, *, with_submodules=True, with_state=True, with_ignored=False):
    from agent_fork.pipeline import ForkRequest, fork

    request = ForkRequest(
        parent=world.parent_path,
        destination=world.parent_path.parent / name,
        name=name,
        branch=f"fork/{name}",
        agent=None,
        with_state=with_state,
        with_submodules=with_submodules,
        with_ignored=with_ignored,
    )
    return fork(request, env=world.env)


@pytest.mark.matrix("T-VER-46")
def test_default_fork_carries_a_dirty_submodule_and_verifies(repo_scenario):
    """The headline case: A6b's whole reason to exist. Default settings, no
    flags, a dirty submodule — the fork succeeds and both statuses match.
    """
    world = repo_scenario("plain@main", states=(submodule(dirty="modified"),))
    result = _fork(world, "default-carry")
    assert (result.creation.path / "vendor/submodule/.git").exists()
    assert _status(world, result.creation.path) == _status(world, world.parent_path)
    inner = _git(
        world, result.creation.path / "vendor/submodule", "status", "--porcelain=v1"
    ).stdout
    assert inner == b" M tracked.txt\n"
    # Gate-6 finding 3 -- materialize() unconditionally emitted the "not
    # carried" loss notice regardless of with_submodules, so a default fork
    # reported both "carried" and "not carried" for the same submodule. The
    # earlier version of this test never checked for the false notice's
    # absence, which is exactly how the bug went unnoticed.
    assert not any("not carried" in notice for notice in result.notices)
    assert any("submodule carried" in notice for notice in result.notices)


@pytest.mark.matrix("T-VER-47")
def test_opt_out_reproduces_a6as_original_behaviour_exactly(repo_scenario):
    """`--no-with-submodules` must still fork successfully — A6a's original
    behaviour, gated rather than deleted.
    """
    world = repo_scenario("plain@main", states=(submodule(dirty="modified"),))
    result = _fork(world, "opt-out", with_submodules=False)
    assert not (result.creation.path / "vendor/submodule/.git").exists()
    assert any("not carried" in notice for notice in result.notices)


@pytest.mark.matrix("T-GRD-27")
def test_cell_c_no_longer_refuses_when_submodules_are_carried(repo_scenario):
    """Gate-4 pass 4's whole reason for the guard's conditional design: an
    unstaged gitlink advance is refused only when submodules are NOT carried.
    With carrying on, the child can represent it, so the guard must not fire.
    """
    world = repo_scenario("plain@main", states=(submodule(dirty="advanced"),))
    result = _fork(world, "cell-c-carried")
    assert (result.creation.path / "vendor/submodule/.git").exists()
    assert _status(world, result.creation.path) == _status(world, world.parent_path)


@pytest.mark.matrix("T-GRD-28")
def test_cell_c_still_refuses_when_submodules_are_not_carried(repo_scenario):
    """The same case, opted out of carrying — the old refusal still applies."""
    from agent_fork.errors import PreconditionError

    world = repo_scenario("plain@main", states=(submodule(dirty="advanced"),))
    with pytest.raises(PreconditionError) as raised:
        _fork(world, "cell-c-uncarried", with_submodules=False)
    assert raised.value.code == "submodule_unrepresentable"


@pytest.mark.matrix("T-GRD-29")
def test_dry_run_does_not_refuse_cell_c_under_the_default(repo_scenario):
    """Gate-6 finding 3 — the dry-run's own `validate_fork_guards` call never
    passed `with_submodules`, so its default of False made a dry-run refuse
    cell `c` (unstaged gitlink advance) under the tool's OWN default settings
    -- a preview disagreeing with what the real fork would actually do.
    """
    from conftest import run_cli

    world = repo_scenario("plain@main", states=(submodule(dirty="advanced"),))
    completed = run_cli(
        ["fork", "preview", "--no-agent", "--dry-run", "-o", "json"],
        world.env,
        world.parent_path,
    )
    assert completed.returncode == 0, completed.stderr.decode()


@pytest.mark.matrix("T-GRD-30")
def test_initialized_gitlink_without_metadata_refuses_before_mutation(repo_scenario):
    """An initialized gitlink cannot be carried without its `.gitmodules` map.

    Both the real fork and dry-run must return the typed refusal before a branch
    or destination exists. Falling through to `git submodule update` after
    worktree creation turns this malformed-but-possible repository state into a
    late Git exit 128 and needless rollback.
    """
    from agent_fork.errors import PreconditionError
    from conftest import run_cli

    world = repo_scenario("plain@main", states=(submodule(committed=True),))
    _git(world, world.parent_path, "rm", "-q", "--", ".gitmodules")
    _git(world, world.parent_path, "commit", "-qm", "remove submodule metadata")
    assert (world.parent_path / "vendor/submodule/.git").exists()

    destination = world.parent_path.parent / "missing-metadata"
    with pytest.raises(PreconditionError) as raised:
        _fork(world, "missing-metadata")
    assert raised.value.code == "submodule_unrepresentable"
    assert "vendor/submodule" in str(raised.value)
    assert not destination.exists()
    branch = _git(
        world,
        world.parent_path,
        "show-ref",
        "--verify",
        "--quiet",
        "refs/heads/fork/missing-metadata",
        check=False,
    )
    assert branch.returncode != 0

    preview = run_cli(
        [
            "fork",
            "missing-metadata-preview",
            "--no-agent",
            "--dry-run",
            "-o",
            "json",
        ],
        world.env,
        world.parent_path,
    )
    assert preview.returncode == 5
    assert b'"code":"submodule_unrepresentable"' in preview.stderr


@pytest.mark.matrix("T-VER-48")
def test_recursive_verification_catches_a_wrong_submodule_head(repo_scenario):
    """Rung 2 (HEAD identity) — the sharpest test in the whole design.

    Two forks can agree on every top-level signal while a submodule inside
    them is verifiably wrong (gate-4 pass 3 finding 2's own example). Inject
    exactly that: carry succeeds, then detach the child's submodule at some
    other commit before verification would run — simulated here by calling
    verify_fork directly against a deliberately corrupted child, since
    corrupting fork()'s own internals mid-flight isn't reachable from outside.
    """
    from agent_fork.content import capture_state, collect_inventory
    from agent_fork.errors import VerificationError
    from agent_fork.repository import create_worktree_at_anchor, validate_fork_guards
    from agent_fork.submodules import carry_submodules, snapshot_submodules
    from agent_fork.verify import verify_fork

    world = repo_scenario("plain@main", states=(submodule(committed=True),))
    validate_fork_guards(
        world.parent_path,
        "fork/wronghead",
        world.parent_path.parent / "wronghead",
        with_state=True,
        with_submodules=True,
        env=world.env,
    )
    plans = snapshot_submodules(world.parent_path, with_state=True, env=world.env)
    before = _status(world, world.parent_path)
    inventory = collect_inventory(
        world.parent_path, with_state=True, with_ignored=False, env=world.env
    )
    parent_state = capture_state(world.parent_path, inventory, env=world.env)
    child = world.parent_path.parent / "wronghead"
    creation = create_worktree_at_anchor(
        world.parent_path, "fork/wronghead", child, env=world.env
    )
    carry_submodules(world.parent_path, child, plans, with_state=True, env=world.env)

    # Corrupt: detach the child's submodule at a DIFFERENT commit than the
    # frozen plan recorded, simulating exactly gate-4 pass 3's failure mode.
    (child / "vendor/submodule/tracked.txt").write_text("a wrong commit\n")
    _git(world, child / "vendor/submodule", "add", "tracked.txt")
    _git(world, child / "vendor/submodule", "commit", "-qm", "wrong")
    _git(
        world,
        child / "vendor/submodule",
        "checkout",
        "--detach",
        "HEAD",
    )

    with pytest.raises(VerificationError) as raised:
        verify_fork(
            creation,
            with_state=True,
            with_submodules=True,
            parent_status_before=before,
            parent_state_before=parent_state,
            submodule_plans=plans,
            env=world.env,
        )
    # Gate-6 finding 7 sharpening: assert the STRUCTURED failed_checks name
    # rung 2 ("submodule-head") specifically, rather than only checking the
    # human message mentions "vendor/submodule" or "head" -- the corruption
    # also makes the submodule's own working tree differ (a new commit was
    # made), so top-level exact-copy-status/content-match can independently
    # fire too. That would make this assertion pass even if rung 2's own
    # HEAD-identity check were deleted, undermining its claim to isolate
    # what it tests. Structured kinds pin it to the recursive rung itself.
    error = raised.value
    assert error.details is not None
    checks = cast("list[dict[str, object]]", error.details["failed_checks"])
    kinds = {
        entry["kind"]
        for check in checks
        for entry in cast("list[dict[str, object]]", check["differences"])
    }
    assert "submodule-head" in kinds


@pytest.mark.matrix("T-VER-57")
def test_submodule_only_failure_is_marked_primary(repo_scenario, monkeypatch):
    """A recursive-only difference owns the structured primary flag."""
    from agent_fork.content import Difference
    from agent_fork.errors import VerificationError

    world = repo_scenario("plain@main", states=(submodule(committed=True),))
    monkeypatch.setattr(
        "agent_fork.verify.verify_submodules",
        lambda *args, **kwargs: [
            Difference(
                "vendor/submodule",
                "submodule-detached",
                "injected recursive-only difference",
            )
        ],
    )

    with pytest.raises(VerificationError) as raised:
        _fork(world, "submodule-primary")

    error = raised.value
    assert error.details is not None
    checks = cast("list[dict[str, object]]", error.details["failed_checks"])
    assert [check["check"] for check in checks] == ["submodule-content-match"]
    assert checks[0]["primary"] is True


@pytest.mark.matrix("T-OUT-32")
def test_json_output_carries_with_submodules_and_the_carry_notice(repo_scenario):
    """The flag's resolved value and the carry outcome both reach the JSON
    document. Gate-6 round 2 finding 9: the notice assertion must specifically
    confirm the CARRY outcome, not just that `vendor/submodule` is mentioned
    anywhere -- a "not carried", "skipped", or "left cold" notice would have
    satisfied a looser assertion just as well, proving nothing about which
    outcome actually happened.
    """
    from conftest import run_cli

    world = repo_scenario("plain@main", states=(submodule(dirty="modified"),))
    completed = run_cli(
        ["fork", "jsoncheck", "--no-agent", "-o", "json"], world.env, world.parent_path
    )
    assert completed.returncode == 0, completed.stderr.decode()
    import json

    document = json.loads(completed.stdout)
    assert document["fork"]["mode"]["with_submodules"] is True
    assert any(
        notice.startswith("submodule carried: vendor/submodule")
        for notice in document["notices"]
    ), document["notices"]


@pytest.mark.matrix("T-VER-52")
def test_ambient_config_at_snapshot_time_does_not_cause_a_false_verification_failure(
    repo_scenario,
):
    """Gate-6 finding 2 -- the snapshot's own `collect_inventory`/`capture_state`
    calls ran WITHOUT the semantic pins that `carry_submodules` and
    `verify_submodules` both apply. Concretely: with ambient
    `diff.ignoreSubmodules=all` set inside the outer submodule's own local
    config, and its inner nested submodule genuinely advanced, the snapshot's
    unpinned inventory call would not see `inner` as dirty (masked by the
    ambient config), while carry (pinned) correctly transports it and verify
    (pinned) correctly detects it in the child -- producing a false
    "newly carried" / "unexpected" difference purely from the domain
    mismatch between an unpinned snapshot and a pinned verify, even though
    carry did exactly the right thing. Drives the real end-to-end pipeline,
    not the primitive directly, so a domain-mismatch regression here fails
    for the right reason.
    """
    world = repo_scenario(
        "plain@main", states=(submodule(nested=True, committed=True),)
    )
    outer = world.parent_path / "vendor/submodule"
    _git(world, outer, "config", "diff.ignoreSubmodules", "all")
    (outer / "inner" / "tracked.txt").write_text("advanced\n")
    _git(world, outer / "inner", "commit", "-qam", "advance the inner submodule")

    result = _fork(world, "ambient-config-snapshot")
    child_inner = result.creation.path / "vendor/submodule" / "inner" / "tracked.txt"
    assert child_inner.read_text() == "advanced\n"


@pytest.mark.matrix("T-VER-56")
def test_equals_named_submodule_left_cold_does_not_roll_back_the_whole_fork(
    repo_scenario,
):
    """Gate-6 round 2 finding 1. A `=`-named submodule is a reasoned,
    deliberate skip (T-MAT-67 -- it cannot be expressed as a `-c
    submodule.<name>.url=...` pin, so carrying it would risk contacting its
    real remote). But rung 6 ("nested-plan completeness") treats ANY
    initialized plan entry present in `skipped` as a failure, with no way to
    distinguish a reasoned skip from an accidental one -- so today, under
    the tool's OWN default settings, a repository containing an
    `=`-named submodule is unforkable: `verify_fork` raises
    `submodule-skipped` and the whole fork rolls back, even though carry did
    exactly what the design doc's own Notices section says it should
    ("left cold -- say so"). The fix: a reasoned skip behaves like
    left-cold-with-notice at rung 6, not a failure -- the fork still
    succeeds, with a notice, and the submodule is left uninitialized.
    """
    world = repo_scenario(
        "plain@main", states=(submodule(name="eq=name", committed=True),)
    )
    result = _fork(world, "eq-name-left-cold")
    assert not (result.creation.path / "vendor/submodule/.git").exists()
    assert any(
        "vendor/submodule" in notice and "=" in notice for notice in result.notices
    )


@pytest.mark.matrix("T-VER-55")
def test_per_submodule_ignore_config_does_not_hide_a_staged_gitlink_advance(
    repo_scenario,
):
    """Gate-6 round 2 findings 4+5, corrected axis. `-c diff.ignoreSubmodules=none`
    (the `SEMANTIC_PINS` pin) does NOT defeat a per-submodule
    `submodule.<name>.ignore=all` local config value -- only the explicit
    `--ignore-submodules=none` command-line flag does (probed directly against
    real Git: `diff --cached --name-only` and `diff-index -p --cached` both
    stay silent under the pin, both report the change under the flag). With
    that config set on the parent and the submodule's gitlink staged forward,
    the unpinned-of-that-axis inventory omits the path from its staged
    listing, so `materialize()` never transports the patch and the child's
    submodule sits at the old commit -- unstaged from the child's own
    perspective where the parent has it staged, which the exact-copy-status
    rung then reports as a real difference and the whole fork rolls back, even
    though the repository was legitimately forkable.
    """
    world = repo_scenario("plain@main", states=(submodule(dirty="advanced-staged"),))
    _git(
        world,
        world.parent_path,
        "config",
        "submodule.vendor/submodule.ignore",
        "all",
    )

    result = _fork(world, "per-submodule-ignore-staged")
    assert _status(world, result.creation.path) == _status(world, world.parent_path)
    child_head = (
        _git(
            world,
            result.creation.path / "vendor/submodule",
            "rev-parse",
            "HEAD",
        )
        .stdout.decode()
        .strip()
    )
    parent_head = (
        _git(world, world.parent_path / "vendor/submodule", "rev-parse", "HEAD")
        .stdout.decode()
        .strip()
    )
    assert child_head == parent_head


@pytest.mark.matrix("T-VER-51")
def test_with_ignored_carries_and_verifies_an_ignored_file_inside_a_submodule(
    repo_scenario,
):
    """Coverage audit — step 1's sixteen-cell commitment names the
    `--with-ignored` interaction inside a submodule as its own axis. An
    ignored file inside the submodule must both carry (via `--with-ignored`)
    and pass verification -- not merely transport while
    `verify_submodules`'s recursive content rung, if it silently used
    `with_ignored=False` internally, disagreed with what the frozen snapshot
    (taken with the real flag) actually recorded.
    """
    world = repo_scenario("plain@main", states=(submodule(committed=True),))
    outer = world.parent_path / "vendor/submodule"
    (outer / ".gitignore").write_text("secret.txt\n")
    (outer / "secret.txt").write_text("ignored-but-carried\n")
    _git(world, outer, "add", ".gitignore")
    _git(world, outer, "commit", "-qm", "ignore secret.txt")

    result = _fork(world, "with-ignored-submodule", with_ignored=True)

    child_secret = result.creation.path / "vendor/submodule" / "secret.txt"
    assert child_secret.exists()
    assert child_secret.read_text() == "ignored-but-carried\n"
