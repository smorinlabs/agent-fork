"""Shared immutable value objects for agent-fork."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class ConfigValues:
    """Values contributed by one configuration source before precedence."""

    with_state: bool | None = None
    with_ignored: bool | None = None
    branch_prefix: str | None = None
    worktree_location: str | None = None
    verify: bool | None = None
    copy: bool | None = None
    output: str | None = None
    config_path: Path | None = None


@dataclass(frozen=True)
class ResolvedConfig:
    """Concrete configuration after defaults, precedence, and implications."""

    with_state: bool
    with_ignored: bool
    branch_prefix: str
    worktree_location: str
    verify: bool
    copy: bool
    output: str
    config_path: Path | None

    @property
    def mode(self) -> str:
        if not self.with_state:
            return "no-state"
        return "exact+ignored" if self.with_ignored else "exact"


@dataclass(frozen=True)
class RegistryEntry:
    """Stable v1 record for one worktree created by agent-fork."""

    name: str
    branch: str
    worktree: str
    agent: str
    created_at: str

    @classmethod
    def create(
        cls, *, name: str, branch: str, worktree: Path, agent: str
    ) -> RegistryEntry:
        created = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        return cls(name, branch, str(worktree.resolve()), agent, created)

    def to_dict(self, *, include_exists: bool = False) -> dict[str, object]:
        value: dict[str, object] = {
            "name": self.name,
            "branch": self.branch,
            "worktree": self.worktree,
            "agent": self.agent,
            "created_at": self.created_at,
        }
        if include_exists:
            value["worktree_exists"] = Path(self.worktree).exists()
        return value
