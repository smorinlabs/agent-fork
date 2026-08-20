"""Atomic JSON persistence with uniform crash durability."""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile


def atomic_write_json(
    path: Path,
    document: object,
    *,
    fsync: bool = True,
    prefix: str | None = None,
) -> None:
    """Write ``document`` to ``path`` via a same-directory rename.

    Every store written here is owner-only. ``NamedTemporaryFile`` *requests*
    mode 0600, but the process umask still masks it — under ``umask 0777`` the
    file lands at 0000, which the owner cannot even read back. The explicit
    ``chmod`` is therefore load-bearing, not redundant; it runs on the
    temporary file so the store is never visible at the wrong mode.

    ``fsync`` flushes the file and its parent directory before returning, so a
    crash cannot lose the rename. Pass ``fsync=False`` for a disposable cache
    that is revalidated on read: durability buys nothing there, and the cost is
    paid once per entry inside a deadline-bounded loop.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_prefix = prefix if prefix is not None else f".{path.stem}-"
    temporary_name: str | None = None
    try:
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=temporary_prefix,
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            os.chmod(temporary_name, 0o600)
            json.dump(document, temporary, sort_keys=True, separators=(",", ":"))
            temporary.write("\n")
            if fsync:
                temporary.flush()
                os.fsync(temporary.fileno())
        os.replace(temporary_name, path)
        temporary_name = None
        if fsync:
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)
