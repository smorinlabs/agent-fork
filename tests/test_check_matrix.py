import pytest
from scripts.check_matrix import Group, Item, Row, parse_matrix, run_checks

SAMPLE = """\
## G-GRD — fork guards
Status: pending
Varying axes: none

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
| T-GRD-01 | branch exists refuses | baseline | F | live | REQ-19 |
| T-GRD-99 | old thing | baseline | F | tombstone | A7 |
"""


def test_parse_matrix_reads_groups_rows_and_statuses():
    groups = parse_matrix(SAMPLE)
    assert groups["G-GRD"].status == "pending"
    assert groups["G-GRD"].rows["T-GRD-01"].row_status == "live"
    assert groups["G-GRD"].rows["T-GRD-01"].tier == "F"
    assert groups["G-GRD"].rows["T-GRD-99"].row_status == "tombstone"


def test_collect_items_reads_marker_and_skip_reason(tmp_path):
    (tmp_path / "tests" / "unit").mkdir(parents=True)
    (tmp_path / "tests" / "unit" / "test_x.py").write_text(
        "import pytest\n"
        "@pytest.mark.matrix('T-CFG-01')\n"
        "@pytest.mark.skip(reason='pending: T-CFG-01')\n"
        "def test_a():\n    raise NotImplementedError\n"
    )
    from scripts.check_matrix import collect_items

    items = collect_items(tmp_path)
    assert items[0].matrix_id == "T-CFG-01"
    assert items[0].skip_reason is not None
    assert items[0].skip_reason.startswith("pending:")


def test_collect_items_raises_on_broken_tree(tmp_path):
    (tmp_path / "tests" / "unit").mkdir(parents=True)
    (tmp_path / "tests" / "unit" / "test_broken.py").write_text(
        "def test_a(\n    this is not valid python\n"
    )
    from scripts.check_matrix import CollectionError, collect_items

    with pytest.raises(CollectionError):
        collect_items(tmp_path)


TIER_DIRS = {
    "tests/unit": "U",
    "tests/pipeline": "F",
    "tests/cli": "C",
    "tests/live": "R",
    "tests/fixtures": "F",
}


def _group(gid, status, rows):
    return {gid: Group(status=status, rows={r.row_id: r for r in rows})}


def _row(rid, status="live", tier="U"):
    return Row(row_id=rid, row_status=status, tier=tier)


def _item(mid, path="tests/unit/test_x.py", skip="pending: x"):
    return [
        Item(nodeid=f"{path}::t[{mid}]", path=path, matrix_id=mid, skip_reason=skip)
    ]


def test_check1_live_cell_without_item_fails():
    findings = run_checks(_group("G-CFG", "pending", [_row("T-CFG-01")]), [], TIER_DIRS)
    assert any("CHECK1" in f and "T-CFG-01" in f for f in findings)


def test_check2_retired_and_requires_real_cli_skips_are_exempt():
    groups = _group("G-EXP", "done", [_row("T-EXP-04", status="retired", tier="R")])
    items = _item(
        "T-EXP-04",
        path="tests/live/test_exp.py",
        skip="retired: T-EXP-04 until v1.1 (A8)",
    )
    assert run_checks(groups, items, TIER_DIRS) == []


def test_check1_item_citing_unknown_id_fails():
    groups = _group("G-CFG", "pending", [_row("T-CFG-01")])
    items = _item("T-CFG-01") + [
        Item(
            nodeid="tests/unit/test_x.py::t[T-CFG-99]",
            path="tests/unit/test_x.py",
            matrix_id="T-CFG-99",
            skip_reason="pending: x",
        )
    ]
    findings = run_checks(groups, items, TIER_DIRS)
    assert any("CHECK1" in f and "T-CFG-99" in f for f in findings)


def test_check2_pending_group_with_unskipped_stub_fails():
    groups = _group("G-CFG", "pending", [_row("T-CFG-01")])
    items = _item("T-CFG-01", skip=None)
    findings = run_checks(groups, items, TIER_DIRS)
    assert any("CHECK2" in f and "T-CFG-01" in f for f in findings)


def test_check2_tdd_group_with_lifecycle_skip_fails():
    groups = _group("G-CFG", "tdd", [_row("T-CFG-01")])
    items = _item("T-CFG-01", skip="pending: T-CFG-01")
    findings = run_checks(groups, items, TIER_DIRS)
    assert any("CHECK2" in f and "T-CFG-01" in f for f in findings)


def test_check3_experiments_e1_to_e6_all_mapped():
    groups = _group(
        "G-EXP",
        "pending",
        [
            _row("T-EXP-01", status="live", tier="R"),
            _row("T-EXP-02", status="live", tier="R"),
            _row("T-EXP-03", status="live", tier="R"),
            _row("T-EXP-04", status="retired", tier="R"),
            _row("T-EXP-05", status="n/a", tier="n/a"),
        ],
    )
    items = (
        _item("T-EXP-01", path="tests/live/test_exp.py", skip="pending: T-EXP-01")
        + _item("T-EXP-02", path="tests/live/test_exp.py", skip="pending: T-EXP-02")
        + _item("T-EXP-03", path="tests/live/test_exp.py", skip="pending: T-EXP-03")
        + _item(
            "T-EXP-04",
            path="tests/live/test_exp.py",
            skip="retired: T-EXP-04 until v1.1 (A8)",
        )
    )
    findings = run_checks(groups, items, TIER_DIRS)
    assert any("CHECK3" in f and "T-EXP-06" in f for f in findings)


def test_check4_tombstone_cited_by_item_fails():
    groups = _group(
        "G-GRD", "pending", [_row("T-GRD-99", status="tombstone", tier="F")]
    )
    items = _item("T-GRD-99", path="tests/pipeline/test_grd.py", skip="pending: x")
    findings = run_checks(groups, items, TIER_DIRS)
    assert any("CHECK4" in f and "T-GRD-99" in f for f in findings)


def test_check4_na_cell_cited_by_item_fails():
    groups = _group("G-GRD", "pending", [_row("T-GRD-50", status="n/a", tier="n/a")])
    items = _item("T-GRD-50", path="tests/pipeline/test_grd.py", skip="pending: x")
    findings = run_checks(groups, items, TIER_DIRS)
    assert any("CHECK4" in f and "T-GRD-50" in f for f in findings)


def test_check5_item_directory_mismatches_row_tier_fails():
    groups = _group("G-GRD", "pending", [_row("T-GRD-01", status="live", tier="F")])
    items = _item("T-GRD-01", path="tests/unit/test_grd.py", skip="pending: T-GRD-01")
    findings = run_checks(groups, items, TIER_DIRS)
    assert any("CHECK5" in f and "T-GRD-01" in f for f in findings)
