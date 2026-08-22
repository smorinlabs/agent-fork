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
    with_submodules: bool | None = None
    branch_prefix: str | None = None
    worktree_location: str | None = None
    agent_mode: str | None = None
    verify: bool | None = None
    copy: bool | None = None
    output: str | None = None
    config_path: Path | None = None
    claude_extra_args: tuple[str, ...] | None = None
    codex_extra_args: tuple[str, ...] | None = None
    codex_session_name_resolution: bool | None = None
    setup_hook_policy: str | None = None
    setup_hook_timeout: int | None = None


@dataclass(frozen=True)
class ResolvedConfig:
    """Concrete configuration after defaults, precedence, and implications."""

    with_state: bool
    with_ignored: bool
    with_submodules: bool
    branch_prefix: str
    worktree_location: str
    worktree_location_explicit: bool
    agent_mode: str
    verify: bool
    copy: bool
    output: str
    config_path: Path | None
    claude_extra_args: tuple[str, ...]
    codex_extra_args: tuple[str, ...]
    codex_session_name_resolution: bool
    setup_hook_policy: str
    setup_hook_timeout: int

    @property
    def mode(self) -> str:
        if not self.with_state:
            return "no-state"
        return "exact+ignored" if self.with_ignored else "exact"


@dataclass(frozen=True)
class RegistryEntry:
    """One worktree created by agent-fork.

    `repository` is the resolved Git common directory the fork belongs to. It
    is appended last so existing positional construction keeps its meaning, and
    it is None for rows migrated from a v1 registry, where the repository was
    never recorded and cannot be inferred after the fact.
    """

    name: str
    branch: str
    worktree: str
    agent: str | None
    created_at: str
    mode: str = "agent"
    repository: str | None = None

    @classmethod
    def create(
        cls,
        *,
        name: str,
        branch: str,
        worktree: Path,
        agent: str | None,
        mode: str = "agent",
        repository: Path | str | None = None,
    ) -> RegistryEntry:
        created = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        return cls(
            name,
            branch,
            str(worktree.resolve()),
            agent,
            created,
            mode,
            None if repository is None else str(repository),
        )

    def to_dict(self, *, include_exists: bool = False) -> dict[str, object]:
        """Serialize for public command output; `repository` is internal."""
        value: dict[str, object] = {
            "name": self.name,
            "branch": self.branch,
            "worktree": self.worktree,
            "agent": self.agent,
            "created_at": self.created_at,
            "mode": self.mode,
        }
        if include_exists:
            value["worktree_exists"] = Path(self.worktree).exists()
        return value

    def to_registry_dict(self) -> dict[str, object]:
        """Serialize for the on-disk registry, which records `repository`."""
        return {**self.to_dict(), "repository": self.repository}

    def token(self) -> tuple[object, ...]:
        """Identity for compare-and-swap removal.

        Every persisted field, `repository` included. An earlier revision
        excluded it as "derived", which was true only while a backfill could
        rewrite it mid-operation; with backfill gone it is written once and
        never changes, so excluding it would let a record whose identity
        changed during consent still satisfy the swap.

        `agent` is carried as-is rather than coerced to a string, so a
        recorded absence stays distinct from an empty name.
        """
        return (
            self.name,
            self.branch,
            self.worktree,
            self.agent,
            self.created_at,
            self.mode,
            self.repository,
        )
