"""Shared fixture layer for the agent-fork test suite.

Signatures only (skeleton phase). Bodies land via TDD in the VM, G-FIX first.
Spec: docs/superpowers/specs/2026-08-08-test-architecture-design.md §6.
"""

from __future__ import annotations

import errno
import hashlib
import os
import re
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import termios
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

TEST_HARNESS_GIT_MIN = (2, 43)  # spec §2/§7.5 — F/C/R tiers hard-error below this
PTY_PROCESS_TIMEOUT_SECONDS = 10


def _parse_git_version(output: str) -> tuple[int, int, int]:
    match = re.search(r"\b(\d+)\.(\d+)(?:\.(\d+))?", output)
    if match is None:
        raise ValueError(f"unrecognized git version output: {output!r}")
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch or 0)


def _harness_floor_error(paths: list[str], version_output: str) -> str | None:
    tier_segments = {"pipeline", "cli", "live", "fixtures"}
    invokes_real_git = any(
        any(
            parts[index] == "tests" and parts[index + 1] in tier_segments
            for index in range(len(parts) - 1)
        )
        for parts in (Path(path).parts for path in paths)
    )
    version = _parse_git_version(version_output)
    if invokes_real_git and version < (*TEST_HARNESS_GIT_MIN, 0):
        floor = ".".join(map(str, TEST_HARNESS_GIT_MIN))
        installed = ".".join(map(str, version))
        return f"Git {installed} is below TEST_HARNESS_GIT_MIN {floor} for F/C/R tiers"
    return None


