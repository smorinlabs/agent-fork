import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from agent_fork.lineage_inference_store import (
    MAX_SOURCE_FINGERPRINTS,
    InferenceRecord,
    _legacy_index_freshness_path,
    add_inference,
    assess_inference,
    find_inference,
    index_freshness_path,
    inference_freshness,
    inference_path,
    remove_index_freshness,
    remove_inference,
    update_index_freshness,
)
from agent_fork.registry import registry_lock


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


def _fp(path: Path) -> str:
    stat = path.stat()
    raw = (
        f"{path.absolute()}:{stat.st_dev}:{stat.st_ino}:"
        f"{stat.st_size}:{stat.st_mtime_ns}"
    )
    return f"{path}:{hashlib.sha256(raw.encode()).hexdigest()}"


def _env(tmp_path):
    return {
        "XDG_STATE_HOME": str(tmp_path / "state"),
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
    }


@pytest.mark.matrix("T-CPI-40")
def test_assess_inference_full_status_evidence_table(tmp_path):
    env = _env(tmp_path)
    target = tmp_path / "child.jsonl"
    target.write_text("{}\n")
    parent = tmp_path / "parent.jsonl"
    parent.write_text("{}\n")
    base = InferenceRecord(
        "child",
        "parent",
        "inferred",
        "boundary",
        3,
        1,
        1,
        "2026-01-01T00:00:00Z",
        (_fp(target), _fp(parent)),
        "generation-1",
        "universe-1",
    )

    update_index_freshness("child", "universe-1", "generation-1", env=env)
    result = assess_inference(base, env=env)
    assert (result.status, result.evidence) == ("current_at_last_analysis", "current")
    assert result.satisfies_strict_parent is True
    assert result.displayable is True
    assert result.changed_sources == ()

    update_index_freshness("child", "universe-2", "generation-2", env=env)
    result = assess_inference(base, env=env)
    assert (result.status, result.evidence) == (
        "stale_candidate_universe",
        "last_known_good",
    )
    assert result.satisfies_strict_parent is False
    assert result.displayable is True

    unknown = replace(base, analysis_index_generation="")
    result = assess_inference(unknown, env=env)
    assert (result.status, result.evidence) == ("freshness_unknown", "unknown")
    assert result.satisfies_strict_parent is False
    assert result.displayable is True

    superseded = replace(base, algorithm_version=2)
    result = assess_inference(superseded, env=env)
    assert (result.status, result.evidence) == ("stale_algorithm", "superseded")
    assert result.satisfies_strict_parent is False
    assert result.displayable is False

    # re-establish currency (universe was bumped above) before mutating files,
    # so what follows tests only the source-fingerprint mismatch in isolation.
    update_index_freshness("child", "universe-1", "generation-1", env=env)
    target.write_text("{}\nmore\n")
    result = assess_inference(base, env=env)
    assert (result.status, result.evidence) == ("stale_sources", "last_known_good")
    assert result.changed_sources == ("target",)

    parent.write_text("{}\nmore\n")
    result = assess_inference(base, env=env)
    assert result.status == "stale_sources"
    assert result.changed_sources == ("parent", "target")


@pytest.mark.matrix("T-CPI-41")
def test_assess_inference_deleted_index_at_both_locations_is_unknown(tmp_path):
    env = _env(tmp_path)
    target = tmp_path / "child.jsonl"
    target.write_text("{}\n")
    record = InferenceRecord(
        "child",
        "parent",
        "inferred",
        "boundary",
        3,
        1,
        1,
        "2026-01-01T00:00:00Z",
        (_fp(target),),
        "generation-1",
        "universe-1",
    )
    update_index_freshness("child", "universe-1", "generation-1", env=env)
    assert assess_inference(record, env=env).status == "current_at_last_analysis"

    index_freshness_path(env).unlink()
    result = assess_inference(record, env=env)
    assert result.status == "freshness_unknown"
    assert result.satisfies_strict_parent is False


@pytest.mark.matrix("T-CPI-42")
def test_assess_inference_missing_or_invalid_index_entry(tmp_path):
    env = _env(tmp_path)
    target = tmp_path / "child.jsonl"
    target.write_text("{}\n")
    record = InferenceRecord(
        "child",
        "parent",
        "inferred",
        "boundary",
        3,
        1,
        1,
        "2026-01-01T00:00:00Z",
        (_fp(target),),
        "generation-1",
        "universe-1",
    )

    # no legacy file, no state entry for this child
    assert assess_inference(record, env=env).status == "freshness_unknown"

    # state index present but for a different child only
    update_index_freshness("someone-else", "universe-9", "generation-9", env=env)
    assert assess_inference(record, env=env).status == "freshness_unknown"

    # invalid state index: symlinked
    path = index_freshness_path(env)
    real = path.with_name("real-index.json")
    path.replace(real)
    path.symlink_to(real)
    assert assess_inference(record, env=env).status == "freshness_unknown"
    path.unlink()
    real.replace(path)

    # invalid state index: oversized
    path.write_text("x" * (8 * 1024 * 1024 + 1))
    assert assess_inference(record, env=env).status == "freshness_unknown"


