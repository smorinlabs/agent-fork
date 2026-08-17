"""G-CLN cleanup targeting, mutation, and guard proofs."""

import subprocess

import pytest


def _forked(repo_scenario, name="cleanup"):
    from agent_fork.agents import AgentContext
    from agent_fork.pipeline import ForkRequest, fork
    from conftest import origin

    world = repo_scenario("plain@main", remote=origin())
    request = ForkRequest(
        parent=world.parent_path,
        destination=world.parent_path.parent / f"child-{name}",
        name=name,
        branch=f"fork/{name}",
        agent=AgentContext("claude", "11111111-1111-1111-1111-111111111111"),
        agent_executable="/fake/claude",
        agent_version_output="Claude Code 2.1.220",
        git_version_output="git version 2.43.0",
        child_session_id="33333333-3333-3333-3333-333333333333",
    )
    return world, fork(request, env=world.env)


def _branch_exists(world, branch):
    return (
        subprocess.run(
            [
                "git",
                "-C",
                str(world.parent_path),
                "show-ref",
                "--verify",
                "--quiet",
                f"refs/heads/{branch}",
            ],
            env=world.env,
        ).returncode
        == 0
    )


@pytest.mark.matrix("T-CLN-01")
def test_cleanup_target_accepts_name_branch_or_path(repo_scenario):
    from agent_fork.cleanup import resolve_cleanup_target

    for form in ("name", "branch", "path"):
        world, result = _forked(repo_scenario, name=f"target-{form}")
        target = {
            "name": f"target-{form}",
            "branch": f"fork/target-{form}",
            "path": str(result.creation.path),
        }[form]
        plan = resolve_cleanup_target(target, cwd=world.parent_path, env=world.env)
        assert plan.entry.name == f"target-{form}"
        assert plan.branch == f"fork/target-{form}"
        assert plan.worktree == result.creation.path


@pytest.mark.matrix("T-CLN-02")
def test_cleanup_removes_and_prunes_worktree(repo_scenario):
    from agent_fork.cleanup import cleanup, resolve_cleanup_target

    world, forked = _forked(repo_scenario)
    plan = resolve_cleanup_target("cleanup", cwd=world.parent_path, env=world.env)
    result = cleanup(plan, cwd=world.parent_path, env=world.env)
    assert result.removed and not forked.creation.path.exists()
    listing = subprocess.run(
        ["git", "-C", str(world.parent_path), "worktree", "list", "--porcelain"],
        env=world.env,
        capture_output=True,
        check=True,
    ).stdout.decode()
    assert str(forked.creation.path) not in listing


@pytest.mark.matrix("T-SES-15")
def test_cleanup_retains_claude_lineage(repo_scenario):
    from agent_fork.cleanup import cleanup, resolve_cleanup_target
    from agent_fork.lineage import find_lineage

    world, _ = _forked(repo_scenario, name="lineage-retained")
    child = "33333333-3333-3333-3333-333333333333"
    assert find_lineage("claude", child, env=world.env) is not None
    plan = resolve_cleanup_target(
        "lineage-retained", cwd=world.parent_path, env=world.env
    )
    cleanup(plan, cwd=world.parent_path, env=world.env)
    claim = find_lineage("claude", child, env=world.env)
    assert claim is not None
    assert claim.parent_session_id == "11111111-1111-1111-1111-111111111111"


@pytest.mark.matrix("T-CLN-03")
def test_cleanup_deletes_branch_unless_keep_branch(repo_scenario):
    from agent_fork.cleanup import cleanup, resolve_cleanup_target

    world, _ = _forked(repo_scenario, "delete")
    cleanup(
        resolve_cleanup_target("delete", cwd=world.parent_path, env=world.env),
        cwd=world.parent_path,
        env=world.env,
    )
    assert not _branch_exists(world, "fork/delete")

    kept_world, _ = _forked(repo_scenario, "kept")
    cleanup(
        resolve_cleanup_target("kept", cwd=kept_world.parent_path, env=kept_world.env),
        cwd=kept_world.parent_path,
        env=kept_world.env,
        keep_branch=True,
    )
    assert _branch_exists(kept_world, "fork/kept")


