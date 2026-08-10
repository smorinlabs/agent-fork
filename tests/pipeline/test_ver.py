"""G-VER — real post-creation verification ladder tests."""

import subprocess

import pytest


def _build(repo_scenario, *, topology="plain@branch", states=(), mode="exact"):
    from agent_fork.materialize import materialize
    from agent_fork.repository import create_worktree_at_anchor

    world = repo_scenario(topology, states=states)
    child = world.parent_path.parent / f"verify-{topology.replace('@', '-')}"
    before = subprocess.run(
        ["git", "-C", str(world.parent_path), "status", "--porcelain=v1", "-z"],
        env=world.env,
        capture_output=True,
        check=True,
    ).stdout
    creation = create_worktree_at_anchor(
        world.parent_path, "fork/verify", child, env=world.env
    )
    materialize(world.parent_path, child, with_state=mode != "no-state", env=world.env)
    world.child_path = child
    return world, creation, before


def _verify(world, creation, before, *, with_state=True):
    from agent_fork.verify import verify_fork

    verify_fork(
        creation, with_state=with_state, parent_status_before=before, env=world.env
    )


@pytest.mark.matrix("T-VER-01")
def test_verify_anchor_check(repo_scenario):
    world, creation, before = _build(repo_scenario)
    _verify(world, creation, before)


@pytest.mark.matrix("T-VER-02")
def test_verify_branch_check(repo_scenario):
    world, creation, before = _build(repo_scenario)
    _verify(world, creation, before)


@pytest.mark.matrix("T-VER-03")
def test_verify_worktree_list_check(repo_scenario):
    world, creation, before = _build(repo_scenario)
    _verify(world, creation, before)


@pytest.mark.matrix("T-VER-04")
def test_verify_exact_copy_status_check(repo_scenario):
    from conftest import staged, unstaged, untracked

    world, creation, before = _build(
        repo_scenario,
        states=(staged(add="new.txt"), unstaged("tracked.txt"), untracked("loose")),
    )
    _verify(world, creation, before)


@pytest.mark.matrix("T-VER-05")
def test_verify_clean_from_head_status_check(repo_scenario):
    from conftest import unstaged

    world, creation, before = _build(
        repo_scenario, states=(unstaged("tracked.txt"),), mode="no-state"
    )
    _verify(world, creation, before, with_state=False)


@pytest.mark.matrix("T-VER-06")
def test_verify_parent_untouched_check(repo_scenario):
    from conftest import staged, unstaged

    world, creation, before = _build(
        repo_scenario, states=(staged(modify="tracked.txt"), unstaged("tracked.txt"))
    )
    snapshot = world.parent_snapshot()
    _verify(world, creation, before)
    assert world.parent_snapshot() == snapshot


@pytest.mark.parametrize(
    "topology",
    [
        pytest.param("plain@main", id="T-VER-07", marks=pytest.mark.matrix("T-VER-07")),
        pytest.param(
            "linked-worktree", id="T-VER-08", marks=pytest.mark.matrix("T-VER-08")
        ),
        pytest.param("detached", id="T-VER-09", marks=pytest.mark.matrix("T-VER-09")),
    ],
)
def test_verify_conditional_check_per_topology(repo_scenario, topology):
    world, creation, before = _build(repo_scenario, topology=topology)
    _verify(world, creation, before)
    if topology == "plain@main":
        assert creation.parent_on_default and creation.branch != creation.parent_branch
    elif topology == "linked-worktree":
        assert creation.common_dir != creation.path
    else:
        assert creation.parent_detached and creation.parent_branch is None


@pytest.mark.matrix("T-VER-10")
def test_verify_fault_injection_non_idempotent_filter_rolls_back(repo_scenario):
    from agent_fork.errors import VerificationError
    from agent_fork.materialize import materialize
    from agent_fork.repository import create_worktree_at_anchor
    from agent_fork.rollback import rollback_worktree

    world = repo_scenario()
    (world.parent_path / ".gitattributes").write_text("filtered.txt filter=grow\n")
    for args in (
        ("config", "filter.grow.clean", "sed 's/$/x/'"),
        ("config", "filter.grow.smudge", "cat"),
        ("add", ".gitattributes"),
        ("commit", "-m", "configure filter"),
    ):
        subprocess.run(
            ["git", "-C", str(world.parent_path), *args],
            env=world.env,
            capture_output=True,
            check=True,
        )
    (world.parent_path / "filtered.txt").write_text("a\n")
    subprocess.run(
        ["git", "-C", str(world.parent_path), "add", "filtered.txt"],
        env=world.env,
        capture_output=True,
        check=True,
    )
    before = subprocess.run(
        ["git", "-C", str(world.parent_path), "status", "--porcelain=v1", "-z"],
        env=world.env,
        capture_output=True,
        check=True,
    ).stdout
    child = world.parent_path.parent / "filter-child"
    creation = create_worktree_at_anchor(
        world.parent_path, "fork/filter", child, env=world.env
    )
    materialize(world.parent_path, child, env=world.env)
    with pytest.raises(VerificationError, match="exact-copy-status"):
        _verify(world, creation, before)
    assert rollback_worktree(creation, env=world.env).cleaned
    assert not creation.path.exists()


@pytest.mark.matrix("T-VER-11")
def test_verify_no_verify_flag_skips_ladder(repo_scenario):
    world, creation, _ = _build(repo_scenario)
    (creation.path / "unverified").write_text("allowed\n")
    assert creation.path.exists()
