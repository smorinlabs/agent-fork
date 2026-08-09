"""G-PRE — Preflight & refusal (U-tier rows only; F rows land in Task 8).

Matrix: docs/testing/TEST-MATRIX.md §G-PRE.
"""

import pytest


@pytest.mark.matrix("T-PRE-02")
@pytest.mark.skip(reason="pending: T-PRE-02")
def test_claude_below_pinned_id_fork_floor_refuses(repo_scenario):
    """T-PRE-02 — Claude below the pinned-ID fork floor (2.0.73) is refused.

    Given:  detected Claude CLI version below 2.0.73
    Expect: refusal
    Source: REQ-27; RESEARCH §5.2
    """
    raise NotImplementedError


@pytest.mark.matrix("T-PRE-03")
@pytest.mark.skip(reason="pending: T-PRE-03")
def test_claude_warn_band_warns_and_proceeds(repo_scenario):
    """T-PRE-03 — Claude in the warn-band (<~2.1.1xx) warns and proceeds.

    Given:  detected Claude CLI version in the warn-band (<~2.1.1xx)
    Expect: proceeds with notices[] populated
    Source: REQ-27; RESEARCH §5.1 Q1
    """
    raise NotImplementedError


@pytest.mark.matrix("T-PRE-04")
@pytest.mark.skip(reason="pending: T-PRE-04")
def test_codex_below_fork_subcommand_floor_refuses(repo_scenario):
    """T-PRE-04 — Codex below the fork-subcommand floor (0.81.0) is refused.

    Given:  detected Codex CLI version below 0.81.0
    Expect: refusal
    Source: REQ-27; RESEARCH §5.1 Q4
    """
    raise NotImplementedError
