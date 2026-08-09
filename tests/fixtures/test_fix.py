"""G-FIX — Fixture layer (tier F, the declared exception living in tests/fixtures/).

Matrix: docs/testing/TEST-MATRIX.md §G-FIX.
"""

import pytest


@pytest.mark.parametrize(
    "topology",
    [
        pytest.param(
            "plain@branch", id="T-FIX-01", marks=pytest.mark.matrix("T-FIX-01")
        ),
        pytest.param("plain@main", id="T-FIX-02", marks=pytest.mark.matrix("T-FIX-02")),
        pytest.param("detached", id="T-FIX-03", marks=pytest.mark.matrix("T-FIX-03")),
        pytest.param(
            "linked-worktree", id="T-FIX-04", marks=pytest.mark.matrix("T-FIX-04")
        ),
        pytest.param("bare@bare", id="T-FIX-05", marks=pytest.mark.matrix("T-FIX-05")),
        pytest.param("bare@wt", id="T-FIX-06", marks=pytest.mark.matrix("T-FIX-06")),
        pytest.param(
            "dot-bare@wt", id="T-FIX-07", marks=pytest.mark.matrix("T-FIX-07")
        ),
        pytest.param(
            "nested-bare", id="T-FIX-08", marks=pytest.mark.matrix("T-FIX-08")
        ),
        pytest.param(
            "unborn(plain)", id="T-FIX-09", marks=pytest.mark.matrix("T-FIX-09")
        ),
        pytest.param(
            "unborn(bare)", id="T-FIX-10", marks=pytest.mark.matrix("T-FIX-10")
        ),
    ],
)
@pytest.mark.skip(reason="pending: T-FIX-01..T-FIX-10 family")
def test_builder_matches_declared_spec(repo_scenario, topology):
    """Builder-vs-spec verification: each topology's constructor matches its
    declared spec (linked-worktree is built with a divergent, separately-dirty
    main checkout). Source: spec §6.3; RESEARCH §2.3.
    """
    raise NotImplementedError


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param("flip-byte", id="T-FIX-11", marks=pytest.mark.matrix("T-FIX-11")),
        pytest.param("chmod", id="T-FIX-12", marks=pytest.mark.matrix("T-FIX-12")),
        pytest.param(
            "retarget-symlink", id="T-FIX-13", marks=pytest.mark.matrix("T-FIX-13")
        ),
        pytest.param(
            "add-untracked", id="T-FIX-14", marks=pytest.mark.matrix("T-FIX-14")
        ),
        pytest.param(
            "update-index", id="T-FIX-15", marks=pytest.mark.matrix("T-FIX-15")
        ),
    ],
)
@pytest.mark.skip(reason="pending: T-FIX-11..T-FIX-15 family")
def test_oracle_mutation_detected(repo_scenario, mutation):
    """Oracle mutation: an out-of-band change (byte flip, chmod, symlink retarget,
    added untracked file, or an update-index edit) is caught by exactly the
    corresponding oracle (manifest+hash, lstat mode, symlink target, manifest,
    or index-comparison) on exactly that entry. Source: spec §5; spec §6.5.
    """
    raise NotImplementedError


@pytest.mark.matrix("T-FIX-16")
@pytest.mark.skip(reason="pending: T-FIX-16")
def test_env_seal_leaks_no_agent_or_git_prefixed_keys(repo_scenario):
    """T-FIX-16 — the sealed subprocess env leaks no undeclared agent/git-prefixed key.

    Given:  a sealed subprocess env built by sealed_env()
    Expect: no key prefixed CLAUDE, CODEX, AI_AGENT, or GIT_ is present outside the
            declared whitelist
    Source: spec §6.2
    """
    raise NotImplementedError


@pytest.mark.matrix("T-FIX-17")
@pytest.mark.skip(reason="pending: T-FIX-17")
def test_realpath_rule_holds_for_every_handle_path(repo_scenario):
    """T-FIX-17 — every fixture handle path is already realpathed.

    Given:  a built WorldHandle
    Expect: handle.path == realpath(handle.path)
    Source: spec §6.5
    """
    raise NotImplementedError


@pytest.mark.matrix("T-FIX-18")
@pytest.mark.skip(reason="pending: T-FIX-18")
def test_git_version_canary_filter_divergence(repo_scenario):
    """T-FIX-18 — git-version canary: filter-divergence is identical on git 2.43/2.50.

    Given:  a non-idempotent clean filter applied to a staged new file
    Expect: the filter diverges identically on git 2.43 and git 2.50
    Source: spec §6.6; spec §5
    """
    raise NotImplementedError


@pytest.mark.matrix("T-FIX-19")
@pytest.mark.skip(reason="pending: T-FIX-19")
def test_git_version_canary_origin_head_determinism(repo_scenario):
    """T-FIX-19 — git-version canary: origin/HEAD is deterministic across git 2.43/2.50.

    Given:  `git remote set-head origin -a` applied by the remote constructor
    Expect: origin/HEAD is deterministic across git 2.43 and git 2.50
    Source: spec §6.4
    """
    raise NotImplementedError


@pytest.mark.matrix("T-FIX-20")
@pytest.mark.skip(reason="pending: T-FIX-20")
def test_git_version_canary_origin_head_deletion_fallback(repo_scenario):
    """T-FIX-20 — git-version canary: detection fallback fires when origin/HEAD is
    absent.

    Given:  origin/HEAD deleted after being set
    Expect: the detection fallback is exercised, consistent across git 2.43/2.50
    Source: spec §6.4
    """
    raise NotImplementedError


@pytest.mark.matrix("T-FIX-21")
@pytest.mark.skip(reason="pending: T-FIX-21")
def test_git_version_canary_unborn_head_rc_128(repo_scenario):
    """T-FIX-21 — git-version canary: unborn-HEAD repos return rc=128 consistently.

    Given:  an unborn(plain) topology repo
    Expect: git commands return rc=128 consistently across git 2.43 and git 2.50
    Source: spec §5
    """
    raise NotImplementedError


@pytest.mark.matrix("T-FIX-22")
@pytest.mark.skip(reason="pending: T-FIX-22")
def test_git_version_canary_ita_flags_supported(repo_scenario):
    """T-FIX-22 — git-version canary: ITA flags are present/supported on both floors.

    Given:  a staged intent-to-add entry
    Expect: `--ita-invisible-in-index` and `apply --intent-to-add` are present/supported
            on both git 2.43 and git 2.50
    Source: spec §5; REQ-21 (A3)
    """
    raise NotImplementedError


@pytest.mark.matrix("T-FIX-23")
@pytest.mark.skip(reason="pending: T-FIX-23")
def test_shim_interception_canary_logs_nonempty_argv(repo_scenario):
    """T-FIX-23 — the producer-failure git shim logs non-empty argv per intercepted
    call.

    Given:  shim_git() intercepting a call during materialize
    Expect: every intercepted call is logged with non-empty argv
    Source: spec §6.6; REQ-43 (A10)
    """
    raise NotImplementedError


@pytest.mark.matrix("T-FIX-24")
@pytest.mark.skip(reason="pending: T-FIX-24")
def test_harness_git_floor_gate(repo_scenario):
    """T-FIX-24 — F/C/R-tier collection hard-errors below TEST_HARNESS_GIT_MIN;
    U-tier does not.

    Given:  an installed git below TEST_HARNESS_GIT_MIN (2.43)
    Expect: F/C/R-tier collection hard-errors; unit tests remain collectible on any
            git version
    Source: spec §7.5; spec §2
    """
    raise NotImplementedError
