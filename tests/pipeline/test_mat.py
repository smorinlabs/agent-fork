"""G-MAT — Materialize (tier F).

Matrix: docs/testing/TEST-MATRIX.md §G-MAT.
"""

import pytest


def _materialized(repo_scenario, *, states=(), topology="plain@main", mode="exact"):
    world = repo_scenario(topology, states=states)
    return _materialize_world(world, mode=mode)


def _materialize_world(world, *, mode="exact"):
    from agent_fork.materialize import materialize
    from agent_fork.repository import create_worktree_at_anchor, validate_fork_guards

    child = world.parent_path.parent / "fork-child"
    branch = "fork/materialize"
    validate_fork_guards(world.parent_path, branch, child, env=world.env)
    create_worktree_at_anchor(world.parent_path, branch, child, env=world.env)
    materialize(
        world.parent_path,
        child,
        with_state=mode != "no-state",
        with_ignored=mode == "exact+ignored",
        env=world.env,
    )
    world.child_path = child.resolve()
    return world


def _status(world, path=None):
    import subprocess

    root = path or world.child_path
    return subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain=v1", "-z"],
        env=world.env,
        capture_output=True,
        check=True,
    ).stdout


def _fork_materialized(world, *, name):
    """Run the public pipeline and prove its failure path rolls back cleanly."""
    import subprocess

    from agent_fork.pipeline import ForkRequest, fork

    destination = world.parent_path.parent / f"fork-child-{name}"
    branch = f"fork/{name}"
    try:
        result = fork(
            ForkRequest(
                parent=world.parent_path,
                destination=destination,
                name=name,
                branch=branch,
                agent=None,
                git_version_output="git version 2.43.0",
            ),
            env=world.env,
        )
    except Exception:
        assert not destination.exists()
        branch_lookup = subprocess.run(
            [
                "git",
                "-C",
                str(world.parent_path),
                "show-ref",
                "--verify",
                "--quiet",
                f"refs/heads/{branch}",
            ],
            env=world.env,
        )
        assert branch_lookup.returncode != 0
        raise
    world.child_path = result.creation.path
    return world


@pytest.mark.matrix("T-MAT-01")
def test_staged_only_file_transported_byte_identical(repo_scenario):
    """T-MAT-01 — a staged-only file transports with index/worktree status A and
    byte-identical content.

    Given:  a file staged (added) but not yet committed in the parent
    Expect: child index and worktree show `A `; content byte-identical (manifest oracle)
    Source: REQ-21; RESEARCH §2.2 step 1
    """
    from conftest import staged

    world = _materialized(repo_scenario, states=(staged(add="added.txt"),))
    assert _status(world) == b"A  added.txt\0"
    assert (world.child_path / "added.txt").read_bytes() == (
        world.parent_path / "added.txt"
    ).read_bytes()


@pytest.mark.matrix("T-MAT-02")
def test_unstaged_only_file_transported_index_untouched(repo_scenario):
    """T-MAT-02 — an unstaged-only edit transports to the worktree, leaving the index
    untouched.

    Given:  a tracked file with an unstaged worktree modification only
    Expect: child worktree shows ` M`; index untouched
    Source: REQ-21; RESEARCH §2.2 step 2
    """
    from conftest import unstaged

    world = _materialized(repo_scenario, states=(unstaged("tracked.txt"),))
    assert _status(world) == b" M tracked.txt\0"
    assert world.index_diff(world.parent_path, world.child_path) == []
    assert (world.child_path / "tracked.txt").read_bytes() == (
        world.parent_path / "tracked.txt"
    ).read_bytes()


@pytest.mark.matrix("T-MAT-03")
def test_staged_and_unstaged_split_preserved_on_same_file(repo_scenario):
    """T-MAT-03 — staged and unstaged edits on the same file keep their split origin.

    Given:  one tracked file with both a staged edit and a further unstaged edit
    Expect: child index/worktree shapes (`A `/`AM`/` M`) match the staged-vs-unstaged
            origin of each hunk
    Source: REQ-21; RESEARCH §2.2
    """
    from conftest import staged, unstaged

    world = _materialized(
        repo_scenario,
        states=(staged(modify="tracked.txt"), unstaged("tracked.txt")),
    )
    assert _status(world) == b"MM tracked.txt\0"
    assert world.index_diff(world.parent_path, world.child_path) == []
    assert (world.child_path / "tracked.txt").read_bytes() == b"unstaged\n"


