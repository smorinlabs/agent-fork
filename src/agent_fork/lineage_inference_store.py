"""Versioned, atomic storage for heuristic Claude parent inferences."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from agent_fork.registry import registry_lock
from agent_fork.storage import atomic_write_json
from agent_fork.xdg import xdg_path

VERSION = 2
MAX_STORE_BYTES = 8 * 1024 * 1024
MAX_SOURCE_FINGERPRINTS = 1_024

FreshnessStatus = Literal[
    "current_at_last_analysis",
    "stale_sources",
    "stale_candidate_universe",
    "stale_algorithm",
    "freshness_unknown",
]
EvidenceStatus = Literal["current", "last_known_good", "unknown", "superseded"]
ChangedSource = Literal["target", "parent", "other"]


@dataclass(frozen=True)
class InferenceRecord:
    child_session_id: str
    parent_session_id: str
    status: str
    fork_boundary_message_id: str
    shared_message_count: int
    shared_substantive_message_count: int
    algorithm_version: int
    analyzed_at: str
    source_fingerprints: tuple[str, ...]
    analysis_index_generation: str = ""
    candidate_universe_digest: str = ""
    agent: str = "claude"

    def document(self) -> dict[str, object]:
        value = asdict(self)
        value["source_fingerprints"] = list(self.source_fingerprints)
        return value


@dataclass(frozen=True)
class InferenceAssessment:
    status: FreshnessStatus
    evidence: EvidenceStatus
    changed_sources: tuple[ChangedSource, ...] = ()

    @property
    def satisfies_strict_parent(self) -> bool:
        return self.evidence == "current"

    @property
    def displayable(self) -> bool:
        return self.evidence != "superseded"


_EVIDENCE_BY_STATUS: dict[FreshnessStatus, EvidenceStatus] = {
    "current_at_last_analysis": "current",
    "stale_sources": "last_known_good",
    "stale_candidate_universe": "last_known_good",
    "freshness_unknown": "unknown",
    "stale_algorithm": "superseded",
}


def inference_path(env: Mapping[str, str] | None = None) -> Path:
    environment = os.environ if env is None else env
    return xdg_path(
        environment,
        "XDG_STATE_HOME",
        ".local/state",
        "agent-fork",
        "session-lineage-inferences.json",
    )


def index_freshness_path(env: Mapping[str, str] | None = None) -> Path:
    environment = os.environ if env is None else env
    return xdg_path(
        environment,
        "XDG_STATE_HOME",
        ".local/state",
        "agent-fork",
        "claude-lineage-freshness.json",
    )


def _legacy_index_freshness_path(env: Mapping[str, str] | None = None) -> Path:
    environment = os.environ if env is None else env
    return xdg_path(
        environment,
        "XDG_CACHE_HOME",
        ".cache",
        "agent-fork",
        "claude-lineage-freshness.json",
    )


def _read_targets(path: Path) -> dict[str, object] | None:
    """Return the validated ``targets`` dict, or None if structurally invalid."""
    if path.is_symlink():
        return None
    if not path.exists():
        return {}
    if path.stat().st_size > MAX_STORE_BYTES:
        return None
    try:
        with path.open("rb") as stream:
            document = json.loads(stream.read(MAX_STORE_BYTES + 1))
    except (OSError, TypeError, json.JSONDecodeError):
        return None
    if (
        not isinstance(document, dict)
        or document.get("version") != 1
        or not isinstance(document.get("targets"), dict)
    ):
        return None
    return document["targets"]


def _write_targets(path: Path, entries: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    atomic_write_json(path, {"version": 1, "targets": entries}, prefix=".freshness-")


def update_index_freshness(
    child_session_id: str,
    candidate_universe_digest: str,
    analysis_index_generation: str,
    *,
    env: Mapping[str, str] | None = None,
) -> None:
    path = index_freshness_path(env)
    legacy_path = _legacy_index_freshness_path(env)
    with registry_lock(path):
        with registry_lock(legacy_path):
            entries = _read_targets(path)
            if entries is None:
                raise ValueError("invalid Claude lineage freshness index")
            entries[child_session_id] = {
                "candidate_universe_digest": candidate_universe_digest,
                "analysis_index_generation": analysis_index_generation,
            }
            _write_targets(path, entries)

            try:
                legacy_entries = _read_targets(legacy_path)
                if legacy_entries is not None and child_session_id in legacy_entries:
                    del legacy_entries[child_session_id]
                    _write_targets(legacy_path, legacy_entries)
            except (OSError, ValueError):
                pass


def remove_index_freshness(
    child_session_id: str, *, env: Mapping[str, str] | None = None
) -> bool:
    path = index_freshness_path(env)
    legacy_path = _legacy_index_freshness_path(env)
    changed = False
    with registry_lock(path):
        with registry_lock(legacy_path):
            entries = _read_targets(path)
            if entries is None:
                raise ValueError("invalid Claude lineage freshness index")
            if child_session_id in entries:
                del entries[child_session_id]
                _write_targets(path, entries)
                changed = True

            legacy_entries = _read_targets(legacy_path)
            if legacy_entries is None:
                raise ValueError("invalid Claude lineage freshness index")
            if child_session_id in legacy_entries:
                del legacy_entries[child_session_id]
                _write_targets(legacy_path, legacy_entries)
                changed = True
    return changed


def _decode(path: Path) -> list[InferenceRecord]:
    if not path.exists():
        return []
    if path.is_symlink() or path.stat().st_size > MAX_STORE_BYTES:
        raise ValueError(f"invalid agent-fork inference store: {path}")
    try:
        document = json.loads(path.read_bytes())
        if document.get("version") != VERSION:
            raise ValueError("unsupported version")
        records = []
        for item in document["inferences"]:
            fingerprints = tuple(str(value) for value in item["source_fingerprints"])
            if len(fingerprints) > MAX_SOURCE_FINGERPRINTS:
                raise ValueError("source fingerprint list exceeds bound")
            records.append(
                InferenceRecord(
                    child_session_id=str(item["child_session_id"]),
                    parent_session_id=str(item["parent_session_id"]),
                    status=str(item["status"]),
                    fork_boundary_message_id=str(item["fork_boundary_message_id"]),
                    shared_message_count=int(item["shared_message_count"]),
                    shared_substantive_message_count=int(
                        item["shared_substantive_message_count"]
                    ),
                    algorithm_version=int(item["algorithm_version"]),
                    analyzed_at=str(item["analyzed_at"]),
                    source_fingerprints=fingerprints,
                    analysis_index_generation=str(item["analysis_index_generation"]),
                    candidate_universe_digest=str(item["candidate_universe_digest"]),
                    agent=str(item.get("agent", "claude")),
                )
            )
        return records
    except (OSError, TypeError, KeyError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid agent-fork inference store: {path}") from error


def read_inferences(
    *, env: Mapping[str, str] | None = None
) -> tuple[InferenceRecord, ...]:
    return tuple(
        sorted(
            _decode(inference_path(env)),
            key=lambda x: (x.analyzed_at, x.child_session_id),
        )
    )


def find_inference(
    child_session_id: str, *, env: Mapping[str, str] | None = None
) -> InferenceRecord | None:
    return next(
        (x for x in read_inferences(env=env) if x.child_session_id == child_session_id),
        None,
    )


def _classify_changed_source(record: InferenceRecord, raw_path: str) -> ChangedSource:
    stem = Path(raw_path).stem
    if stem == record.child_session_id:
        return "target"
    if stem == record.parent_session_id:
        return "parent"
    return "other"


def assess_inference(
    record: InferenceRecord, *, env: Mapping[str, str] | None = None
) -> InferenceAssessment:
    """Describe only what cheap source checks can truthfully establish.

    Evaluation order is fixed and must not be reordered: (1) algorithm
    version and presence of source fingerprints, (2) presence of the
    corpus-wide generation/digest on the record itself, (3) per-file
    fingerprint comparison against the recorded sources, (4) the freshness
    index's per-child candidate-universe corroboration, checked at the state
    path and falling back to the legacy path only for this specific child.
    """
    if record.algorithm_version != 1 or not record.source_fingerprints:
        return InferenceAssessment(
            "stale_algorithm", _EVIDENCE_BY_STATUS["stale_algorithm"]
        )
    if not record.analysis_index_generation or not record.candidate_universe_digest:
        return InferenceAssessment(
            "freshness_unknown", _EVIDENCE_BY_STATUS["freshness_unknown"]
        )

    changed: set[ChangedSource] = set()
    for item in record.source_fingerprints:
        if ":" not in item:
            # a malformed entry has no path to classify against target/parent
            changed.add("other")
            continue
        raw_path, expected = item.rsplit(":", 1)
        path = Path(raw_path)
        try:
            if path.is_symlink():
                changed.add(_classify_changed_source(record, raw_path))
                continue
            stat = path.stat()
            actual_raw = (
                f"{path.absolute()}:{stat.st_dev}:{stat.st_ino}:"
                f"{stat.st_size}:{stat.st_mtime_ns}"
            )
            actual = hashlib.sha256(actual_raw.encode()).hexdigest()
        except OSError:
            changed.add(_classify_changed_source(record, raw_path))
            continue
        if actual != expected:
            changed.add(_classify_changed_source(record, raw_path))
    if changed:
        return InferenceAssessment(
            "stale_sources",
            _EVIDENCE_BY_STATUS["stale_sources"],
            tuple(sorted(changed)),
        )

    state_targets = _read_targets(index_freshness_path(env))
    if state_targets is None:
        return InferenceAssessment(
            "freshness_unknown", _EVIDENCE_BY_STATUS["freshness_unknown"]
        )

    entry = state_targets.get(record.child_session_id)
    if not (isinstance(entry, dict) and "candidate_universe_digest" in entry):
        legacy_targets = _read_targets(_legacy_index_freshness_path(env))
        if legacy_targets is not None:
            legacy_entry = legacy_targets.get(record.child_session_id)
            if (
                isinstance(legacy_entry, dict)
                and "candidate_universe_digest" in legacy_entry
            ):
                entry = legacy_entry

    if not (isinstance(entry, dict) and "candidate_universe_digest" in entry):
        return InferenceAssessment(
            "freshness_unknown", _EVIDENCE_BY_STATUS["freshness_unknown"]
        )

    if entry.get("candidate_universe_digest") != record.candidate_universe_digest:
        return InferenceAssessment(
            "stale_candidate_universe", _EVIDENCE_BY_STATUS["stale_candidate_universe"]
        )
    return InferenceAssessment(
        "current_at_last_analysis", _EVIDENCE_BY_STATUS["current_at_last_analysis"]
    )


def inference_freshness(
    record: InferenceRecord, *, env: Mapping[str, str] | None = None
) -> str:
    return assess_inference(record, env=env).status


def inference_is_current(
    record: InferenceRecord, *, env: Mapping[str, str] | None = None
) -> bool:
    return assess_inference(record, env=env).satisfies_strict_parent


def _write(path: Path, records: list[InferenceRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    document = {
        "version": VERSION,
        "inferences": [
            x.document()
            for x in sorted(records, key=lambda y: (y.analyzed_at, y.child_session_id))
        ],
    }
    atomic_write_json(path, document, prefix=".inferences-")


def add_inference(
    record: InferenceRecord, *, env: Mapping[str, str] | None = None
) -> None:
    path = inference_path(env)
    with registry_lock(path):
        records = [
            x for x in _decode(path) if x.child_session_id != record.child_session_id
        ]
        records.append(record)
        _write(path, records)


def remove_inference(
    child_session_id: str, *, env: Mapping[str, str] | None = None
) -> bool:
    path = inference_path(env)
    with registry_lock(path):
        records = _decode(path)
        kept = [x for x in records if x.child_session_id != child_session_id]
        if len(kept) == len(records):
            return False
        _write(path, kept)
        return True
