"""G-ANC — Anchor & topology (tier F).

Matrix: docs/testing/TEST-MATRIX.md §G-ANC.
"""

import pytest


@pytest.mark.parametrize(
    "topology",
    [
        pytest.param(
            "plain@branch", id="T-ANC-01", marks=pytest.mark.matrix("T-ANC-01")
        ),
        pytest.param("plain@main", id="T-ANC-02", marks=pytest.mark.matrix("T-ANC-02")),
        pytest.param("detached", id="T-ANC-03", marks=pytest.mark.matrix("T-ANC-03")),
        pytest.param(
            "linked-worktree", id="T-ANC-04", marks=pytest.mark.matrix("T-ANC-04")
        ),
        pytest.param("bare@bare", id="T-ANC-05", marks=pytest.mark.matrix("T-ANC-05")),
        pytest.param("bare@wt", id="T-ANC-06", marks=pytest.mark.matrix("T-ANC-06")),
        pytest.param(
            "dot-bare@wt", id="T-ANC-07", marks=pytest.mark.matrix("T-ANC-07")
        ),
        pytest.param(
            "nested-bare", id="T-ANC-08", marks=pytest.mark.matrix("T-ANC-08")
        ),
    ],
)
@pytest.mark.skip(reason="pending: T-ANC-01..T-ANC-08 family")
def test_anchor_equals_parent_head_per_topology(repo_scenario, topology):
    """Parent-HEAD anchoring holds across every topology value.

    T-ANC-01 — plain@branch: anchor == parent HEAD^{commit} resolved at the parent's own
    path.
    T-ANC-02 — plain@main: anchor == parent HEAD^{commit}; fork branch != default branch
    recorded.
    T-ANC-03 — detached HEAD: anchor == parent HEAD^{commit} (a commit, not a ref);
    parent-detached recorded.
    T-ANC-04 — linked-worktree: anchor == this worktree's own HEAD; git-common-dir
    matches the parent's.
    T-ANC-05 — bare@bare (invoked at the bare root): anchor == bare HEAD^{commit}.
    T-ANC-06 — bare@wt (invoked from a worktree of a bare project): anchor == the
    invoking worktree's HEAD^{commit}.
    T-ANC-07 — dot-bare@wt (.bare/ layout, invoked from a worktree): anchor == the
    invoking worktree's HEAD^{commit}.
    T-ANC-08 — nested-bare: anchor == HEAD^{commit} resolved through the nested bare
    child.
    Source: REQ-20; RESEARCH §2.3/§4 (per-row citation varies, see TEST-MATRIX.md
            §G-ANC)
    """
    raise NotImplementedError
