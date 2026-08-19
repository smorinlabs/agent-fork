"""Tooling tests: scripts/sync_versions.py propagation, guards, and check mode."""

import json
import sys

import pytest
from scripts import sync_versions
from scripts.sync_versions import render_generic, render_json


def _canonical(data):
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _fake_repo(tmp_path, project_version, json_version, text_version):
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname = "demo"\nversion = "{project_version}"\n'
    )
    (tmp_path / "plugin.json").write_text(
        _canonical({"name": "demo", "version": json_version})
    )
    (tmp_path / "notes.md").write_text(
        f"prints `demo {text_version}`. <!-- x-release-please-version -->\n"
    )
    return tmp_path


def _point_script_at(monkeypatch, root):
    monkeypatch.setattr(sync_versions, "ROOT", root)
    monkeypatch.setattr(sync_versions, "JSON_SITES", {"plugin.json": ["version"]})
    monkeypatch.setattr(sync_versions, "GENERIC_SITES", {"notes.md": 1})


def test_render_json_rewrites_only_the_addressed_field(tmp_path):
    path = tmp_path / "plugin.json"
    path.write_text(_canonical({"name": "demo", "version": "1.0.0"}))
    assert render_json(path, ["version"], "2.0.0") == _canonical(
        {"name": "demo", "version": "2.0.0"}
    )


def test_render_json_handles_nested_and_list_jsonpaths(tmp_path):
    path = tmp_path / "marketplace.json"
    data = {
        "metadata": {"version": "1.0.0"},
        "plugins": [{"name": "demo", "version": "1.0.0"}],
    }
    path.write_text(_canonical(data))
    rendered = render_json(path, ["metadata.version", "plugins.0.version"], "2.0.0")
    assert json.loads(rendered) == {
        "metadata": {"version": "2.0.0"},
        "plugins": [{"name": "demo", "version": "2.0.0"}],
    }


def test_render_json_refuses_non_canonical_form(tmp_path):
    path = tmp_path / "plugin.json"
    path.write_text('{"name": "demo", "version": "1.0.0"}\n')  # one line, not 2-space
    with pytest.raises(SystemExit, match="not in canonical 2-space JSON form"):
        render_json(path, ["version"], "2.0.0")


def test_render_json_missing_jsonpath_is_a_hard_error(tmp_path):
    path = tmp_path / "plugin.json"
    path.write_text(_canonical({"name": "demo"}))
    with pytest.raises(KeyError, match="version"):
        render_json(path, ["version"], "2.0.0")


def test_render_generic_rewrites_semver_on_annotated_lines_only(tmp_path):
    path = tmp_path / "notes.md"
    path.write_text(
        "unrelated 0.9.9 stays\n"
        "prints `demo 1.0.0`. <!-- x-release-please-version -->\n"
    )
    assert render_generic(path, 1, "2.0.0") == (
        "unrelated 0.9.9 stays\n"
        "prints `demo 2.0.0`. <!-- x-release-please-version -->\n"
    )


def test_render_generic_wrong_annotation_count_is_a_hard_error(tmp_path):
    path = tmp_path / "notes.md"
    path.write_text("no annotation here 1.0.0\n")
    with pytest.raises(SystemExit, match="expected 1 'x-release-please-version'"):
        render_generic(path, 1, "2.0.0")


def test_render_generic_annotated_line_without_semver_is_a_hard_error(tmp_path):
    path = tmp_path / "notes.md"
    path.write_text("stale marker, no version <!-- x-release-please-version -->\n")
    with pytest.raises(SystemExit, match="line 1 has no semver"):
        render_generic(path, 1, "2.0.0")


def test_write_mode_repairs_stale_sites_idempotently(tmp_path, monkeypatch, capsys):
    root = _fake_repo(tmp_path, "2.0.0", "1.0.0", "1.5.0")
    _point_script_at(monkeypatch, root)
    monkeypatch.setattr(sys, "argv", ["sync_versions.py"])
    sync_versions.main()
    assert json.loads((root / "plugin.json").read_text())["version"] == "2.0.0"
    assert "`demo 2.0.0`" in (root / "notes.md").read_text()
    out = capsys.readouterr().out
    assert "synced plugin.json" in out and "synced notes.md" in out
    sync_versions.main()  # second run converges: nothing left to sync
    assert "synced" not in capsys.readouterr().out


def test_check_mode_with_no_drift_exits_zero_and_writes_nothing(tmp_path, monkeypatch):
    root = _fake_repo(tmp_path, "2.0.0", "2.0.0", "2.0.0")
    _point_script_at(monkeypatch, root)
    monkeypatch.setattr(sys, "argv", ["sync_versions.py", "--check"])
    before = {p.name: p.read_text() for p in root.iterdir()}
    sync_versions.main()  # returning without SystemExit is exit code 0
    assert {p.name: p.read_text() for p in root.iterdir()} == before


def test_check_mode_with_drift_exits_nonzero_names_files_writes_nothing(
    tmp_path, monkeypatch
):
    root = _fake_repo(tmp_path, "2.0.0", "1.0.0", "2.0.0")
    _point_script_at(monkeypatch, root)
    monkeypatch.setattr(sys, "argv", ["sync_versions.py", "--check"])
    before = {p.name: p.read_text() for p in root.iterdir()}
    with pytest.raises(SystemExit, match="version drift.*plugin.json") as excinfo:
        sync_versions.main()
    assert excinfo.value.code != 0
    assert {p.name: p.read_text() for p in root.iterdir()} == before
