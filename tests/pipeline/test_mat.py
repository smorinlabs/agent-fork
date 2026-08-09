"""G-MAT — Materialize (tier F).

Matrix: docs/testing/TEST-MATRIX.md §G-MAT.
"""

import pytest


@pytest.mark.matrix("T-MAT-01")
@pytest.mark.skip(reason="pending: T-MAT-01")
def test_staged_only_file_transported_byte_identical(repo_scenario):
    """T-MAT-01 — a staged-only file transports with index/worktree status A and
    byte-identical content.

    Given:  a file staged (added) but not yet committed in the parent
    Expect: child index and worktree show `A `; content byte-identical (manifest oracle)
    Source: REQ-21; RESEARCH §2.2 step 1
    """
    raise NotImplementedError


@pytest.mark.matrix("T-MAT-02")
@pytest.mark.skip(reason="pending: T-MAT-02")
def test_unstaged_only_file_transported_index_untouched(repo_scenario):
    """T-MAT-02 — an unstaged-only edit transports to the worktree, leaving the index
    untouched.

    Given:  a tracked file with an unstaged worktree modification only
    Expect: child worktree shows ` M`; index untouched
    Source: REQ-21; RESEARCH §2.2 step 2
    """
    raise NotImplementedError


@pytest.mark.matrix("T-MAT-03")
@pytest.mark.skip(reason="pending: T-MAT-03")
def test_staged_and_unstaged_split_preserved_on_same_file(repo_scenario):
    """T-MAT-03 — staged and unstaged edits on the same file keep their split origin.

    Given:  one tracked file with both a staged edit and a further unstaged edit
    Expect: child index/worktree shapes (`A `/`AM`/` M`) match the staged-vs-unstaged
            origin of each hunk
    Source: REQ-21; RESEARCH §2.2
    """
    raise NotImplementedError


@pytest.mark.matrix("T-MAT-04")
@pytest.mark.skip(reason="pending: T-MAT-04")
def test_untracked_files_including_nested_dirs_copied(repo_scenario):
    """T-MAT-04 — untracked files, including nested directories, copy byte-for-byte.

    Given:  untracked files at the repo root and inside nested untracked directories
    Expect: copied byte-for-byte; manifest oracle proves inner files present
    Source: REQ-21; RESEARCH §2.2 step 3
    """
    raise NotImplementedError


@pytest.mark.matrix("T-MAT-05")
@pytest.mark.skip(reason="pending: T-MAT-05")
def test_ignored_files_copied_under_exact_plus_ignored(repo_scenario):
    """T-MAT-05 — ignored files copy under mode=exact+ignored via the opt-in second
    pass.

    Given:  mode=exact+ignored with files matched by `.gitignore` present
    Expect: the union of both `ls-files --others` passes is copied
    Source: REQ-21; RESEARCH §2.2 step 3b
    """
    raise NotImplementedError


@pytest.mark.matrix("T-MAT-06")
@pytest.mark.skip(reason="pending: T-MAT-06")
def test_symlink_relative_target_recreated_verbatim(repo_scenario):
    """T-MAT-06 — a relative-target symlink is recreated verbatim.

    Given:  a tracked symlink with a relative target
    Expect: recreated verbatim via readlink; target stays relative
    Source: REQ-21; RESEARCH §2.2
    """
    raise NotImplementedError


@pytest.mark.matrix("T-MAT-07")
@pytest.mark.skip(reason="pending: T-MAT-07")
def test_symlink_absolute_target_recreated_verbatim(repo_scenario):
    """T-MAT-07 — an absolute-target symlink is recreated verbatim.

    Given:  a tracked symlink with an absolute target
    Expect: recreated verbatim via readlink; target stays absolute
    Source: REQ-21; RESEARCH §2.2
    """
    raise NotImplementedError


@pytest.mark.matrix("T-MAT-08")
@pytest.mark.skip(reason="pending: T-MAT-08")
def test_exec_bit_only_change_preserved(repo_scenario):
    """T-MAT-08 — an exec-bit-only change preserves the permission bit with identical
    content.

    Given:  a tracked file with only its executable bit changed (no content diff)
    Expect: permission bit preserved in the child; content identical
    Source: REQ-21; RESEARCH §2.2
    """
    raise NotImplementedError


@pytest.mark.matrix("T-MAT-09")
@pytest.mark.skip(reason="pending: T-MAT-09")
def test_binary_file_staged_transported_byte_identical(repo_scenario):
    """T-MAT-09 — a staged binary file transports byte-identical via a cached --binary
    diff.

    Given:  a binary file staged in the parent
    Expect: cached `--binary` diff applies with `--index`; child byte-identical
    Source: REQ-21; RESEARCH §2.2 step 1
    """
    raise NotImplementedError


@pytest.mark.matrix("T-MAT-10")
@pytest.mark.skip(reason="pending: T-MAT-10")
def test_binary_file_unstaged_transported_byte_identical(repo_scenario):
    """T-MAT-10 — an unstaged binary file transports byte-identical via an uncached
    --binary diff.

    Given:  a binary file with an unstaged modification in the parent
    Expect: uncached `--binary` diff applies without `--index`; child byte-identical
    Source: REQ-21; RESEARCH §2.2 step 2
    """
    raise NotImplementedError