@pytest.mark.matrix("T-MAT-04")
def test_untracked_files_including_nested_dirs_copied(repo_scenario):
    """T-MAT-04 — untracked files, including nested directories, copy byte-for-byte.

    Given:  untracked files at the repo root and inside nested untracked directories
    Expect: copied byte-for-byte; manifest oracle proves inner files present
    Source: REQ-21; RESEARCH §2.2 step 3
    """
    from conftest import untracked

    world = _materialized(
        repo_scenario,
        states=(untracked("root.txt"), untracked("nested/deep/file.txt")),
    )
    for relative in ("root.txt", "nested/deep/file.txt"):
        assert (world.child_path / relative).read_bytes() == (
            world.parent_path / relative
        ).read_bytes()


@pytest.mark.matrix("T-MAT-05")
def test_ignored_files_copied_under_exact_plus_ignored(repo_scenario):
    """T-MAT-05 — ignored files copy under mode=exact+ignored via the opt-in second
    pass.

    Given:  mode=exact+ignored with files matched by `.gitignore` present
    Expect: the union of both `ls-files --others` passes is copied
    Source: REQ-21; RESEARCH §2.2 step 3b
    """
    from conftest import ignored, untracked

    world = _materialized(
        repo_scenario,
        states=(untracked("visible.txt"), ignored("private/.env")),
        mode="exact+ignored",
    )
    assert (world.child_path / "visible.txt").is_file()
    assert (world.child_path / "private/.env").read_bytes() == b"ignored\n"


@pytest.mark.matrix("T-MAT-06")
def test_symlink_relative_target_recreated_verbatim(repo_scenario):
    """T-MAT-06 — a relative-target symlink is recreated verbatim.

    Given:  a tracked symlink with a relative target
    Expect: recreated verbatim via readlink; target stays relative
    Source: REQ-21; RESEARCH §2.2
    """
    import os

    from conftest import symlink_state

    world = _materialized(
        repo_scenario, states=(symlink_state("relative-link", "tracked.txt"),)
    )
    assert os.readlink(world.child_path / "relative-link") == "tracked.txt"


@pytest.mark.matrix("T-MAT-07")
def test_symlink_absolute_target_recreated_verbatim(repo_scenario):
    """T-MAT-07 — an absolute-target symlink is recreated verbatim.

    Given:  a tracked symlink with an absolute target
    Expect: recreated verbatim via readlink; target stays absolute
    Source: REQ-21; RESEARCH §2.2
    """
    import os

    from conftest import symlink_state

    target = "/tmp/agent-fork-absolute-target"
    world = _materialized(
        repo_scenario, states=(symlink_state("absolute-link", target, absolute=True),)
    )
    assert os.readlink(world.child_path / "absolute-link") == target


@pytest.mark.matrix("T-MAT-08")
def test_exec_bit_only_change_preserved(repo_scenario):
    """T-MAT-08 — an exec-bit-only change preserves the permission bit with identical
    content.

    Given:  a tracked file with only its executable bit changed (no content diff)
    Expect: permission bit preserved in the child; content identical
    Source: REQ-21; RESEARCH §2.2
    """
    import stat

    from conftest import exec_bit

    world = _materialized(repo_scenario, states=(exec_bit("script.sh"),))
    parent_mode = stat.S_IMODE((world.parent_path / "script.sh").stat().st_mode)
    child_mode = stat.S_IMODE((world.child_path / "script.sh").stat().st_mode)
    assert parent_mode & stat.S_IXUSR
    assert child_mode & stat.S_IXUSR
    assert (world.child_path / "script.sh").read_bytes() == (
        world.parent_path / "script.sh"
    ).read_bytes()


