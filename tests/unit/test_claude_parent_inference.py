"""Claude structural parent inference and performance contracts."""

from __future__ import annotations

import hashlib
import json
import stat
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from agent_fork.claude_lineage_inference import (
    ClaudeLineageCorpus,
    Limits,
    Node,
    Transcript,
    Work,
    _longest_shared_chain,
    _screen,
    deep_parse,
    discover,
    infer,
)

ROOT = "10000000-0000-4000-8000-000000000001"
SHARED = "10000000-0000-4000-8000-000000000002"
PARENT_ONLY = "10000000-0000-4000-8000-000000000003"
CHILD_ONLY = "10000000-0000-4000-8000-000000000004"
PARENT = "20000000-0000-4000-8000-000000000001"
CHILD = "20000000-0000-4000-8000-000000000002"


def _record(session: str, uuid: str, parent: str | None, kind: str, at: str):
    return {
        "sessionId": session,
        "uuid": uuid,
        "parentUuid": parent,
        "type": kind,
        "timestamp": at,
        "message": {"content": "SECRET-CONTENT-CANARY"},
    }


def _write(root: Path, session: str, records: list[dict[str, object]]) -> None:
    directory = root / "projects" / "-repo"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{session}.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in records)
    )


def _world(tmp_path: Path):
    root = tmp_path / ".claude"
    common_parent = [
        _record(PARENT, ROOT, None, "system", "2026-01-01T00:00:00Z"),
        _record(PARENT, SHARED, ROOT, "user", "2026-01-01T00:00:01Z"),
        _record(PARENT, PARENT_ONLY, SHARED, "assistant", "2026-01-01T00:00:02Z"),
    ]
    common_child: list[dict[str, object]] = [
        {**item, "sessionId": CHILD} for item in common_parent[:3]
    ]
    _write(root, PARENT, common_parent)
    _write(
        root,
        CHILD,
        common_child
        + [_record(CHILD, CHILD_ONLY, PARENT_ONLY, "user", "2026-01-01T00:00:03Z")],
    )
    history = [
        {"sessionId": PARENT, "timestamp": 1000, "display": "secret"},
        {"sessionId": CHILD, "timestamp": 2000, "display": "secret"},
    ]
    (root / "history.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in history)
    )
    return {
        "HOME": str(tmp_path),
        "CLAUDE_CONFIG_DIR": str(root),
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
        "XDG_STATE_HOME": str(tmp_path / "state"),
    }


@pytest.mark.matrix("T-CPI-01")
def test_infers_parent_from_shared_structure_and_history(tmp_path):
    result = infer(CHILD, _world(tmp_path))
    assert result.parent_session_id == PARENT
    assert result.status == "inferred"
    assert result.boundary == PARENT_ONLY
    assert result.recordable


@pytest.mark.matrix("T-CPI-02")
def test_warm_cache_does_not_rescan_unrelated_transcripts(tmp_path):
    env = _world(tmp_path)
    unrelated = "30000000-0000-4000-8000-000000000001"
    _write(
        Path(env["CLAUDE_CONFIG_DIR"]),
        unrelated,
        [
            _record(
                unrelated,
                "40000000-0000-4000-8000-000000000001",
                None,
                "user",
                "2026-01-01T00:00:00Z",
            )
        ],
    )
    cold = infer(CHILD, env)
    warm = infer(CHILD, env)
    assert cold.work.superficial_bytes > 0
    assert warm.work.superficial_bytes == 0
    assert warm.work.deep_files == 2
    assert warm.work.cache_hits == 2


@pytest.mark.matrix("T-CPI-03")
def test_cache_never_contains_message_content(tmp_path):
    env = _world(tmp_path)
    infer(CHILD, env)
    cache = Path(env["XDG_CACHE_HOME"])
    assert "SECRET-CONTENT-CANARY" not in "".join(
        p.read_text() for p in cache.rglob("*.json")
    )


@pytest.mark.matrix("T-CPI-04")
def test_system_only_overlap_is_insufficient(tmp_path):
    env = _world(tmp_path)
    root = Path(env["CLAUDE_CONFIG_DIR"])
    _write(root, CHILD, [_record(CHILD, ROOT, None, "system", "2026-01-01T00:00:00Z")])
    result = infer(CHILD, env)
    assert result.parent_session_id is None
    assert result.status == "insufficient_evidence"