@pytest.mark.matrix("T-MAT-11")
@pytest.mark.skip(reason="pending: T-MAT-11")
def test_rename_and_edit_transported_correctly(repo_scenario):
    """T-MAT-11 — a renamed-and-edited file transports with the rename and the edit
    intact.

    Given:  a tracked file renamed and edited in the same change
    Expect: child reflects the rename with edited content; manifest oracle confirms the
            old path is absent and the new path's content is correct
    Source: REQ-21; RESEARCH §2.2
    """
    raise NotImplementedError


@pytest.mark.matrix("T-MAT-12")
@pytest.mark.skip(reason="pending: T-MAT-12")
def test_intent_to_add_file_transported_as_ita(repo_scenario):
    """T-MAT-12 — an intent-to-add file transports as ITA, not as an untracked file.

    Given:  a file staged with `git add -N` (intent-to-add)
    Expect: cached diff uses `--ita-invisible-in-index`, applied via `apply
            --intent-to-add`; child shows ` A` not `??` (ITA-aware oracle)
    Source: REQ-21 (A3)
    """
    raise NotImplementedError


@pytest.mark.matrix("T-MAT-13")
@pytest.mark.skip(reason="pending: T-MAT-13")
def test_empty_directory_documented_absence(repo_scenario):
    """T-MAT-13 — an empty directory in the parent is a documented absence in the child.

    Given:  an empty directory present in the parent working tree
    Expect: documented absence in the child (git-visible state copy only; empty-dir
            expectation declared per mode)
    Source: REQ-21; spec §6.5
    """
    raise NotImplementedError


@pytest.mark.matrix("T-MAT-14")
@pytest.mark.skip(reason="pending: T-MAT-14")
def test_submodule_treated_opaque_by_gitlink_oid(repo_scenario):
    """T-MAT-14 — a submodule is treated opaque and compared by gitlink OID.

    Given:  a submodule present in the parent, fixture built with command-scoped `-c
            protocol.file.allow=always`
    Expect: treated opaque; gitlink OID (mode-160000) compared; submodule contents
            pruned from the manifest
    Source: RESEARCH §2.1 step 6; spec §6.3; RESEARCH §4
    """
    raise NotImplementedError


@pytest.mark.matrix("T-MAT-15")
@pytest.mark.skip(reason="pending: T-MAT-15")
def test_parent_read_only_during_materialize(repo_scenario):
    """T-MAT-15 — the parent stays strictly read-only during materialize.

    Given:  a full manifest+index snapshot of the parent taken before materialize
    Expect: the same snapshot taken after materialize is byte-identical
    Source: REQ-21; spec §6.5 item 3
    """
    raise NotImplementedError


@pytest.mark.matrix("T-MAT-16")
@pytest.mark.skip(reason="pending: T-MAT-16")
def test_linked_worktree_dirty_both_checkouts_only_parent_travels(repo_scenario):
    """T-MAT-16 — linked-worktree with dirty state in both checkouts only carries the
    parent worktree's state.

    Given:  distinct staged/unstaged/untracked state in both the parent worktree and the
            main checkout
    Expect: only the parent worktree's state travels to the child
    Source: spec §4 mandatory interaction set; REQ-21
    """
    raise NotImplementedError


@pytest.mark.matrix("T-MAT-17")
@pytest.mark.skip(reason="pending: T-MAT-17")
def test_linked_worktree_exact_plus_ignored_scoped_to_parent(repo_scenario):
    """T-MAT-17 — linked-worktree under mode=exact+ignored scopes both passes to the
    parent worktree only.

    Given:  mode=exact+ignored in a linked-worktree topology
    Expect: materialize plus the ignored pass are both scoped to the parent worktree
            only
    Source: spec §4 mandatory interaction set; REQ-21
    """
    raise NotImplementedError


@pytest.mark.matrix("T-MAT-18")
@pytest.mark.skip(reason="pending: T-MAT-18")
def test_mode_exact_full_materialize(repo_scenario):
    """T-MAT-18 — mode=exact fully materializes staged+unstaged+untracked, excluding
    ignored.

    Given:  mode=exact with staged, unstaged, and untracked state present
    Expect: staged+unstaged+untracked copied; ignored excluded
    Source: REQ-21
    """
    raise NotImplementedError


@pytest.mark.matrix("T-MAT-19")
@pytest.mark.skip(reason="pending: T-MAT-19")
def test_mode_exact_plus_ignored_full_materialize(repo_scenario):
    """T-MAT-19 — mode=exact+ignored fully materializes
    staged+unstaged+untracked+ignored.

    Given:  mode=exact+ignored with staged, unstaged, untracked, and ignored state
            present
    Expect: staged+unstaged+untracked+ignored all copied
    Source: REQ-21
    """
    raise NotImplementedError


@pytest.mark.matrix("T-MAT-20")
@pytest.mark.skip(reason="pending: T-MAT-20")
def test_mode_no_state_full_materialize(repo_scenario):
    """T-MAT-20 — mode=no-state materializes a clean worktree at parent HEAD.

    Given:  mode=no-state with staged, unstaged, and untracked state present in the
            parent
    Expect: child worktree sits at parent HEAD, no materialization; child status clean
    Source: REQ-21; RESEARCH §4
    """
    raise NotImplementedError