@pytest.mark.matrix("T-CLN-04")
def test_cleanup_removes_registry_entry(repo_scenario):
    from agent_fork.cleanup import cleanup, resolve_cleanup_target
    from agent_fork.registry import find_candidates

    world, _ = _forked(repo_scenario)
    cleanup(
        resolve_cleanup_target("cleanup", cwd=world.parent_path, env=world.env),
        cwd=world.parent_path,
        env=world.env,
    )
    assert not find_candidates("cleanup", env=world.env)


@pytest.mark.parametrize(
    "guard",
    [
        pytest.param(
            "dirty-worktree", id="T-CLN-05", marks=pytest.mark.matrix("T-CLN-05")
        ),
        pytest.param(
            "unpushed-commits", id="T-CLN-06", marks=pytest.mark.matrix("T-CLN-06")
        ),
        pytest.param(
            "target-is-cwd", id="T-CLN-07", marks=pytest.mark.matrix("T-CLN-07")
        ),
    ],
)
def test_cleanup_guard_refuses_without_force(repo_scenario, guard):
    from agent_fork.cleanup import cleanup, resolve_cleanup_target
    from agent_fork.errors import PreconditionError

    world, result = _forked(repo_scenario, guard)
    if guard == "dirty-worktree":
        (result.creation.path / "dirty.txt").write_text("dirty\n")
    elif guard == "unpushed-commits":
        (result.creation.path / "commit.txt").write_text("commit\n")
        subprocess.run(
            ["git", "-C", str(result.creation.path), "add", "commit.txt"],
            env=world.env,
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(result.creation.path), "commit", "-m", "unpushed"],
            env=world.env,
            check=True,
        )
    plan = resolve_cleanup_target(guard, cwd=world.parent_path, env=world.env)
    cwd = result.creation.path if guard == "target-is-cwd" else world.parent_path
    with pytest.raises(PreconditionError) as captured:
        cleanup(plan, cwd=cwd, env=world.env)
    assert captured.value.exit_code == 5
    assert guard.replace("-", "_") in captured.value.code
    assert result.creation.path.exists()


@pytest.mark.matrix("T-CLN-08")
def test_cleanup_force_extends_targeting_and_overrides_guards(repo_scenario):
    from agent_fork.cleanup import cleanup, resolve_cleanup_target
    from agent_fork.repository import create_worktree_at_anchor
    from conftest import origin

    world = repo_scenario("plain@main", remote=origin())
    target = world.parent_path.parent / "outside"
    create_worktree_at_anchor(world.parent_path, "outside", target, env=world.env)
    (target / "dirty").write_text("dirty\n")
    plan = resolve_cleanup_target(
        str(target), cwd=world.parent_path, env=world.env, force=True
    )
    assert not plan.owned
    result = cleanup(plan, cwd=world.parent_path, env=world.env, force=True)
    assert result.removed and not target.exists()


@pytest.mark.matrix("T-CLN-14")
def test_cleanup_force_does_not_override_cwd_guard(repo_scenario):
    from agent_fork.cleanup import cleanup, resolve_cleanup_target
    from agent_fork.errors import PreconditionError

    world, result = _forked(repo_scenario, "cwd-force")
    plan = resolve_cleanup_target("cwd-force", cwd=world.parent_path, env=world.env)
    with pytest.raises(PreconditionError) as captured:
        cleanup(plan, cwd=result.creation.path, env=world.env, force=True)
    assert captured.value.code == "cleanup_target_is_cwd"
    assert result.creation.path.exists()


@pytest.mark.matrix("T-CLN-12")
def test_cleanup_never_deletes_session_files(repo_scenario):
    from agent_fork.cleanup import cleanup, resolve_cleanup_target

    world, _ = _forked(repo_scenario, "session")
    session = world.parent_path.parent / "agent-home/session.jsonl"
    session.parent.mkdir()
    session.write_text("conversation\n")
    result = cleanup(
        resolve_cleanup_target("session", cwd=world.parent_path, env=world.env),
        cwd=world.parent_path,
        env=world.env,
    )
    assert session.read_text() == "conversation\n"
    assert any(
        "remains resumable" in notice and "archived" in notice
        for notice in result.notices
    )
