"""G-OUT — Output contract (tier C).

Matrix: docs/testing/TEST-MATRIX.md §G-OUT.
"""

import pytest


@pytest.mark.matrix("T-OUT-01")
@pytest.mark.skip(reason="pending: T-OUT-01")
def test_stdout_carries_only_requested_result(repo_scenario):
    """T-OUT-01 — stdout carries only the requested result; all
    progress/diagnostics/prompts go to stderr.

    Given:  any successful CLI invocation
    Expect: stdout carries only the requested result; progress/diagnostics/prompts are
            on stderr
    Source: REQ-16
    """
    raise NotImplementedError


@pytest.mark.matrix("T-OUT-02")
@pytest.mark.skip(reason="pending: T-OUT-02")
def test_human_format_ends_with_paste_command(repo_scenario):
    """T-OUT-02 — human-format output ends with the paste command as the final stdout
    block.

    Given:  a successful fork in human output format
    Expect: output ends with the paste command as the final stdout block
    Source: REQ-16
    """
    raise NotImplementedError


@pytest.mark.matrix("T-OUT-03")
@pytest.mark.skip(reason="pending: T-OUT-03")
def test_tty_does_not_change_output_format(repo_scenario):
    """T-OUT-03 — a TTY does not change the output format.

    Given:  the CLI run attached to a pty
    Expect: output format is unchanged from the non-TTY case
    Source: REQ-16; spec §6.6
    """
    raise NotImplementedError


@pytest.mark.parametrize(
    "agent",
    [
        pytest.param("codex", id="T-OUT-04", marks=pytest.mark.matrix("T-OUT-04")),
        pytest.param("claude", id="T-OUT-05", marks=pytest.mark.matrix("T-OUT-05")),
    ],
)
@pytest.mark.skip(reason="pending: T-OUT-04..T-OUT-05 family")
def test_cwd_prompt_expected_field_present_only_for_codex(repo_scenario, agent):
    """-o json includes cwd_prompt_expected for Codex and omits it for Claude.

    T-OUT-04 — agent=codex: -o json includes the cwd_prompt_expected field.
    T-OUT-05 — agent=claude: -o json omits the cwd_prompt_expected field.
    Source: REQ-17; RESEARCH §5.1 Q4
    """
    raise NotImplementedError


@pytest.mark.matrix("T-OUT-06")
@pytest.mark.skip(reason="pending: T-OUT-06")
def test_error_object_shape_on_stderr(repo_scenario):
    """T-OUT-06 — the error object shape on stderr is a single
    {"error":{"code","message"}}.

    Given:  a failing invocation under any machine output format
    Expect: single `{"error":{"code","message"}}` object on stderr
    Source: REQ-17
    """
    raise NotImplementedError


@pytest.mark.matrix("T-OUT-07")
@pytest.mark.skip(reason="pending: T-OUT-07")
def test_stable_error_codes_round_trip_in_json(repo_scenario):
    """T-OUT-07 — every stable error code round-trips correctly in the -o json error
    object.

    Given:  each stable error code (conflict_branch_exists, parent_mid_operation,
            session_not_found, verify_failed, repo_no_commits, unmerged_index,
            registry_busy)
    Expect: each round-trips correctly in the `-o json` error object, asserted
            individually
    Source: REQ-17
    """
    raise NotImplementedError


@pytest.mark.matrix("T-OUT-08")
@pytest.mark.skip(reason="pending: T-OUT-08")
def test_dry_run_lists_planned_mutations_and_local_only(repo_scenario):
    """T-OUT-08 — --dry-run output lists every planned mutation and states validation
    was local-only.

    Given:  fork invoked with `--dry-run`
    Expect: output lists every planned mutation (branch, worktree path, files-to-carry
            counts, paste command) and states validation was local-only
    Source: REQ-18
    """
    raise NotImplementedError


@pytest.mark.matrix("T-OUT-09")
@pytest.mark.skip(reason="pending: T-OUT-09")
def test_clipboard_copy_failure_emits_notice_only(repo_scenario):
    """T-OUT-09 — a clipboard copy failure emits a stderr notice without affecting the
    exit code.

    Given:  the clipboard copy step fails
    Expect: a stderr notice is emitted; exit code is unaffected
    Source: DESIGN-DECISIONS D9
    """
    raise NotImplementedError


@pytest.mark.matrix("T-OUT-10")
@pytest.mark.skip(reason="pending: T-OUT-10")
def test_non_c_locale_json_output_byte_identical(repo_scenario):
    """T-OUT-10 — -o json output is byte-identical regardless of a non-C process locale.

    Given:  the process run under a non-C locale
    Expect: `-o json` machine output is byte-identical regardless of process locale
    Source: REQ-38 R9.4
    """
    raise NotImplementedError


@pytest.mark.matrix("T-OUT-11")
@pytest.mark.skip(reason="pending: T-OUT-11")
def test_json_success_object_carries_req17_minimum_fields(repo_scenario):
    """T-OUT-11 — the -o json success object carries the REQ-17 minimum fields.

    Given:  a successful `fork -o json` invocation
    Expect: the success object carries the REQ-17 minimum fields — `agent`,
            `parent_session_id`, `fork.branch`, `fork.worktree`,
            `fork.anchor_commit`, `fork.mode` (state-carry booleans),
            `verification` (per-check results), `command`, `notices[]`
    Source: REQ-17
    """
    raise NotImplementedError
