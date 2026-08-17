"""Registry-only repair: clear rows whose worktree is gone.

The actionability predicate makes a row that no longer matches disk permanently
unusable for cleanup, so there has to be a way to clear one. Pruning touches
the registry and nothing else: it never runs a destructive Git command and
never removes a worktree.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from agent_fork.models import RegistryEntry
from agent_fork.registry import (
    DEFAULT_LOCK_TIMEOUT,
    _atomic_write,
    _decode,
    is_live,
    registry_lock,
    registry_path,
)
from agent_fork.repository import live_worktree_pairs


@dataclass(frozen=True)
class PrunePlan:
    """What pruning would change, split by the evidence for each row."""

    missing: tuple[RegistryEntry, ...]
    displaced: tuple[RegistryEntry, ...]
    kept: tuple[RegistryEntry, ...]

    def document(self) -> dict[str, object]:
        return {
            "removed": [entry.to_dict() for entry in self.missing],
            "displaced": [entry.to_dict() for entry in self.displaced],
            "kept": len(self.kept),
        }


def _classify(
    entries: list[RegistryEntry], *, env: Mapping[str, str] | None
) -> PrunePlan:
    missing: list[RegistryEntry] = []
    displaced: list[RegistryEntry] = []
    kept: list[RegistryEntry] = []
    for entry in entries:
        worktree = Path(entry.worktree)
        if not worktree.exists():
            # Nothing is there. Removing the row destroys no work, and this
            # judgement needs no repository context, so it is safe to make
            # from anywhere.
            missing.append(entry)
            continue
        try:
            live = live_worktree_pairs(worktree, env=env)
        except Exception:
            # The path exists but is not a usable repository. Report rather
            # than remove: the row may still describe real work.
            displaced.append(entry)
            kept.append(entry)
            continue
        if not is_live(entry, live):
            # Something else occupies the path. It may be another repository's
            # live worktree, so this row is reported and left alone.
            displaced.append(entry)
        kept.append(entry)
    return PrunePlan(tuple(missing), tuple(displaced), tuple(kept))


def plan_prune(*, env: Mapping[str, str] | None = None) -> PrunePlan:
    """Classify registry rows without taking the lock or writing anything."""
    return _classify(_decode(registry_path(env)), env=env)


def apply_prune(
    *,
    env: Mapping[str, str] | None = None,
    timeout: float = DEFAULT_LOCK_TIMEOUT,
) -> PrunePlan:
    """Re-classify under the lock, then drop only the rows with nothing there.

    Classification is repeated inside the lock so a row created or removed
    since planning cannot be acted on from a stale view.
    """
    path = registry_path(env)
    with registry_lock(path, timeout=timeout):
        plan = _classify(_decode(path), env=env)
        if plan.missing:
            _atomic_write(path, list(plan.kept))
        return plan


def render(plan: PrunePlan, *, dry_run: bool) -> list[str]:
    lines: list[str] = []
    verb = "would remove" if dry_run else "removed"
    for entry in plan.missing:
        lines.append(f"{verb} {entry.name}\t{entry.branch}\t{entry.worktree}")
    for entry in plan.displaced:
        lines.append(
            f"kept {entry.name}\t{entry.branch}\t{entry.worktree}\t"
            "(path occupied by something else; not this fork)"
        )
    if not plan.missing:
        lines.append("no registry records to remove")
    return lines