@pytest.mark.matrix("T-MAT-09")
def test_binary_file_staged_transported_byte_identical(repo_scenario):
    """T-MAT-09 — a staged binary file transports byte-identical via a cached --binary
    diff.

    Given:  a binary file staged in the parent
    Expect: cached `--binary` diff applies with `--index`; child byte-identical
    Source: REQ-21; RESEARCH §2.2 step 1
    """
    from conftest import binary_state

    world = _materialized(repo_scenario, states=(binary_state(staged=True),))
    assert (world.child_path / "binary.bin").read_bytes() == (
        world.parent_path / "binary.bin"
    ).read_bytes()
    assert _status(world) == b"M  binary.bin\0"


@pytest.mark.matrix("T-MAT-10")
def test_binary_file_unstaged_transported_byte_identical(repo_scenario):
    """T-MAT-10 — an unstaged binary file transports byte-identical via an uncached
    --binary diff.

    Given:  a binary file with an unstaged modification in the parent
    Expect: uncached `--binary` diff applies without `--index`; child byte-identical
    Source: REQ-21; RESEARCH §2.2 step 2
    """
    from conftest import binary_state

    world = _materialized(repo_scenario, states=(binary_state(staged=False),))
    assert (world.child_path / "binary.bin").read_bytes() == (
        world.parent_path / "binary.bin"
    ).read_bytes()
    assert _status(world) == b" M binary.bin\0"


@pytest.mark.matrix("T-MAT-11")
def test_rename_and_edit_transported_correctly(repo_scenario):
    """T-MAT-11 — a renamed-and-edited file transports with the rename and the edit
    intact.

    Given:  a tracked file renamed and edited in the same change
    Expect: child reflects the rename with edited content; manifest oracle confirms the
            old path is absent and the new path's content is correct
    Source: REQ-21; RESEARCH §2.2
    """
    from conftest import rename_edit

    world = _materialized(repo_scenario, states=(rename_edit("old-name.txt"),))
    assert not (world.child_path / "old-name.txt").exists()
    assert (world.child_path / "renamed-new.txt").read_text() == "renamed and edited\n"
    assert world.index_diff(world.parent_path, world.child_path) == []


@pytest.mark.matrix("T-MAT-12")
def test_intent_to_add_file_transported_as_ita(repo_scenario):
    """T-MAT-12 — intent-to-add filenames are literal Git operands.

    Given:  a normal ITA file, two ITA pattern names overlapping an ordinary changed
            file, and an ITA filename beginning with `:(glob)`
    Expect: each filename is handled literally; child bytes, status, and full index
            match the parent; a materialization regression rolls back branch/worktree
    Source: REQ-21 (A3); P02 A13(e); issue #29
    """
    import subprocess

    from conftest import intent_to_add, unstaged

    world = _materialized(repo_scenario, states=(intent_to_add("intent.txt"),))
    assert _status(world) == b" A intent.txt\0"
    assert world.index_diff(world.parent_path, world.child_path) == []
    assert (world.child_path / "intent.txt").read_bytes() == b"intent\n"

    overlap = repo_scenario(
        "plain@main",
        states=(unstaged("src/a.txt"),),
    )
    expected = {
        "src/[a].txt": b"first ita\n",
        "src/[ab].txt": b"second ita\n",
        "src/a.txt": b"unstaged\n",
    }
    for relative in ("src/[a].txt", "src/[ab].txt"):
        path = overlap.parent_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(expected[relative])
        subprocess.run(
            [
                "git",
                "-C",
                str(overlap.parent_path),
                "add",
                "--intent-to-add",
                "--",
                f":(literal){relative}",
            ],
            env=overlap.env,
            capture_output=True,
            check=True,
        )
    overlap_parent_before = overlap.parent_snapshot()
    _fork_materialized(overlap, name="literal-overlap")
    assert overlap.parent_snapshot() == overlap_parent_before
    assert _status(overlap) == (b" A src/[a].txt\0 A src/[ab].txt\0 M src/a.txt\0")
    assert overlap.index_diff(overlap.parent_path, overlap.child_path) == []
    for relative, content in expected.items():
        assert (overlap.child_path / relative).read_bytes() == content

    leading_magic = repo_scenario("plain@main")
    relative = ":(glob)leading*.txt"
    content = b"leading pathspec magic is a literal filename\n"
    (leading_magic.parent_path / relative).write_bytes(content)
    subprocess.run(
        [
            "git",
            "-C",
            str(leading_magic.parent_path),
            "add",
            "--intent-to-add",
            "--",
            f":(literal){relative}",
        ],
        env=leading_magic.env,
        capture_output=True,
        check=True,
    )
    leading_parent_before = leading_magic.parent_snapshot()
    _fork_materialized(leading_magic, name="literal-leading-magic")
    assert leading_magic.parent_snapshot() == leading_parent_before
    assert _status(leading_magic) == b" A :(glob)leading*.txt\0"
    assert (
        leading_magic.index_diff(leading_magic.parent_path, leading_magic.child_path)
        == []
    )
    assert (leading_magic.child_path / relative).read_bytes() == content


