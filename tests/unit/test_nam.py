"""G-NAM — Naming pipeline (U-tier; the whole group is tier U).

Matrix: docs/testing/TEST-MATRIX.md §G-NAM.
"""

import pytest


@pytest.mark.matrix("T-NAM-01")
def test_sanitizer_rules_asserted_individually(repo_scenario):
    """T-NAM-01 — the sanitizer strips illegal chars, spaces, dashes, dots, and .lock.

    Given:  one crafted input exercising every sanitizer rule
    Expect: git-illegal chars (`.. ~ ^ : ? * [ \\ @{`) stripped, spaces become dashes,
            repeated dashes collapse, leading dots strip, trailing `.lock` strips —
            each rule asserted individually
    Source: RESEARCH §2.4
    """
    from agent_fork.naming import sanitize_name

    cases = {
        "Hello World": "hello-world",
        "a..b": "ab",
        "a~b^c:d?e*f[g\\h": "abcdefgh",
        "a@{b": "ab",
        "many---dashes": "many-dashes",
        "...leading": "leading",
        "topic.lock": "topic",
    }
    for raw, expected in cases.items():
        assert sanitize_name(raw) == expected


@pytest.mark.matrix("T-NAM-02")
def test_auto_name_derivation_bare_fork(repo_scenario):
    """T-NAM-02 — bare fork (no positional) derives <branch-slug>-<mmdd> at call time.

    Given:  bare `fork` invocation (no positional name); a run that spans midnight
    Expect: name uses <branch-slug>-<mmdd> computed at call time; a midnight-spanning
            run rebuilds a fresh world and reruns rather than reusing the stale date
    Source: D4; RESEARCH §2.4; spec §6.6
    """
    from datetime import datetime

    from agent_fork.naming import derive_auto_name

    assert (
        derive_auto_name("Feature/Auth", now=datetime(2026, 8, 10))
        == "featureauth-0810"
    )
    assert (
        derive_auto_name("Feature/Auth", now=datetime(2026, 8, 11))
        == "featureauth-0811"
    )


@pytest.mark.matrix("T-NAM-03")
def test_a5_detached_head_auto_name(repo_scenario):
    """T-NAM-03 — A5 detached-HEAD auto-name derives detached-<short-sha>-<mmdd>.

    Given:  detached HEAD, bare `fork` invocation
    Expect: name is detached-<short-sha>-<mmdd>, collision-suffixed like any other
            auto name
    Source: D4 (A5); spec §8 A5
    """
    from datetime import datetime

    from agent_fork.naming import derive_auto_name

    assert (
        derive_auto_name(None, detached_sha="abcdef123456", now=datetime(2026, 8, 10))
        == "detached-abcdef1-0810"
    )


@pytest.mark.matrix("T-NAM-04")
def test_collision_suffix_escalates(repo_scenario):
    """T-NAM-04 — auto-name collision suffix escalates -2, -3, … until non-colliding.

    Given:  auto-name mode with colliding names already present
    Expect: suffix escalates through -2, -3, … until a non-colliding name is found
    Source: D4; RESEARCH §2.4
    """
    from agent_fork.naming import unique_auto_name

    collisions = {"feature-0810", "feature-0810-2", "feature-0810-3"}
    assert unique_auto_name("feature-0810", collisions.__contains__) == "feature-0810-4"


@pytest.mark.matrix("T-NAM-05")
def test_explicit_colliding_name_refused_not_suffixed(repo_scenario):
    """T-NAM-05 — an explicit colliding name is refused, not auto-suffixed.

    Given:  explicit name collides with an existing branch/worktree
    Expect: refusal; the name is passed through unmodified, no auto-suffix
    Source: D4; REQ-19
    """
    from agent_fork.errors import ConflictError
    from agent_fork.naming import resolve_name

    with pytest.raises(ConflictError) as caught:
        resolve_name(
            "fix-auth", auto_base="unused", collides=lambda value: value == "fix-auth"
        )
    assert caught.value.code == "conflict_branch_exists"
    assert "fix-auth" in str(caught.value)


@pytest.mark.matrix("T-NAM-06")
def test_collision_suffix_search_hard_stops_at_1000(repo_scenario):
    """T-NAM-06 — the collision-suffix search hard-stops after 1000 attempts.

    Given:  1000 colliding names already present
    Expect: search hard-stops after 1000 attempts
    Source: D4; RESEARCH §2.4
    """
    from agent_fork.errors import ConflictError
    from agent_fork.naming import unique_auto_name

    attempts = 0

    def always_collides(_candidate):
        nonlocal attempts
        attempts += 1
        return True

    with pytest.raises(ConflictError):
        unique_auto_name("busy", always_collides)
    assert attempts == 1000


@pytest.mark.matrix("T-NAM-07")
def test_derived_name_feeds_branch_worktree_and_display_name(repo_scenario):
    """T-NAM-07 — the derived name feeds the branch, worktree dir, and display name.

    Given:  one fork with a derived name
    Expect: fork branch (<branch_prefix><name>), worktree directory, and session
            display name each carry the derived name, asserted individually
    Source: REQUIREMENTS §3.3; D6
    """
    from agent_fork.naming import naming_plan

    plan = naming_plan("fix-auth", branch_prefix="fork/")
    assert plan.name == "fix-auth"
    assert plan.branch == "fork/fix-auth"
    assert plan.worktree_suffix == "fix-auth"
    assert plan.display_name == "fix-auth"


@pytest.mark.matrix("T-NAM-08")
def test_destination_defaults_preserve_identity_feed_through(repo_scenario):
    from agent_fork.naming import naming_plan

    plan = naming_plan("same", branch_prefix="fork/")
    assert (plan.name, plan.branch, plan.worktree_suffix, plan.display_name) == (
        "same",
        "fork/same",
        "same",
        "same",
    )


@pytest.mark.matrix("T-NAM-09")
def test_explicit_resource_overrides_do_not_rewrite_display_identity(repo_scenario):
    from agent_fork.naming import naming_plan

    plan = naming_plan("session", branch_prefix="fork/")
    explicit_branch, explicit_leaf = "review/branch", "Exact Leaf"
    assert plan.name == plan.display_name == "session"
    assert explicit_branch != plan.branch and explicit_leaf != plan.worktree_suffix


@pytest.mark.matrix("T-NAM-10")
def test_derived_collision_advances_auto_name(repo_scenario):
    from agent_fork.naming import unique_auto_name

    assert unique_auto_name("auto", lambda value: value == "auto") == "auto-2"


@pytest.mark.matrix("T-NAM-12")
def test_fixed_collision_can_abort_before_candidate_cap(repo_scenario):
    from agent_fork.errors import PreconditionError
    from agent_fork.naming import unique_auto_name

    calls = 0

    def fixed(_value):
        nonlocal calls
        calls += 1
        raise PreconditionError("conflict_worktree_path", "fixed destination")

    with pytest.raises(PreconditionError):
        unique_auto_name("auto", fixed)
    assert calls == 1
