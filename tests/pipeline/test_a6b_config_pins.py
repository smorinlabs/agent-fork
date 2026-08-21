"""G-FIX — A6b step 2: `config_pins` at the `run_git` chokepoint.

Design: docs/superpowers/plans/2026-08-17-p02-a6-dirty-submodules.md, "Semantic
pins on recursive commands". `run_git` is the one place every Git invocation
passes through; pins have to enter there because the environment channel is
deliberately closed (A2's `without_config_injection`). No caller passes pins
yet — this only proves the primitive itself is inert until used.
"""

from __future__ import annotations

import pytest


@pytest.mark.matrix("T-FIX-30")
def test_config_pins_are_prepended_as_dash_c_flags(repo_scenario):
    """A pin reaches Git as `-c key=value`, before the subcommand."""
    from agent_fork.git import run_git

    world = repo_scenario("plain@main")
    result = run_git(
        world.parent_path,
        ["config", "--get", "user.pinnedtest"],
        config_pins=(("user.pinnedtest", "from-a-pin"),),
        env=world.env,
        check=False,
    )
    assert result.stdout.decode().strip() == "from-a-pin"


@pytest.mark.matrix("T-FIX-31")
def test_config_pins_default_to_empty_and_change_nothing(repo_scenario):
    """No caller passes pins yet — the default must be behaviourally inert."""
    from agent_fork.git import run_git

    world = repo_scenario("plain@main")
    with_default = run_git(
        world.parent_path, ["status", "--porcelain=v1"], env=world.env
    )
    with_empty_pins = run_git(
        world.parent_path,
        ["status", "--porcelain=v1"],
        config_pins=(),
        env=world.env,
    )
    assert with_default.stdout == with_empty_pins.stdout


@pytest.mark.matrix("T-FIX-32")
def test_config_pins_survive_config_injection_stripping(repo_scenario):
    """Pins are not the environment-injection channel A2 closed.

    `without_config_injection` strips `GIT_CONFIG_COUNT`/`GIT_CONFIG_KEY_*`/
    `GIT_CONFIG_PARAMETERS` from the environment before every `run_git` call.
    Pins must still reach Git even when a caller's environment carries (and
    loses) an unrelated injection attempt, proving pins are a distinct,
    explicit channel rather than routed through the same environment path.
    """
    from agent_fork.git import run_git

    world = repo_scenario("plain@main")
    hostile_env = {
        **world.env,
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "user.hostile",
        "GIT_CONFIG_VALUE_0": "should-not-appear",
    }
    result = run_git(
        world.parent_path,
        ["config", "--get", "user.pinnedtest"],
        config_pins=(("user.pinnedtest", "pin-wins"),),
        env=hostile_env,
        check=False,
    )
    assert result.stdout.decode().strip() == "pin-wins"
    hostile = run_git(
        world.parent_path,
        ["config", "--get", "user.hostile"],
        env=hostile_env,
        check=False,
    )
    assert hostile.returncode != 0, (
        "run_git must strip GIT_CONFIG_KEY_0/VALUE_0 before invoking git, so "
        "the injected user.hostile must not be visible to git's own eyes "
        "through this same call"
    )
