"""Deterministic worktree destination derivation."""

from __future__ import annotations

from pathlib import Path

from platformdirs import user_data_path


def _branch_escaped(branch: str) -> str:
    return branch.replace("/", "-").replace("\\", "-")


def derive_worktree_path(
    repo_root: Path,
    branch: str,
    name: str,
    location: str,
    *,
    xdg_data_home: Path | None = None,
    parent_path: Path | None = None,
    parent_is_linked: bool = False,
    bare_at_root: bool = False,
    location_explicit: bool = False,
    session_id: str = "",
) -> Path:
    """Apply D5 placement, including linked-parent and bare-root rules."""
    root = repo_root.resolve()
    escaped = _branch_escaped(branch)

    if bare_at_root and not location_explicit:
        return (root / name).resolve()

    if location == "central":
        data_root = xdg_data_home.resolve() if xdg_data_home else user_data_path()
        return (data_root / "agent-fork/worktrees" / root.name / name).resolve()

    if location == "subdirectory":
        return (root / ".worktrees" / name).resolve()

    if location == "sibling":
        destination_parent = root.parent
        if parent_is_linked and not location_explicit and parent_path is not None:
            destination_parent = parent_path.resolve().parent
        return (destination_parent / f"{root.name}-{escaped}").resolve()

    values = {
        "repo-name": root.name,
        "repo-root": str(root.parent),
        "branch": branch,
        "branch-escaped": escaped,
        "session-id": session_id,
    }
    try:
        rendered = location.format_map(values)
    except (KeyError, ValueError) as error:
        raise ValueError(f"invalid worktree location template: {error}") from None
    return Path(rendered).expanduser().resolve()
