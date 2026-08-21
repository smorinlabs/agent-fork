"""G-INC — include/hook behavior through the real fork orchestrator."""

import os
import signal
import subprocess
import time

import pytest

HOOK_RELATIVE = ".agent-fork/worktree-setup.sh"
SENTINEL = "hook-ran.txt"
SENTINEL_HOOK = f"#!/bin/sh\nprintf ran > {SENTINEL}\n"


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
        path = world.parent_path / HOOK_RELATIVE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(hook)
        path.chmod(0o755)
    _git(world, "add", ".")
    _git(world, "commit", "-m", "configure worktree support")


def _write_hook(world, body, *, mode=0o755):
    """Place a hook in the parent working tree without committing it."""
    path = world.parent_path / HOOK_RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    path.chmod(mode)
    return path


def _request(
    world,
    *,
    name="include",
    with_ignored=False,
    setup_hook_policy="tracked",
    setup_hook_timeout=300,
):
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
        setup_hook_policy=setup_hook_policy,
        setup_hook_timeout=setup_hook_timeout,
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
        "setup hook failed (exit 17): deliberate" in notice
        for notice in result.setup_hook.notices
    )
    assert find_owned("hook-fail", env=world.env) is not None

    second = repo_scenario()
    _commit_support(second, hook="#!/bin/sh\nexit 0\n")
    (second.parent_path / HOOK_RELATIVE).chmod(0o644)
    _git(second, "add", HOOK_RELATIVE)
    _git(second, "commit", "-m", "remove hook execute bit")
    non_executable = fork(_request(second, name="hook-mode"), env=second.env)
    assert any(
        "setup hook failed to start" in notice
        for notice in non_executable.setup_hook.notices
    )
    assert non_executable.setup_hook.status == "failed_to_start"
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


@pytest.mark.matrix("T-INC-08")
def test_setup_hook_committed_at_anchor_and_unchanged_runs(repo_scenario):
    """T-INC-08 — the eligible case is the one that still runs.

    Given:  a hook committed at the fork anchor and byte-identical on disk
    Expect: eligibility "eligible", status "ran", exit code 0
    Source: P02 A12; REQ-24
    """
    from agent_fork.pipeline import fork

    world = repo_scenario()
    _commit_support(world, hook=SENTINEL_HOOK)
    result = fork(_request(world, name="hook-eligible"), env=world.env)
    hook = result.setup_hook
    assert hook.path == HOOK_RELATIVE
    assert hook.present is True
    assert hook.policy == "tracked"
    assert hook.eligibility == "eligible"
    assert hook.status == "ran"
    assert hook.exit_code == 0
    assert hook.timed_out is False
    assert (result.creation.path / SENTINEL).read_text() == "ran"


@pytest.mark.matrix("T-INC-09")
def test_untracked_setup_hook_is_skipped_by_default(repo_scenario):
    """T-INC-09 — Gate-1 fact 1: an index-untracked hook executed unconditionally.

    Given:  a hook present in the parent working tree but never committed
    Expect: the child never runs it; eligibility "untracked", status "skipped",
            and the notice names the override flag
    Source: P02 A12 Gate-1 fact 1
    """
    from agent_fork.pipeline import fork

    world = repo_scenario()
    _write_hook(world, SENTINEL_HOOK)
    result = fork(_request(world, name="hook-untracked"), env=world.env)
    hook = result.setup_hook
    assert (result.creation.path / HOOK_RELATIVE).is_file()
    assert not (result.creation.path / SENTINEL).exists()
    assert hook.present is True
    assert hook.eligibility == "untracked"
    assert hook.status == "skipped"
    assert hook.exit_code is None
    assert "--setup-hook-policy any" in " ".join(hook.notices)
    assert any("--setup-hook-policy any" in notice for notice in result.notices)


@pytest.mark.matrix("T-INC-10")
def test_modified_setup_hook_is_skipped_by_default(repo_scenario):
    """T-INC-10 — committed once, edited since: the executed bytes are unreviewed.

    Given:  a hook committed at the anchor, then modified in the parent tree and
            carried into the child by `materialize()`
    Expect: eligibility "modified" (byte comparison, never `git status`), skipped
    Source: P02 A12; A1 (status is not a byte-equality oracle)
    """
    from agent_fork.pipeline import fork

    world = repo_scenario()
    _commit_support(world, hook="#!/bin/sh\nexit 0\n")
    _write_hook(world, SENTINEL_HOOK)
    result = fork(_request(world, name="hook-modified"), env=world.env)
    hook = result.setup_hook
    assert (result.creation.path / HOOK_RELATIVE).read_text() == SENTINEL_HOOK
    assert not (result.creation.path / SENTINEL).exists()
    assert hook.eligibility == "modified"
    assert hook.status == "skipped"
    assert "--setup-hook-policy any" in " ".join(hook.notices)