def pytest_collection_modifyitems(items):
    paths = [str(item.path) for item in items]
    version = subprocess.run(
        ["git", "--version"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    error = _harness_floor_error(paths, version)
    if error is not None:
        raise pytest.UsageError(error)


@dataclass(frozen=True)
class StateSpec:
    """One file-state element of a scenario (spec §6.3 vocabulary)."""

    kind: str
    path: str
    target: str | None = None
    content: bytes | None = None


@dataclass(frozen=True)
class OriginSpec:
    """Local bare-repo remote: wired, fetched, set-head applied (spec §6.4)."""

    pushed: int = 0
    unpushed: int = 0


@dataclass(frozen=True)
class RepoSpec:
    """Declarative world description consumed by repo_scenario (spec §6.1)."""

    topology: str = "plain@branch"
    states: tuple[StateSpec, ...] = ()
    remote: OriginSpec | None = None


def staged(modify: str | None = None, add: str | None = None) -> StateSpec:
    """Staged modification or staged new file (spec §6.3)."""
    if modify is not None and add is not None:
        raise ValueError("staged accepts either modify or add, not both")
    if add is not None:
        return StateSpec("staged-add", add, content=b"staged add\n")
    return StateSpec("staged-modify", modify or "tracked.txt", content=b"staged\n")


def unstaged(path: str | None = None) -> StateSpec:
    """Unstaged worktree modification of a tracked file (spec §6.3)."""
    return StateSpec("unstaged", path or "tracked.txt", content=b"unstaged\n")


def untracked(
    path: str | None = None, symlink: str | None = None, target: str | None = None
) -> StateSpec:
    """Untracked file, including nested-directory paths (spec §6.3)."""
    chosen = path or symlink or "untracked.txt"
    kind = "untracked-symlink" if symlink is not None else "untracked"
    return StateSpec(kind, chosen, target=target, content=b"untracked\n")


def ignored(path: str | None = None) -> StateSpec:
    """File matched by `.gitignore` (spec §6.3)."""
    return StateSpec("ignored", path or "ignored.txt", content=b"ignored\n")


def symlink_state(
    path: str | None = None, target: str | None = None, absolute: bool = False
) -> StateSpec:
    """Tracked symlink, relative or absolute target (spec §6.3)."""
    chosen_path = path or "tracked-link"
    chosen_target = target or ("/tmp/agent-fork-target" if absolute else "tracked.txt")
    return StateSpec("symlink", chosen_path, target=chosen_target)


def exec_bit(path: str | None = None) -> StateSpec:
    """Exec-bit-only change on an otherwise-unmodified tracked file (spec §6.3)."""
    return StateSpec(
        "exec-bit", path or "executable.sh", content=b"#!/bin/sh\nexit 0\n"
    )


def binary_state(staged: bool) -> StateSpec:
    """Binary file, staged or unstaged variant (spec §6.3)."""
    return StateSpec("binary-staged" if staged else "binary-unstaged", "binary.bin")


def rename_edit(path: str | None = None) -> StateSpec:
    """Renamed-and-edited tracked file (spec §6.3)."""
    return StateSpec("rename-edit", path or "renamed.txt", target="renamed-new.txt")


def intent_to_add(path: str | None = None) -> StateSpec:
    """`git add -N` intent-to-add entry (spec §6.3)."""
    return StateSpec("intent-to-add", path or "intent.txt", content=b"intent\n")


def unmerged(markerless: bool) -> StateSpec:
    """Unmerged index entry, optionally markerless in the worktree (spec §6.3)."""
    return StateSpec(
        "unmerged", "conflicted.txt", target="markerless" if markerless else "markers"
    )


def empty_dir(ignored: bool) -> StateSpec:
    """Empty directory, plain or `.gitignore`d (spec §6.3)."""
    return StateSpec("empty-dir-ignored" if ignored else "empty-dir", "empty-dir")


def submodule(path: str | None = None, dirty: str | None = None) -> StateSpec:
    """Submodule gitlink, seeded with `-c protocol.file.allow=always` (spec §6.3).

    ``dirty`` selects what state the submodule carries, which is what A6
    distinguishes. ``None`` leaves it clean. ``"modified"`` edits a tracked file
    inside it and ``"untracked"`` adds an untracked one — both make the parent
    report ` M <path>` while the child, whose submodule is never initialized,
    reports nothing. ``"advanced"`` commits inside the submodule without staging
    the gitlink in the parent, and ``"advanced-staged"`` also stages it; only the
    staged form is transportable, because the gitlink OID then travels in the
    parent's staged patch.
    """
    if dirty not in (None, "modified", "untracked", "advanced", "advanced-staged"):
        raise ValueError(f"unknown submodule dirt: {dirty}")
    return StateSpec("submodule", path or "vendor/submodule", target=dirty)


def worktreeinclude(pattern: str | None = None) -> StateSpec:
    """`.worktreeinclude` entry (spec §6.3)."""
    return StateSpec("worktreeinclude", ".worktreeinclude", target=pattern or ".env")


def origin(pushed: int = 0, unpushed: int = 0) -> OriginSpec:
    """Local bare-repo remote spec: wired, fetched, set-head applied (spec §6.4)."""
    return OriginSpec(pushed=pushed, unpushed=unpushed)


@dataclass
class WorldHandle:
    """Built world: realpathed paths, sealed env, test-side oracles (spec §6.5)."""

    parent_path: Path
    child_path: Path | None
    env: dict[str, str]
    topology: str = "plain@branch"
    repo_root: Path | None = None
    main_path: Path | None = None
    git_dir: Path | None = None
    go_files: list[Path] = field(default_factory=list)
    process_groups: list[int] = field(default_factory=list)

    def manifest_diff(self, a: Path, b: Path) -> list[str]:
        """lstat-only manifest+hash comparison; empty list means identical."""
        left = _manifest(a, self.env)
        right = _manifest(b, self.env)
        return _mapping_diff("manifest", left, right)

    def index_diff(self, a: Path, b: Path) -> list[str]:
        """git ls-files --stage comparison (blob IDs + modes), ITA-aware."""
        left = _index_snapshot(a, self.env)
        right = _index_snapshot(b, self.env)
        return _mapping_diff("index", left, right)

    def parent_snapshot(self) -> object:
        """Full manifest+index snapshot for the parent-inviolate assertion."""
        return (
            _manifest(self.parent_path, self.env),
            _index_snapshot(self.parent_path, self.env),
        )


def _run_git(
    env: dict[str, str],
    cwd: Path,
    *args: str,
    check: bool = True,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        env=env,
        input=input_bytes,
        capture_output=True,
        check=check,
    )


def _commit_file(repo: Path, env: dict[str, str], name: str, content: str) -> None:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    _run_git(env, repo, "add", "--", name)
    _run_git(env, repo, "commit", "-m", f"seed {name}")


def _init_plain(path: Path, env: dict[str, str], *, commit: bool = True) -> None:
    path.mkdir(parents=True)
    _run_git(env, path, "init", "-b", "main")
    if commit:
        _commit_file(path, env, "tracked.txt", "base\n")


def _seed_bare(path: Path, seed: Path, env: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "--bare", "--initial-branch=main", str(path)],
        env=env,
        capture_output=True,
        check=True,
    )
    _init_plain(seed, env)
    _run_git(env, seed, "remote", "add", "origin", str(path))
    _run_git(env, seed, "push", "-u", "origin", "main")


def _chmod_retry(function, path, exc_info) -> None:
    del exc_info
    candidate = Path(path)
    candidate.chmod(candidate.stat().st_mode | stat.S_IWUSR | stat.S_IXUSR)
    function(path)


@pytest.fixture
def repo_scenario(tmp_path, request):
    """Build a WorldHandle from a RepoSpec. Sealed whitelist env (spec §6.2)."""

    counter = 0
    go_files: list[Path] = []
    process_groups: list[int] = []

    def finalize() -> None:
        for go_file in go_files:
            go_file.parent.mkdir(parents=True, exist_ok=True)
            go_file.touch(exist_ok=True)
        for process_group in process_groups:
            try:
                os.killpg(process_group, signal.SIGKILL)
            except ProcessLookupError:
                pass
        shutil.rmtree(tmp_path, onerror=_chmod_retry)
        proc = Path("/proc")
        if proc.exists():
            root = str(tmp_path.resolve())
            orphans: list[str] = []
            for cwd_link in proc.glob("[0-9]*/cwd"):
                try:
                    cwd = os.path.realpath(cwd_link)
                except OSError:
                    continue
                if cwd == root or cwd.startswith(f"{root}{os.sep}"):
                    orphans.append(cwd_link.parent.name)
            if orphans:
                pytest.fail(f"orphan processes survived fixture teardown: {orphans}")

    request.addfinalizer(finalize)

    def _build(topology: str = "plain@branch", states=(), remote=None) -> WorldHandle:
        nonlocal counter
        counter += 1
        world = tmp_path / f"world-{counter}"
        env = sealed_env(
            {
                "HOME": str(world / "home"),
                "TMPDIR": str(world / "tmp"),
                "XDG_CONFIG_HOME": str(world / "xdg/config"),
                "XDG_STATE_HOME": str(world / "xdg/state"),
                "XDG_DATA_HOME": str(world / "xdg/data"),
                "XDG_CONFIG_DIRS": str(world / "xdg/config-dirs"),
            }
        )
        repo_root: Path
        parent: Path
        main: Path | None = None

        if topology in {"plain@branch", "plain@main", "detached"}:
            repo_root = world / "repo"
            _init_plain(repo_root, env)
            parent = repo_root
            main = repo_root
            if topology == "plain@branch":
                _run_git(env, repo_root, "switch", "-c", "feature")
            elif topology == "detached":
                _run_git(env, repo_root, "checkout", "--detach", "HEAD")
        elif topology == "linked-worktree":
            repo_root = world / "main"
            _init_plain(repo_root, env)
            _run_git(env, repo_root, "branch", "feature")
            parent = world / "external-worktrees/linked"
            parent.parent.mkdir()
            _run_git(env, repo_root, "worktree", "add", str(parent), "feature")
            _commit_file(parent, env, "linked-only.txt", "linked commit\n")
            (repo_root / "tracked.txt").write_text("dirty main\n")
            (parent / "linked-only.txt").write_text("dirty linked\n")
            main = repo_root
        elif topology in {"bare@bare", "bare@wt"}:
            repo_root = world / "repo.git"
            _seed_bare(repo_root, world / "seed", env)
            if topology == "bare@bare":
                parent = repo_root
            else:
                parent = world / "worktree"
                _run_git(env, repo_root, "worktree", "add", str(parent), "main")
        elif topology == "dot-bare@wt":
            project = world / "project"
            repo_root = project / ".bare"
            _seed_bare(repo_root, world / "seed", env)
            parent = project / "main"
            _run_git(env, repo_root, "worktree", "add", str(parent), "main")
        elif topology == "nested-bare":
            project = world / "project"
            repo_root = project / "nested.git"
            _seed_bare(repo_root, world / "seed", env)
            parent = repo_root
        elif topology == "unborn(plain)":
            repo_root = world / "repo"
            _init_plain(repo_root, env, commit=False)
            parent = repo_root
            main = repo_root
        elif topology == "unborn(bare)":
            repo_root = world / "repo.git"
            repo_root.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "init", "--bare", "--initial-branch=main", str(repo_root)],
                env=env,
                capture_output=True,
                check=True,
            )
            parent = repo_root
        else:
            raise ValueError(f"unknown topology: {topology}")

        handle = WorldHandle(
            parent_path=parent.resolve(),
            child_path=None,
            env=env,
            topology=topology,
            repo_root=repo_root.resolve(),
            main_path=main.resolve() if main is not None else None,
            go_files=go_files,
            process_groups=process_groups,
        )
        git_dir_result = _run_git(env, handle.parent_path, "rev-parse", "--git-dir")
        git_dir_text = git_dir_result.stdout.decode().strip()
        git_dir = Path(git_dir_text)
        if not git_dir.is_absolute():
            git_dir = handle.parent_path / git_dir
        handle.git_dir = git_dir.resolve()
        if remote is not None:
            _apply_origin(handle, remote)
        _apply_states(handle, tuple(states))
        return handle

    return _build


