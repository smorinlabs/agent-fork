"""G-PRE — Preflight & refusal (tier F rows only; U rows in tests/unit/).

T-PRE-06/07/08/09 are blocked pending A9's implementation-time git-feature
audit (spec §8 A9); they get authored pending stubs, not skips-for-blocked.

Matrix: docs/testing/TEST-MATRIX.md §G-PRE.
"""

import pytest


@pytest.mark.matrix("T-PRE-01")
@pytest.mark.skip(reason="pending: T-PRE-01")
def test_agent_cli_entirely_missing_refuses_with_diagnosis(repo_scenario):
    """T-PRE-01 — a fully missing agent CLI refuses with a diagnosis naming what was
    detected and what's missing.

    Given:  the detected agent's CLI binary is entirely missing (agent=claude)
    Expect: refusal, exit 3, diagnosis names what was detected and what's missing
    Source: REQ-27; REQ-29
    """
    raise NotImplementedError


@pytest.mark.matrix("T-PRE-05")
@pytest.mark.skip(reason="pending: T-PRE-05")
def test_codex_rollout_not_flushed_refuses_before_mutation(repo_scenario):
    """T-PRE-05 — an unflushed Codex parent rollout file refuses before any mutation.

    Given:  the Codex parent rollout file not yet flushed to disk
    Expect: refuse before any mutation
    Source: REQ-27; RESEARCH §3.2
    """
    raise NotImplementedError


@pytest.mark.parametrize(
    "boundary",
    [
        pytest.param(
            "below-floor", id="T-PRE-06", marks=pytest.mark.matrix("T-PRE-06")
        ),
        pytest.param(
            "at-or-above-floor", id="T-PRE-07", marks=pytest.mark.matrix("T-PRE-07")
        ),
    ],
)
@pytest.mark.skip(reason="pending: T-PRE-06..T-PRE-07 family")
def test_product_git_min_boundary_blocked_on_a9(repo_scenario, boundary):
    """PRODUCT_GIT_MIN boundary checks are blocked pending A9's implementation-time
    git-feature audit fixing the floor value.

    T-PRE-06 — an injected `git --version` just below the fixed floor fails the named
    check.
    T-PRE-07 — an injected `git --version` at/above the fixed floor passes the named
    check.
    Source: REQ-38 (A9); spec §8 A9
    """
    raise NotImplementedError


@pytest.mark.matrix("T-PRE-08")
@pytest.mark.skip(reason="pending: T-PRE-08")
def test_a14_below_floor_fork_refusal_names_remedy(repo_scenario):
    """T-PRE-08 — A14 — a below-floor fork refusal names the installed version, floor,
    and upgrade path (blocked on A9's implementation-time git-feature audit).

    Given:  an injected `git --version` below PRODUCT_GIT_MIN
    Expect: refusal, exit 5, remedy names installed version/floor/upgrade path
    Source: REQ-19 (A14); spec §8 A14
    """
    raise NotImplementedError


@pytest.mark.matrix("T-PRE-09")
@pytest.mark.skip(reason="pending: T-PRE-09")
def test_a14_force_overrides_git_floor_refusal_only(repo_scenario):
    """T-PRE-09 — A14 — fork --force overrides the git-floor refusal only (blocked on
    A9's implementation-time git-feature audit).

    Given:  an injected below-floor `git --version` with `fork --force` passed
    Expect: the git-floor refusal is overridden only; stderr warning emitted; verify
            ladder still runs
    Source: REQUIREMENTS §3.3 (A14); spec §8 A14
    """
    raise NotImplementedError


@pytest.mark.matrix("T-PRE-10")
@pytest.mark.skip(reason="pending: T-PRE-10")
def test_d14_nothing_created_on_preflight_refusal(repo_scenario):
    """T-PRE-10 — D14 — nothing is created (no worktree, no branch) on any preflight
    refusal.

    Given:  any preflight refusal path
    Expect: no worktree, no branch created
    Source: DESIGN-DECISIONS D14; REQ-29
    """
    raise NotImplementedError
