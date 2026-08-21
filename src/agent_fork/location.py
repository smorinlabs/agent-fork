"""Deterministic worktree destination derivation."""

from __future__ import annotations

import os
import string
from pathlib import Path

from platformdirs import user_data_path

from agent_fork.config import ConfigError
from agent_fork.errors import PreconditionError

_ALLOWED_TEMPLATE_FIELDS = {"repo-name", "repo-root", "branch", "branch-escaped"}


def _branch_escaped(branch: str) -> str:
    return branch.replace("/", "-").replace("\\", "-")


def worktree_location_reason(template: str) -> str | None:
    """None if `template` is a safe `worktree_location` template; else why not.

    A template is safe when its `str.format_map` render is guaranteed to be
    a well-formed absolute path with no filesystem-lookup risk, entirely from
    the template string itself — no repository context is needed to decide
    this. That guarantee rests on five properties, each checked below:
    bare field references only (no conversion, format spec, or subscript, all
    of which render successfully today but were found to misbehave); an
    exact match against the four supported placeholder names, with
    `{session-id}` recognized but permanently rejected (no session ID exists
    when the destination is derived, and A8 — the only tracked work that
    would have changed that — closed will-not-fix); no C0 or C1 control
    characters, including an embedded NUL (reachable from a TOML string, not
    just a shell argument); no `..` path component (checked component-wise,
    not as a substring — a name like `release..candidate` is not a traversal
    and stays legal); and a guaranteed-absolute render, which is decidable
    statically because only `{repo-root}` ever substitutes an absolute value
    — `{repo-name}`, `{branch}`, and `{branch-escaped}` never do, so a
    template starting with any of those (or with no field at all) can only
    render as CWD-relative. A leading `~`/`~/` is accepted as home-relative;
    a longer `~user` form is rejected, since expanding it can raise
    ``RuntimeError`` for an unresolvable user. `derive_worktree_path()`
    additionally checks that a `~`/`~/`-leading template actually expands to
    an absolute path — a relative `HOME` would otherwise silently anchor the
    result to the process CWD instead of raising.
    """
    if any(
        ord(character) < 0x20 or 0x7F <= ord(character) <= 0x9F
        for character in template
    ):
        return "must not contain control characters"
    if ".." in template.split("/"):
        return "must not contain a '..' path component"
    if template.startswith("~") and not (template == "~" or template.startswith("~/")):
        return "does not support ~user expansion"
    try:
        parsed = list(string.Formatter().parse(template))
    except ValueError as error:
        return str(error)
    starts_absolute = template.startswith("/") or template.startswith("~")
    first_field_is_repo_root = False
    for index, (literal_text, field_name, format_spec, conversion) in enumerate(parsed):
        if index == 0 and literal_text == "" and field_name == "repo-root":
            first_field_is_repo_root = True
        if field_name is None:
            continue
        if field_name == "session-id":
            return (
                "{session-id} is not supported: no session ID exists when the "
                "destination is derived, and none is scheduled to be added"
            )
        if field_name not in _ALLOWED_TEMPLATE_FIELDS:
            return f"unknown placeholder {{{field_name}}}"
        if conversion is not None:
            return f"{{{field_name}!{conversion}}} conversions are not supported"
        if format_spec:
            return f"{{{field_name}:{format_spec}}} format specifiers are not supported"
    if not (starts_absolute or first_field_is_repo_root):
        return "must render to an absolute path (start with '/', '~', or {repo-root})"
    return None


def validate_worktree_name(value: str) -> str:
    """Validate an explicit worktree leaf without rewriting it.

    Control characters are refused alongside the separators. A newline is the
    one that matters: it is legal in a POSIX filename but ambiguous in Git's
    newline-delimited porcelain, so a worktree carrying one can be misread.
    Refusing it here reports the problem against the argument the caller
    actually passed, rather than surfacing later as a verification failure.
    This is a guard, not the fix — ``worktree_list`` handles paths this
    function never sees, such as those from ``--worktree-dir``.
    """
    if (
        not value.strip()
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
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

    reason = worktree_location_reason(location)
    if reason is not None:
        raise ConfigError(f"invalid worktree location template {location!r}: {reason}")
    values = {
        "repo-name": root.name,
        "repo-root": str(root.parent),
        "branch": branch,
        "branch-escaped": escaped,
    }
    try:
        rendered = location.format_map(values)
        if location.startswith("~") and "HOME" in os.environ and not os.environ["HOME"]:
            # `Path.expanduser()` treats a *present but empty* HOME as a
            # literal empty prefix, not as unset — "" + "/x" is "/x", which
            # passes an absoluteness check while silently anchoring to the
            # filesystem root instead of raising. A genuinely *absent* HOME
            # is fine: expanduser() then falls back to the pwd database.
            # This matches xdg.py's documented convention (an empty value
            # counts as unset for HOME, same as for an XDG variable).
            raise ValueError("expands relative to an empty HOME")
        expanded = Path(rendered).expanduser()
        if not expanded.is_absolute():
            # A `~`/`~/`-leading template that a misconfigured (relative)
            # HOME failed to actually expand would otherwise silently
            # resolve relative to the process CWD instead of the intended
            # home directory.
            raise ValueError(f"expands to a non-absolute path: {expanded}")
        return expanded.resolve()
    except (KeyError, ValueError, RuntimeError, OSError) as error:
        # Belt-and-braces: worktree_location_reason() rules out every render
        # failure this function has ever been found to have, but a render
        # failure must still exit 2 (config_error), not 1, if one slips
        # through some case this grammar didn't anticipate.
        raise ConfigError(
            f"invalid worktree location template {location!r}: {error}"
        ) from None