def _gitlinks(root: Path, env: dict[str, str]) -> set[str]:
    result = _run_git(env, root, "ls-files", "--stage", "-z", check=False)
    links: set[str] = set()
    for record in result.stdout.split(b"\0"):
        if not record or b"\t" not in record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        if metadata.startswith(b"160000 "):
            links.add(os.fsdecode(raw_path))
    return links


def _manifest(root: Path, env: dict[str, str]) -> dict[str, tuple[Any, ...]]:
    root = root.resolve()
    gitlinks = _gitlinks(root, env)
    entries: dict[str, tuple[Any, ...]] = {}
    for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        rel_current = current_path.relative_to(root)
        if rel_current == Path("."):
            dirs[:] = [name for name in dirs if name != ".git"]
            files = [name for name in files if name != ".git"]
        for name in list(dirs):
            path = current_path / name
            rel = path.relative_to(root).as_posix()
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode):
                entries[rel] = (
                    "symlink",
                    stat.S_IMODE(info.st_mode),
                    os.readlink(path),
                )
                dirs.remove(name)
            elif rel in gitlinks:
                entries[rel] = ("gitlink",)
                dirs.remove(name)
            else:
                entries[rel] = ("dir", stat.S_IMODE(info.st_mode))
        for name in files:
            path = current_path / name
            rel = path.relative_to(root).as_posix()
            info = path.lstat()
            mode = stat.S_IMODE(info.st_mode)
            if stat.S_ISLNK(info.st_mode):
                entries[rel] = ("symlink", mode, os.readlink(path))
            elif stat.S_ISREG(info.st_mode):
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                entries[rel] = ("file", mode, digest)
            else:
                entries[rel] = ("special", stat.S_IFMT(info.st_mode), mode)
    return entries


