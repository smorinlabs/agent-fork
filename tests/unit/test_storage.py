"""Unit tests for the shared atomic JSON writer."""

import json
import os
import stat

import pytest

from agent_fork.storage import atomic_write_json


def _mode(path):
    return stat.S_IMODE(os.stat(path).st_mode)


@pytest.mark.matrix("T-REG-09")
def test_atomic_write_json_round_trips(tmp_path):
    target = tmp_path / "store.json"
    atomic_write_json(target, {"version": 1, "items": []})
    assert json.loads(target.read_text()) == {"version": 1, "items": []}


@pytest.mark.matrix("T-REG-10")
def test_store_is_owner_only_even_under_a_restrictive_umask(tmp_path):
    """The explicit chmod is load-bearing, not redundant.

    ``NamedTemporaryFile`` only *requests* 0600; the process umask still masks
    it. Under ``umask 0777`` the file would land at 0000 — unreadable by its
    own owner — so the store must be chmod'ed back explicitly.
    """
    target = tmp_path / "store.json"
    previous = os.umask(0o777)
    try:
        atomic_write_json(target, {"version": 1})
    finally:
        os.umask(previous)
    assert _mode(target) == 0o600
    assert json.loads(target.read_text()) == {"version": 1}


@pytest.mark.matrix("T-REG-11")
def test_no_temporary_file_survives_a_successful_write(tmp_path):
    target = tmp_path / "store.json"
    atomic_write_json(target, {"version": 1})
    assert [p.name for p in tmp_path.iterdir()] == ["store.json"]


@pytest.mark.matrix("T-REG-12")
def test_temporary_file_is_not_left_behind_when_serialization_fails(tmp_path):
    """The temp file is created inside the try, so a dump failure cleans up."""

    class Unserializable:
        pass

    target = tmp_path / "store.json"
    with pytest.raises(TypeError):
        atomic_write_json(target, {"bad": Unserializable()})
    assert list(tmp_path.iterdir()) == []


@pytest.mark.matrix("T-REG-13")
def test_fsync_false_still_writes_the_document(tmp_path):
    target = tmp_path / "cache.json"
    atomic_write_json(target, {"cached": True}, fsync=False)
    assert json.loads(target.read_text()) == {"cached": True}
    assert _mode(target) == 0o600
