"""Git-safe fork identity derivation and collision handling."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from agent_fork.errors import ConflictError

_ILLEGAL = re.compile(r"[~^:?*\[\\/@{}]+")
_DASHES = re.compile(r"-+")


def sanitize_name(value: str) -> str:
    """Turn a human label into the locked lowercase Git-safe slug."""
    slug = value.strip().lower().replace(" ", "-")
    slug = slug.replace("..", "")
    slug = _ILLEGAL.sub("", slug)
    slug = _DASHES.sub("-", slug)
    slug = slug.lstrip(".").rstrip(".")
    while slug.endswith(".lock"):
        slug = slug[: -len(".lock")].rstrip(".")
    return slug or "fork"


def derive_auto_name(
    branch: str | None,
    *,
    detached_sha: str | None = None,
    now: datetime | None = None,
) -> str:
    """Derive a branch- or detached-based name using the date at call time."""
    instant = now or datetime.now()
    date = instant.strftime("%m%d")
    if branch is None or branch == "HEAD":
        if not detached_sha:
            raise ValueError("detached auto-name requires a commit SHA")
        base = f"detached-{detached_sha[:7]}"
    else:
        base = sanitize_name(branch)
    return f"{base}-{date}"


def unique_auto_name(base: str, collides: Callable[[str], bool]) -> str:
    """Return the first free auto-name, attempting at most 1000 candidates."""
    for attempt in range(1, 1001):
        candidate = base if attempt == 1 else f"{base}-{attempt}"
        if not collides(candidate):
            return candidate
    raise ConflictError(f"no available fork name after 1000 attempts from {base!r}")


def resolve_name(
    explicit: str | None,
    *,
    auto_base: str,
    collides: Callable[[str], bool],
) -> str:
    """Refuse explicit collisions; suffix only automatically derived names."""
    if explicit is None:
        return unique_auto_name(auto_base, collides)
    name = sanitize_name(explicit)
    if collides(name):
        raise ConflictError(f"fork name {name!r} already exists")
    return name


@dataclass(frozen=True)
class NamingPlan:
    name: str
    branch: str
    worktree_suffix: str
    display_name: str


def naming_plan(name: str, *, branch_prefix: str) -> NamingPlan:
    """Feed one identity into its branch, path suffix, and display name."""
    safe_name = sanitize_name(name)
    return NamingPlan(
        name=safe_name,
        branch=f"{branch_prefix}{safe_name}",
        worktree_suffix=safe_name,
        display_name=safe_name,
    )
