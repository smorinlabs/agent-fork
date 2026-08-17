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

The defence is to **strip the inline-injection triple** in `run_git`, which
kills the class without enumerating which keys matter.

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
    subprocess.run(
        ["ln", "-s", "target.txt", str(world.parent_path / "committed_link")],
        check=True,
    )
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
def test_injected_apply_whitespace_cannot_rewrite_transported_content(repo_scenario):
    """Injection must not reach transport even for keys A1 already pins.

    A1 pins `--whitespace=nowarn` on the apply, which holds. This asserts the
    same outcome through the sanitization layer, so the guarantee does not
    depend on one flag being remembered at one call site.
    """
    world = repo_scenario()
    (world.parent_path / "tracked.txt").write_bytes(b"line one   \nline two\n")

    result = _fork(world, "ws", env=_inject(world, "apply.whitespace", "fix"))

    carried = (result.creation.path / "tracked.txt").read_bytes()
    assert carried == b"line one   \nline two\n"


@pytest.mark.matrix("T-GRD-19")
def test_config_file_pointers_are_still_honoured(repo_scenario):
    """Regression guard — do not over-strip.

    `GIT_CONFIG_GLOBAL` points at a configuration file, which is how tooling
    (this harness included) deliberately controls Git. If sanitization removed
    it, every sealed test would silently fall back to the real `~/.gitconfig`.
    """
    world = repo_scenario()
    marker = world.parent_path.parent / "marker.gitconfig"
    marker.write_text("[user]\n\tname = sentinel-from-file-pointer\n")
    env = dict(world.env)
    env["GIT_CONFIG_GLOBAL"] = str(marker)

    observed = (
        subprocess.run(
            ["git", "-C", str(world.parent_path), "config", "--get", "user.name"],
            env=env,
            capture_output=True,
            check=False,
        )
        .stdout.decode()
        .strip()
    )

    assert observed == "sentinel-from-file-pointer"


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
