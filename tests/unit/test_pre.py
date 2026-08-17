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


@pytest.mark.matrix("T-PRE-21")
def test_ambiguous_version_output_warns_and_names_the_parse(repo_scenario):
    """A4(a): banner-polluted output must not misparse silently."""
    from agent_fork.agents import preflight_agent

    world = repo_scenario()
    result = preflight_agent(
        _context(),
        world.env,
        executable="/fake/claude",
        version_output="notice: new version 10.2.3 available\n2.1.233 (Claude Code)",
    )
    assert result.version == (10, 2, 3)
    assert any("ambiguous" in notice for notice in result.notices)


@pytest.mark.matrix("T-PRE-22")
def test_single_version_token_emits_no_ambiguity_notice(repo_scenario):
    from agent_fork.agents import preflight_agent

    world = repo_scenario()
    result = preflight_agent(
        _context(),
        world.env,
        executable="/fake/claude",
        version_output="2.1.233 (Claude Code)",
    )
    assert result.version == (2, 1, 233)
    assert not any("ambiguous" in notice for notice in result.notices)


@pytest.mark.matrix("T-PRE-23")
def test_absent_recipe_flag_warns_and_proceeds(repo_scenario):
    """A4(b): a dropped recipe flag warns before mutation, never refuses."""
    from agent_fork.agents import preflight_agent

    world = repo_scenario()
    result = preflight_agent(
        _context(),
        world.env,
        executable="/fake/claude",
        version_output="2.1.233 (Claude Code)",
        help_output="  -r, --resume [value]\n  --session-id <uuid>\n  -n, --name <x>",
    )
    assert result.verify is True
    assert any("--fork-session" in notice for notice in result.notices)


@pytest.mark.matrix("T-PRE-24")
def test_codex_recipe_flag_probe_detects_absent_cd_flag():
    from agent_fork.agents import missing_recipe_flags

    assert missing_recipe_flags("codex", "  -c, --config <key=value>\n") == ("-C",)
    assert missing_recipe_flags("codex", "  -C, --cd <DIR>\n") == ()


@pytest.mark.matrix("T-PRE-25")
def test_unreadable_help_reports_unverified_not_supported(repo_scenario):
    """Third state: no evidence must not read as verified support."""
    from agent_fork.agents import preflight_agent

    world = repo_scenario()
    result = preflight_agent(
        _context(),
        world.env,
        executable="/fake/claude",
        version_output="2.1.233 (Claude Code)",
        help_output="",
    )
    assert result.verify is True
    assert any("unverified" in notice for notice in result.notices)
    assert not any("no longer documents" in notice for notice in result.notices)


@pytest.mark.matrix("T-PRE-27")
def test_removal_prose_does_not_prove_a_flag_survives():
    """Prose mentioning a flag is not an option declaration."""
    from agent_fork.agents import missing_recipe_flags

    prose = "This option replaces --fork-session; use --resume and --session-id."
    assert set(missing_recipe_flags("claude", prose)) == {
        "--session-id",
        "--resume",
        "--fork-session",
        "-n",
    }
    assert missing_recipe_flags("codex", "The old -C flag is no longer supported.") == (
        "-C",
    )


@pytest.mark.matrix("T-PRE-28")
def test_undecodable_help_never_raises_out_of_the_probe(tmp_path):
    """`never refuse` must hold for undecodable bytes, not just clean output."""
    import os

    from agent_fork.agents import read_help

    stub = tmp_path / "claude"
    stub.write_text('#!/bin/sh\nprintf "\\377"\n')
    stub.chmod(0o755)
    assert read_help("claude", str(stub), dict(os.environ)) is None


@pytest.mark.matrix("T-PRE-26")
def test_declared_recipe_flags_cover_every_rendered_flag():
    """Guards the flag list against drift in the rendered recipe itself."""
    import re
    from pathlib import Path

    from agent_fork.agents import build_launch_command, recipe_flags

    for agent in ("claude", "codex"):
        launch = build_launch_command(
            _context(agent), worktree=Path("/tmp/wt"), name="demo"
        )
        rendered = set(re.findall(r"(?<!\S)-{1,2}[A-Za-z][\w-]*", launch.command))
        declared = set(recipe_flags(agent))
        assert rendered, f"no flags rendered for {agent}"
        # Equality, not subset: a subset check lets a declared flag go stale
        # after the renderer stops emitting it, leaving the probe guarding a
        # flag the recipe no longer uses.
        assert rendered == declared, f"{agent}: {rendered ^ declared} out of step"