@pytest.mark.matrix("T-CPI-05")
def test_same_boundary_older_candidates_are_ambiguous(tmp_path):
    env = _world(tmp_path)
    sibling = "20000000-0000-4000-8000-000000000003"
    root = Path(env["CLAUDE_CONFIG_DIR"])
    parent_rows = [
        json.loads(x)
        for x in (root / "projects/-repo" / f"{PARENT}.jsonl").read_text().splitlines()
    ]
    _write(root, sibling, [dict(item, sessionId=sibling) for item in parent_rows])
    with (root / "history.jsonl").open("a") as stream:
        stream.write(json.dumps({"sessionId": sibling, "timestamp": 1500}) + "\n")
    result = infer(CHILD, env)
    assert result.status == "ambiguous"
    assert result.parent_session_id is None


@pytest.mark.matrix("T-CPI-10")
def test_bulk_analysis_reuses_one_corpus_and_each_pair(tmp_path, monkeypatch):
    env = _world(tmp_path)
    from agent_fork import claude_lineage_inference as inference

    parsed: list[Path] = []
    original = inference.deep_parse

    def observed(path, limits, work):
        parsed.append(path)
        return original(path, limits, work)

    monkeypatch.setattr(inference, "deep_parse", observed)
    corpus = ClaudeLineageCorpus(env)
    results = corpus.infer_many([PARENT, CHILD])

    assert [result.session_id for result in results] == [PARENT, CHILD]
    assert corpus.work.discovery_passes == 1
    assert corpus.work.history_passes == 1
    assert corpus.work.candidate_comparisons == 1
    assert len(parsed) == len(set(parsed)) == 2


def _transcript(nodes: dict[str, Node], session_id: str) -> Transcript:
    return Transcript(session_id, Path(f"/{session_id}"), nodes, None, session_id)


@pytest.mark.matrix("T-CPI-11")
def test_shared_chain_is_iterative_and_linear_for_deep_reverse_ordered_graph():
    nodes: dict[str, Node] = {}
    parent = None
    for index in range(10_000):
        uid = f"{10_000 - index:08x}-0000-4000-8000-000000000000"
        nodes[uid] = Node(uid, parent, "user", f"{index:08d}")
        parent = uid
    work = Work()

    chain, boundary = _longest_shared_chain(
        _transcript(nodes, PARENT), _transcript(nodes, CHILD), work
    )

    assert len(chain) == 10_000
    assert boundary == parent
    assert work.graph_visits == 10_000
    assert work.graph_edges == 9_999
    assert work.winning_chain_nodes == 10_000


@pytest.mark.matrix("T-CPI-12")
def test_shared_chain_rejects_cycles_in_any_component():
    for self_cycle in (True, False):
        first = "10000000-0000-4000-8000-000000000010"
        second = "10000000-0000-4000-8000-000000000011"
        nodes = {
            first: Node(first, first if self_cycle else second, "user", None),
            second: Node(second, None if self_cycle else first, "assistant", None),
            ROOT: Node(ROOT, None, "user", None),
        }

        with pytest.raises(ValueError, match="cyclic Claude message ancestry"):
            _longest_shared_chain(
                _transcript(nodes, PARENT), _transcript(nodes, CHILD), Work()
            )


@pytest.mark.matrix("T-CPI-13")
def test_screen_decodes_escaped_top_level_uuid_without_false_negative(tmp_path):
    env = _world(tmp_path)
    path = Path(env["CLAUDE_CONFIG_DIR"]) / "projects/-repo" / f"{CHILD}.jsonl"
    encodings = (
        '{"uuid":"10000000-0000-4000-8000-00000000000\\u0031","type":"user"}',
        '{"u\\u0075id":"10000000-0000-4000-8000-000000000001","type":"user"}',
        '{"uuid":"\\u0031\\u0030\\u0030\\u0030\\u0030\\u0030\\u0030\\u0030-0000-4000-8000-000000000001","type":"user"}',
    )
    for index, encoded in enumerate(encodings):
        path.write_text(encoded + "\n")
        env["XDG_CACHE_HOME"] = str(tmp_path / f"cache-{index}")
        transcript = deep_parse(path, Limits(), Work())
        screen = _screen(path, env, Work())
        accepted = next(iter(transcript.nodes))

        assert not screen.always_candidate
        assert hashlib.sha256(accepted.encode()).hexdigest() in screen.hashes


@pytest.mark.matrix("T-CPI-14")
def test_screen_uncertainty_is_always_a_candidate(tmp_path):
    env = _world(tmp_path)
    path = Path(env["CLAUDE_CONFIG_DIR"]) / "projects/-repo" / f"{CHILD}.jsonl"
    path.write_bytes(b'{"uuid":"unterminated')
    work = Work()

    screen = _screen(path, env, work)

    assert screen.always_candidate
    assert work.screen_wildcards == 1


