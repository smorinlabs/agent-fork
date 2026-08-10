"""Deterministic worktree destination derivation."""

from __future__ import annotations

from pathlib import Path

from platformdirs import user_data_path

from agent_fork.errors import PreconditionError


def _branch_escaped(branch: str) -> str:
    return branch.replace("/", "-").replace("\\", "-")


def validate_worktree_name(value: str) -> str:
    """Validate an explicit worktree leaf without rewriting it."""
    if (
        not value.strip()
        or value in {".", ".."}
        or "\0" in value
        or "/" in value
        or "\\" in value
        or Path(value).is_absolute()
    ):
        raise PreconditionError(
            "invalid_worktree_name",
            f"worktree name must be one non-empty path component: {value!r}",
        )
    return value


def compose_worktree_destination(
    derived: Path,
    *,
    invocation_cwd: Path,
    base_dir: Path | None = None,
    worktree_name: str | None = None,
) -> Path:
    """Apply independent parent and leaf overrides to a derived destination."""
    if base_dir is None:
        base = derived.parent
    else:
        base = base_dir.expanduser()
        if not base.is_absolute():
            base = invocation_cwd / base
        base = base.resolve()
        if not base.is_dir():
            raise PreconditionError(
                "invalid_worktree_base",
                f"worktree base must be an existing directory: {base}",
            )
    leaf = (
        validate_worktree_name(worktree_name)
        if worktree_name is not None
        else derived.name
    )
    # Deliberately do not resolve the leaf: an existing symlink must remain visible
    # to the repository destination guard rather than being followed.
    return base / leaf


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
