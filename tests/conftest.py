"""Shared fixture layer for the agent-fork test suite.

Signatures only (skeleton phase). Bodies land via TDD in the VM, G-FIX first.
Spec: docs/superpowers/specs/2026-08-08-test-architecture-design.md §6.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

TEST_HARNESS_GIT_MIN = (2, 43)  # spec §2/§7.5 — F/C/R tiers hard-error below this


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
    raise NotImplementedError("skeleton phase: implemented in VM TDD")


def unstaged(path: str | None = None) -> StateSpec:
    """Unstaged worktree modification of a tracked file (spec §6.3)."""
    raise NotImplementedError("skeleton phase: implemented in VM TDD")


def untracked(
    path: str | None = None, symlink: str | None = None, target: str | None = None
) -> StateSpec:
    """Untracked file, including nested-directory paths (spec §6.3)."""
    raise NotImplementedError("skeleton phase: implemented in VM TDD")


def ignored(path: str | None = None) -> StateSpec:
    """File matched by `.gitignore` (spec §6.3)."""
    raise NotImplementedError("skeleton phase: implemented in VM TDD")


def symlink_state(
    path: str | None = None, target: str | None = None, absolute: bool = False
) -> StateSpec:
    """Tracked symlink, relative or absolute target (spec §6.3)."""
    raise NotImplementedError("skeleton phase: implemented in VM TDD")


def exec_bit(path: str | None = None) -> StateSpec:
    """Exec-bit-only change on an otherwise-unmodified tracked file (spec §6.3)."""
    raise NotImplementedError("skeleton phase: implemented in VM TDD")


def binary_state(staged: bool) -> StateSpec:
    """Binary file, staged or unstaged variant (spec §6.3)."""
    raise NotImplementedError("skeleton phase: implemented in VM TDD")


def rename_edit(path: str | None = None) -> StateSpec:
    """Renamed-and-edited tracked file (spec §6.3)."""
    raise NotImplementedError("skeleton phase: implemented in VM TDD")


def intent_to_add(path: str | None = None) -> StateSpec:
    """`git add -N` intent-to-add entry (spec §6.3)."""
    raise NotImplementedError("skeleton phase: implemented in VM TDD")


def unmerged(markerless: bool) -> StateSpec:
    """Unmerged index entry, optionally markerless in the worktree (spec §6.3)."""
    raise NotImplementedError("skeleton phase: implemented in VM TDD")


def empty_dir(ignored: bool) -> StateSpec:
    """Empty directory, plain or `.gitignore`d (spec §6.3)."""
    raise NotImplementedError("skeleton phase: implemented in VM TDD")


def submodule(path: str | None = None) -> StateSpec:
    """Submodule gitlink, seeded with `-c protocol.file.allow=always` (spec §6.3)."""
    raise NotImplementedError("skeleton phase: implemented in VM TDD")


def worktreeinclude(pattern: str | None = None) -> StateSpec:
    """`.worktreeinclude` entry (spec §6.3)."""
    raise NotImplementedError("skeleton phase: implemented in VM TDD")


def origin(pushed: int = 0, unpushed: int = 0) -> OriginSpec:
    """Local bare-repo remote spec: wired, fetched, set-head applied (spec §6.4)."""
    return OriginSpec(pushed=pushed, unpushed=unpushed)


@dataclass
class WorldHandle:
    """Built world: realpathed paths, sealed env, test-side oracles (spec §6.5)."""

    parent_path: Path
    child_path: Path | None
    env: dict[str, str]

    def manifest_diff(self, a: Path, b: Path) -> list[str]:
        """lstat-only manifest+hash comparison; empty list means identical."""
        raise NotImplementedError("skeleton phase: implemented in VM TDD")

    def index_diff(self, a: Path, b: Path) -> list[str]:
        """git ls-files --stage comparison (blob IDs + modes), ITA-aware."""
        raise NotImplementedError("skeleton phase: implemented in VM TDD")

    def parent_snapshot(self) -> object:
        """Full manifest+index snapshot for the parent-inviolate assertion."""
        raise NotImplementedError("skeleton phase: implemented in VM TDD")


@pytest.fixture
def repo_scenario():
    """Build a WorldHandle from a RepoSpec. Sealed whitelist env (spec §6.2)."""

    def _build(topology: str = "plain@branch", states=(), remote=None) -> WorldHandle:
        raise NotImplementedError("skeleton phase: implemented in VM TDD")

    return _build


def sealed_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Whitelist-from-empty subprocess environment (spec §6.2)."""
    raise NotImplementedError("skeleton phase: implemented in VM TDD")


def run_cli(args: list[str], env: dict[str, str], cwd: Path):
    """Run the built agent-fork console script via subprocess (tier C black box)."""
    raise NotImplementedError("skeleton phase: implemented in VM TDD")


def pty_run(args: list[str], env: dict[str, str], tty_fd: int):
    """Per-fd pty harness: only tty_fd on pty, others piped; ONLCR cleared (§6.6)."""
    raise NotImplementedError("skeleton phase: implemented in VM TDD")


def shim_git(fail_call: str | None = None, park_at: str | None = None):
    """PATH git shim: fault injection and the race barrier (spec §6.6)."""
    raise NotImplementedError("skeleton phase: implemented in VM TDD")


def stall_filter(world: WorldHandle):
    """Parent-side step-2 diff clean-filter stall with readiness file (spec §6.6)."""
    raise NotImplementedError("skeleton phase: implemented in VM TDD")
