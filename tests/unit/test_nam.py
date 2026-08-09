"""G-NAM — Naming pipeline (U-tier; the whole group is tier U).

Matrix: docs/testing/TEST-MATRIX.md §G-NAM.
"""

import pytest


@pytest.mark.matrix("T-NAM-01")
@pytest.mark.skip(reason="pending: T-NAM-01")
def test_sanitizer_rules_asserted_individually(repo_scenario):
    """T-NAM-01 — the sanitizer strips illegal chars, spaces, dashes, dots, and .lock.

    Given:  one crafted input exercising every sanitizer rule
    Expect: git-illegal chars (`.. ~ ^ : ? * [ \\ @{`) stripped, spaces become dashes,
            repeated dashes collapse, leading dots strip, trailing `.lock` strips —
            each rule asserted individually
    Source: RESEARCH §2.4
    """
    raise NotImplementedError


@pytest.mark.matrix("T-NAM-02")
@pytest.mark.skip(reason="pending: T-NAM-02")
def test_auto_name_derivation_bare_fork(repo_scenario):
    """T-NAM-02 — bare fork (no positional) derives <branch-slug>-<mmdd> at call time.

    Given:  bare `fork` invocation (no positional name); a run that spans midnight
    Expect: name uses <branch-slug>-<mmdd> computed at call time; a midnight-spanning
            run rebuilds a fresh world and reruns rather than reusing the stale date
    Source: D4; RESEARCH §2.4; spec §6.6
    """
    raise NotImplementedError


@pytest.mark.matrix("T-NAM-03")
@pytest.mark.skip(reason="pending: T-NAM-03")
def test_a5_detached_head_auto_name(repo_scenario):
    """T-NAM-03 — A5 detached-HEAD auto-name derives detached-<short-sha>-<mmdd>.

    Given:  detached HEAD, bare `fork` invocation
    Expect: name is detached-<short-sha>-<mmdd>, collision-suffixed like any other
            auto name
    Source: D4 (A5); spec §8 A5
    """
    raise NotImplementedError


@pytest.mark.matrix("T-NAM-04")
@pytest.mark.skip(reason="pending: T-NAM-04")
def test_collision_suffix_escalates(repo_scenario):
    """T-NAM-04 — auto-name collision suffix escalates -2, -3, … until non-colliding.

    Given:  auto-name mode with colliding names already present
    Expect: suffix escalates through -2, -3, … until a non-colliding name is found
    Source: D4; RESEARCH §2.4
    """
    raise NotImplementedError


@pytest.mark.matrix("T-NAM-05")
@pytest.mark.skip(reason="pending: T-NAM-05")
def test_explicit_colliding_name_refused_not_suffixed(repo_scenario):
    """T-NAM-05 — an explicit colliding name is refused, not auto-suffixed.

    Given:  explicit name collides with an existing branch/worktree
    Expect: refusal; the name is passed through unmodified, no auto-suffix
    Source: D4; REQ-19
    """
    raise NotImplementedError


@pytest.mark.matrix("T-NAM-06")
@pytest.mark.skip(reason="pending: T-NAM-06")
def test_collision_suffix_search_hard_stops_at_1000(repo_scenario):
    """T-NAM-06 — the collision-suffix search hard-stops after 1000 attempts.

    Given:  1000 colliding names already present
    Expect: search hard-stops after 1000 attempts
    Source: D4; RESEARCH §2.4
    """
    raise NotImplementedError


@pytest.mark.matrix("T-NAM-07")
@pytest.mark.skip(reason="pending: T-NAM-07")
def test_derived_name_feeds_branch_worktree_and_display_name(repo_scenario):
    """T-NAM-07 — the derived name feeds the branch, worktree dir, and display name.

    Given:  one fork with a derived name
    Expect: fork branch (<branch_prefix><name>), worktree directory, and session
            display name each carry the derived name, asserted individually
    Source: REQUIREMENTS §3.3; D6
    """
    raise NotImplementedError