@pytest.mark.matrix("T-CPI-43")
def test_assess_inference_stale_sources_preserves_record(tmp_path):
    env = _env(tmp_path)
    target = tmp_path / "child.jsonl"
    target.write_text("{}\n")
    record = InferenceRecord(
        "child",
        "parent",
        "inferred",
        "boundary",
        3,
        1,
        1,
        "2026-01-01T00:00:00Z",
        (_fp(target),),
        "generation-1",
        "universe-1",
    )
    update_index_freshness("child", "universe-1", "generation-1", env=env)
    target.write_text("{}\n\n")
    result = assess_inference(record, env=env)
    assert result.status == "stale_sources"
    assert result.changed_sources == ("target",)
    assert record.parent_session_id == "parent"


@pytest.mark.matrix("T-CPI-45")
def test_decode_rejects_oversized_fingerprint_list(tmp_path):
    env = {"XDG_STATE_HOME": str(tmp_path)}
    record = replace(
        _record(),
        source_fingerprints=tuple(
            f"f{i}:{'0' * 64}" for i in range(MAX_SOURCE_FINGERPRINTS + 1)
        ),
    )
    add_inference(record, env=env)
    with pytest.raises(ValueError):
        find_inference("child", env=env)


@pytest.mark.matrix("T-CPI-50")
def test_index_freshness_path_relocated_and_legacy_key_removed(tmp_path):
    env = _env(tmp_path)
    assert str(index_freshness_path(env)).startswith(str(tmp_path / "state"))
    assert str(_legacy_index_freshness_path(env)).startswith(str(tmp_path / "cache"))

    legacy = _legacy_index_freshness_path(env)
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(
        json.dumps(
            {
                "version": 1,
                "targets": {
                    "child": {
                        "candidate_universe_digest": "legacy-universe",
                        "analysis_index_generation": "legacy-gen",
                    }
                },
            }
        )
    )

    update_index_freshness("child", "universe-1", "generation-1", env=env)
    assert index_freshness_path(env).exists()
    legacy_document = json.loads(legacy.read_text())
    assert legacy_document["targets"] == {}
    assert legacy.exists()


@pytest.mark.matrix("T-CPI-51")
def test_assess_inference_falls_back_to_legacy_when_state_absent(tmp_path):
    env = _env(tmp_path)
    target = tmp_path / "child.jsonl"
    target.write_text("{}\n")
    record = InferenceRecord(
        "child",
        "parent",
        "inferred",
        "boundary",
        3,
        1,
        1,
        "2026-01-01T00:00:00Z",
        (_fp(target),),
        "generation-1",
        "universe-1",
    )
    legacy = _legacy_index_freshness_path(env)
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(
        json.dumps(
            {
                "version": 1,
                "targets": {
                    "child": {
                        "candidate_universe_digest": "universe-1",
                        "analysis_index_generation": "generation-1",
                    }
                },
            }
        )
    )
    assert not index_freshness_path(env).exists()
    result = assess_inference(record, env=env)
    assert result.status == "current_at_last_analysis"


@pytest.mark.matrix("T-CPI-53")
def test_assess_inference_per_child_migration_does_not_mass_invalidate(tmp_path):
    env = _env(tmp_path)
    target = tmp_path / "child.jsonl"
    target.write_text("{}\n")
    record = InferenceRecord(
        "other-child",
        "parent",
        "inferred",
        "boundary",
        3,
        1,
        1,
        "2026-01-01T00:00:00Z",
        (_fp(target),),
        "generation-1",
        "universe-1",
    )
    legacy = _legacy_index_freshness_path(env)
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(
        json.dumps(
            {
                "version": 1,
                "targets": {
                    "other-child": {
                        "candidate_universe_digest": "universe-1",
                        "analysis_index_generation": "generation-1",
                    }
                },
            }
        )
    )

    # re-inferring an unrelated child creates the state file, but with no
    # entry for "other-child" -- it must not become unreadable.
    update_index_freshness("some-other-session", "universe-x", "generation-x", env=env)
    assert index_freshness_path(env).exists()

    result = assess_inference(record, env=env)
    assert result.status == "current_at_last_analysis"

    # a structurally invalid state file still yields freshness_unknown,
    # without ever consulting the legacy path.
    index_freshness_path(env).write_text("not json")
    result = assess_inference(record, env=env)
    assert result.status == "freshness_unknown"


@pytest.mark.matrix("T-CPI-54")
def test_update_index_freshness_removes_only_this_childs_legacy_key(tmp_path):
    env = _env(tmp_path)
    legacy = _legacy_index_freshness_path(env)
    legacy.parent.mkdir(parents=True, exist_ok=True)
    other_entry = {
        "candidate_universe_digest": "universe-other",
        "analysis_index_generation": "generation-other",
    }
    legacy.write_text(
        json.dumps(
            {
                "version": 1,
                "targets": {
                    "child": {
                        "candidate_universe_digest": "universe-1",
                        "analysis_index_generation": "generation-1",
                    },
                    "sibling": other_entry,
                },
            }
        )
    )

    update_index_freshness("child", "universe-2", "generation-2", env=env)

    legacy_document = json.loads(legacy.read_text())
    assert legacy_document["targets"] == {"sibling": other_entry}
    assert legacy.exists()

    # popping the last remaining key rewrites an empty targets dict, not unlink
    update_index_freshness("sibling", "universe-3", "generation-3", env=env)
    # sibling's legacy entry survives until *sibling* itself is recorded via
    # the state path -- record it now to exercise the empty-targets rewrite.
    legacy_document = json.loads(legacy.read_text())
    assert legacy.exists()
    assert isinstance(legacy_document["targets"], dict)