@pytest.mark.matrix("T-CPI-15")
def test_deep_parse_accepts_complete_final_record_without_newline(tmp_path):
    env = _world(tmp_path)
    path = Path(env["CLAUDE_CONFIG_DIR"]) / "projects/-repo" / f"{CHILD}.jsonl"
    row = _record(CHILD, ROOT, None, "user", "2026-01-01T00:00:00Z")
    encoded = json.dumps(row).encode()
    path.write_bytes(encoded)
    work = Work()

    transcript = deep_parse(path, Limits(), work)

    assert transcript.nodes[ROOT].kind == "user"
    assert work.records_decoded == 1
    assert work.deep_bytes == len(encoded)


@pytest.mark.matrix("T-CPI-16")
def test_deep_parse_ignores_truncated_final_record(tmp_path):
    env = _world(tmp_path)
    path = Path(env["CLAUDE_CONFIG_DIR"]) / "projects/-repo" / f"{CHILD}.jsonl"
    complete = json.dumps(
        _record(CHILD, ROOT, None, "user", "2026-01-01T00:00:00Z")
    ).encode()
    path.write_bytes(complete + b'\n{"uuid":')

    transcript = deep_parse(path, Limits(), Work())

    assert set(transcript.nodes) == {ROOT}


@pytest.mark.matrix("T-CPI-17")
def test_deep_parse_bounds_newline_terminated_record(tmp_path):
    env = _world(tmp_path)
    path = Path(env["CLAUDE_CONFIG_DIR"]) / "projects/-repo" / f"{CHILD}.jsonl"
    path.write_bytes(b"{}  \n")

    with pytest.raises(ValueError, match="record exceeds limit"):
        deep_parse(path, Limits(max_record_bytes=3), Work())


@pytest.mark.matrix("T-CPI-18")
def test_concurrent_cold_screen_cache_publication_is_atomic(tmp_path):
    env = _world(tmp_path)
    path = Path(env["CLAUDE_CONFIG_DIR"]) / "projects/-repo" / f"{CHILD}.jsonl"

    def run_screen(_):
        return _screen(path, env, Work())

    with ThreadPoolExecutor(max_workers=12) as pool:
        screens = list(pool.map(run_screen, range(12)))

    assert all(screen == screens[0] for screen in screens)
    cache = Path(env["XDG_CACHE_HOME"])
    shards = list(cache.rglob("*.json"))
    assert len(shards) == 1
    cache_document = json.loads(shards[0].read_text())
    assert cache_document["schema"] == "agent-fork.claude-lineage-screen"
    assert cache_document["version"] == 2
    assert stat.S_IMODE(shards[0].stat().st_mode) == 0o600
    assert not list(cache.rglob("*.tmp"))


@pytest.mark.matrix("T-CPI-19")
def test_cache_write_failure_does_not_fail_screening(tmp_path, monkeypatch):
    env = _world(tmp_path)
    path = Path(env["CLAUDE_CONFIG_DIR"]) / "projects/-repo" / f"{CHILD}.jsonl"
    from agent_fork import claude_lineage_inference as inference

    def fail_replace(source, destination):
        raise OSError("injected cache failure")

    monkeypatch.setattr(inference.os, "replace", fail_replace)
    work = Work()

    screen = _screen(path, env, work)

    assert screen.hashes
    assert work.cache_write_failures == 1
    assert not list(Path(env["XDG_CACHE_HOME"]).rglob("*.tmp"))


@pytest.mark.matrix("T-CPI-20")
def test_invalid_cache_schema_is_a_miss_and_rebuild(tmp_path):
    env = _world(tmp_path)
    path = Path(env["CLAUDE_CONFIG_DIR"]) / "projects/-repo" / f"{CHILD}.jsonl"
    _screen(path, env, Work())
    shard = next(Path(env["XDG_CACHE_HOME"]).rglob("*.json"))
    document = json.loads(shard.read_text())
    document["source"]["session_id"] = PARENT
    shard.write_text(json.dumps(document))
    work = Work()

    rebuilt = _screen(path, env, work)

    assert rebuilt.hashes
    assert work.cache_hits == 0
    assert work.cache_misses == 1
    assert work.superficial_bytes == path.stat().st_size
    assert json.loads(shard.read_text())["source"]["session_id"] == CHILD


