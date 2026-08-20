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
    """Resolve one XDG base directory and optional trailing path segments."""
    base = env.get(var)
    if base is None:
        base = str(Path(env.get("HOME", "~")).expanduser() / home_default)
    return Path(base).expanduser().joinpath(*segments)
