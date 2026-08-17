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

import hashlib
import os
import stat
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from agent_fork.git import run_git

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
class CarriedState:
    paths: tuple[str, ...]
    index: tuple[IndexEntry, ...]
    manifest: tuple[ManifestEntry, ...]


def _nul_paths(data: bytes) -> list[str]:
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


def collect_inventory(
    root: Path,
    *,
    with_state: bool,
    with_ignored: bool,
    env: Mapping[str, str] | None = None,
) -> tuple[str, ...]:
    """Resolve every path a fork of ``root`` carries, as sorted literal paths.

    Renames are recorded at both endpoints and deletions are kept as members so
    the child can be checked for the file's absence; ``--no-renames`` reports a
    rename as a delete of the old path plus an add of the new one, which yields
    both endpoints without rename-detection heuristics.
    """
    if not with_state:
        return ()
    paths: set[str] = set()
    for arguments in (
        ["diff", "--cached", "--name-only", "-z", "--no-renames"],
        ["diff", "--name-only", "-z", "--no-renames"],
        ["ls-files", "--others", "-z", "--exclude-standard"],
    ):
        paths.update(_nul_paths(run_git(root, arguments, env=env).stdout))
    if with_ignored:
        paths.update(
            _nul_paths(
                run_git(
                    root,
                    ["ls-files", "--others", "-z", "--ignored", "--exclude-standard"],
                    env=env,
                ).stdout
            )
        )
    return tuple(sorted(paths))


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
    except OSError:
        return ManifestEntry(relative, tracked, "absent", 0, "", "")
    mode = stat.S_IMODE(info.st_mode)
    if stat.S_ISLNK(info.st_mode):
        return ManifestEntry(
            relative, tracked, "symlink", mode, "", os.readlink(target)
        )
    if stat.S_ISREG(info.st_mode):
        return ManifestEntry(relative, tracked, "file", mode, _digest(target), "")
    return ManifestEntry(relative, tracked, "other", mode, "", "")


def capture_state(
    root: Path,
    inventory: Iterable[str],
    *,
    env: Mapping[str, str] | None = None,
) -> CarriedState:
    """Snapshot index and working-tree facts for ``inventory`` inside ``root``."""
    paths = tuple(inventory)
    carried = set(paths)
    index = tuple(
        entry for entry in _index_records(root, env=env) if entry.path in carried
    )
    gitlinks = {entry.path for entry in index if entry.mode == GITLINK_MODE}
    tracked = {entry.path for entry in index}
    manifest = tuple(
        _manifest_entry(root, relative, tracked=relative in tracked)
        for relative in paths
        if relative not in gitlinks
    )
    return CarriedState(paths, index, manifest)


def _index_map(state: CarriedState) -> dict[tuple[str, str], IndexEntry]:
    return {(entry.path, entry.stage): entry for entry in state.index}


def _manifest_map(state: CarriedState) -> dict[str, ManifestEntry]:
    return {entry.path: entry for entry in state.manifest}


def _manifest_difference(expected: ManifestEntry, actual: ManifestEntry) -> str | None:
    if expected.kind != actual.kind:
        return f"{expected.path}: {expected.kind} became {actual.kind}"
    if expected.kind == "symlink" and expected.target != actual.target:
        return f"{expected.path}: symlink target differs"
    if expected.kind == "file" and expected.digest != actual.digest:
        return f"{expected.path}: content differs"
    if expected.tracked:
        if bool(expected.mode & 0o111) != bool(actual.mode & 0o111):
            return f"{expected.path}: executable bit differs"
    elif expected.mode != actual.mode:
        return f"{expected.path}: mode differs"
    return None


def compare_states(expected: CarriedState, actual: CarriedState) -> tuple[str, ...]:
    """Describe every way ``actual`` departs from ``expected``, most specific first."""
    differences: list[str] = []
    missing = [path for path in expected.paths if path not in set(actual.paths)]
    extra = [path for path in actual.paths if path not in set(expected.paths)]
    differences.extend(f"{path}: no longer carried" for path in missing)
    differences.extend(f"{path}: newly carried" for path in extra)

    actual_index = _index_map(actual)
    for key, entry in _index_map(expected).items():
        other = actual_index.get(key)
        if other is None:
            differences.append(f"{entry.path}: staged entry missing")
        elif (entry.mode, entry.oid) != (other.mode, other.oid):
            differences.append(f"{entry.path}: staged content differs")
    for key, entry in actual_index.items():
        if key not in _index_map(expected):
            differences.append(f"{entry.path}: unexpected staged entry")

    actual_manifest = _manifest_map(actual)
    for path, entry in _manifest_map(expected).items():
        other = actual_manifest.get(path)
        if other is None:
            continue
        difference = _manifest_difference(entry, other)
        if difference is not None:
            differences.append(difference)
    return tuple(differences)
