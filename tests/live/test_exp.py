"""G-EXP — Live experiments (tier R; E1-E3 additionally require a real agent CLI).

E5 (n/a, absorbed into G-MAT/G-VER core TDD) and E6 (tombstone, pre-0.95 Codex
fallback disambiguation) get no stub.

Matrix: docs/testing/TEST-MATRIX.md §G-EXP.
"""

import pytest


@pytest.mark.matrix("T-EXP-01")
@pytest.mark.requires_real_cli
@pytest.mark.skip(reason="pending: T-EXP-01")
def test_e1_claude_flag_combo_no_silent_noop():
    """T-EXP-01 — E1 — the Claude flag combo runs together with no flag silently
    no-oping.

    Given:  a real Claude CLI invoked non-interactively with `--resume <id>
            --fork-session --session-id <pre-pinned> -n <name>` combined
    Expect: all four flags take effect; none silently no-ops
    Source: RESEARCH §7 E1; EXPERIMENTS.md
    """
    raise NotImplementedError


@pytest.mark.matrix("T-EXP-02")
@pytest.mark.requires_real_cli
@pytest.mark.skip(reason="pending: T-EXP-02")
def test_e2_codex_cross_cwd_fork_explicit_id():
    """T-EXP-02 — E2 — Codex cross-cwd fork with an explicit thread ID bypasses cwd
    filtering.

    Given:  `codex fork <explicit-uuid>` run cross-cwd, plus a `-C <worktree>` variant
    Expect: the explicit ID bypasses cwd filtering; the TUI cwd-change prompt behavior
            is documented
    Source: RESEARCH §7 E2; RESEARCH §5.1 Q4; EXPERIMENTS.md
    """
    raise NotImplementedError


@pytest.mark.matrix("T-EXP-03")
@pytest.mark.requires_real_cli
@pytest.mark.skip(reason="pending: T-EXP-03")
def test_e3_claude_e2e_full_paste_command():
    """T-EXP-03 — E3 — the full Claude paste command run E2E recalls full context in a
    fresh session.

    Given:  the full paste command run in a real worktree
    Expect: full context recall, fresh UUID, parent transcript untouched
    Source: RESEARCH §7 E3; EXPERIMENTS.md
    """
    raise NotImplementedError


@pytest.mark.matrix("T-EXP-04")
@pytest.mark.skip(
    reason="retired: T-EXP-04 until v1.1 (A8 — D14 mooted the .jsonl-copy fallback)"
)
def test_jsonl_copy_last_resort():
    """T-EXP-04 — retired. Returns with the v1.1 fallback ladder."""
    raise NotImplementedError