def _index_snapshot(
    root: Path, env: dict[str, str]
) -> dict[str, tuple[tuple[str, str, str], ...]]:
    result = _run_git(env, root, "ls-files", "--stage", "-z", check=False)
    mutable: dict[str, list[tuple[str, str, str]]] = {}
    for record in result.stdout.split(b"\0"):
        if not record or b"\t" not in record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        mode, oid, stage = metadata.decode("ascii").split()
        mutable.setdefault(os.fsdecode(raw_path), []).append((mode, oid, stage))
    return {path: tuple(sorted(stages)) for path, stages in mutable.items()}


def _mapping_diff(
    label: str, left: dict[str, tuple[Any, ...]], right: dict[str, tuple[Any, ...]]
) -> list[str]:
    differences: list[str] = []
    for path in sorted(left.keys() | right.keys()):
        if path not in left:
            differences.append(f"{label}:{path}: unexpected {right[path]!r}")
        elif path not in right:
            differences.append(f"{label}:{path}: missing; expected {left[path]!r}")
        elif left[path] != right[path]:
            differences.append(
                f"{label}:{path}: expected {left[path]!r}, got {right[path]!r}"
            )
    return differences


def _apply_states(handle: WorldHandle, states: tuple[StateSpec, ...]) -> None:
    if not states:
        return
    if handle.git_dir is None:
        raise AssertionError("world git_dir must be resolved before applying states")
    parent = handle.parent_path
    baseline_paths: list[str] = []
    for spec in states:
        path = parent / spec.path
        if spec.kind in {"staged-modify", "unstaged"}:
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("baseline\n")
                baseline_paths.append(spec.path)
        elif spec.kind == "symlink":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.symlink_to("baseline-target")
            baseline_paths.append(spec.path)
        elif spec.kind == "exec-bit":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(spec.content or b"#!/bin/sh\n")
            path.chmod(0o644)
            baseline_paths.append(spec.path)
        elif spec.kind.startswith("binary-"):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"\x00baseline\xff")
            baseline_paths.append(spec.path)
        elif spec.kind == "rename-edit":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("rename baseline\n")
            baseline_paths.append(spec.path)

    if baseline_paths:
        _run_git(handle.env, parent, "add", "--", *baseline_paths)
        _run_git(
            handle.env,
            parent,
            "commit",
            "-m",
            "seed fixture state",
            "--",
            *baseline_paths,
        )

    for spec in states:
        path = parent / spec.path
        path.parent.mkdir(parents=True, exist_ok=True)
        if spec.kind == "staged-modify":
            path.write_bytes(spec.content or b"staged\n")
            _run_git(handle.env, parent, "add", "--", spec.path)
        elif spec.kind == "staged-add":
            path.write_bytes(spec.content or b"staged add\n")
            _run_git(handle.env, parent, "add", "--", spec.path)
        elif spec.kind == "unstaged":
            path.write_bytes(spec.content or b"unstaged\n")
        elif spec.kind == "untracked":
            path.write_bytes(spec.content or b"untracked\n")
        elif spec.kind == "untracked-symlink":
            path.symlink_to(spec.target or "tracked.txt")
        elif spec.kind == "ignored":
            exclude_path = (
                _run_git(handle.env, parent, "rev-parse", "--git-path", "info/exclude")
                .stdout.decode()
                .strip()
            )
            exclude = Path(exclude_path)
            if not exclude.is_absolute():
                exclude = parent / exclude
            exclude.parent.mkdir(parents=True, exist_ok=True)
            with exclude.open("a") as stream:
                stream.write(f"/{spec.path}\n")
            path.write_bytes(spec.content or b"ignored\n")
        elif spec.kind == "symlink":
            path.unlink()
            path.symlink_to(spec.target or "tracked.txt")
        elif spec.kind == "exec-bit":
            path.chmod(path.stat().st_mode | stat.S_IXUSR)
        elif spec.kind == "binary-staged":
            path.write_bytes(b"\x00staged\xfe\xff")
            _run_git(handle.env, parent, "add", "--", spec.path)
        elif spec.kind == "binary-unstaged":
            path.write_bytes(b"\x00unstaged\xfe\xff")
        elif spec.kind == "rename-edit":
            target = spec.target or "renamed-new.txt"
            _run_git(handle.env, parent, "mv", "--", spec.path, target)
            (parent / target).write_text("renamed and edited\n")
        elif spec.kind == "intent-to-add":
            path.write_bytes(spec.content or b"intent\n")
            _run_git(handle.env, parent, "add", "-N", "--", spec.path)
        elif spec.kind == "unmerged":
            ours = (
                _run_git(
                    handle.env,
                    parent,
                    "hash-object",
                    "-w",
                    "--stdin",
                    input_bytes=b"ours\n",
                )
                .stdout.strip()
                .decode()
            )
            theirs = (
                _run_git(
                    handle.env,
                    parent,
                    "hash-object",
                    "-w",
                    "--stdin",
                    input_bytes=b"theirs\n",
                )
                .stdout.strip()
                .decode()
            )
            base = (
                _run_git(
                    handle.env,
                    parent,
                    "hash-object",
                    "-w",
                    "--stdin",
                    input_bytes=b"base\n",
                )
                .stdout.strip()
                .decode()
            )
            index_info = (
                f"100644 {base} 1\t{spec.path}\n"
                f"100644 {ours} 2\t{spec.path}\n"
                f"100644 {theirs} 3\t{spec.path}\n"
            ).encode()
            _run_git(
                handle.env,
                parent,
                "update-index",
                "--index-info",
                input_bytes=index_info,
            )
            if spec.target == "markers":
                path.write_text("<<<<<<< ours\nours\n=======\ntheirs\n>>>>>>> theirs\n")
            else:
                path.write_text("resolved-looking content\n")
        elif spec.kind.startswith("empty-dir"):
            path.mkdir(parents=True, exist_ok=True)
            if spec.kind == "empty-dir-ignored":
                exclude_path = (
                    _run_git(
                        handle.env, parent, "rev-parse", "--git-path", "info/exclude"
                    )
                    .stdout.decode()
                    .strip()
                )
                exclude = Path(exclude_path)
                if not exclude.is_absolute():
                    exclude = parent / exclude
                exclude.parent.mkdir(parents=True, exist_ok=True)
                with exclude.open("a") as stream:
                    stream.write(f"/{spec.path}/\n")
        elif spec.kind == "submodule":
            module = parent.parent / f"module-{path.name}"
            _init_plain(module, handle.env)
            _run_git(
                handle.env,
                parent,
                "-c",
                "protocol.file.allow=always",
                "submodule",
                "add",
                str(module),
                spec.path,
            )
            _dirty_submodule(handle, parent, path, spec.path, spec.target)
        elif spec.kind == "worktreeinclude":
            path.write_text(f"{spec.target}\n")
        else:
            raise ValueError(f"unknown state kind: {spec.kind}")


