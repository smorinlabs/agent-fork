import hashlib
from dataclasses import replace

import pytest

from agent_fork.lineage_inference_store import (
    InferenceRecord,
    add_inference,
    find_inference,
    inference_freshness,
    inference_path,
    remove_inference,
    update_index_freshness,
)


def _record(parent="parent"):
    return InferenceRecord(
        "child",
        parent,
        "inferred",
        "boundary",
        3,
        1,
        1,
        "2026-01-01T00:00:00Z",
        ("a", "b"),
    )


@pytest.mark.matrix("T-CPI-06")
def test_inference_store_round_trip_replace_and_remove(tmp_path):
    env = {"XDG_STATE_HOME": str(tmp_path)}
    add_inference(_record(), env=env)
    found = find_inference("child", env=env)
    assert found is not None and found.parent_session_id == "parent"
    add_inference(_record("replacement"), env=env)
    found = find_inference("child", env=env)
    assert found is not None and found.parent_session_id == "replacement"
    assert remove_inference("child", env=env)
    assert find_inference("child", env=env) is None
    assert inference_path(env).stat().st_mode & 0o777 == 0o600


@pytest.mark.matrix("T-CPI-28")
def test_explicit_index_refresh_marks_relevant_universe_stale(tmp_path):
    env = {
        "XDG_STATE_HOME": str(tmp_path / "state"),
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
    }
    source = tmp_path / "source.jsonl"
    source.write_text("{}\n")
    metadata = source.stat()
    raw = (
        f"{source.absolute()}:{metadata.st_dev}:{metadata.st_ino}:"
        f"{metadata.st_size}:{metadata.st_mtime_ns}"
    )
    record = replace(
        _record(),
        source_fingerprints=(f"{source}:{hashlib.sha256(raw.encode()).hexdigest()}",),
        analysis_index_generation="generation-1",
        candidate_universe_digest="universe-1",
    )

    update_index_freshness("child", "universe-1", "generation-1", env=env)
    assert inference_freshness(record, env=env) == "current_at_last_analysis"

    update_index_freshness("child", "universe-2", "generation-2", env=env)
    assert inference_freshness(record, env=env) == "stale_candidate_universe"
