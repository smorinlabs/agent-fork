"""G-GRD/G-INC — repository-controlled text is safe to render (issue #32).

A repository can name a branch, path, or file with almost any bytes except
``/`` and NUL, and a setup hook can print whatever it likes. Terminals treat
some of those bytes as instructions rather than characters, so text taken from
a repository must be escaped before it reaches a message. Bytes that are not
valid UTF-8 also arrive as surrogates through ``surrogateescape`` and cannot be
encoded into a machine-readable document at all.

Each test below drives a real refusal or notice with a hostile value and asserts
the rendered message carries no raw control byte. A1 escaped the verification
paths; these cover the sinks it did not.
"""

from __future__ import annotations

import subprocess

import pytest

ESC = "\x1b"
HOSTILE = f"bad{ESC}[2J\nforged"


def _git(world, *args, check=True):
    return subprocess.run(
        ["git", "-C", str(world.parent_path), *args],
        env=world.env,
        capture_output=True,
        check=check,
    )


def _assert_renders_safely(message: str) -> None:
    """No raw control byte survives into a rendered message."""
    assert ESC not in message, f"raw ESC in message: {message!r}"
    assert "\n" not in message, f"raw newline in message: {message!r}"
    message.encode("utf-8")


@pytest.mark.matrix("T-GRD-15")
def test_attached_worktree_refusal_escapes_the_worktree_path(repo_scenario, tmp_path):
    """The conflict_branch_worktree refusal interpolates a worktree path.

    The branch beside it is rendered with `!r`, which already escapes; the path
    was not, so a worktree checked out under a hostile directory name reached
    the terminal raw.
    """
    from agent_fork.errors import PreconditionError
    from agent_fork.repository import validate_fork_guards

    world = repo_scenario()
    hostile_dir = tmp_path / HOSTILE.replace("\n", "")
    _git(world, "worktree", "add", "-b", "fork/taken", str(hostile_dir))

    with pytest.raises(PreconditionError) as raised:
        validate_fork_guards(
            world.parent_path,
            "fork/taken",
            world.parent_path.parent / "child",
            env=world.env,
        )
    assert raised.value.code == "conflict_branch_worktree"
    _assert_renders_safely(str(raised.value))


@pytest.mark.matrix("T-GRD-16")
def test_unmerged_index_refusal_escapes_conflicted_filenames(repo_scenario):
    """The unmerged_index refusal joins conflicted filenames into its message."""
    from agent_fork.errors import PreconditionError
    from agent_fork.repository import validate_fork_guards

    world = repo_scenario()
    name = f"conflict{ESC}[2J.txt"
    blob = (
        subprocess.run(
            ["git", "-C", str(world.parent_path), "hash-object", "-w", "--stdin"],
            env=world.env,
            input=b"side\n",
            capture_output=True,
            check=True,
        )
        .stdout.decode()
        .strip()
    )
    subprocess.run(
        ["git", "-C", str(world.parent_path), "update-index", "--index-info"],
        env=world.env,
        input=f"100644 {blob} 1\t{name}\n100644 {blob} 2\t{name}\n".encode(),
        capture_output=True,
        check=True,
    )

    with pytest.raises(PreconditionError) as raised:
        validate_fork_guards(
            world.parent_path,
            "fork/unmerged",
            world.parent_path.parent / "child",
            env=world.env,
        )
    assert raised.value.code == "unmerged_index"
    _assert_renders_safely(str(raised.value))


@pytest.mark.matrix("T-INC-07")
def test_setup_hook_failure_notice_escapes_hook_output(repo_scenario, tmp_path):
    """A failing setup hook's own output reaches a notice.

    This one needs no hostile filename: the hook is a program the repository
    ships, so its stdout and stderr are directly attacker-chosen.
    """
    from agent_fork.include import SetupHookPolicy, run_setup_hook

    world = repo_scenario()
    child = tmp_path / "child"
    hook = child / ".agent-fork/worktree-setup.sh"
    hook.parent.mkdir(parents=True)
    hook.write_text(f"#!/bin/sh\nprintf 'boom{ESC}[2J\\n' >&2\nexit 3\n")
    hook.chmod(0o755)

    # `child` is a bare directory, not a worktree, so the eligibility plumbing
    # cannot answer; `any` runs the hook regardless, which is what this row asserts.
    result = run_setup_hook(
        world.parent_path,
        child,
        anchor="HEAD",
        policy=SetupHookPolicy(mode="any", timeout_seconds=300),
        env=world.env,
    )
    notices = result.notices

    assert len(notices) == 1
    assert "exit 3" in notices[0]
    _assert_renders_safely(notices[0])