def _dirty_submodule(
    handle: WorldHandle,
    parent: Path,
    path: Path,
    relative: str,
    dirt: str | None,
):
    """Put the submodule at ``path`` into the state named by ``dirt``.

    ``_init_plain`` seeds every submodule with `tracked.txt`, so "modified"
    rewrites that file rather than introducing a second fixture filename.
    """
    if dirt is None:
        return
    # Commit the gitlink first, so the dirt below is the only state in play.
    # Clean submodules deliberately stay uncommitted: T-VER-30 and T-MAT-14 pin
    # the index-only gitlink shape, which a commit would erase.
    # Pathspec-scoped, so a `staged()` element earlier in the same states tuple
    # is not swept into this commit and silently lost.
    _run_git(
        handle.env,
        parent,
        "commit",
        "-m",
        f"add submodule {relative}",
        "--",
        ".gitmodules",
        f":(literal){relative}",
    )
    if dirt == "modified":
        (path / "tracked.txt").write_text("submodule modified\n")
    elif dirt == "untracked":
        (path / "loose.txt").write_text("untracked inside the submodule\n")
    elif dirt in ("advanced", "advanced-staged"):
        (path / "tracked.txt").write_text("submodule advanced\n")
        _run_git(handle.env, path, "commit", "-am", "advance the submodule")
        if dirt == "advanced-staged":
            _run_git(handle.env, parent, "add", "--", f":(literal){relative}")
    else:
        raise ValueError(f"unknown submodule dirt: {dirt}")


