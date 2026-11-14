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
    assert any("claude --help" in notice for notice in result.notices)
    assert not any("no longer documents" in notice for notice in result.notices)


@pytest.mark.matrix("T-PRE-29")
def test_unverified_notice_names_the_command_that_actually_ran():
    """Codex declares recipe flags on the subcommand, so `codex --help` is
    the wrong thing to report: it still succeeds when `fork` is gone."""
    from agent_fork.agents import _HELP_ARGS, help_invocation

    assert help_invocation("claude") == "claude --help"
    assert help_invocation("codex") == "codex fork --help"
    for agent in ("claude", "codex"):
        assert help_invocation(agent).split()[1:] == list(_HELP_ARGS[agent])


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


def _opencode_world(repo_scenario, fake_opencode, **build):
    world = repo_scenario()
    fake = fake_opencode(
        {"ses_parent1": {"title": "Parent", "directory": str(world.parent_path)}},
        **build,
    )
    return world, fake, fake.path_env(world.env)


@pytest.mark.matrix("T-PRE-31")
def test_opencode_preflight_confirms_the_parent_session_exists(
    repo_scenario, fake_opencode
):
    """T-PRE-31 — an existing OpenCode session passes; there is no version floor."""
    from agent_fork.agents import AgentContext, preflight_agent

    world, fake, env = _opencode_world(
        repo_scenario, fake_opencode, version="opencode v0.0.1"
    )
    result = preflight_agent(AgentContext("opencode", "ses_parent1"), env)
    assert result.agent == "opencode"
    assert result.version == (0, 0, 1)
    assert result.context == AgentContext("opencode", "ses_parent1")
    assert result.notices == ()
    assert fake.api_ops() == ["session.get"]


@pytest.mark.matrix("T-PRE-32")
def test_opencode_unknown_session_refuses_before_mutation(repo_scenario, fake_opencode):
    """T-PRE-32 — `opencode --session <unknown>` would create a session, so refuse."""
    from agent_fork.agents import AgentContext, preflight_agent
    from agent_fork.errors import AgentPreflightError

    world, fake, env = _opencode_world(repo_scenario, fake_opencode)
    with pytest.raises(AgentPreflightError) as caught:
        preflight_agent(AgentContext("opencode", "ses_missing9"), env)
    assert caught.value.code == "session_not_found"
    assert caught.value.exit_code == 3
    assert "ses_missing9" in str(caught.value)
    assert "not found" in str(caught.value)
    assert "doctor" in str(caught.value)
    assert fake.api_ops() == ["session.get"]


@pytest.mark.matrix("T-PRE-33")
def test_opencode_unreadable_session_lookup_refuses(
    repo_scenario, fake_opencode, monkeypatch
):
    """T-PRE-33 — unreachable, malformed, or slow lookups refuse as unconfirmed."""
    import agent_fork.opencode_api as opencode_api
    from agent_fork.agents import AgentContext, preflight_agent
    from agent_fork.errors import AgentPreflightError

    monkeypatch.setattr(opencode_api, "OPENCODE_API_TIMEOUT", 1)
    world, fake, env = _opencode_world(repo_scenario, fake_opencode)
    failures = (
        {"code": 1, "stderr": "Error: Could not reach server at x: ECONNREFUSED"},
        {"code": 0, "stdout": "not json"},
        {"code": 0, "sleep": 5},
    )
    for failure in failures:
        fake.update(fail={"session.get": failure})
        with pytest.raises(AgentPreflightError) as caught:
            preflight_agent(AgentContext("opencode", "ses_parent1"), env)
        assert caught.value.code == "session_not_found"
        assert "could not confirm OpenCode session ses_parent1" in str(caught.value)
    # A successful reply must describe the parent itself: empty output, a
    # missing id, or another session's id leaves the parent unconfirmed.
    fake.update(fail={})
    for reply in ("", '{"data":{}}', '{"data":{"id":"ses_other9"}}'):
        fake.update(replies={"session.get": reply})
        with pytest.raises(AgentPreflightError) as caught:
            preflight_agent(AgentContext("opencode", "ses_parent1"), env)
        assert caught.value.code == "session_not_found"
        assert "could not confirm OpenCode session ses_parent1" in str(caught.value)


@pytest.mark.matrix("T-PRE-34")
def test_opencode_unsafe_session_id_refuses_before_any_call(
    repo_scenario, fake_opencode
):
    """T-PRE-34 — IDs failing the `ses_` pattern never reach the OpenCode CLI."""
    from agent_fork.agents import AgentContext, preflight_agent
    from agent_fork.errors import AgentPreflightError

    world, fake, env = _opencode_world(repo_scenario, fake_opencode)
    for unsafe in ("parent1", "ses_x;rm -rf", "ses_\x1b[31m", "ses_"):
        with pytest.raises(AgentPreflightError, match="not a valid OpenCode session"):
            preflight_agent(AgentContext("opencode", unsafe), env)
    assert fake.api_ops() == []


@pytest.mark.matrix("T-PRE-35")
def test_opencode_recipe_flag_matches_the_rendered_resume_command(
    repo_scenario, fake_opencode
):
    """T-PRE-35 — the paste command's one flag is declared and probed in help."""
    import re
    from pathlib import Path

    from agent_fork.agents import (
        AgentContext,
        build_launch_command,
        help_invocation,
        preflight_agent,
        recipe_flags,
    )

    assert recipe_flags("opencode") == ("--session",)
    assert help_invocation("opencode") == "opencode --help"
    launch = build_launch_command(
        AgentContext("opencode", "ses_parent1"),
        worktree=Path("/tmp/wt"),
        name="demo",
        child_session_id="ses_child1",
    )
    assert launch.command == "cd /tmp/wt && opencode --session ses_child1"
    assert launch.child_session_id == "ses_child1"
    rendered = set(re.findall(r"(?<!\S)-{1,2}[A-Za-z][\w-]*", launch.command))
    assert rendered == set(recipe_flags("opencode"))
    world, fake, env = _opencode_world(
        repo_scenario, fake_opencode, help_text="USAGE\n  opencode [flags]\n"
    )
    result = preflight_agent(AgentContext("opencode", "ses_parent1"), env)
    assert any("no longer documents --session" in notice for notice in result.notices)
