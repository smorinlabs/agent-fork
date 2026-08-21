"""Carried-state inventory and content snapshots for fork verification.

The inventory is the single set of paths a fork transports. It is captured in
the parent before the worktree exists, then reused for both the parent-side
bracket and the parent-versus-child comparison, so verification can never
compare a different set of paths than materialization carried.

Membership is resolved with Git, but every path filter is applied in Python on
literal strings: passing recorded paths back to Git as pathspec operands would
reinterpret glob characters such as ``[`` in a filename.
"""

from __future__ import annotations

import errno
import hashlib
import os
import stat
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from agent_fork.errors import EntryUnreadableError
from agent_fork.git import run_git
from agent_fork.text import escape_terminal_text

GITLINK_MODE = "160000"
_DIGEST_CHUNK = 1 << 20


@dataclass(frozen=True)
class IndexEntry:
    mode: str
    oid: str
    stage: str
    path: str


@dataclass(frozen=True)
class ManifestEntry:
    path: str
    tracked: bool
    kind: str
    mode: int
    digest: str
    target: str


@dataclass(frozen=True)
class Inventory:
    """The paths a fork carries, kept by facet so transport can act on each.

    ``paths`` is the flat union used for comparison; the facets are what
    materialization consumes, so both steps are driven by one resolution.
    """

    staged: tuple[str, ...] = ()
    unstaged: tuple[str, ...] = ()
    intent_to_add: tuple[str, ...] = ()
    untracked: tuple[str, ...] = ()
    ignored: tuple[str, ...] = ()
    deletions: tuple[str, ...] = ()
    """Paths the fork carries a deletion for, staged or unstaged.

    Collected explicitly with ``--diff-filter=D`` rather than inferred from a
    missing working-tree path, because a staged ``git rm --cached`` leaves the
    file present on disk: nothing looks absent, yet the cached deletion still
    transports. A skip must be refused while any deletion is carried, since
    ``--no-renames`` splits ``old -> new`` into unassociated endpoints and
    skipping one would silently drop the other (P02 A5).
    """

    @property
    def paths(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    *self.staged,
                    *self.unstaged,
                    *self.intent_to_add,
                    *self.untracked,
                    *self.ignored,
                }
            )
        )


@dataclass(frozen=True)
class Difference:
    """One way two carried states disagree, as structured data."""

    path: str
    check: str
    detail: str


@dataclass(frozen=True)
class SkipRecord:
    """One carried entry that could not be copied and qualified for a skip.

    ``sentinel`` is ``lstat`` metadata taken at observation and rechecked at
    finalization. It carries mode and ctime as well as the obvious fields:
    changing a file from mode ``000`` to ``0644`` preserves inode, size and
    mtime, and its porcelain record stays ``?? path``, so without those two a
    file that became readable mid-fork would be omitted with every check
    reporting agreement.
    """

    path: str
    reason: str
    phase: str
    sentinel: tuple[int, int, int, int, int, int]


def sentinel_for(root: Path, relative: str) -> tuple[int, int, int, int, int, int]:
    info = (root / relative).lstat()
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


@dataclass(frozen=True)
class CarriedState:
    paths: tuple[str, ...]
    index: tuple[IndexEntry, ...]
    manifest: tuple[ManifestEntry, ...]
    skipped: tuple[SkipRecord, ...] = ()


def nul_paths(data: bytes) -> list[str]:
    return [os.fsdecode(value) for value in data.split(b"\0") if value]


def _index_records(root: Path, *, env: Mapping[str, str] | None) -> list[IndexEntry]:
    result = run_git(root, ["ls-files", "--stage", "-z"], env=env)
    entries: list[IndexEntry] = []
    for record in result.stdout.split(b"\0"):
        if not record or b"\t" not in record:
            continue
        meta, raw_path = record.split(b"\t", 1)
        fields = meta.split()
        if len(fields) != 3:
            continue
        mode, oid, stage = (value.decode("ascii", "replace") for value in fields)
        entries.append(IndexEntry(mode, oid, stage, os.fsdecode(raw_path)))
    return entries


