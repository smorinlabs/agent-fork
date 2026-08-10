"""G-INC — include/hook behavior through the real fork orchestrator."""

import subprocess

import pytest


def _git(world, *args):
    return subprocess.run(
        ["git", "-C", str(world.parent_path), *args],
        env=world.env,
        capture_output=True,
        check=True,
    )


def _commit_support(world, *, include=None, hook=None):
    if include is not None:
        (world.parent_path / ".worktreeinclude").write_text(include)
    if hook is not None:
        path = world.parent_path / ".agent-fork/worktree-setup.sh"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(hook)
        path.chmod(0o755)
    _git(world, "add", ".")
    _git(world, "commit", "-m", "configure worktree support")


def _request(world, *, name="include", with_ignored=False):
    from agent_fork.agents import AgentContext
    from agent_fork.pipeline import ForkRequest

    return ForkRequest(
        parent=world.parent_path,
        destination=world.parent_path.parent / f"child-{name}",
        name=name,
        branch=f"fork/{name}",
        agent=AgentContext("claude", "11111111-1111-1111-1111-111111111111"),
        with_ignored=with_ignored,
        agent_executable="/fake/claude",
        agent_version_output="Claude Code 2.1.220",
        git_version_output="git version 2.43.0",
        child_session_id="33333333-3333-3333-3333-333333333333",
    )


@pytest.mark.matrix("T-INC-01")
def test_worktreeinclude_copies_listed_gitignored_files(repo_scenario):
    from agent_fork.pipeline import fork

    world = repo_scenario()
    (world.parent_path / ".gitignore").write_text(".env\nignored/**\n")
    _commit_support(world, include=".env\nignored/**\n")
    (world.parent_path / ".env").write_text("TOKEN=secret\n")
    nested = world.parent_path / "ignored/nested.txt"
    nested.parent.mkdir()
    nested.write_text("nested\n")
    result = fork(_request(world), env=world.env)
    assert set(result.included) == {".env", "ignored/nested.txt"}
    assert (result.creation.path / ".env").read_bytes() == b"TOKEN=secret\n"
    assert (result.creation.path / "ignored/nested.txt").read_bytes() == b"nested\n"


@pytest.mark.matrix("T-INC-02")
def test_worktreeinclude_yields_to_materialized_copies(repo_scenario):
    from agent_fork.pipeline import fork

    world = repo_scenario()
    (world.parent_path / ".gitignore").write_text(".env\n")
    _commit_support(world, include=".env\n")
    (world.parent_path / ".env").write_text("materialized\n")
    result = fork(_request(world, name="precedence", with_ignored=True), env=world.env)
    assert ".env" not in result.included
    assert (result.creation.path / ".env").read_text() == "materialized\n"


@pytest.mark.matrix("T-INC-03")
def test_setup_hook_runs_with_worktree_cwd_and_env(repo_scenario):
    from agent_fork.pipeline import fork

    world = repo_scenario()
    _commit_support(
        world,
        hook=(
            "#!/bin/sh\n"
            'printf \'%s\\n%s\\n%s\\n\' "$PWD" "$REPO_ROOT" '
            '"$WORKTREE_PATH" > hook-env.txt\n'
        ),
    )
    result = fork(_request(world, name="hook-env"), env=world.env)
    assert (result.creation.path / "hook-env.txt").read_text().splitlines() == [
        str(result.creation.path),
        str(world.parent_path),
        str(result.creation.path),
    ]


@pytest.mark.matrix("T-INC-04")
def test_setup_hook_failure_is_non_fatal(repo_scenario):
    from agent_fork.pipeline import fork
    from agent_fork.registry import find_owned

    world = repo_scenario()
    _commit_support(world, hook="#!/bin/sh\necho deliberate >&2\nexit 17\n")
    result = fork(_request(world, name="hook-fail"), env=world.env)
    assert result.creation.path.exists()
    assert any(
        "setup hook failed (exit 17): deliberate" in notice for notice in result.notices
    )
    assert find_owned("hook-fail", env=world.env) is not None

    second = repo_scenario()
    _commit_support(second, hook="#!/bin/sh\nexit 0\n")
    (second.parent_path / ".agent-fork/worktree-setup.sh").chmod(0o644)
    _git(second, "add", ".agent-fork/worktree-setup.sh")
    _git(second, "commit", "-m", "remove hook execute bit")
    non_executable = fork(_request(second, name="hook-mode"), env=second.env)
    assert any(
        "setup hook failed to start" in notice for notice in non_executable.notices
    )
    assert non_executable.creation.path.exists()


@pytest.mark.matrix("T-INC-05")
def test_include_and_hook_run_after_verify(repo_scenario):
    from agent_fork.pipeline import fork

    world = repo_scenario()
    (world.parent_path / ".gitignore").write_text("post-verify.env\n")
    _commit_support(
        world,
        include="post-verify.env\n",
        hook="#!/bin/sh\nprintf hook > hook-after-verify.txt\n",
    )
    (world.parent_path / "post-verify.env").write_text("included\n")
    result = fork(_request(world, name="order"), env=world.env)
    assert result.verification is True
    assert result.included == ("post-verify.env",)
    assert (result.creation.path / "hook-after-verify.txt").read_text() == "hook"
    from agent_fork.registry import find_owned

    assert find_owned("order", env=world.env) is not None
    assert result.launch.command.endswith("--fork-session -n order")
