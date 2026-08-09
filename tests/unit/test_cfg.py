"""G-CFG — Config resolution (U-tier rows only; F/C rows land in Task 8).

Matrix: docs/testing/TEST-MATRIX.md §G-CFG.
"""

import pytest


@pytest.mark.matrix("T-CFG-01")
@pytest.mark.skip(reason="pending: T-CFG-01")
def test_with_state_unset_defaults_true(repo_scenario):
    """T-CFG-01 — with_state unset resolves to True.

    Given:  no config file, no flags
    Expect: resolved plan carries state (exact)
    Source: REQ-13; RESEARCH §1.1 tri-state accessors
    """
    raise NotImplementedError


@pytest.mark.matrix("T-CFG-02")
@pytest.mark.skip(reason="pending: T-CFG-02")
def test_explicit_with_state_false_is_honored(repo_scenario):
    """T-CFG-02 — explicit with_state=false is honored, not coerced back to default.

    Given:  with_state=false set in a single config source
    Expect: resolved plan honors with_state=false, not the tri-state default
    Source: REQ-13; RESEARCH §1.1
    """
    raise NotImplementedError


@pytest.mark.matrix("T-CFG-03")
@pytest.mark.skip(reason="pending: T-CFG-03")
def test_within_source_implication_resolves_exact_ignored(repo_scenario):
    """T-CFG-03 — within-source implication resolves conflicting flags to exact+ignored.

    Given:  --no-with-state --with-ignored typed together on one source
    Expect: resolved mode is exact+ignored
    Source: REQ-13; RESEARCH §1.1
    """
    raise NotImplementedError


@pytest.mark.matrix("T-CFG-04")
@pytest.mark.skip(reason="pending: T-CFG-04")
def test_a12_cross_source_config_false_plus_flag_ignored_true(repo_scenario):
    """T-CFG-04 — A12 cross-source: config with_state=false + --with-ignored resolves
    exact+ignored.

    Given:  config sets with_state=false; --with-ignored flag passed
    Expect: resolved mode is exact+ignored (the flag's implication forces state back on)
    Source: REQ-13 (A12); spec §4
    """
    raise NotImplementedError


@pytest.mark.matrix("T-CFG-05")
@pytest.mark.skip(reason="pending: T-CFG-05")
def test_a12_cross_source_config_ignored_true_plus_flag_no_with_state(repo_scenario):
    """T-CFG-05 — A12 cross-source: config with_ignored=true + --no-with-state resolves
    no-state.

    Given:  config sets with_ignored=true; --no-with-state flag passed
    Expect: resolved mode is no-state (flag wins; config's with_ignored suppressed)
    Source: REQ-13 (A12); spec §4
    """
    raise NotImplementedError


@pytest.mark.matrix("T-CFG-06")
@pytest.mark.skip(reason="pending: T-CFG-06")
def test_a12_cross_source_all_sources_unset_resolves_exact(repo_scenario):
    """T-CFG-06 — A12 cross-source: all sources unset resolves to exact.

    Given:  no config, no env, no flags set
    Expect: resolved mode is exact
    Source: REQ-13 (A12); spec §4
    """
    raise NotImplementedError


@pytest.mark.matrix("T-CFG-07")
@pytest.mark.skip(reason="pending: T-CFG-07")
def test_precedence_chain_flags_beat_env_beat_config_file(repo_scenario):
    """T-CFG-07 — precedence chain: flags beat env beat config-file order.

    Given:  flags, env, and config-file each set to conflicting values
    Expect: resolved value follows flags > env > config-file order
    Source: REQ-12; RESEARCH §1.1
    """
    raise NotImplementedError


@pytest.mark.matrix("T-CFG-08")
@pytest.mark.skip(reason="pending: T-CFG-08")
def test_branch_prefix_whitespace_only_resolves_to_default(repo_scenario):
    """T-CFG-08 — a whitespace-only branch_prefix resolves to the default fork/.

    Given:  branch_prefix set to a whitespace-only string
    Expect: resolved branch_prefix is the default fork/
    Source: REQ-13
    """
    raise NotImplementedError


@pytest.mark.matrix("T-CFG-09")
@pytest.mark.skip(reason="pending: T-CFG-09")
def test_env_vars_applied_to_config_path_and_output_format(repo_scenario):
    """T-CFG-09 — AGENT_FORK_CONFIG and AGENT_FORK_OUTPUT env vars are read and applied.

    Given:  AGENT_FORK_CONFIG and AGENT_FORK_OUTPUT env vars set
    Expect: config-path and output-format resolution reflect them respectively
    Source: REQ-14
    """
    raise NotImplementedError
