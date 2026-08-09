"""G-CLN — Cleanup (tier C rows only; F rows in tests/pipeline/).

Matrix: docs/testing/TEST-MATRIX.md §G-CLN.
"""

import pytest


@pytest.mark.matrix("T-CLN-09")
@pytest.mark.skip(reason="pending: T-CLN-09")
def test_yes_flag_bypasses_consent_prompt(repo_scenario):
    """T-CLN-09 — --yes bypasses the interactive consent prompt.

    Given:  cleanup invoked with `--yes`
    Expect: the interactive consent prompt is bypassed
    Source: REQ-33
    """
    raise NotImplementedError


@pytest.mark.matrix("T-CLN-10")
@pytest.mark.skip(reason="pending: T-CLN-10")
def test_no_input_without_yes_or_override_fails_exit_2(repo_scenario):
    """T-CLN-10 — --no-input without --yes or a guard-override flag fails with exit 2.

    Given:  cleanup invoked with `--no-input` but neither `--yes` nor a guard-override
            flag
    Expect: fail, exit 2
    Source: REQ-33
    """
    raise NotImplementedError


@pytest.mark.matrix("T-CLN-11")
@pytest.mark.skip(reason="pending: T-CLN-11")
def test_tty_consent_prompt_names_exact_removal_targets(repo_scenario):
    """T-CLN-11 — the TTY consent prompt on stderr names exactly what will be removed.

    Given:  cleanup run attached to a pty, no `--yes`
    Expect: the consent prompt on stderr names exactly what will be removed
    Source: REQ-33; spec §6.6
    """
    raise NotImplementedError


@pytest.mark.matrix("T-CLN-13")
@pytest.mark.skip(reason="pending: T-CLN-13")
def test_dry_run_prints_removal_plan_without_mutating(repo_scenario):
    """T-CLN-13 — --dry-run prints the cleanup removal plan without mutating anything.

    Given:  cleanup invoked with `--dry-run`
    Expect: the removal plan is printed; nothing is mutated
    Source: REQ-33; REQ-18
    """
    raise NotImplementedError
