"""G-GRD — Git configuration injection cannot alter a fork (A2 / issue #35).

Git reads settings from three places: files, the command line, and the
environment. `GIT_CONFIG_COUNT` with `GIT_CONFIG_KEY_<n>`/`GIT_CONFIG_VALUE_<n>`
injects settings inline through the environment. Those have no legitimate use
in agent-fork's own subprocesses, and `git-config(1)` places them above
configuration files in precedence, so an injected value silently outranks what
the repository and the user actually configured.

The demonstrated consequence (2026-08-17): with `core.symlinks=false` injected,
a fork produced a child whose **committed** symlink had become a regular file,
and reported success. Verification did not catch it because verification is
scoped to *carried* paths, while the child's copy of committed content comes
from the checkout `git worktree add` performs.

The defence is to **strip both inline-injection channels** — the
`GIT_CONFIG_COUNT` triple and `GIT_CONFIG_PARAMETERS` — in `run_git`. That
removes the need to enumerate which configuration *keys* matter, but it still
requires enumerating *channels*: the first revision stripped only the triple
and left `GIT_CONFIG_PARAMETERS` open.

Two things are deliberately *not* done, each because probing showed they would
be wrong:

* `GIT_CONFIG_GLOBAL` and `GIT_CONFIG_SYSTEM` are **not** stripped. They name
  configuration *files*, which is how tooling — including this test harness —
  deliberately controls Git; discarding them would amount to ignoring the
  user's configuration rather than protecting it.
* The parent's checkout-affecting values are **not** forced onto
  `worktree add`. Under file-based configuration, agent-fork was measured to
  behave identically to plain `git worktree add`; overriding that would
  substitute the tool's judgement for the user's own explicit setting.
"""

from __future__ import annotations

import subprocess

import pytest


def _git(world, *args, check=True):
    return subprocess.run(
        ["git", "-C", str(world.parent_path), *args],
        env=world.env,
        capture_output=True,
        check=check,
    )


def _fork(world, name, *, env=None):
    from agent_fork.agents import AgentContext
    from agent_fork.pipeline import ForkRequest, fork

    request = ForkRequest(
        parent=world.parent_path,
        destination=world.parent_path.parent / f"child-{name}",
        name=name,
        branch=f"fork/{name}",
        agent=AgentContext("claude", "11111111-1111-1111-1111-111111111111"),
        agent_executable="/fake/claude",
        agent_version_output="2.1.220",
        git_version_output="git version 2.43.0",
    )
    return fork(request, env=env if env is not None else world.env)


def _inject(world, key, value):
    """Environment with one inline-injected configuration pair."""
    env = dict(world.env)
    env["GIT_CONFIG_COUNT"] = "1"
    env["GIT_CONFIG_KEY_0"] = key
    env["GIT_CONFIG_VALUE_0"] = value
    return env


@pytest.mark.matrix("T-GRD-17")
def test_injected_core_symlinks_cannot_flatten_committed_symlinks(repo_scenario):
    """Issue #35 — the demonstrated silent divergence.

    A committed, unmodified symlink is not in the carried inventory, so no
    verification rung examines it; it reaches the child through `worktree add`'s
    checkout, which `core.symlinks` governs. Before the fix the child held a
    regular file containing the link target, and the fork reported success.
    """
    world = repo_scenario()
    (world.parent_path / "target.txt").write_bytes(b"target content\n")
    _git(world, "add", "target.txt")
    (world.parent_path / "committed_link").symlink_to("target.txt")
    _git(world, "add", "committed_link")
    _git(world, "commit", "-m", "commit a symlink")
    (world.parent_path / "tracked.txt").write_bytes(
        b"an edit, so the fork carries state\n"
    )

    result = _fork(world, "sym", env=_inject(world, "core.symlinks", "false"))

    child_link = result.creation.path / "committed_link"
    assert child_link.is_symlink(), (
        "committed symlink became a regular file in the child; "
        "injected core.symlinks reached the checkout"
    )