def intent_to_add_paths(
    root: Path, *, env: Mapping[str, str] | None = None
) -> list[str]:
    """Paths added with ``--intent-to-add``: visible in the index, content unstaged."""
    visible = run_git(
        root,
        ["diff", "--cached", "--ita-visible-in-index", "--name-only", "-z"],
        env=env,
    )
    hidden = run_git(
        root,
        ["diff", "--cached", "--ita-invisible-in-index", "--name-only", "-z"],
        env=env,
    )
    return sorted(set(nul_paths(visible.stdout)) - set(nul_paths(hidden.stdout)))


def gitlink_paths(root: Path, *, env: Mapping[str, str] | None = None) -> list[str]:
    """Every submodule path recorded in the index, as literal strings.

    Mode 160000 is Git's gitlink entry. Callers need the paths to describe what
    a fork does not carry and to refuse states it cannot represent.
    """
    result = run_git(root, ["ls-files", "--stage", "-z"], env=env)
    paths = [
        os.fsdecode(record.split(b"\t", 1)[1])
        for record in result.stdout.split(b"\0")
        if record.startswith(b"160000 ") and b"\t" in record
    ]
    return sorted(paths)


def parse_porcelain_status(data: bytes) -> dict[str, str]:
    """Map each reported path to its two-letter status code.

    Porcelain v1 with ``-z`` emits a rename or copy as **two** records: the
    entry itself, then a bare source path carrying no status prefix. Slicing a
    prefix off that second record fabricates a path — for a rename source of
    ``abcvendor/submodule`` it yields ``vendor/submodule``, which can collide
    with a real entry. The cursor below skips it, matching the parser in
    ``cleanup.py``.
    """
    records = data.split(b"\0")
    parsed: dict[str, str] = {}
    index = 0
    while index < len(records):
        record = records[index]
        if not record:
            index += 1
            continue
        status = record[:2].decode("ascii", errors="replace")
        parsed[os.fsdecode(record[3:])] = status
        index += 2 if "R" in status or "C" in status else 1
    return parsed


def suppressed_submodules(
    root: Path, *, env: Mapping[str, str] | None = None
) -> list[str]:
    """Submodule paths whose state `--ignore-submodules=dirty` stops reporting.

    This is what a fork actually leaves behind: submodules Git would call
    modified on working-tree grounds alone. A submodule sitting at its recorded
    commit is not in this set, and neither is a commit-level gitlink difference
    alone, because the filter keeps reporting that and the fork carries it.

    The comparison is per status **code**, not per path. A submodule can be both
    staged at a new commit and dirty inside, which Git reports as ``MM`` and the
    filter reduces to ``M ``: the path is present on both sides, so comparing
    membership alone would miss the working-tree half that is genuinely lost.
    """
    gitlinks = set(gitlink_paths(root, env=env))
    if not gitlinks:
        return []

    def reported(mode: str) -> dict[str, str]:
        result = run_git(
            root,
            [
                "status",
                "--porcelain=v1",
                "-z",
                "--untracked-files=all",
                f"--ignore-submodules={mode}",
            ],
            env=env,
        )
        return parse_porcelain_status(result.stdout)

    unfiltered = reported("none")
    filtered = reported("dirty")
    return sorted(
        path
        for path in gitlinks
        if path in unfiltered and unfiltered[path] != filtered.get(path)
    )