def _apply_origin(handle: WorldHandle, spec: OriginSpec) -> None:
    parent = handle.parent_path
    origin_path = parent.parent / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", "--initial-branch=main", str(origin_path)],
        env=handle.env,
        capture_output=True,
        check=True,
    )
    _run_git(handle.env, parent, "remote", "add", "origin", str(origin_path))
    branch = (
        _run_git(handle.env, parent, "rev-parse", "--abbrev-ref", "HEAD")
        .stdout.decode()
        .strip()
    )
    for number in range(spec.pushed):
        _commit_file(parent, handle.env, f"pushed-{number}.txt", f"pushed {number}\n")
    _run_git(handle.env, parent, "push", "-u", "origin", f"HEAD:{branch}")
    _run_git(handle.env, parent, "fetch", "origin")
    _run_git(handle.env, parent, "remote", "set-head", "origin", "-a")
    for number in range(spec.unpushed):
        _commit_file(
            parent, handle.env, f"unpushed-{number}.txt", f"unpushed {number}\n"
        )


def _git_targets() -> list[Path]:
    candidates = [Path("/usr/bin/git"), Path(shutil.which("git") or "/usr/bin/git")]
    targets: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.exists() and resolved not in targets:
            targets.append(resolved)
    return targets


def filter_divergence_probe() -> dict[str, tuple[str, str]]:
    """Exercise the non-idempotent clean-filter scenario on installed Git targets."""
    results: dict[str, tuple[str, str]] = {}
    for executable in _git_targets():
        root = Path(tempfile.mkdtemp(prefix="agent-fork-filter-canary-"))
        try:
            env = sealed_env({"HOME": str(root / "home")})
            repo = root / "repo"
            repo.mkdir()

            def command(
                *args: str,
                input_bytes: bytes | None = None,
                executable: Path = executable,
                repo: Path = repo,
                env: dict[str, str] = env,
            ):
                return subprocess.run(
                    [str(executable), "-C", str(repo), *args],
                    env=env,
                    input=input_bytes,
                    capture_output=True,
                    check=True,
                )

            command("init", "-b", "main")
            (repo / ".gitattributes").write_text("*.txt filter=grow\n")
            command("config", "filter.grow.clean", "sed 's/$/x/'")
            command("config", "filter.grow.smudge", "cat")
            command("add", ".gitattributes")
            command("commit", "-m", "configure filter")
            (repo / "sample.txt").write_text("a\n")
            command("add", "sample.txt")
            parent_status = command("status", "--porcelain=v1").stdout.decode().strip()
            patch_bytes = command("diff", "--binary", "--cached").stdout
            child = root / "child"
            command("worktree", "add", "-b", "child", str(child), "HEAD")
            subprocess.run(
                [str(executable), "-C", str(child), "apply", "--binary", "--index"],
                env=env,
                input=patch_bytes,
                capture_output=True,
                check=True,
            )
            child_status = subprocess.run(
                [str(executable), "-C", str(child), "status", "--porcelain=v1"],
                env=env,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            version = subprocess.run(
                [str(executable), "--version"],
                env=env,
                stdout=subprocess.PIPE,
                text=True,
                check=True,
            ).stdout.strip()
            results[version] = (parent_status, child_status)
        finally:
            shutil.rmtree(root, ignore_errors=True)
    return results


@dataclass
class GitShim:
    directory: Path
    log_path: Path

    @property
    def ready(self) -> Path:
        return self.directory / "ready"

    @property
    def release(self) -> Path:
        return self.directory / "release"

    def calls(self) -> list[list[str]]:
        if not self.log_path.exists():
            return []
        return [line.split() for line in self.log_path.read_text().splitlines() if line]

    def __enter__(self) -> GitShim:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        shutil.rmtree(self.directory, ignore_errors=True)


def shim_git(fail_call: str | None = None, park_at: str | None = None) -> GitShim:
    """PATH-first Git shim that logs and optionally fails/parks matching calls."""
    directory = Path(tempfile.mkdtemp(prefix="agent-fork-git-shim-")).resolve()
    log_path = directory / "calls.log"
    real_git = Path(shutil.which("git") or "/usr/bin/git").resolve()
    fail_pattern = fail_call or "__never_fail__"
    park_pattern = park_at or "__never_park__"
    ready = directory / "ready"
    release = directory / "release"
    script = directory / "git"
    script.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$*\" >> {shlex.quote(str(log_path))}\n"
        f'case "$*" in *{shlex.quote(fail_pattern)}*) exit 1 ;; esac\n'
        f'case "$*" in *{shlex.quote(park_pattern)}*) '
        f"touch {shlex.quote(str(ready))}; "
        f"while [ ! -e {shlex.quote(str(release))} ]; do sleep 0.01; done ;; esac\n"
        f'exec {shlex.quote(str(real_git))} "$@"\n'
    )
    script.chmod(0o755)
    return GitShim(directory=directory, log_path=log_path)


