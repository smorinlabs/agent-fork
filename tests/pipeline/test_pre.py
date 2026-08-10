"""G-PRE refusal, Git-floor, rollout, and no-mutation proofs."""

import subprocess

import pytest


def _context(agent="claude"):
    from agent_fork.agents import AgentContext

    return AgentContext(agent, "12345678-1234-1234-1234-123456789abc")


@pytest.mark.matrix("T-PRE-01")
def test_agent_cli_entirely_missing_refuses_with_diagnosis(repo_scenario):
    from agent_fork.agents import preflight_agent
    from agent_fork.errors import AgentPreflightError

    world = repo_scenario()
    with pytest.raises(AgentPreflightError) as captured:
        preflight_agent(_context(), {**world.env, "PATH": ""})
    assert captured.value.exit_code == 3
    message = str(captured.value)
    assert "agent=claude" in message
    assert "claude CLI is missing" in message
    assert "agent-fork doctor" in message


@pytest.mark.matrix("T-PRE-05")
def test_codex_rollout_not_flushed_refuses_before_mutation(repo_scenario):
    from agent_fork.agents import preflight_agent
    from agent_fork.errors import AgentPreflightError

    world = repo_scenario()
    snapshot = world.parent_snapshot()
    with pytest.raises(AgentPreflightError, match=r"not flushed.*doctor"):
        preflight_agent(
            _context("codex"),
            world.env,
            executable="/fake/codex",
            version_output="codex-cli 0.145.0",
        )
    assert world.parent_snapshot() == snapshot
    assert not list(world.parent_path.parent.glob("*fork*"))

    context = _context("codex")
    rollout = (
        world.parent_path.parent
        / "codex-home/sessions/2026/08/10"
        / f"rollout-2026-08-10T00-00-00-{context.parent_session_id}.jsonl"
    )
    rollout.parent.mkdir(parents=True)
    rollout.write_text("{}\n")
    result = preflight_agent(
        context,
        {**world.env, "CODEX_HOME": str(world.parent_path.parent / "codex-home")},
        executable="/fake/codex",
        version_output="codex-cli 0.145.0",
    )
    assert result.version == (0, 145, 0)


@pytest.mark.parametrize(
    "version,passes",
    [
        pytest.param(
            "git version 2.18.9",
            False,
            id="T-PRE-06",
            marks=pytest.mark.matrix("T-PRE-06"),
        ),
        pytest.param(
            "git version 2.19.0.windows.1",
            True,
            id="T-PRE-07",
            marks=pytest.mark.matrix("T-PRE-07"),
        ),
    ],
)
def test_product_git_min_boundary_blocked_on_a9(repo_scenario, version, passes):
    from agent_fork.agents import preflight_git
    from agent_fork.errors import PreconditionError
    from agent_fork.git import PRODUCT_GIT_MIN

    repo_scenario()
    assert PRODUCT_GIT_MIN == (2, 19, 0)
    if passes:
        assert preflight_git(version) == ()
    else:
        with pytest.raises(PreconditionError) as captured:
            preflight_git(version)
        assert captured.value.code == "git_version_unsupported"


@pytest.mark.matrix("T-PRE-08")
def test_a14_below_floor_fork_refusal_names_remedy(repo_scenario):
    from agent_fork.agents import preflight_git
    from agent_fork.errors import PreconditionError

    repo_scenario()
    with pytest.raises(PreconditionError) as captured:
        preflight_git("git version 2.18.9")
    assert captured.value.exit_code == 5
    message = str(captured.value)
    assert "2.18.9" in message and "2.19.0" in message
    assert "upgrade Git" in message and "re-run" in message


@pytest.mark.matrix("T-PRE-09")
def test_a14_force_overrides_git_floor_refusal_only(repo_scenario):
    from agent_fork.agents import preflight_git

    repo_scenario()
    notices = preflight_git("git version 2.18.9", force=True, verify=True)
    assert len(notices) == 1
    assert "--force overrides Git floor only" in notices[0]
    with pytest.raises(ValueError, match="must not disable verification"):
        preflight_git("git version 2.18.9", force=True, verify=False)


@pytest.mark.matrix("T-PRE-10")
def test_d14_nothing_created_on_preflight_refusal(repo_scenario):
    from agent_fork.agents import preflight_agent
    from agent_fork.errors import AgentPreflightError

    world = repo_scenario()
    before = subprocess.run(
        ["git", "-C", str(world.parent_path), "worktree", "list", "--porcelain"],
        env=world.env,
        capture_output=True,
        check=True,
    ).stdout
    snapshot = world.parent_snapshot()
    with pytest.raises(AgentPreflightError):
        preflight_agent(_context(), {**world.env, "PATH": ""})
    after = subprocess.run(
        ["git", "-C", str(world.parent_path), "worktree", "list", "--porcelain"],
        env=world.env,
        capture_output=True,
        check=True,
    ).stdout
    assert after == before
    assert world.parent_snapshot() == snapshot
    branch = subprocess.run(
        ["git", "-C", str(world.parent_path), "branch", "--list", "fork/*"],
        env=world.env,
        capture_output=True,
        check=True,
    ).stdout
    assert branch == b""