def collect_inventory(
    root: Path,
    *,
    with_state: bool,
    with_ignored: bool,
    env: Mapping[str, str] | None = None,
) -> Inventory:
    """Resolve every path a fork of ``root`` carries, by facet.

    Renames are recorded at both endpoints and deletions are kept as members so
    the child can be checked for the file's absence; ``--no-renames`` reports a
    rename as a delete of the old path plus an add of the new one, which yields
    both endpoints without rename-detection heuristics.

    The result is the single domain shared by transport and verification. It is
    resolved once, before the worktree exists, so a file that appears or
    disappears mid-fork cannot change what either step operates on.
    """
    if not with_state:
        return Inventory()

    def listing(arguments: list[str]) -> tuple[str, ...]:
        return tuple(nul_paths(run_git(root, arguments, env=env).stdout))

    ignored: tuple[str, ...] = ()
    if with_ignored:
        ignored = listing(
            ["ls-files", "--others", "-z", "--ignored", "--exclude-standard"]
        )
    return Inventory(
        staged=listing(["diff", "--cached", "--name-only", "-z", "--no-renames"]),
        unstaged=listing(
            [
                "diff",
                "--name-only",
                "-z",
                "--no-renames",
                "--ignore-submodules=dirty",
            ]
        ),
        intent_to_add=tuple(intent_to_add_paths(root, env=env)),
        untracked=listing(["ls-files", "--others", "-z", "--exclude-standard"]),
        ignored=ignored,
        deletions=tuple(
            sorted(
                {
                    *listing(
                        [
                            "diff",
                            "--cached",
                            "--name-only",
                            "-z",
                            "--no-renames",
                            "--diff-filter=D",
                        ]
                    ),
                    *listing(
                        [
                            "diff",
                            "--name-only",
                            "-z",
                            "--no-renames",
                            "--diff-filter=D",
                            "--ignore-submodules=dirty",
                        ]
                    ),
                }
            )
        ),
    )


def _digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_DIGEST_CHUNK):
            hasher.update(chunk)
    return hasher.hexdigest()


def _manifest_entry(root: Path, relative: str, *, tracked: bool) -> ManifestEntry:
    target = root / relative
    try:
        info = target.lstat()
    except OSError as error:
        # Only a genuinely missing path may read as absent. Every other errno —
        # EACCES from an untraversable ancestor, EIO, ELOOP — would otherwise
        # masquerade as a deletion, which the carried-state rules treat as
        # legitimate, and the entry would be dropped silently (P02 A5).
        if error.errno not in (errno.ENOENT, errno.ENOTDIR):
            raise EntryUnreadableError(
                f"cannot stat carried entry: {escape_terminal_text(relative)}",
                path=relative,
                reason="lstat-failed",
                phase="capture",
            ) from error
        return ManifestEntry(relative, tracked, "absent", 0, "", "")
    mode = stat.S_IMODE(info.st_mode)
    if stat.S_ISLNK(info.st_mode):
        return ManifestEntry(
            relative, tracked, "symlink", mode, "", os.readlink(target)
        )
    if stat.S_ISREG(info.st_mode):
        try:
            digest = _digest(target)
        except OSError as error:
            raise EntryUnreadableError(
                f"cannot read carried entry: {escape_terminal_text(relative)}",
                path=relative,
                reason="unreadable",
                phase="capture",
            ) from error
        return ManifestEntry(relative, tracked, "file", mode, digest, "")
    return ManifestEntry(relative, tracked, "other", mode, "", "")