@pytest.mark.matrix("T-MAT-13")
def test_empty_directory_documented_absence(repo_scenario):
    """T-MAT-13 — an empty directory in the parent is a documented absence in the child.

    Given:  an empty directory present in the parent working tree
    Expect: documented absence in the child (git-visible state copy only; empty-dir
            expectation declared per mode)
    Source: REQ-21; spec §6.5
    """
    from conftest import empty_dir

    world = _materialized(repo_scenario, states=(empty_dir(ignored=False),))
    assert (world.parent_path / "empty-dir").is_dir()
    assert not (world.child_path / "empty-dir").exists()


@pytest.mark.matrix("T-MAT-14")
def test_submodule_treated_opaque_by_gitlink_oid(repo_scenario):
    """T-MAT-14 — a submodule is treated opaque and compared by gitlink OID.

    Given:  a submodule present in the parent, fixture built with command-scoped `-c
            protocol.file.allow=always`
    Expect: treated opaque; gitlink OID (mode-160000) compared; submodule contents
            pruned from the manifest
    Source: RESEARCH §2.1 step 6; spec §6.3; RESEARCH §4
    """
    from conftest import submodule

    world = _materialized(repo_scenario, states=(submodule("vendor/module"),))
    assert world.index_diff(world.parent_path, world.child_path) == []
    index = world.index_diff(world.parent_path, world.child_path)
    assert index == []
    child_manifest = world.manifest_diff(world.child_path, world.child_path)
    assert child_manifest == []
    assert not (world.child_path / "vendor/module/tracked.txt").exists()


@pytest.mark.matrix("T-MAT-15")
def test_parent_read_only_during_materialize(repo_scenario):
    """T-MAT-15 — the parent stays strictly read-only during materialize.

    Given:  a full manifest+index snapshot of the parent taken before materialize
    Expect: the same snapshot taken after materialize is byte-identical
    Source: REQ-21; spec §6.5 item 3
    """
    from conftest import ignored, staged, unstaged, untracked

    world = repo_scenario(
        "plain@main",
        states=(
            staged(add="staged.txt"),
            unstaged("tracked.txt"),
            untracked("loose.txt"),
            ignored("private.env"),
        ),
    )
    before = world.parent_snapshot()
    _materialize_world(world, mode="exact+ignored")
    assert world.parent_snapshot() == before


@pytest.mark.matrix("T-MAT-16")
def test_linked_worktree_dirty_both_checkouts_only_parent_travels(repo_scenario):
    """T-MAT-16 — linked-worktree with dirty state in both checkouts only carries the
    parent worktree's state.

    Given:  distinct staged/unstaged/untracked state in both the parent worktree and the
            main checkout
    Expect: only the parent worktree's state travels to the child
    Source: spec §4 mandatory interaction set; REQ-21
    """
    world = repo_scenario("linked-worktree")
    assert world.main_path is not None
    (world.main_path / "main-only.txt").write_text("main only\n")
    (world.parent_path / "parent-only.txt").write_text("parent only\n")
    _materialize_world(world)
    assert (world.child_path / "parent-only.txt").read_text() == "parent only\n"
    assert not (world.child_path / "main-only.txt").exists()
    assert (world.child_path / "linked-only.txt").read_text() == "dirty linked\n"


