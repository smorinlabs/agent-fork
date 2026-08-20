"""Consistent XDG base-directory resolution."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path


def xdg_path(
    env: Mapping[str, str],
    var: str,
    home_default: str,
    *segments: str,
) -> Path:
    """Resolve one XDG base directory and optional trailing path segments.

    An empty value counts as unset, per the XDG Base Directory specification —
    for the XDG variable and for ``HOME`` alike. Either one accepted as a base
    would resolve the store relative to the current working directory, putting
    state wherever the process happened to be running. ``env.get(name, "~")``
    is not enough on its own: it returns the empty string when the variable is
    set but empty, which is exactly the case that produces a relative path.
    """
    base = env.get(var)
    if not base:
        base = str(Path(env.get("HOME") or "~").expanduser() / home_default)
    return Path(base).expanduser().joinpath(*segments)
