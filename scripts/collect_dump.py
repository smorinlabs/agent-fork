"""pytest plugin: dump collected items as JSON lines for check_matrix.collect_items.

Loaded via `-p scripts.collect_dump`. Writes one JSON object per collected
item ({"nodeid", "path", "matrix", "skip_reason"}) to the file named by the
COLLECT_DUMP_OUT env var, once collection finishes.
"""

from __future__ import annotations

import json
import os


def pytest_collection_finish(session):
    out_path = os.environ.get("COLLECT_DUMP_OUT")
    if not out_path:
        return

    lines = []
    for item in session.items:
        matrix_marker = item.get_closest_marker("matrix")
        matrix_id = (
            matrix_marker.args[0] if matrix_marker and matrix_marker.args else None
        )

        skip_marker = item.get_closest_marker("skip")
        skip_reason = None
        if skip_marker is not None:
            if skip_marker.args:
                skip_reason = skip_marker.args[0]
            else:
                skip_reason = skip_marker.kwargs.get("reason")

        lines.append(
            json.dumps(
                {
                    "nodeid": item.nodeid,
                    "path": str(item.path),
                    "matrix": matrix_id,
                    "skip_reason": skip_reason,
                }
            )
        )

    with open(out_path, "w") as f:
        f.write("\n".join(lines))
        if lines:
            f.write("\n")