def sealed_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Whitelist-from-empty subprocess environment (spec §6.2)."""
    overrides = dict(extra or {})
    home = Path(overrides.pop("HOME", Path.cwd() / ".test-home")).resolve()
    tmpdir = Path(overrides.pop("TMPDIR", home / "tmp")).resolve()
    config_home = Path(overrides.pop("XDG_CONFIG_HOME", home / ".config")).resolve()
    state_home = Path(overrides.pop("XDG_STATE_HOME", home / ".local/state")).resolve()
    data_home = Path(overrides.pop("XDG_DATA_HOME", home / ".local/share")).resolve()
    config_dirs = Path(overrides.pop("XDG_CONFIG_DIRS", home / "etc/xdg")).resolve()
    git_config = Path(
        overrides.pop("GIT_CONFIG_GLOBAL", config_home / "git/config")
    ).resolve()

    for directory in (
        home,
        tmpdir,
        config_home,
        state_home,
        data_home,
        config_dirs,
        git_config.parent,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    if not git_config.exists():
        git_config.write_text(
            "[user]\n"
            "\tname = agent-fork tests\n"
            "\temail = agent-fork@example.invalid\n"
            "[init]\n"
            "\tdefaultBranch = main\n"
            "[core]\n"
            "\tquotePath = false\n"
            "\tautocrlf = false\n"
            "\tsymlinks = true\n"
        )

    env = {
        "PATH": overrides.pop("PATH", os.environ.get("PATH", os.defpath)),
        "HOME": str(home),
        "LC_ALL": overrides.pop("LC_ALL", "C"),
        "XDG_CONFIG_HOME": str(config_home),
        "XDG_STATE_HOME": str(state_home),
        "XDG_DATA_HOME": str(data_home),
        "XDG_CONFIG_DIRS": str(config_dirs),
        "GIT_CONFIG_GLOBAL": str(git_config),
        "GIT_CONFIG_NOSYSTEM": "1",
        "TERM": overrides.pop("TERM", "dumb"),
        "COLUMNS": overrides.pop("COLUMNS", "80"),
        "LINES": overrides.pop("LINES", "24"),
        "TMPDIR": str(tmpdir),
        "GIT_TERMINAL_PROMPT": "0",
    }
    env.update(overrides)
    return env


def run_cli(args: list[str], env: dict[str, str], cwd: Path):
    """Run the built agent-fork console script via subprocess (tier C black box)."""
    executable = Path(sys.executable).with_name("agent-fork")
    return subprocess.run(
        [str(executable), *args],
        env=env,
        cwd=cwd,
        capture_output=True,
        text=False,
    )


@dataclass(frozen=True)
class PtyResult:
    returncode: int
    stdout: bytes
    stderr: bytes
    tty: bytes


def pty_run(args: list[str], env: dict[str, str], tty_fd: int):
    """Per-fd pty harness: only tty_fd on pty, others piped; ONLCR cleared (§6.6)."""
    if tty_fd not in {0, 1, 2}:
        raise ValueError("tty_fd must be 0, 1, or 2")
    master, slave = os.openpty()
    attrs = termios.tcgetattr(slave)
    attrs[1] &= ~termios.ONLCR
    attrs[3] &= ~termios.ECHO
    termios.tcsetattr(slave, termios.TCSANOW, attrs)
    stdin: int | None = slave if tty_fd == 0 else subprocess.DEVNULL
    stdout: int = slave if tty_fd == 1 else subprocess.PIPE
    stderr: int = slave if tty_fd == 2 else subprocess.PIPE
    executable = Path(sys.executable).with_name("agent-fork")
    process = subprocess.Popen(
        [str(executable), *args],
        env=env,
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
        start_new_session=True,
    )
    os.close(slave)
    chunks: list[bytes] = []
    drain_errors: list[Exception] = []

    def drain_pty() -> None:
        try:
            while True:
                try:
                    chunk = os.read(master, 65536)
                except OSError as error:
                    if error.errno == errno.EIO:
                        break
                    raise
                if not chunk:
                    break
                chunks.append(chunk)
        except Exception as error:
            drain_errors.append(error)

    drain = threading.Thread(target=drain_pty, name="agent-fork-pty-drain", daemon=True)
    drain.start()
    try:
        try:
            captured_stdout, captured_stderr = process.communicate(
                timeout=PTY_PROCESS_TIMEOUT_SECONDS
            )
        except subprocess.TimeoutExpired:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait()
            drain.join(timeout=5)
            raise
        drain.join(timeout=5)
        if drain.is_alive():
            raise RuntimeError("PTY drain did not finish after child exit")
        if drain_errors:
            raise drain_errors[0]
    finally:
        os.close(master)
    return PtyResult(
        returncode=process.returncode,
        stdout=captured_stdout or b"",
        stderr=captured_stderr or b"",
        tty=b"".join(chunks),
    )


@dataclass(frozen=True)
class StallFilter:
    ready: Path
    release: Path
    script: Path


def stall_filter(world: WorldHandle):
    """Parent-side step-2 diff clean-filter stall with readiness file (spec §6.6)."""
    root = Path(world.env["TMPDIR"]) / "stall-filter"
    root.mkdir(parents=True, exist_ok=True)
    ready = root / "ready"
    release = root / "release"
    payload = root / "payload"
    script = root / "clean-filter"
    script.write_text(
        "#!/bin/sh\n"
        f"cat > {shlex.quote(str(payload))}\n"
        f"touch {shlex.quote(str(ready))}\n"
        f"while [ ! -e {shlex.quote(str(release))} ]; do "
        "kill -0 $PPID 2>/dev/null || exit 143; sleep 0.01; done\n"
        f"cat {shlex.quote(str(payload))}\n"
    )
    script.chmod(0o755)
    _run_git(world.env, world.parent_path, "config", "filter.stall.clean", str(script))
    _run_git(world.env, world.parent_path, "config", "filter.stall.smudge", "cat")
    world.go_files.append(release)
    return StallFilter(ready=ready, release=release, script=script)
