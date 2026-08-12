"""Bounded deferred output for explicit bulk Claude lineage analysis."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from typing import TextIO

MAX_CANDIDATES = 5
MAX_NOTICES = 10
MAX_SCALAR = 512
MAX_SPOOL_BYTES = 64 * 1024 * 1024


def _text(value: object) -> str:
    return str(value)[:MAX_SCALAR]


def compact_result(document: Mapping[str, object]) -> dict[str, object]:
    relationship = document.get("relationship")
    relation = relationship if isinstance(relationship, dict) else {}
    candidates = document.get("candidates")
    candidate_rows = candidates if isinstance(candidates, list) else []
    compact_candidates = []
    for candidate in candidate_rows[:MAX_CANDIDATES]:
        if not isinstance(candidate, dict):
            continue
        compact_candidates.append(
            {
                key: candidate.get(key)
                for key in (
                    "session_id",
                    "shared",
                    "substantive",
                    "boundary",
                    "older",
                    "clocks",
                )
            }
        )
    notices = document.get("notices")
    notice_rows = notices if isinstance(notices, list) else []
    result: dict[str, object] = {
        "agent": "claude",
        "session_id": _text(document.get("session_id", "")),
        "relationship": {
            key: relation.get(key)
            for key in (
                "status",
                "likely_parent_session_id",
                "fork_boundary_message_id",
                "shared_message_count",
                "shared_substantive_message_count",
            )
        },
        "recorded": bool(document.get("recorded")),
        "candidate_count": len(candidate_rows),
        "candidates": compact_candidates,
        "candidates_truncated": len(candidate_rows) > len(compact_candidates),
        "notices": [_text(value) for value in notice_rows[:MAX_NOTICES]],
        "notices_truncated": len(notice_rows) > MAX_NOTICES,
    }
    if "error" in document:
        result["error"] = _text(document["error"])
    return result


class BulkSpool:
    def __init__(self):
        self.stream = tempfile.TemporaryFile("w+", encoding="utf-8")
        os.chmod(self.stream.fileno(), 0o600)
        self.bytes_written = 0
        self.count = 0

    def append(self, document: Mapping[str, object]) -> None:
        encoded = json.dumps(
            compact_result(document),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        added = len(encoded.encode()) + 1
        if self.bytes_written + added > MAX_SPOOL_BYTES:
            raise ValueError("Claude parent bulk output exceeds limit")
        self.stream.write(encoded + "\n")
        self.bytes_written += added
        self.count += 1

    def _results(self, target: TextIO) -> None:
        self.stream.flush()
        self.stream.seek(0)
        first = True
        for line in self.stream:
            if not first:
                target.write(",")
            target.write(line.rstrip("\n"))
            first = False

    def render_json(
        self,
        target: TextIO,
        summary: Mapping[str, int],
        *,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        if error_code is None:
            target.write('{"results":[')
            self._results(target)
            target.write(
                '],"summary":'
                + json.dumps(dict(summary), sort_keys=True, separators=(",", ":"))
                + "}\n"
            )
            return
        target.write(
            '{"error":{"code":'
            + json.dumps(error_code)
            + ',"details":{"analysis":{"results":['
        )
        self._results(target)
        target.write(
            '],"summary":'
            + json.dumps(dict(summary), sort_keys=True, separators=(",", ":"))
            + '}},"message":'
            + json.dumps(error_message or "bulk Claude parent analysis failed")
            + "}}\n"
        )

    def render_human(self, target: TextIO, summary: Mapping[str, int]) -> None:
        self.stream.flush()
        self.stream.seek(0)
        for line in self.stream:
            document = json.loads(line)
            relation = document["relationship"]
            target.write(
                f"{document['session_id']}  {relation.get('status')}  "
                f"{relation.get('likely_parent_session_id') or '-'}  "
                f"recorded={str(document['recorded']).lower()}\n"
            )
        target.write(
            "summary: "
            + " ".join(f"{key}={value}" for key, value in summary.items())
            + "\n"
        )

    def close(self) -> None:
        self.stream.close()

    def __enter__(self) -> BulkSpool:
        return self

    def __exit__(self, *_args) -> None:
        self.close()
