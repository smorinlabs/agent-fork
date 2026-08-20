"""Bounded structural inference for Claude transcript relationships."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat as stat_module
import time
from collections import deque
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, cast

from agent_fork.storage import atomic_write_json
from agent_fork.xdg import xdg_path

UUID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SUBSTANTIVE = frozenset(("user", "assistant"))
ALGORITHM_VERSION = 1
SCREEN_SCHEMA = "agent-fork.claude-lineage-screen"
SCREEN_SCHEMA_VERSION = 2
SCANNER_VERSION = 2
SCREEN_RECORD_BYTES = 8 * 1024 * 1024
SCREEN_HASH_LIMIT = 100_000
SCREEN_TOKEN_BYTES = 1024
CACHE_SHARD_BYTES = 8 * 1024 * 1024


class CorpusLimitError(ValueError):
    """A bounded analysis limit was exceeded.

    Subclasses ``ValueError`` deliberately: every existing ``except
    ValueError`` handler in this module keeps working unchanged.
    """

    def __init__(
        self, limit: str, allowed: int, observed: int, *, scope: str = "corpus"
    ):
        super().__init__(
            f"Claude transcript corpus exceeds {limit} limit: "
            f"{observed} > {allowed} ({scope})"
        )
        self.limit = limit
        self.allowed = allowed
        self.observed = observed
        self.scope = scope


def map_timeout_to_limit_error(error: TimeoutError, limits: Limits) -> CorpusLimitError:
    """Map the per-target `max_seconds` deadline guard to the same typed shape.

    `TimeoutError` is not itself a `CorpusLimitError` (it derives from
    `OSError`, not `ValueError`), so the CLI boundary maps it explicitly
    rather than catching it as one.
    """
    allowed = int(limits.max_seconds)
    return CorpusLimitError("max_seconds", allowed, allowed + 1, scope="target")


@dataclass(frozen=True)
class Limits:
    max_files: int = 10_000
    max_entries: int = 50_000
    max_file_bytes: int = 256 * 1024 * 1024
    max_total_bytes: int = 2 * 1024 * 1024 * 1024
    max_records: int = 250_000
    max_record_bytes: int = 8 * 1024 * 1024
    max_candidates: int = 1_000
    max_seconds: float = 120.0


@dataclass
class Work:
    discovery_passes: int = 0
    history_passes: int = 0
    files_enumerated: int = 0
    entries_seen: int = 0
    superficial_bytes: int = 0
    deep_files: int = 0
    deep_bytes: int = 0
    records_decoded: int = 0
    candidate_comparisons: int = 0
    graph_visits: int = 0
    graph_edges: int = 0
    winning_chain_nodes: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    cache_write_failures: int = 0
    screen_wildcards: int = 0
    screen_overflows: int = 0
    unsafe_skipped: int = 0
    unavailable_skipped: int = 0
    identity_mismatches: int = 0
    corpus_incomplete: int = 0
    history_bytes: int = 0
    history_records_seen: int = 0
    history_records_decoded: int = 0
    history_malformed: int = 0
    history_oversized: int = 0
    history_unavailable: int = 0
    freshness_write_failures: int = 0
    cache_shards_pruned: int = 0
    cache_bytes_reclaimed: int = 0
    cache_prune_failures: int = 0
    cache_sweep_incomplete: int = 0
    legacy_cache_removed: int = 0

    def document(self) -> dict[str, int]:
        return dict(vars(self))


@dataclass(frozen=True)
class Node:
    uuid: str
    parent: str | None
    kind: str
    timestamp: str | None


@dataclass(frozen=True)
class Transcript:
    session_id: str
    path: Path
    nodes: dict[str, Node]
    birth_ns: int | None
    fingerprint: str


@dataclass(frozen=True)
class Screen:
    hashes: frozenset[str]
    always_candidate: bool = False


@dataclass(frozen=True)
class Candidate:
    session_id: str
    shared: int
    substantive: int
    boundary: str
    older: bool | None
    clocks: int


@dataclass(frozen=True)
class Result:
    session_id: str
    status: str
    parent_session_id: str | None
    boundary: str | None
    shared: int
    substantive: int
    candidates: tuple[Candidate, ...]
    work: Work
    fingerprints: tuple[str, ...] = ()
    analysis_index_generation: str = ""
    candidate_universe_digest: str = ""

    @property
    def recordable(self) -> bool:
        return (
            self.status in {"strongly_inferred", "inferred"}
            and self.parent_session_id is not None
        )

    def document(self) -> dict[str, object]:
        return {
            "agent": "claude",
            "session_id": self.session_id,
            "relationship": {
                "kind": "shared-lineage" if self.boundary else None,
                "likely_parent_session_id": self.parent_session_id,
                "status": self.status,
                "immediate_parent_proven": False,
                "fork_boundary_message_id": self.boundary,
                "shared_message_count": self.shared,
                "shared_substantive_message_count": self.substantive,
            },
            "candidates": [vars(x) for x in self.candidates],
            "algorithm": {
                "name": "claude-transcript-lineage",
                "version": ALGORITHM_VERSION,
            },
            "freshness": {
                "status": "current_at_last_analysis",
                "analysis_index_generation": self.analysis_index_generation,
                "candidate_universe_digest": self.candidate_universe_digest,
            },
            "work": self.work.document(),
            "recorded": False,
            "notices": [],
        }


def claude_root(env: Mapping[str, str]) -> Path:
    return (
        Path(env.get("CLAUDE_CONFIG_DIR", Path(env.get("HOME", "~")) / ".claude"))
        .expanduser()
        .resolve()
    )


def _fingerprint(path: Path, stat: os.stat_result) -> str:
    raw = (
        f"{path.absolute()}:{stat.st_dev}:{stat.st_ino}:"
        f"{stat.st_size}:{stat.st_mtime_ns}"
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def _identity(value: os.stat_result) -> tuple[int, int, int, int]:
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)


@contextmanager
def _stable_reader(path: Path) -> Iterator[tuple[BinaryIO, os.stat_result]]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    stream: BinaryIO | None = None
    try:
        before = os.fstat(descriptor)
        if not stat_module.S_ISREG(before.st_mode):
            raise OSError(f"not a regular Claude transcript: {path.name}")
        stream = os.fdopen(descriptor, "rb", closefd=True)
        descriptor = -1
        yield stream, before
        after = os.fstat(stream.fileno())
        if _identity(after) != _identity(before):
            raise OSError(f"Claude transcript changed during analysis: {path.name}")
    finally:
        if stream is not None:
            stream.close()
        elif descriptor >= 0:
            os.close(descriptor)


def discover(env: Mapping[str, str], limits: Limits, work: Work) -> list[Path]:
    work.discovery_passes += 1
    root = claude_root(env)
    project = root / "projects"
    result = []
    total = 0
    if not project.is_dir():
        return []
    try:
        with os.scandir(project) as iterator:
            projects = []
            for entry in iterator:
                work.entries_seen += 1
                if work.entries_seen > limits.max_entries:
                    raise CorpusLimitError(
                        "max_entries", limits.max_entries, work.entries_seen
                    )
                projects.append(entry)
        projects.sort(key=lambda entry: entry.name)
    except OSError as error:
        raise ValueError("Claude transcript corpus is unavailable") from error
    for directory in projects:
        try:
            if directory.is_symlink() or not directory.is_dir(follow_symlinks=False):
                work.unsafe_skipped += 1
                continue
            with os.scandir(directory.path) as iterator:
                entries = []
                for entry in iterator:
                    work.entries_seen += 1
                    if work.entries_seen > limits.max_entries:
                        raise CorpusLimitError(
                            "max_entries", limits.max_entries, work.entries_seen
                        )
                    entries.append(entry)
            entries.sort(key=lambda entry: entry.name)
        except OSError:
            work.unavailable_skipped += 1
            work.corpus_incomplete = 1
            continue
        for entry in entries:
            path = Path(entry.path)
            if path.suffix != ".jsonl" or not UUID.fullmatch(path.stem):
                continue
            try:
                if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                    work.unsafe_skipped += 1
                    continue
                metadata = entry.stat(follow_symlinks=False)
            except OSError:
                work.unavailable_skipped += 1
                work.corpus_incomplete = 1
                continue
            if metadata.st_size > limits.max_file_bytes:
                work.unavailable_skipped += 1
                work.corpus_incomplete = 1
                continue
            total += metadata.st_size
            if total > limits.max_total_bytes:
                raise CorpusLimitError("max_total_bytes", limits.max_total_bytes, total)
            result.append(path.absolute())
            if len(result) > limits.max_files:
                raise CorpusLimitError("max_files", limits.max_files, len(result))
    work.files_enumerated = len(result)
    return result


def _cache_root(env: Mapping[str, str]) -> Path:
    return xdg_path(
        env, "XDG_CACHE_HOME", ".cache", "agent-fork", "claude-lineage-index-v3"
    )


def _legacy_cache_root(env: Mapping[str, str]) -> Path:
    return xdg_path(
        env, "XDG_CACHE_HOME", ".cache", "agent-fork", "claude-lineage-index-v2"
    )


CACHE_SWEEP_INTERVAL = 86_400
CACHE_TEMP_GRACE_SECONDS = 3_600
CACHE_MAX_AGE_SECONDS = 30 * 86_400
CACHE_MAX_BYTES = 64 * 1024 * 1024
CACHE_SWEEP_MAX_ENTRIES = 20_000
_SHARD_NAME = UUID


def _root_safe(root: Path) -> bool:
    try:
        if not root.exists():
            return False
        root_stat = root.lstat()
        return (
            stat_module.S_ISDIR(root_stat.st_mode)
            and not root.is_symlink()
            and (not hasattr(os, "getuid") or root_stat.st_uid == os.getuid())
        )
    except OSError:
        return False


def sweep_cache(env: Mapping[str, str], stems: set[str], work: Work) -> None:
    """Bounded, marker-gated maintenance of the v3 screen-cache directory.

    Confined to the v3 root (plus, once, an independently safety-checked v2
    root for one-time legacy removal). Never raises; every failure is
    counted. Never touches the freshness index at either location.
    """
    root = _cache_root(env)
    if not _root_safe(root):
        return
    marker = root / ".sweep"
    try:
        marker_stat = marker.stat()
        if time.time() - marker_stat.st_mtime < CACHE_SWEEP_INTERVAL:
            return
    except OSError:
        pass
    try:
        marker.touch()
    except OSError:
        work.cache_prune_failures += 1
        return

    legacy_root = _legacy_cache_root(env)
    if legacy_root != root and _root_safe(legacy_root):
        try:
            for child in legacy_root.rglob("*"):
                if child.is_file() or child.is_symlink():
                    try:
                        child.unlink()
                    except OSError:
                        work.cache_prune_failures += 1
            for directory in sorted(
                (item for item in legacy_root.rglob("*") if item.is_dir()),
                key=lambda item: len(item.parts),
                reverse=True,
            ):
                try:
                    directory.rmdir()
                except OSError:
                    work.cache_prune_failures += 1
            legacy_root.rmdir()
            work.legacy_cache_removed = 1
        except OSError:
            work.cache_prune_failures += 1

    now = time.time()
    scanned = 0
    candidates: list[tuple[Path, os.stat_result]] = []
    try:
        entries = list(root.iterdir())
    except OSError:
        work.cache_prune_failures += 1
        entries = []
    for entry in entries:
        scanned += 1
        if scanned > CACHE_SWEEP_MAX_ENTRIES:
            work.cache_sweep_incomplete = 1
            break
        if entry.name == ".sweep":
            continue
        try:
            entry_stat = entry.lstat()
        except OSError:
            continue
        if entry.is_symlink():
            continue
        if _SHARD_NAME.fullmatch(entry.stem) is None or entry.suffix != ".json":
            if now - entry_stat.st_mtime > CACHE_TEMP_GRACE_SECONDS:
                try:
                    entry.unlink()
                    work.cache_shards_pruned += 1
                    work.cache_bytes_reclaimed += entry_stat.st_size
                except OSError:
                    work.cache_prune_failures += 1
            continue
        if entry.stem not in stems:
            try:
                entry.unlink()
                work.cache_shards_pruned += 1
                work.cache_bytes_reclaimed += entry_stat.st_size
            except OSError:
                work.cache_prune_failures += 1
            continue
        if now - entry_stat.st_mtime > CACHE_MAX_AGE_SECONDS:
            try:
                entry.unlink()
                work.cache_shards_pruned += 1
                work.cache_bytes_reclaimed += entry_stat.st_size
            except OSError:
                work.cache_prune_failures += 1
            continue
        candidates.append((entry, entry_stat))

    total_bytes = sum(entry_stat.st_size for _, entry_stat in candidates)
    if total_bytes > CACHE_MAX_BYTES:
        for entry, entry_stat in sorted(candidates, key=lambda item: item[1].st_mtime):
            if total_bytes <= CACHE_MAX_BYTES:
                break
            try:
                entry.unlink()
                work.cache_shards_pruned += 1
                work.cache_bytes_reclaimed += entry_stat.st_size
                total_bytes -= entry_stat.st_size
            except OSError:
                work.cache_prune_failures += 1


def _screen_record(raw: bytes) -> tuple[set[str], bool]:
    """Extract top-level UUID values without materializing message content."""
    hashes: set[str] = set()
    stack: list[int] = []
    top_key: str | None = None
    expect_top_key = False
    expect_top_value = False
    index = 0
    uncertain = False
    while index < len(raw):
        byte = raw[index]
        if byte in b" \t\r\n":
            index += 1
            continue
        if byte == ord('"'):
            relevant = (
                len(stack) == 1
                and stack[0] == ord("{")
                and (expect_top_key or (expect_top_value and top_key == "uuid"))
            )
            start = index
            index += 1
            while index < len(raw):
                if raw[index] == ord("\\"):
                    index += 2
                    continue
                if raw[index] == ord('"'):
                    index += 1
                    break
                index += 1
            else:
                return hashes, True
            decoded = None
            if relevant:
                token = raw[start:index]
                if len(token) > SCREEN_TOKEN_BYTES:
                    uncertain = True
                else:
                    try:
                        decoded = json.loads(token)
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        uncertain = True
            if len(stack) == 1 and stack[0] == ord("{"):
                if expect_top_key:
                    top_key = decoded if isinstance(decoded, str) else None
                    expect_top_key = False
                elif expect_top_value:
                    if top_key == "uuid" and isinstance(decoded, str):
                        if UUID.fullmatch(decoded):
                            hashes.add(
                                hashlib.sha256(decoded.lower().encode()).hexdigest()
                            )
                    expect_top_value = False
            continue
        if byte == ord("{"):
            if not stack:
                expect_top_key = True
            elif len(stack) == 1 and expect_top_value:
                expect_top_value = False
            stack.append(byte)
        elif byte == ord("["):
            if len(stack) == 1 and expect_top_value:
                expect_top_value = False
            stack.append(byte)
        elif byte in (ord("}"), ord("]")):
            if (
                not stack
                or (byte == ord("}") and stack[-1] != ord("{"))
                or (byte == ord("]") and stack[-1] != ord("["))
            ):
                uncertain = True
            elif stack:
                stack.pop()
        elif byte == ord(":") and len(stack) == 1 and stack[0] == ord("{"):
            expect_top_value = True
        elif byte == ord(",") and len(stack) == 1 and stack[0] == ord("{"):
            top_key = None
            expect_top_key = True
            expect_top_value = False
        index += 1
    if stack:
        uncertain = True
    return hashes, uncertain


def _screen(path: Path, env: Mapping[str, str], work: Work) -> Screen:
    metadata = path.lstat()
    if not stat_module.S_ISREG(metadata.st_mode):
        raise OSError(f"not a regular Claude transcript: {path.name}")
    fp = _fingerprint(path, metadata)
    root = _cache_root(env)
    shard = root / f"{path.stem}.json"
    cache_safe = True
    try:
        if root.exists():
            root_stat = root.lstat()
            cache_safe = (
                stat_module.S_ISDIR(root_stat.st_mode)
                and not root.is_symlink()
                and (not hasattr(os, "getuid") or root_stat.st_uid == os.getuid())
            )
    except OSError:
        cache_safe = False
    if cache_safe and shard.is_file() and not shard.is_symlink():
        try:
            with shard.open("rb") as cache_stream:
                raw = cache_stream.read(CACHE_SHARD_BYTES + 1)
            if len(raw) > CACHE_SHARD_BYTES:
                raise ValueError("cache shard exceeds limit")
            data = json.loads(raw)
            expected_keys = {
                "schema",
                "version",
                "scanner_version",
                "source",
                "mode",
                "uuid_sha256",
            }
            if not isinstance(data, dict) or set(data) != expected_keys:
                raise ValueError("invalid cache schema")
            source = data["source"]
            hashes = data["uuid_sha256"]
            if (
                data["schema"] != SCREEN_SCHEMA
                or data["version"] != SCREEN_SCHEMA_VERSION
                or isinstance(data["version"], bool)
                or data["scanner_version"] != SCANNER_VERSION
                or isinstance(data["scanner_version"], bool)
                or not isinstance(source, dict)
                or set(source) != {"session_id", "fingerprint"}
                or source["session_id"] != path.stem
                or source["fingerprint"] != fp
                or data["mode"] not in {"exact", "always_candidate"}
                or not isinstance(hashes, list)
                or len(hashes) > SCREEN_HASH_LIMIT
                or any(not isinstance(value, str) for value in hashes)
                or any(SHA256.fullmatch(value) is None for value in hashes)
                or hashes != sorted(set(hashes))
            ):
                raise ValueError("invalid cache data")
            work.cache_hits += 1
            if _identity(path.lstat()) != _identity(metadata):
                work.identity_mismatches += 1
                raise OSError(f"Claude transcript changed during analysis: {path.name}")
            return Screen(
                frozenset(cast(list[str], hashes)),
                data["mode"] == "always_candidate",
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            pass
    work.cache_misses += 1
    values: set[str] = set()
    always_candidate = False
    hash_overflow = False
    buffer = bytearray()
    draining = False
    with _stable_reader(path) as (stream, opened):
        if _identity(opened) != _identity(metadata):
            work.identity_mismatches += 1
            raise OSError(f"Claude transcript changed during analysis: {path.name}")
        while chunk := stream.read(64 * 1024):
            work.superficial_bytes += len(chunk)
            for byte in chunk:
                if byte == ord("\n"):
                    if not draining and buffer.strip():
                        found, uncertain = _screen_record(bytes(buffer))
                        if not hash_overflow:
                            values.update(found)
                            if len(values) > SCREEN_HASH_LIMIT:
                                values.clear()
                                hash_overflow = True
                                work.screen_overflows += 1
                        always_candidate |= uncertain
                    buffer.clear()
                    draining = False
                elif not draining:
                    buffer.append(byte)
                    if len(buffer) > SCREEN_RECORD_BYTES:
                        buffer.clear()
                        draining = True
                        always_candidate = True
                        work.screen_overflows += 1
        if not draining and buffer.strip():
            found, uncertain = _screen_record(bytes(buffer))
            if not hash_overflow:
                values.update(found)
            always_candidate |= uncertain
    if _identity(path.lstat()) != _identity(metadata):
        work.identity_mismatches += 1
        raise OSError(f"Claude transcript replaced during analysis: {path.name}")
    if len(values) > SCREEN_HASH_LIMIT:
        values.clear()
        hash_overflow = True
        work.screen_overflows += 1
    if hash_overflow:
        always_candidate = True
    if always_candidate:
        work.screen_wildcards += 1
    document = {
        "schema": SCREEN_SCHEMA,
        "version": SCREEN_SCHEMA_VERSION,
        "scanner_version": SCANNER_VERSION,
        "source": {"session_id": path.stem, "fingerprint": fp},
        "mode": "always_candidate" if always_candidate else "exact",
        "uuid_sha256": sorted(values),
    }
    try:
        if not cache_safe:
            raise OSError("unsafe Claude lineage cache root")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(root, 0o700)
        atomic_write_json(
            shard,
            document,
            fsync=False,
            prefix=f".{shard.name}.",
        )
    except OSError:
        work.cache_write_failures += 1
    return Screen(frozenset(values), always_candidate)


def _bounded_jsonl_records(
    stream,
    *,
    max_record_bytes: int,
    max_records: int,
    source: Path,
    skip_oversized: bool = False,
    on_oversized=None,
) -> Iterator[tuple[bytes, int]]:
    buffer = bytearray()
    count = 0
    draining = False
    while chunk := stream.read(64 * 1024):
        if draining:
            newline = chunk.find(b"\n")
            if newline < 0:
                continue
            chunk = chunk[newline + 1 :]
            draining = False
        buffer.extend(chunk)
        while (newline := buffer.find(b"\n")) >= 0:
            count += 1
            if count > max_records:
                raise ValueError(f"Claude transcript exceeds record limit: {source}")
            if newline > max_record_bytes:
                del buffer[: newline + 1]
                if skip_oversized:
                    if on_oversized is not None:
                        on_oversized()
                    continue
                raise ValueError(f"Claude transcript record exceeds limit: {source}")
            raw = bytes(buffer[:newline])
            del buffer[: newline + 1]
            yield raw, len(raw) + 1
        if len(buffer) > max_record_bytes:
            if skip_oversized:
                count += 1
                if count > max_records:
                    raise ValueError(
                        f"Claude transcript exceeds record limit: {source}"
                    )
                buffer.clear()
                draining = True
                if on_oversized is not None:
                    on_oversized()
                continue
            raise ValueError(f"Claude transcript record exceeds limit: {source}")
    if buffer and not draining:
        count += 1
        if count > max_records:
            raise ValueError(f"Claude transcript exceeds record limit: {source}")
        if len(buffer) > max_record_bytes:
            raise ValueError(f"Claude transcript record exceeds limit: {source}")
        yield bytes(buffer), len(buffer)


def deep_parse(path: Path, limits: Limits, work: Work) -> Transcript:
    nodes = {}
    work.deep_files += 1
    with _stable_reader(path) as (stream, metadata):
        for raw, consumed in _bounded_jsonl_records(
            stream,
            max_record_bytes=limits.max_record_bytes,
            max_records=limits.max_records,
            source=path,
        ):
            work.deep_bytes += consumed
            try:
                record = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            work.records_decoded += 1
            if not isinstance(record, dict):
                continue
            uid = record.get("uuid")
            parent = record.get("parentUuid")
            kind = record.get("type")
            if (
                not isinstance(uid, str)
                or not UUID.fullmatch(uid)
                or not isinstance(kind, str)
            ):
                continue
            if parent is not None and (
                not isinstance(parent, str) or not UUID.fullmatch(parent)
            ):
                continue
            node = Node(
                uid.lower(),
                parent.lower() if parent else None,
                kind,
                record.get("timestamp")
                if isinstance(record.get("timestamp"), str)
                else None,
            )
            if node.uuid in nodes and nodes[node.uuid] != node:
                raise ValueError(f"conflicting Claude message UUID: {node.uuid}")
            nodes[node.uuid] = node
    current = path.lstat()
    if _identity(current) != _identity(metadata):
        work.identity_mismatches += 1
        raise OSError(f"Claude transcript replaced during analysis: {path.name}")
    birth = getattr(current, "st_birthtime_ns", None)
    return Transcript(
        path.stem,
        path,
        nodes,
        birth if isinstance(birth, int) else None,
        _fingerprint(path, metadata),
    )


def _first_history(
    env: Mapping[str, str], relevant: set[str], work: Work
) -> dict[str, int]:
    path = claude_root(env) / "history.jsonl"
    result: dict[str, int] = {}
    work.history_passes += 1
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return result
    except OSError:
        work.history_unavailable += 1
        return result
    if not stat_module.S_ISREG(metadata.st_mode) or metadata.st_size > 64 * 1024 * 1024:
        work.history_unavailable += 1
        return result

    def oversized():
        work.history_oversized += 1
        work.history_records_seen += 1

    try:
        with _stable_reader(path) as (stream, opened):
            if _identity(opened) != _identity(metadata):
                raise OSError("Claude history changed before analysis")
            records = _bounded_jsonl_records(
                stream,
                max_record_bytes=1024 * 1024,
                max_records=1_000_000,
                source=path,
                skip_oversized=True,
                on_oversized=oversized,
            )
            for raw, _consumed in records:
                work.history_records_seen += 1
                try:
                    document = json.loads(raw)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    work.history_malformed += 1
                    continue
                work.history_records_decoded += 1
                if not isinstance(document, dict):
                    continue
                sid = document.get("sessionId")
                timestamp = document.get("timestamp")
                if (
                    isinstance(sid, str)
                    and sid in relevant
                    and isinstance(timestamp, int)
                    and not isinstance(timestamp, bool)
                ):
                    result[sid] = min(result.get(sid, timestamp), timestamp)
            work.history_bytes = metadata.st_size
    except (OSError, ValueError):
        work.history_unavailable += 1
        return {}
    return result


def _longest_shared_chain(
    target: Transcript, other: Transcript, work: Work
) -> tuple[list[str], str | None]:
    compatible = {
        uid
        for uid in set(target.nodes) & set(other.nodes)
        if target.nodes[uid].parent == other.nodes[uid].parent
        and target.nodes[uid].kind == other.nodes[uid].kind
    }
    if not compatible:
        return [], None

    predecessor: dict[str, str | None] = {}
    children: dict[str, list[str]] = {uid: [] for uid in compatible}
    indegree: dict[str, int] = {}
    for uid in compatible:
        parent = target.nodes[uid].parent
        predecessor[uid] = parent if parent in compatible else None
        indegree[uid] = int(parent in compatible)
        if parent in compatible:
            children[parent].append(uid)
            work.graph_edges += 1

    roots = deque(sorted(uid for uid, degree in indegree.items() if degree == 0))
    depth = {uid: 1 for uid in roots}
    processed = 0
    while roots:
        uid = roots.popleft()
        processed += 1
        work.graph_visits += 1
        for child in sorted(children[uid]):
            depth[child] = depth[uid] + 1
            indegree[child] -= 1
            if indegree[child] == 0:
                roots.append(child)
    if processed != len(compatible):
        raise ValueError("cyclic Claude message ancestry")

    boundary = max(
        compatible,
        key=lambda uid: (
            depth[uid],
            target.nodes[uid].timestamp or "",
            uid,
        ),
    )
    chain = []
    cursor: str | None = boundary
    while cursor is not None:
        chain.append(cursor)
        cursor = predecessor[cursor]
    chain.reverse()
    work.winning_chain_nodes += len(chain)
    return chain, boundary


class ClaudeLineageCorpus:
    """One bounded corpus snapshot shared by one or many target analyses."""

    def __init__(self, env: Mapping[str, str], limits: Limits | None = None):
        self.env = env
        self.limits = Limits() if limits is None else limits
        self.work = Work()
        self.started = time.monotonic()
        self.paths = discover(env, self.limits, self.work)
        self.by_id = {path.stem: path for path in self.paths}
        sweep_cache(env, set(self.by_id), self.work)
        generation_rows = []
        for path in self.paths:
            metadata = path.lstat()
            generation_rows.append(f"{path}:{_identity(metadata)}")
        self.index_generation = hashlib.sha256(
            "\n".join(generation_rows).encode()
        ).hexdigest()
        self.screens: dict[Path, Screen] = {}
        self.history = _first_history(env, set(self.by_id), self.work)
        self.parsed: dict[Path, Transcript] = {}
        self.pairs: dict[tuple[str, str], tuple[int, int, str | None]] = {}

    def transcript(self, path: Path) -> Transcript:
        if path not in self.parsed:
            self.parsed[path] = deep_parse(path, self.limits, self.work)
        return self.parsed[path]

    def screen(self, path: Path) -> Screen:
        if path not in self.screens:
            self.screens[path] = _screen(path, self.env, self.work)
        return self.screens[path]

    def infer_one(self, session_id: str) -> Result:
        if not UUID.fullmatch(session_id):
            raise ValueError("invalid Claude session ID")
        target_path = self.by_id.get(session_id)
        if target_path is None:
            raise FileNotFoundError(session_id)
        target = self.transcript(target_path)
        target_hashes = {
            hashlib.sha256(u.encode()).hexdigest()
            for u, node in target.nodes.items()
            if node.kind in SUBSTANTIVE
        }
        candidates = []
        candidate_universe = []
        fps = [f"{target.path}:{target.fingerprint}"]
        for path in self.paths:
            if path == target_path:
                continue
            if time.monotonic() - self.started > self.limits.max_seconds:
                raise TimeoutError("Claude parent inference timed out")
            try:
                screen = self.screen(path)
            except OSError:
                self.work.unavailable_skipped += 1
                self.work.corpus_incomplete = 1
                continue
            if not screen.always_candidate and not (screen.hashes & target_hashes):
                continue
            candidate_universe.append(path.stem)
            if len(candidates) >= self.limits.max_candidates:
                raise CorpusLimitError(
                    "max_candidates",
                    self.limits.max_candidates,
                    len(candidates) + 1,
                    scope="target",
                )
            try:
                other = self.transcript(path)
            except OSError:
                self.work.unavailable_skipped += 1
                self.work.corpus_incomplete = 1
                continue
            first, second = sorted((session_id, other.session_id))
            pair = (first, second)
            if pair not in self.pairs:
                self.work.candidate_comparisons += 1
                chain, boundary = _longest_shared_chain(target, other, self.work)
                substantive = sum(
                    target.nodes[uid].kind in SUBSTANTIVE for uid in chain
                )
                self.pairs[pair] = (len(chain), substantive, boundary)
            fps.append(f"{other.path}:{other.fingerprint}")
            shared, substantive, boundary = self.pairs[pair]
            if shared < 3 or substantive < 1 or boundary is None:
                continue
            clocks = []
            if target.birth_ns is not None and other.birth_ns is not None:
                clocks.append(other.birth_ns < target.birth_ns)
            if session_id in self.history and other.session_id in self.history:
                clocks.append(self.history[other.session_id] < self.history[session_id])
            older = all(clocks) if clocks else None
            if clocks and not all(value == clocks[0] for value in clocks):
                older = None
            candidates.append(
                Candidate(
                    other.session_id,
                    shared,
                    substantive,
                    boundary,
                    older,
                    len(clocks),
                )
            )
        candidates.sort(key=lambda c: (-c.substantive, -c.shared, c.session_id))
        eligible = [candidate for candidate in candidates if candidate.older is True]

        def finish(result: Result) -> Result:
            universe_digest = hashlib.sha256(
                "\n".join(sorted(candidate_universe)).encode()
            ).hexdigest()
            try:
                from agent_fork.lineage_inference_store import update_index_freshness

                update_index_freshness(
                    session_id,
                    universe_digest,
                    self.index_generation,
                    env=self.env,
                )
            except (OSError, ValueError):
                self.work.cache_write_failures += 1
                self.work.freshness_write_failures += 1
            return replace(
                result,
                analysis_index_generation=self.index_generation,
                candidate_universe_digest=universe_digest,
            )

        if self.work.corpus_incomplete:
            provisional = (eligible or candidates)[0] if candidates else None
            return finish(
                Result(
                    session_id,
                    "incomplete",
                    None,
                    provisional.boundary if provisional else None,
                    provisional.shared if provisional else 0,
                    provisional.substantive if provisional else 0,
                    tuple(candidates),
                    self.work,
                    tuple(fps),
                )
            )
        if not candidates:
            return finish(
                Result(
                    session_id,
                    "insufficient_evidence",
                    None,
                    None,
                    0,
                    0,
                    (),
                    self.work,
                    tuple(fps),
                )
            )
        best = (eligible or candidates)[0]
        if (
            not eligible
            or len(
                [
                    c
                    for c in eligible
                    if (c.substantive, c.shared, c.boundary)
                    == (best.substantive, best.shared, best.boundary)
                ]
            )
            > 1
        ):
            return finish(
                Result(
                    session_id,
                    "ambiguous",
                    None,
                    best.boundary,
                    best.shared,
                    best.substantive,
                    tuple(candidates),
                    self.work,
                    tuple(fps),
                )
            )
        status = "strongly_inferred" if best.clocks >= 2 else "inferred"
        return finish(
            Result(
                session_id,
                status,
                best.session_id,
                best.boundary,
                best.shared,
                best.substantive,
                tuple(candidates),
                self.work,
                tuple(fps),
            )
        )

    def infer_many(self, session_ids: list[str]) -> list[Result]:
        return [self.infer_one(session_id) for session_id in session_ids]

    def evidence_stable(self, result: Result) -> bool:
        """Revalidate the corpus and parsed evidence immediately before recording."""
        try:
            current = discover(self.env, self.limits, Work())
            if set(current) != set(self.paths):
                return False
            evidence_ids = {result.session_id, result.parent_session_id}
            for transcript in self.parsed.values():
                if transcript.session_id not in evidence_ids:
                    continue
                metadata = transcript.path.lstat()
                if _fingerprint(transcript.path, metadata) != transcript.fingerprint:
                    return False
            return True
        except (OSError, ValueError):
            return False


def infer(
    session_id: str, env: Mapping[str, str], *, limits: Limits | None = None
) -> Result:
    return ClaudeLineageCorpus(env, limits).infer_one(session_id)


def to_record(result: Result):
    from agent_fork.lineage_inference_store import InferenceRecord

    if (
        not result.recordable
        or result.parent_session_id is None
        or result.boundary is None
    ):
        raise ValueError("Claude parent result is not recordable")
    return InferenceRecord(
        result.session_id,
        result.parent_session_id,
        result.status,
        result.boundary,
        result.shared,
        result.substantive,
        ALGORITHM_VERSION,
        datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        result.fingerprints,
        result.analysis_index_generation,
        result.candidate_universe_digest,
    )
