"""Versioned, atomic storage for heuristic Claude parent inferences."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

from agent_fork.registry import registry_lock

VERSION = 2
MAX_STORE_BYTES = 8 * 1024 * 1024


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


def inference_path(env: Mapping[str, str] | None = None) -> Path:
    environment = os.environ if env is None else env
    base = environment.get("XDG_STATE_HOME")
    if base is None:
        base = str(Path(environment.get("HOME", "~")).expanduser() / ".local/state")
    return Path(base).expanduser() / "agent-fork" / "session-lineage-inferences.json"


def index_freshness_path(env: Mapping[str, str] | None = None) -> Path:
    environment = os.environ if env is None else env
    base = environment.get("XDG_CACHE_HOME")
    if base is None:
        base = str(Path(environment.get("HOME", "~")).expanduser() / ".cache")
    return Path(base).expanduser() / "agent-fork" / "claude-lineage-freshness.json"


def update_index_freshness(
    child_session_id: str,
    candidate_universe_digest: str,
    analysis_index_generation: str,
    *,
    env: Mapping[str, str] | None = None,
) -> None:
    path = index_freshness_path(env)
    with registry_lock(path):
        entries: dict[str, object] = {}
        if path.exists():
            if path.is_symlink() or path.stat().st_size > MAX_STORE_BYTES:
                raise ValueError("invalid Claude lineage freshness index")
            with path.open("rb") as stream:
                document = json.loads(stream.read(MAX_STORE_BYTES + 1))
            if document.get("version") != 1 or not isinstance(
                document.get("targets"), dict
            ):
                raise ValueError("invalid Claude lineage freshness index")
            entries = document["targets"]
        entries[child_session_id] = {
            "candidate_universe_digest": candidate_universe_digest,
            "analysis_index_generation": analysis_index_generation,
        }
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary_name: str | None = None
        try:
            with NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=path.parent,
                prefix=".freshness-",
                delete=False,
            ) as stream:
                temporary_name = stream.name
                os.chmod(temporary_name, 0o600)
                json.dump(
                    {"version": 1, "targets": entries},
                    stream,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                stream.write("\n")
            os.replace(temporary_name, path)
            temporary_name = None
        finally:
            if temporary_name is not None:
                Path(temporary_name).unlink(missing_ok=True)


def _decode(path: Path) -> list[InferenceRecord]:
    if not path.exists():
        return []
    if path.is_symlink() or path.stat().st_size > MAX_STORE_BYTES:
        raise ValueError(f"invalid agent-fork inference store: {path}")
    try:
        document = json.loads(path.read_bytes())
        if document.get("version") != VERSION:
            raise ValueError("unsupported version")
        return [
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
                source_fingerprints=tuple(
                    str(value) for value in item["source_fingerprints"]
                ),
                analysis_index_generation=str(item["analysis_index_generation"]),
                candidate_universe_digest=str(item["candidate_universe_digest"]),
                agent=str(item.get("agent", "claude")),
            )
            for item in document["inferences"]
        ]
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


def inference_freshness(
    record: InferenceRecord, *, env: Mapping[str, str] | None = None
) -> str:
    """Describe only what cheap source checks can truthfully establish."""
    if record.algorithm_version != 1 or not record.source_fingerprints:
        return "stale_algorithm"
    if not record.analysis_index_generation or not record.candidate_universe_digest:
        return "freshness_unknown"
    for item in record.source_fingerprints:
        try:
            raw_path, expected = item.rsplit(":", 1)
            path = Path(raw_path)
            if path.is_symlink():
                return "stale_sources"
            stat = path.stat()
            actual_raw = (
                f"{path.absolute()}:{stat.st_dev}:{stat.st_ino}:"
                f"{stat.st_size}:{stat.st_mtime_ns}"
            )
            actual = hashlib.sha256(actual_raw.encode()).hexdigest()
        except (OSError, ValueError):
            return "stale_sources"
        if actual != expected:
            return "stale_sources"
    path = index_freshness_path(env)
    try:
        if (
            path.is_file()
            and not path.is_symlink()
            and path.stat().st_size <= MAX_STORE_BYTES
        ):
            with path.open("rb") as stream:
                document = json.loads(stream.read(MAX_STORE_BYTES + 1))
            target = document.get("targets", {}).get(record.child_session_id)
            if isinstance(target, dict) and (
                target.get("candidate_universe_digest")
                != record.candidate_universe_digest
            ):
                return "stale_candidate_universe"
    except (OSError, TypeError, json.JSONDecodeError):
        return "freshness_unknown"
    return "current_at_last_analysis"


def inference_is_current(
    record: InferenceRecord, *, env: Mapping[str, str] | None = None
) -> bool:
    return inference_freshness(record, env=env) == "current_at_last_analysis"


def _write(path: Path, records: list[InferenceRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    document = {
        "version": VERSION,
        "inferences": [
            x.document()
            for x in sorted(records, key=lambda y: (y.analyzed_at, y.child_session_id))
        ],
    }
    temporary_name: str | None = None
    try:
        with NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, prefix=".inferences-", delete=False
        ) as stream:
            temporary_name = stream.name
            os.chmod(temporary_name, 0o600)
            json.dump(document, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
        temporary_name = None
        os.chmod(path, 0o600)
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


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
