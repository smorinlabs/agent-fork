"""G-MAT — transport uses plumbing diff, not porcelain (A2 transport finding).

`git diff` is Git's human-facing command. Its defaults include display drivers
that convert content for reading: `textconv`, declared per path by a committed
`.gitattributes`, and `diff.external`, set in configuration. Git documents that
textconv output "cannot be applied", and enables it by default for `git diff`
but "not for … diff plumbing commands".

Transport is a machine-to-machine operation: the patch is serialized index
state to be replayed, never text for a person to read. It therefore belongs on
the plumbing commands `git diff-index` and `git diff-files`, which do not apply
display conversions.

Two distinct failure modes are covered here, both observed on 2026-08-17
against porcelain transport:

* **Unappliable** — the driver renders content as text, and `git apply` refuses
  it: `error: doc.txt: patch does not apply`.
* **Collapsed** — the driver renders every revision identically, so the diff is
  *empty* and the change is dropped. A1's content verification catches this as
  `verify_failed`, but the fork still cannot be created.

Neither requires a hostile environment. `.gitattributes` is committed, so
cloning a repository that uses a diff driver is sufficient.
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


def _driver(world, name, script_body):
    """Install an executable textconv driver and return its path."""
    script = world.parent_path.parent / f"{name}.sh"
    script.write_text(script_body)
    script.chmod(0o755)
    _git(world, "config", f"diff.{name}.textconv", str(script))
    return script


def _fork(world, name):
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
    return fork(request, env=world.env)


@pytest.mark.matrix("T-MAT-21")
def test_textconv_driver_does_not_break_transport(repo_scenario):
    """A repository shipping a textconv driver stays forkable.

    Observed before the plumbing swap: `error: patch failed: doc.txt:1 / error:
    doc.txt: patch does not apply`, surfaced as an uncategorized runtime_error.
    """
    world = repo_scenario()
    _driver(world, "readable", '#!/bin/sh\nprintf "RENDERED:\\n"\ncat "$1"\n')
    (world.parent_path / ".gitattributes").write_text("tracked.txt diff=readable\n")
    _git(world, "add", ".gitattributes")
    _git(world, "commit", "-m", "ship a diff driver")
    (world.parent_path / "tracked.txt").write_bytes(b"MY UNCOMMITTED WORK\n")

    result = _fork(world, "textconv")

    child = result.creation.path / "tracked.txt"
    assert child.read_bytes() == b"MY UNCOMMITTED WORK\n"


@pytest.mark.matrix("T-MAT-22")
def test_lossy_textconv_driver_does_not_drop_the_change(repo_scenario):
    """A driver that renders every revision alike must not empty the patch.

    Realistic analogue: a converter reporting "3 pages, 2 images" for any
    revision of a document. Under porcelain the diff was 0 bytes, so the edit
    was dropped entirely; plumbing produced the real 162-byte patch.
    """
    world = repo_scenario()
    _driver(world, "lossy", '#!/bin/sh\nprintf "SUMMARY: unchanged\\n"\n')
    (world.parent_path / ".gitattributes").write_text("tracked.txt diff=lossy\n")
    _git(world, "add", ".gitattributes")
    _git(world, "commit", "-m", "ship a lossy driver")
    (world.parent_path / "tracked.txt").write_bytes(b"IMPORTANT EDIT\n")

    result = _fork(world, "lossy")

    child = result.creation.path / "tracked.txt"
    assert child.read_bytes() == b"IMPORTANT EDIT\n"


@pytest.mark.matrix("T-MAT-23")
def test_external_diff_does_not_break_transport(repo_scenario):
    """`diff.external` replaces the diff engine repository-wide.

    Unlike textconv, this is not per-path: it affects every file, so under
    porcelain no patch of any kind survived.
    """
    world = repo_scenario()
    script = world.parent_path.parent / "ext.sh"
    script.write_text('#!/bin/sh\nprintf "EXTERNAL DIFF — not a patch\\n"\n')
    script.chmod(0o755)
    _git(world, "config", "diff.external", str(script))
    (world.parent_path / "tracked.txt").write_bytes(b"CARRIED THROUGH\n")

    result = _fork(world, "extdiff")

    child = result.creation.path / "tracked.txt"
    assert child.read_bytes() == b"CARRIED THROUGH\n"


@pytest.mark.matrix("T-MAT-24")
def test_staged_and_unstaged_split_survives_a_diff_driver(repo_scenario):
    """The three-way split is what transport exists to preserve.

    A file edited, staged, then edited again holds three versions: committed,
    staged, and on disk. Copying files would flatten that to one. This asserts
    the split survives transport while a diff driver is active.
    """
    world = repo_scenario()
    _driver(world, "readable", '#!/bin/sh\nprintf "RENDERED:\\n"\ncat "$1"\n')
    (world.parent_path / ".gitattributes").write_text("tracked.txt diff=readable\n")
    _git(world, "add", ".gitattributes")
    _git(world, "commit", "-m", "ship a diff driver")

    (world.parent_path / "tracked.txt").write_bytes(b"STAGED VERSION\n")
    _git(world, "add", "tracked.txt")
    (world.parent_path / "tracked.txt").write_bytes(b"WORKING TREE VERSION\n")

    result = _fork(world, "split")
    child_root = result.creation.path

    assert (child_root / "tracked.txt").read_bytes() == b"WORKING TREE VERSION\n"
    staged = subprocess.run(
        ["git", "-C", str(child_root), "show", ":tracked.txt"],
        env=world.env,
        capture_output=True,
        check=True,
    ).stdout
    assert staged == b"STAGED VERSION\n"
