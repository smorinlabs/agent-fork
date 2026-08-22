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


@pytest.mark.matrix("T-VER-40")
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


@pytest.mark.matrix("T-VER-41")
def test_opt_out_reproduces_a6as_original_behaviour_exactly(repo_scenario):
    """`--no-with-submodules` must still fork successfully — A6a's original
    behaviour, gated rather than deleted.
    """
    world = repo_scenario("plain@main", states=(submodule(dirty="modified"),))
    result = _fork(world, "opt-out", with_submodules=False)
    assert not (result.creation.path / "vendor/submodule/.git").exists()
    assert any(
        "not carried" in notice or "vendor/submodule" in notice
        for notice in result.notices
    )


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


@pytest.mark.matrix("T-VER-42")
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


@pytest.mark.matrix("T-OUT-29")
def test_json_output_carries_with_submodules_and_the_carry_notice(repo_scenario):
    """The flag's resolved value and the carry outcome both reach the JSON document."""
    from conftest import run_cli

    world = repo_scenario("plain@main", states=(submodule(dirty="modified"),))
    completed = run_cli(
        ["fork", "jsoncheck", "--no-agent", "-o", "json"], world.env, world.parent_path
    )
    assert completed.returncode == 0, completed.stderr.decode()
    import json

    document = json.loads(completed.stdout)
    assert document["fork"]["mode"]["with_submodules"] is True
    assert any("vendor/submodule" in notice for notice in document["notices"])


@pytest.mark.matrix("T-VER-46")
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


@pytest.mark.matrix("T-VER-45")
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