@pytest.mark.matrix("T-INC-11")
def test_any_policy_runs_ineligible_hooks_without_masking_eligibility(repo_scenario):
    """T-INC-11 — the override runs the hook but never hides why it was ineligible.

    Given:  `--setup-hook-policy any` with an untracked hook, and separately with
            a modified one
    Expect: both run, and eligibility still reports "untracked" / "modified"
    Source: P02 A12 policy table
    """
    from agent_fork.pipeline import fork

    untracked_world = repo_scenario()
    _write_hook(untracked_world, SENTINEL_HOOK)
    untracked = fork(
        _request(untracked_world, name="any-untracked", setup_hook_policy="any"),
        env=untracked_world.env,
    )
    assert (untracked.creation.path / SENTINEL).read_text() == "ran"
    assert untracked.setup_hook.eligibility == "untracked"
    assert untracked.setup_hook.status == "ran"
    assert untracked.setup_hook.policy == "any"

    modified_world = repo_scenario()
    _commit_support(modified_world, hook="#!/bin/sh\nexit 0\n")
    _write_hook(modified_world, SENTINEL_HOOK)
    modified = fork(
        _request(modified_world, name="any-modified", setup_hook_policy="any"),
        env=modified_world.env,
    )
    assert (modified.creation.path / SENTINEL).read_text() == "ran"
    assert modified.setup_hook.eligibility == "modified"
    assert modified.setup_hook.status == "ran"


@pytest.mark.matrix("T-INC-12")
def test_symlinked_setup_hook_is_not_a_regular_blob(repo_scenario):
    """T-INC-12 — a symlink is a redirection, not reviewable committed content.

    Given:  (a) the anchor tree records the hook path as mode 120000, and
            (b) the hook path is a symlink on disk in the child
    Expect: both report eligibility "not_a_regular_blob" and are skipped
    Source: P02 A12 Axis B
    """
    from agent_fork.pipeline import fork

    committed = repo_scenario()
    target = committed.parent_path / ".agent-fork/real-setup.sh"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(SENTINEL_HOOK)
    target.chmod(0o755)
    (committed.parent_path / HOOK_RELATIVE).symlink_to("real-setup.sh")
    _git(committed, "add", ".")
    _git(committed, "commit", "-m", "commit hook as a symlink")
    linked = fork(_request(committed, name="hook-gitlink"), env=committed.env)
    assert not (linked.creation.path / SENTINEL).exists()
    assert linked.setup_hook.eligibility == "not_a_regular_blob"
    assert linked.setup_hook.status == "skipped"

    on_disk = repo_scenario()
    _commit_support(on_disk, hook="#!/bin/sh\nexit 0\n")
    replacement = on_disk.parent_path / ".agent-fork/replacement.sh"
    replacement.write_text(SENTINEL_HOOK)
    replacement.chmod(0o755)
    (on_disk.parent_path / HOOK_RELATIVE).unlink()
    (on_disk.parent_path / HOOK_RELATIVE).symlink_to("replacement.sh")
    swapped = fork(_request(on_disk, name="hook-symlink"), env=on_disk.env)
    assert (swapped.creation.path / HOOK_RELATIVE).is_symlink()
    assert not (swapped.creation.path / SENTINEL).exists()
    assert swapped.setup_hook.eligibility == "not_a_regular_blob"
    assert swapped.setup_hook.status == "skipped"


@pytest.mark.matrix("T-INC-13")
def test_off_policy_never_evaluates_or_executes_the_hook(repo_scenario):
    """T-INC-13 — `off` dominates: no eligibility check, no process.

    Given:  `--setup-hook-policy off` with an eligible committed hook
    Expect: status "disabled", eligibility "unchecked", nothing executed
    Source: P02 A12 policy table; Outcome 3
    """
    from agent_fork.pipeline import fork

    world = repo_scenario()
    _commit_support(world, hook=SENTINEL_HOOK)
    result = fork(
        _request(world, name="hook-off", setup_hook_policy="off"), env=world.env
    )
    hook = result.setup_hook
    assert not (result.creation.path / SENTINEL).exists()
    assert hook.status == "disabled"
    assert hook.eligibility == "unchecked"
    assert hook.policy == "off"
    assert hook.exit_code is None
    assert hook.duration_seconds is None


