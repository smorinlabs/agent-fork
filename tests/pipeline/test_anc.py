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
    import os
    import subprocess

    from agent_fork.repository import (
        create_worktree_at_anchor,
        resolve_anchor,
        validate_fork_guards,
    )

    world = repo_scenario(topology)
    expected = subprocess.run(
        ["git", "-C", str(world.parent_path), "rev-parse", "--verify", "HEAD^{commit}"],
        env=world.env,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    anchor = resolve_anchor(world.parent_path, env=world.env)
    assert anchor == expected

    destination = world.parent_path.parent / f"anchor-{topology.replace('/', '-')}"
    branch = f"fork/anchor-{topology.replace('/', '-').replace('@', '-')}"
    validate_fork_guards(world.parent_path, branch, destination, env=world.env)
    created = create_worktree_at_anchor(
        world.parent_path, branch, destination, anchor=anchor, env=world.env
    )
    child_head = subprocess.run(
        ["git", "-C", str(destination), "rev-parse", "HEAD"],
        env=world.env,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    child_branch = subprocess.run(
        ["git", "-C", str(destination), "rev-parse", "--abbrev-ref", "HEAD"],
        env=world.env,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert created.anchor == expected
    assert child_head == expected
    assert child_branch == branch
    assert created.branch_created is True

    if topology == "plain@main":
        assert created.parent_on_default is True
        assert created.branch != "main"
    if topology == "detached":
        assert created.parent_detached is True
    if topology == "linked-worktree":
        assert world.main_path is not None
        main_head = subprocess.run(
            ["git", "-C", str(world.main_path), "rev-parse", "HEAD"],
            env=world.env,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert created.anchor != main_head
        child_common = subprocess.run(
            ["git", "-C", str(destination), "rev-parse", "--git-common-dir"],
            env=world.env,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert os.path.realpath(child_common) == str(created.common_dir)