@pytest.mark.matrix("T-CPI-55")
def test_duplicate_entry_in_both_locations(tmp_path):
    env = _env(tmp_path)
    target = tmp_path / "child.jsonl"
    target.write_text("{}\n")
    record = InferenceRecord(
        "child",
        "parent",
        "inferred",
        "boundary",
        3,
        1,
        1,
        "2026-01-01T00:00:00Z",
        (_fp(target),),
        "generation-1",
        "universe-legacy",
    )
    legacy = _legacy_index_freshness_path(env)
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(
        json.dumps(
            {
                "version": 1,
                "targets": {
                    "child": {
                        "candidate_universe_digest": "universe-legacy",
                        "analysis_index_generation": "generation-legacy",
                    }
                },
            }
        )
    )
    update_index_freshness("child", "universe-state", "generation-state", env=env)

    # state-path entry (universe-state) wins over legacy (universe-legacy)
    result = assess_inference(record, env=env)
    assert result.status == "stale_candidate_universe"

    assert remove_index_freshness("child", env=env) is True
    state_document = json.loads(index_freshness_path(env).read_text())
    assert "child" not in state_document["targets"]
    legacy_document = json.loads(legacy.read_text())
    assert "child" not in legacy_document["targets"]


@pytest.mark.matrix("T-CPI-56")
def test_lock_ordering_state_before_legacy(tmp_path, monkeypatch):
    env = _env(tmp_path)
    order: list[str] = []
    original_lock = registry_lock

    def recording_lock(path, *args, **kwargs):
        order.append(str(path))
        return original_lock(path, *args, **kwargs)

    import agent_fork.lineage_inference_store as store

    monkeypatch.setattr(store, "registry_lock", recording_lock)

    legacy = _legacy_index_freshness_path(env)
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(
        json.dumps(
            {
                "version": 1,
                "targets": {
                    "child": {
                        "candidate_universe_digest": "u",
                        "analysis_index_generation": "g",
                    }
                },
            }
        )
    )

    order.clear()
    update_index_freshness("child", "universe-1", "generation-1", env=env)
    state_path = str(index_freshness_path(env))
    legacy_path = str(legacy)
    assert order.index(state_path) < order.index(legacy_path)

    order.clear()
    remove_index_freshness("child", env=env)
    assert order.index(state_path) < order.index(legacy_path)


@pytest.mark.matrix("T-CPI-44")
def test_remove_index_freshness_targeted_removal(tmp_path):
    env = _env(tmp_path)
    update_index_freshness("child", "universe-1", "generation-1", env=env)
    update_index_freshness("sibling", "universe-2", "generation-2", env=env)

    assert remove_index_freshness("missing", env=env) is False

    assert remove_index_freshness("child", env=env) is True
    document = json.loads(index_freshness_path(env).read_text())
    assert "child" not in document["targets"]
    assert "sibling" in document["targets"]
    assert not index_freshness_path(env).is_symlink()
    assert index_freshness_path(env).stat().st_mode & 0o777 == 0o600


@pytest.mark.matrix("T-CPI-52")
def test_remove_index_freshness_both_locations(tmp_path):
    env = _env(tmp_path)
    legacy = _legacy_index_freshness_path(env)
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(
        json.dumps(
            {
                "version": 1,
                "targets": {
                    "child": {
                        "candidate_universe_digest": "u",
                        "analysis_index_generation": "g",
                    }
                },
            }
        )
    )

    # only in legacy
    assert remove_index_freshness("child", env=env) is True
    assert "child" not in json.loads(legacy.read_text())["targets"]
    assert not index_freshness_path(env).exists()

    # present in both
    legacy.write_text(
        json.dumps(
            {
                "version": 1,
                "targets": {
                    "child": {
                        "candidate_universe_digest": "u",
                        "analysis_index_generation": "g",
                    }
                },
            }
        )
    )
    update_index_freshness("child", "universe-2", "generation-2", env=env)
    # update_index_freshness already migrated the legacy entry away; recreate
    # it to prove removal acts on both when both are independently present.
    legacy.write_text(
        json.dumps(
            {
                "version": 1,
                "targets": {
                    "child": {
                        "candidate_universe_digest": "u",
                        "analysis_index_generation": "g",
                    }
                },
            }
        )
    )
    assert remove_index_freshness("child", env=env) is True
    assert "child" not in json.loads(index_freshness_path(env).read_text())["targets"]
    assert "child" not in json.loads(legacy.read_text())["targets"]