@pytest.mark.matrix("T-INC-14")
def test_successful_hook_output_is_retained_and_bounded(repo_scenario):
    """T-INC-14 — Gate-1 fact 3: successful stdout and stderr were discarded.

    Given:  a hook that succeeds after printing to both streams, and separately
            one that prints far more than the 4096-byte bound
    Expect: bounded tails plus pre-bound byte totals and a `truncated` flag
    Source: P02 A12 Gate-1 fact 3; Axis C1
    """
    from agent_fork.include import OUTPUT_TAIL_BYTES
    from agent_fork.pipeline import fork

    world = repo_scenario()
    _commit_support(
        world,
        hook="#!/bin/sh\nprintf 'installed 42 packages\\n'\nprintf 'warned\\n' >&2\n",
    )
    result = fork(_request(world, name="hook-output"), env=world.env)
    hook = result.setup_hook
    assert hook.status == "ran"
    assert hook.stdout_tail == "installed 42 packages\\n"
    assert hook.stderr_tail == "warned\\n"
    assert hook.stdout_bytes == 22
    assert hook.stderr_bytes == 7
    assert hook.truncated is False
    assert hook.duration_seconds is not None

    noisy = repo_scenario()
    _commit_support(
        noisy,
        hook=(
            "#!/bin/sh\n"
            f"awk 'BEGIN {{ while (i++ < {OUTPUT_TAIL_BYTES}) printf \"ab\" }}'\n"
        ),
    )
    loud = fork(_request(noisy, name="hook-loud"), env=noisy.env)
    assert loud.setup_hook.status == "ran"
    assert loud.setup_hook.stdout_bytes == OUTPUT_TAIL_BYTES * 2
    assert len(loud.setup_hook.stdout_tail) == OUTPUT_TAIL_BYTES
    assert loud.setup_hook.truncated is True


@pytest.mark.matrix("T-INC-15")
def test_successful_hook_output_is_escaped(repo_scenario):
    """T-INC-15 — the success path needs T-INC-07's escaping too.

    Given:  a hook that prints a terminal escape sequence and exits 0
    Expect: the retained tail carries no raw control byte
    Source: P02 A12; issue #32 (T-INC-07 covered only the failure path)
    """
    from agent_fork.pipeline import fork

    world = repo_scenario()
    _commit_support(world, hook="#!/bin/sh\nprintf 'boom\\033[2J\\n'\n")
    result = fork(_request(world, name="hook-escape"), env=world.env)
    hook = result.setup_hook
    assert hook.status == "ran"
    assert hook.exit_code == 0
    assert "\x1b" not in hook.stdout_tail
    assert "\n" not in hook.stdout_tail
    assert "\\x1b" in hook.stdout_tail


@pytest.mark.requires_process_group_signals
@pytest.mark.matrix("T-INC-16")
def test_setup_hook_timeout_kills_the_whole_process_group(repo_scenario):
    """T-INC-16 — Gate-1 fact 2: an unbounded hook and its children outlived the CLI.

    Given:  a hook that backgrounds a long sleeper and then sleeps past the
            configured timeout
    Expect: the fork still succeeds, `timed_out` is true, and the hook's own
            grandchild is gone — the process group was reaped, not just the shell
    Source: P02 A12 Gate-1 fact 2; Axis A1
    """
    from agent_fork.pipeline import fork

    world = repo_scenario()
    _commit_support(
        world,
        hook=('#!/bin/sh\nsleep 120 &\nprintf "%s" "$!" > grandchild.pid\nsleep 120\n'),
    )
    result = fork(
        _request(world, name="hook-timeout", setup_hook_timeout=1), env=world.env
    )
    hook = result.setup_hook
    assert result.creation.path.exists()
    assert hook.status == "ran"
    assert hook.timed_out is True
    assert hook.timeout_seconds == 1
    assert any("timed out" in notice for notice in hook.notices)
    grandchild = int((result.creation.path / "grandchild.pid").read_text())
    for _ in range(200):
        try:
            os.kill(grandchild, 0)
        except ProcessLookupError:
            break
        time.sleep(0.01)
    else:
        os.kill(grandchild, signal.SIGKILL)
        pytest.fail(f"setup-hook grandchild {grandchild} survived the timeout")