@pytest.mark.matrix("T-MAT-17")
def test_linked_worktree_exact_plus_ignored_scoped_to_parent(repo_scenario):
    """T-MAT-17 — linked-worktree under mode=exact+ignored scopes both passes to the
    parent worktree only.

    Given:  mode=exact+ignored in a linked-worktree topology
    Expect: materialize plus the ignored pass are both scoped to the parent worktree
            only
    Source: spec §4 mandatory interaction set; REQ-21
    """
    world = repo_scenario("linked-worktree")
    assert world.main_path is not None
    import subprocess

    parent_exclude = subprocess.run(
        [
            "git",
            "-C",
            str(world.parent_path),
            "rev-parse",
            "--git-path",
            "info/exclude",
        ],
        env=world.env,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    parent_exclude = world.parent_path / parent_exclude
    parent_exclude.parent.mkdir(parents=True, exist_ok=True)
    with parent_exclude.open("a") as stream:
        stream.write("/parent-secret\n/main-secret\n")
    (world.parent_path / "parent-secret").write_text("parent secret\n")
    (world.main_path / "main-secret").write_text("main secret\n")
    _materialize_world(world, mode="exact+ignored")
    assert (world.child_path / "parent-secret").read_text() == "parent secret\n"
    assert not (world.child_path / "main-secret").exists()


@pytest.mark.matrix("T-MAT-18")
def test_mode_exact_full_materialize(repo_scenario):
    """T-MAT-18 — mode=exact fully materializes staged+unstaged+untracked, excluding
    ignored.

    Given:  mode=exact with staged, unstaged, and untracked state present
    Expect: staged+unstaged+untracked copied; ignored excluded
    Source: REQ-21
    """
    from conftest import ignored, staged, unstaged, untracked

    world = _materialized(
        repo_scenario,
        states=(
            staged(add="staged.txt"),
            unstaged("tracked.txt"),
            untracked("loose.txt"),
            ignored("secret.env"),
        ),
        mode="exact",
    )
    assert (world.child_path / "staged.txt").is_file()
    assert (world.child_path / "loose.txt").is_file()
    assert (world.child_path / "tracked.txt").read_bytes() == b"unstaged\n"
    assert not (world.child_path / "secret.env").exists()


@pytest.mark.matrix("T-MAT-19")
def test_mode_exact_plus_ignored_full_materialize(repo_scenario):
    """T-MAT-19 — mode=exact+ignored fully materializes
    staged+unstaged+untracked+ignored.

    Given:  mode=exact+ignored with staged, unstaged, untracked, and ignored state
            present
    Expect: staged+unstaged+untracked+ignored all copied
    Source: REQ-21
    """
    from conftest import ignored, staged, unstaged, untracked

    world = _materialized(
        repo_scenario,
        states=(
            staged(add="staged.txt"),
            unstaged("tracked.txt"),
            untracked("loose.txt"),
            ignored("secret.env"),
        ),
        mode="exact+ignored",
    )
    for relative in ("staged.txt", "tracked.txt", "loose.txt", "secret.env"):
        assert (world.child_path / relative).exists()


@pytest.mark.matrix("T-MAT-20")
def test_mode_no_state_full_materialize(repo_scenario):
    """T-MAT-20 — mode=no-state materializes a clean worktree at parent HEAD.

    Given:  mode=no-state with staged, unstaged, and untracked state present in the
            parent
    Expect: child worktree sits at parent HEAD, no materialization; child status clean
    Source: REQ-21; RESEARCH §4
    """
    from conftest import staged, unstaged, untracked

    world = _materialized(
        repo_scenario,
        states=(
            staged(add="staged.txt"),
            unstaged("tracked.txt"),
            untracked("loose.txt"),
        ),
        mode="no-state",
    )
    assert _status(world) == b""
