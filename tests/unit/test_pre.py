"""G-PRE unit rows for agent version policy."""

import pytest


def _context(agent="claude"):
    from agent_fork.agents import AgentContext

    return AgentContext(agent, "12345678-1234-1234-1234-123456789abc")


@pytest.mark.matrix("T-PRE-02")
def test_claude_below_pinned_id_fork_floor_refuses(repo_scenario):
    from agent_fork.agents import preflight_agent
    from agent_fork.errors import AgentPreflightError

    world = repo_scenario()
    with pytest.raises(AgentPreflightError, match=r"2\.0\.72.*2\.0\.73.*doctor"):
        preflight_agent(
            _context(), world.env, executable="/fake/claude", version_output="2.0.72"
        )


@pytest.mark.matrix("T-PRE-03")
def test_claude_warn_band_warns_and_proceeds(repo_scenario):
    from agent_fork.agents import preflight_agent

    world = repo_scenario()
    result = preflight_agent(
        _context(),
        world.env,
        executable="/fake/claude",
        version_output="Claude Code v2.1.99",
    )
    assert result.version == (2, 1, 99)
    assert result.verify is True
    assert result.notices and "reliable worktree-resume" in result.notices[0]


@pytest.mark.matrix("T-PRE-04")
def test_codex_below_fork_subcommand_floor_refuses(repo_scenario):
    from agent_fork.agents import preflight_agent
    from agent_fork.errors import AgentPreflightError

    world = repo_scenario()
    with pytest.raises(AgentPreflightError, match=r"0\.80\.9.*0\.81\.0.*doctor"):
        preflight_agent(
            _context("codex"),
            world.env,
            executable="/fake/codex",
            version_output="codex-cli 0.80.9",
        )