@pytest.mark.matrix("T-CPI-21")
def test_valid_always_candidate_cache_forces_conservative_mode(tmp_path):
    env = _world(tmp_path)
    path = Path(env["CLAUDE_CONFIG_DIR"]) / "projects/-repo" / f"{CHILD}.jsonl"
    _screen(path, env, Work())
    shard = next(Path(env["XDG_CACHE_HOME"]).rglob("*.json"))
    document = json.loads(shard.read_text())
    document["mode"] = "always_candidate"
    shard.write_text(json.dumps(document))
    work = Work()

    cached = _screen(path, env, work)

    assert cached.always_candidate
    assert work.cache_hits == 1
    assert work.superficial_bytes == 0


@pytest.mark.matrix("T-CPI-22")
def test_discovery_never_follows_transcript_symlink_outside_root(tmp_path):
    env = _world(tmp_path)
    root = Path(env["CLAUDE_CONFIG_DIR"])
    outside = tmp_path / "outside-secret.jsonl"
    outside.write_text("OUTSIDE-CONTENT-CANARY")
    linked_id = "30000000-0000-4000-8000-000000000099"
    (root / "projects/-repo" / f"{linked_id}.jsonl").symlink_to(outside)
    work = Work()

    paths = discover(env, Limits(), work)

    assert linked_id not in {path.stem for path in paths}
    assert work.unsafe_skipped == 1


@pytest.mark.matrix("T-CPI-23")
def test_discovery_bounds_all_entries_not_only_valid_transcripts(tmp_path):
    env = _world(tmp_path)
    project = Path(env["CLAUDE_CONFIG_DIR"]) / "projects/-repo"
    for index in range(10):
        (project / f"invalid-{index}").write_text("x")

    with pytest.raises(ValueError, match="entry limit"):
        discover(env, Limits(max_entries=5), Work())


@pytest.mark.matrix("T-CPI-24")
def test_candidate_read_failure_makes_result_incomplete(tmp_path, monkeypatch):
    env = _world(tmp_path)
    corpus = ClaudeLineageCorpus(env)
    parent_path = corpus.by_id[PARENT]
    original = corpus.screen

    def fail_candidate(path):
        if path == parent_path:
            raise OSError("injected candidate race")
        return original(path)

    monkeypatch.setattr(corpus, "screen", fail_candidate)

    result = corpus.infer_one(CHILD)

    assert result.status == "incomplete"
    assert not result.recordable
    assert result.work.corpus_incomplete == 1


@pytest.mark.matrix("T-CPI-25")
def test_record_revalidation_rejects_changed_candidate_universe(tmp_path):
    env = _world(tmp_path)
    corpus = ClaudeLineageCorpus(env)
    result = corpus.infer_one(CHILD)
    new_session = "30000000-0000-4000-8000-000000000098"
    _write(
        Path(env["CLAUDE_CONFIG_DIR"]),
        new_session,
        [_record(new_session, ROOT, None, "user", "2026-01-01T00:00:00Z")],
    )

    assert result.recordable
    assert not corpus.evidence_stable(result)


@pytest.mark.matrix("T-CPI-26")
def test_history_skips_oversized_record_and_keeps_relevant_clocks(tmp_path):
    env = _world(tmp_path)
    history = Path(env["CLAUDE_CONFIG_DIR"]) / "history.jsonl"
    history.write_bytes(
        b'{"display":"'
        + b"x" * (1024 * 1024)
        + b'"}\n'
        + json.dumps({"sessionId": PARENT, "timestamp": 1000}).encode()
        + b"\n"
        + json.dumps({"sessionId": CHILD, "timestamp": 2000}).encode()
    )

    corpus = ClaudeLineageCorpus(env)
    result = corpus.infer_one(CHILD)

    assert result.parent_session_id == PARENT
    assert corpus.work.history_passes == 1
    assert corpus.work.history_oversized == 1
    assert corpus.work.history_records_seen == 3
    assert corpus.work.history_bytes == history.stat().st_size


@pytest.mark.matrix("T-CPI-27")
def test_history_retains_only_discovered_sessions_and_earliest_timestamp(tmp_path):
    env = _world(tmp_path)
    history = Path(env["CLAUDE_CONFIG_DIR"]) / "history.jsonl"
    unknown = "30000000-0000-4000-8000-000000000097"
    history.write_text(
        "\n".join(
            json.dumps(row)
            for row in (
                {"sessionId": PARENT, "timestamp": 2000},
                {"sessionId": PARENT, "timestamp": 1000},
                {"sessionId": unknown, "timestamp": 1},
            )
        )
    )

    corpus = ClaudeLineageCorpus(env)

    assert corpus.history == {PARENT: 1000}
    assert corpus.work.history_passes == 1
