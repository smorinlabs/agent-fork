"""G-CLI — CLI conformance (tier C).

Matrix: docs/testing/TEST-MATRIX.md §G-CLI.
"""

import pytest


@pytest.mark.matrix("T-CLI-01")
@pytest.mark.skip(reason="pending: T-CLI-01")
def test_bare_invocation_prints_help_exit_0(repo_scenario):
    """T-CLI-01 — bare `agent-fork` prints help on stdout and exits 0.

    Given:  `agent-fork` invoked with no arguments
    Expect: help on stdout, exit 0
    Source: REQ-06; DESIGN-DECISIONS D1
    """
    raise NotImplementedError


@pytest.mark.matrix("T-CLI-02")
@pytest.mark.skip(reason="pending: T-CLI-02")
def test_standard_global_flags_present(repo_scenario):
    """T-CLI-02 — standard global flags are present and each behaves correctly.

    Given:  each of -h/--help, -V/--version, repeated -v, -q, --config, --debug invoked
    Expect: `-V/--version` prints `agent-fork <semver>`; each flag asserted individually
    Source: REQ-10
    """
    raise NotImplementedError


@pytest.mark.matrix("T-CLI-03")
@pytest.mark.skip(reason="pending: T-CLI-03")
def test_malformed_usage_exits_2(repo_scenario):
    """T-CLI-03 — malformed usage exits 2.

    Given:  a malformed command-line invocation
    Expect: exit 2
    Source: REQ-11
    """
    raise NotImplementedError


@pytest.mark.matrix("T-CLI-04")
@pytest.mark.skip(reason="pending: T-CLI-04")
def test_unknown_agent_value_exits_3(repo_scenario):
    """T-CLI-04 — an unknown --agent value exits 3.

    Given:  `--agent` passed an unrecognized value
    Expect: exit 3
    Source: REQ-11; REQ-03
    """
    raise NotImplementedError


@pytest.mark.matrix("T-CLI-05")
@pytest.mark.skip(reason="pending: T-CLI-05")
def test_completion_subcommand_smoke_per_shell(repo_scenario):
    """T-CLI-05 — the completion subcommand is smoke-tested for bash, zsh, and fish.

    Given:  `completion bash`, `completion zsh`, and `completion fish` each invoked
    Expect: each shell's completion script is produced without error, asserted
            individually
    Source: REQUIREMENTS §3.2
    """
    raise NotImplementedError


@pytest.mark.parametrize(
    "subject",
    [
        pytest.param(
            "git-version", id="T-CLI-06", marks=pytest.mark.matrix("T-CLI-06")
        ),
        pytest.param("agent-clis", id="T-CLI-07", marks=pytest.mark.matrix("T-CLI-07")),
        pytest.param(
            "env-signals", id="T-CLI-08", marks=pytest.mark.matrix("T-CLI-08")
        ),
        pytest.param(
            "config-validity", id="T-CLI-09", marks=pytest.mark.matrix("T-CLI-09")
        ),
        pytest.param("xdg-paths", id="T-CLI-10", marks=pytest.mark.matrix("T-CLI-10")),
    ],
)
@pytest.mark.skip(reason="pending: T-CLI-06..T-CLI-10 family")
def test_doctor_content_reports_each_subject(repo_scenario, subject):
    """`doctor` reports content for each subject it checks.

    T-CLI-06 — git version is reported against the named PRODUCT_GIT_MIN check.
    T-CLI-07 — agent CLIs found and their versions are reported against the version
    matrix.
    T-CLI-08 — env signals visible (Claude/Codex detection env vars) are reported.
    T-CLI-09 — config valid/invalid is reported.
    T-CLI-10 — XDG paths writable is reported.
    Source: REQ-38; git-version row also cites A9 (spec §8 A9)
    """
    raise NotImplementedError


@pytest.mark.matrix("T-CLI-11")
@pytest.mark.skip(reason="pending: T-CLI-11")
def test_a14_failing_doctor_check_nonzero_exit(repo_scenario):
    """T-CLI-11 — A14 — a failing doctor check produces a non-zero exit.

    Given:  a doctor check that fails
    Expect: non-zero exit
    Source: REQ-38 (A14); spec §8 A14
    """
    raise NotImplementedError


@pytest.mark.matrix("T-CLI-12")
@pytest.mark.skip(reason="pending: T-CLI-12")
def test_clean_flag_rejected_as_unknown(repo_scenario):
    """T-CLI-12 — `--clean` is rejected as an unknown flag in v1.

    Given:  `fork --clean` invoked
    Expect: usage error, exit 2 (D2; the `--clean` alias is deferred to v1.1+)
    Source: REQUIREMENTS §3.3 (D2)
    """
    raise NotImplementedError