@pytest.mark.matrix("T-GRD-18")
def test_injection_is_absent_from_the_environment_git_receives(repo_scenario):
    """Discriminating check: the injected pair never reaches Git at all.

    An earlier version of this test injected `apply.whitespace=fix` and asserted
    the transported bytes were unchanged. That passes with or without
    sanitization, because A1 independently pins `--whitespace=nowarn` on the
    apply — so it demonstrated nothing about this layer. This instead observes
    the environment Git is actually handed, which fails if the filter is
    removed.
    """
    from agent_fork.git import run_git, without_config_injection

    world = repo_scenario()
    env = _inject(world, "core.symlinks", "false")
    env["GIT_CONFIG_PARAMETERS"] = "'core.autocrlf=true'"

    filtered = without_config_injection(env)
    assert "GIT_CONFIG_COUNT" not in filtered
    assert "GIT_CONFIG_KEY_0" not in filtered
    assert "GIT_CONFIG_VALUE_0" not in filtered
    assert "GIT_CONFIG_PARAMETERS" not in filtered

    # and end to end: Git resolves the setting from configuration, not injection
    observed = run_git(
        world.parent_path, ["config", "--get", "core.symlinks"], env=env, check=False
    )
    assert b"false" not in observed.stdout


@pytest.mark.matrix("T-GRD-19")
def test_config_file_pointers_survive_sanitization(repo_scenario):
    """Regression guard — do not over-strip, checked through `run_git` itself.

    An earlier version ran raw `git` rather than `run_git`, so deleting
    `GIT_CONFIG_GLOBAL` from the filter would not have failed it. This asserts
    the pointer survives the filter and that Git, invoked the way agent-fork
    invokes it, still reads the file it names — which is how the sealed test
    harness controls configuration.
    """
    from agent_fork.git import run_git, without_config_injection

    world = repo_scenario()
    marker = world.parent_path.parent / "marker.gitconfig"
    marker.write_text("[custom]\n\tsentinel = from-file-pointer\n")
    env = dict(world.env)
    env["GIT_CONFIG_GLOBAL"] = str(marker)

    assert without_config_injection(env)["GIT_CONFIG_GLOBAL"] == str(marker)

    observed = run_git(
        world.parent_path, ["config", "--get", "custom.sentinel"], env=env, check=False
    )
    assert observed.stdout.decode().strip() == "from-file-pointer"


@pytest.mark.matrix("T-GRD-20")
def test_repository_local_configuration_still_applies(repo_scenario):
    """Regression guard — repository configuration is user intent, not attack.

    Sanitization targets inline environment injection only. A value the
    repository sets in its own config file must continue to apply.
    """
    world = repo_scenario()
    _git(world, "config", "custom.sentinel", "repo-local-value")
    (world.parent_path / "tracked.txt").write_bytes(b"edit\n")

    result = _fork(world, "repocfg")

    observed = (
        subprocess.run(
            [
                "git",
                "-C",
                str(result.creation.path),
                "config",
                "--get",
                "custom.sentinel",
            ],
            env=world.env,
            capture_output=True,
            check=False,
        )
        .stdout.decode()
        .strip()
    )
    assert observed == "repo-local-value"


@pytest.mark.matrix("T-GRD-21")
def test_git_config_parameters_is_also_stripped(repo_scenario):
    """`GIT_CONFIG_PARAMETERS` is a second inline-injection channel.

    Git uses it internally to propagate `-c` settings to subprocesses, and it
    injects configuration exactly as the `GIT_CONFIG_COUNT` triple does. An
    earlier revision stripped only the triple, leaving this path open: probing
    reproduced the full issue #35 defect through it, with a committed symlink
    flattened and the fork reporting success.
    """
    world = repo_scenario()
    (world.parent_path / "target.txt").write_bytes(b"target content\n")
    _git(world, "add", "target.txt")
    (world.parent_path / "committed_link").symlink_to("target.txt")
    _git(world, "add", "committed_link")
    _git(world, "commit", "-m", "commit a symlink")
    (world.parent_path / "tracked.txt").write_bytes(
        b"an edit, so the fork carries state\n"
    )

    env = dict(world.env)
    env["GIT_CONFIG_PARAMETERS"] = "'core.symlinks=false'"
    result = _fork(world, "params", env=env)

    assert (result.creation.path / "committed_link").is_symlink(), (
        "GIT_CONFIG_PARAMETERS bypassed sanitization"
    )