def capture_state(
    root: Path,
    inventory: Inventory | Iterable[str],
    *,
    env: Mapping[str, str] | None = None,
) -> CarriedState:
    """Snapshot index and working-tree facts for ``inventory`` inside ``root``."""
    paths = tuple(inventory.paths if isinstance(inventory, Inventory) else inventory)
    carried = set(paths)
    index = tuple(
        entry for entry in _index_records(root, env=env) if entry.path in carried
    )
    gitlinks = {entry.path for entry in index if entry.mode == GITLINK_MODE}
    tracked = {entry.path for entry in index}
    skippable: set[str] = set()
    blockers: tuple[str, ...] = ()
    if isinstance(inventory, Inventory):
        skippable = {*inventory.untracked, *inventory.ignored} - tracked
        blockers = inventory.deletions

    entries: list[ManifestEntry] = []
    skipped: list[SkipRecord] = []
    for relative in paths:
        if relative in gitlinks:
            continue
        try:
            entries.append(_manifest_entry(root, relative, tracked=relative in tracked))
        except EntryUnreadableError as error:
            entry = error.details["entry"]
            reason = entry.get("reason", "") if isinstance(entry, dict) else ""
            # Three preconditions, all required. A tracked path never skips
            # because a rename's endpoints land in different listings; a failed
            # lstat never skips because no sentinel could be recorded; and no
            # path skips while a deletion is carried, for the same
            # split-endpoint reason (P02 A5).
            if reason != "unreadable" or relative not in skippable:
                raise
            if blockers:
                raise EntryUnreadableError(
                    "cannot skip a carried entry while the fork carries a "
                    f"deletion: {escape_terminal_text(relative)}",
                    path=relative,
                    reason="skip-blocked-by-deletion",
                    phase="capture",
                    deletion_blockers=blockers,
                ) from error
            skipped.append(
                SkipRecord(
                    relative, "unreadable", "capture", sentinel_for(root, relative)
                )
            )
    carried_paths = tuple(p for p in paths if p not in {r.path for r in skipped})
    return CarriedState(carried_paths, index, tuple(entries), tuple(skipped))


def _index_map(state: CarriedState) -> dict[tuple[str, str], IndexEntry]:
    return {(entry.path, entry.stage): entry for entry in state.index}


def _manifest_map(state: CarriedState) -> dict[str, ManifestEntry]:
    return {entry.path: entry for entry in state.manifest}


def _manifest_difference(
    expected: ManifestEntry, actual: ManifestEntry
) -> Difference | None:
    if expected.kind != actual.kind:
        return Difference(
            expected.path, "type", f"{expected.kind} became {actual.kind}"
        )
    if expected.kind == "symlink":
        if expected.target != actual.target:
            return Difference(expected.path, "symlink-target", "symlink target differs")
        return None
    if expected.kind == "file" and expected.digest != actual.digest:
        return Difference(expected.path, "content", "content differs")
    if expected.tracked:
        if bool(expected.mode & stat.S_IXUSR) != bool(actual.mode & stat.S_IXUSR):
            return Difference(expected.path, "mode", "executable bit differs")
    elif expected.mode != actual.mode:
        return Difference(expected.path, "mode", "mode differs")
    return None


def compare_states(
    expected: CarriedState, actual: CarriedState
) -> tuple[Difference, ...]:
    """Describe every way ``actual`` departs from ``expected``."""
    differences: list[Difference] = []
    expected_paths = set(expected.paths)
    actual_paths = set(actual.paths)
    differences.extend(
        Difference(path, "membership", "no longer carried")
        for path in expected.paths
        if path not in actual_paths
    )
    differences.extend(
        Difference(path, "membership", "newly carried")
        for path in actual.paths
        if path not in expected_paths
    )

    expected_index = _index_map(expected)
    actual_index = _index_map(actual)
    for key, entry in expected_index.items():
        other = actual_index.get(key)
        if other is None:
            differences.append(Difference(entry.path, "staged", "staged entry missing"))
        elif (entry.mode, entry.oid) != (other.mode, other.oid):
            differences.append(
                Difference(entry.path, "staged", "staged content differs")
            )
    for key, entry in actual_index.items():
        if key not in expected_index:
            differences.append(
                Difference(entry.path, "staged", "unexpected staged entry")
            )

    expected_manifest = _manifest_map(expected)
    actual_manifest = _manifest_map(actual)
    for path, entry in expected_manifest.items():
        other = actual_manifest.get(path)
        if other is None:
            differences.append(
                Difference(path, "working-tree", "working-tree entry missing")
            )
            continue
        difference = _manifest_difference(entry, other)
        if difference is not None:
            differences.append(difference)
    for path in actual_manifest:
        if path not in expected_manifest:
            differences.append(
                Difference(path, "working-tree", "unexpected working-tree entry")
            )
    return tuple(differences)
