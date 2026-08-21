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
from agent_fork.repository import inspect_repository, live_worktree_pairs
from agent_fork.text import escape_terminal_text


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
    # Records commonly share a repository, and enumerating one costs a probe
    # per worktree it holds. Without this, N records across one repository of
    # M worktrees would run N*M subprocesses.
    enumerated: dict[Path, frozenset[tuple[str, str]]] = {}
    for entry in entries:
        worktree = Path(entry.worktree)
        if entry.repository is None:
            # Carries no repository, so it can never authorize anything and
            # can never gain one — nothing can show which repository it
            # belonged to. It is inert bookkeeping, and clearing it destroys
            # no work: any worktree still at that path stays on disk and is
            # removable by explicit path.
            missing.append(entry)
            continue
        if not worktree.exists():
            # Nothing is there. Removing the row destroys no work, and this
            # judgement needs no repository context, so it is safe to make
            # from anywhere.
            missing.append(entry)
            continue
        try:
            occupant = inspect_repository(worktree, env=env).common_dir
            if occupant not in enumerated:
                enumerated[occupant] = live_worktree_pairs(worktree, env=env)
            live = enumerated[occupant]
        except Exception:
            # The path exists but is not a usable repository. Report rather
            # than remove: the row may still describe real work.
            displaced.append(entry)
            kept.append(entry)
            continue
        # A record naming a repository is displaced when a different one now
        # holds its path, even if the branch name happens to match — which it
        # will whenever two repositories derived the same default fork name.
        moved_in = entry.repository is not None and str(occupant) != entry.repository
        if moved_in or not is_live(entry, live):
            # Something else occupies the path. It may be another repository's
            # live worktree, so this row is reported and left alone.
            displaced.append(entry)
        kept.append(entry)
    return PrunePlan(tuple(missing), tuple(displaced), tuple(kept))


def plan_prune(*, env: Mapping[str, str] | None = None) -> PrunePlan:
    """Classify registry rows without taking the lock or writing anything."""
    return _classify(_decode(registry_path(env)), env=env)


def apply_prune(
    confirmed: PrunePlan,
    *,
    env: Mapping[str, str] | None = None,
    timeout: float = DEFAULT_LOCK_TIMEOUT,
) -> PrunePlan:
    """Remove only the records the user was shown and agreed to.

    Classification is repeated inside the lock, because a record can be
    created or removed between planning and here — but the re-classification
    *narrows* the set rather than replacing it. A record that became prunable
    in the interval is not removed: the user never saw it, so consent does not
    cover it, and the next run will offer it. Removing it here would be the
    same defect this whole change exists to fix — acting on something other
    than what was confirmed.
    """
    agreed = {item.token() for item in confirmed.missing}
    path = registry_path(env)
    with registry_lock(path, timeout=timeout):
        current = _classify(_decode(path), env=env)
        removing = [item for item in current.missing if item.token() in agreed]
        if removing:
            removed = {item.token() for item in removing}
            _atomic_write(
                path, [item for item in _decode(path) if item.token() not in removed]
            )
        return PrunePlan(tuple(removing), current.displaced, current.kept)


def render(plan: PrunePlan, *, dry_run: bool) -> list[str]:
    lines: list[str] = []
    verb = "would remove" if dry_run else "removed"
    for entry in plan.missing:
        lines.append(
            f"{verb} {escape_terminal_text(entry.name)}\t"
            f"{escape_terminal_text(entry.branch)}\t"
            f"{escape_terminal_text(entry.worktree)}"
        )
    for entry in plan.displaced:
        lines.append(
            f"kept {escape_terminal_text(entry.name)}\t"
            f"{escape_terminal_text(entry.branch)}\t"
            f"{escape_terminal_text(entry.worktree)}\t"
            "(path occupied by something else; not this fork)"
        )
    if not plan.missing:
        lines.append("no registry records to remove")
    return lines
