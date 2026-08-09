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
    groups, errors = parse_matrix(SAMPLE)
    assert errors == []
    assert groups["G-GRD"].status == "pending"
    assert groups["G-GRD"].rows["T-GRD-01"].row_status == "live"
    assert groups["G-GRD"].rows["T-GRD-01"].tier == "F"
    assert groups["G-GRD"].rows["T-GRD-99"].row_status == "tombstone"


def test_parse_matrix_duplicate_group_heading_is_schema_error():
    text = SAMPLE + (
        "\n## G-GRD — duplicate heading\n"
        "Status: pending\n\n"
        "| ID | Scenario | Axes | Tier | row_status | Source |\n"
        "|---|---|---|---|---|---|\n"
        "| T-GRD-50 | dup heading row | baseline | F | live | X |\n"
    )
    groups, errors = parse_matrix(text)
    assert any("SCHEMA" in e and "G-GRD" in e for e in errors)


def test_parse_matrix_duplicate_row_id_same_group_is_schema_error():
    text = (
        "## G-CFG — dup row same group\n"
        "Status: pending\n\n"
        "| ID | Scenario | Axes | Tier | row_status | Source |\n"
        "|---|---|---|---|---|---|\n"
        "| T-CFG-01 | first | baseline | U | live | A |\n"
        "| T-CFG-01 | dup | baseline | U | live | B |\n"
    )
    groups, errors = parse_matrix(text)
    assert any("SCHEMA" in e and "T-CFG-01" in e for e in errors)


def test_parse_matrix_duplicate_row_id_cross_group_is_schema_error():
    text = (
        "## G-CFG — group a\n"
        "Status: pending\n\n"
        "| ID | Scenario | Axes | Tier | row_status | Source |\n"
        "|---|---|---|---|---|---|\n"
        "| T-CFG-01 | first | baseline | U | live | A |\n"
        "\n"
        "## G-DET — group b\n"
        "Status: pending\n\n"
        "| ID | Scenario | Axes | Tier | row_status | Source |\n"
        "|---|---|---|---|---|---|\n"
        "| T-CFG-01 | second | baseline | U | live | B |\n"
    )
    groups, errors = parse_matrix(text)
    assert any("SCHEMA" in e and "T-CFG-01" in e for e in errors)


def test_parse_matrix_unrecognized_group_status_is_schema_error():
    text = (
        "## G-CFG — bad status\n"
        "Status: bogus\n\n"
        "| ID | Scenario | Axes | Tier | row_status | Source |\n"
        "|---|---|---|---|---|---|\n"
        "| T-CFG-01 | x | baseline | U | live | A |\n"
    )
    groups, errors = parse_matrix(text)
    assert any("SCHEMA" in e and "bogus" in e for e in errors)


def test_parse_matrix_unrecognized_row_status_is_schema_error():
    text = (
        "## G-CFG — bad row status\n"
        "Status: pending\n\n"
        "| ID | Scenario | Axes | Tier | row_status | Source |\n"
        "|---|---|---|---|---|---|\n"
        "| T-CFG-01 | x | baseline | U | bogus | A |\n"
    )
    groups, errors = parse_matrix(text)
    assert any("SCHEMA" in e and "bogus" in e for e in errors)


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


def test_collect_items_dumps_marker_count_and_param_id(tmp_path):
    (tmp_path / "tests" / "unit").mkdir(parents=True)
    (tmp_path / "tests" / "unit" / "test_x.py").write_text(
        "import pytest\n"
        "@pytest.mark.matrix('T-CFG-01')\n"
        "@pytest.mark.matrix('T-CFG-02')\n"
        "@pytest.mark.skip(reason='pending: T-CFG-01')\n"
        "def test_two_markers():\n    raise NotImplementedError\n"
        "\n"
        "@pytest.mark.parametrize('x', [pytest.param(1, id='T-CFG-99')])\n"
        "@pytest.mark.matrix('T-CFG-01')\n"
        "@pytest.mark.skip(reason='pending: T-CFG-01')\n"
        "def test_param_mismatch(x):\n    raise NotImplementedError\n"
    )
    from scripts.check_matrix import collect_items

    items = collect_items(tmp_path)
    two_marker_item = next(i for i in items if "test_two_markers" in i.nodeid)
    assert two_marker_item.marker_count == 2

    param_item = next(i for i in items if "test_param_mismatch" in i.nodeid)
    assert param_item.matrix_id == "T-CFG-01"
    assert param_item.param_id == "T-CFG-99"


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


def _item(
    mid,
    path="tests/unit/test_x.py",
    skip="pending: x",
    marker_count=1,
    param_id=None,
):
    return [
        Item(
            nodeid=f"{path}::t[{mid}]",
            path=path,
            matrix_id=mid,
            skip_reason=skip,
            marker_count=marker_count,
            param_id=param_id,
        )
    ]


def test_check1_live_cell_without_item_fails():
    findings = run_checks(_group("G-CFG", "pending", [_row("T-CFG-01")]), [], TIER_DIRS)
    assert any("CHECK1" in f and "T-CFG-01" in f for f in findings)


def test_check3_single_experiment_present_names_other_five_by_default():
    groups = _group("G-EXP", "pending", [_row("T-EXP-04", status="retired", tier="R")])
    items = _item(
        "T-EXP-04",
        path="tests/live/test_exp.py",
        skip="retired: T-EXP-04 until v1.1 (A8)",
    )
    findings = run_checks(groups, items, TIER_DIRS)
    missing = [f for f in findings if "CHECK3" in f and "missing" in f]
    assert len(missing) == 5
    for eid in ("T-EXP-01", "T-EXP-02", "T-EXP-03", "T-EXP-05", "T-EXP-06"):
        assert any(eid in f for f in missing)


def test_check2_retired_and_requires_real_cli_skips_are_exempt():
    groups = _group("G-EXP", "done", [_row("T-EXP-04", status="retired", tier="R")])
    items = _item(
        "T-EXP-04",
        path="tests/live/test_exp.py",
        skip="retired: T-EXP-04 until v1.1 (A8)",
    )
    assert run_checks(groups, items, TIER_DIRS, enforce_experiments=False) == []


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


def test_check3_zero_experiments_present_names_all_six_missing():
    groups = _group("G-EXP", "pending", [])
    findings = run_checks(groups, [], TIER_DIRS)
    for exp_id in (
        "T-EXP-01",
        "T-EXP-02",
        "T-EXP-03",
        "T-EXP-04",
        "T-EXP-05",
        "T-EXP-06",
    ):
        assert any("CHECK3" in f and exp_id in f for f in findings)


def test_check2_pending_group_retired_reason_on_live_row_fails():
    groups = _group("G-CFG", "pending", [_row("T-CFG-01", status="live")])
    items = _item("T-CFG-01", skip="retired: T-CFG-01 stale reason")
    findings = run_checks(groups, items, TIER_DIRS)
    assert any("CHECK2" in f and "T-CFG-01" in f for f in findings)


def test_check2_pending_group_genuinely_retired_row_is_exempt():
    groups = _group("G-CFG", "pending", [_row("T-CFG-02", status="retired")])
    items = _item("T-CFG-02", skip="retired: T-CFG-02 stale reason")
    findings = run_checks(groups, items, TIER_DIRS)
    assert not any("CHECK2" in f for f in findings)


def test_check_two_matrix_markers_on_one_item_fails():
    groups = _group("G-CFG", "pending", [_row("T-CFG-01")])
    items = _item("T-CFG-01", marker_count=2)
    findings = run_checks(groups, items, TIER_DIRS)
    assert any("T-CFG-01" in f for f in findings)


def test_check_param_id_mismatch_with_marker_fails():
    groups = _group("G-CFG", "pending", [_row("T-CFG-01")])
    items = _item("T-CFG-01", param_id="T-CFG-99")
    findings = run_checks(groups, items, TIER_DIRS)
    assert any("T-CFG-99" in f and "T-CFG-01" in f for f in findings)


def test_check_retired_row_with_no_collected_item_fails():
    groups = _group("G-EXP", "pending", [_row("T-EXP-04", status="retired", tier="R")])
    findings = run_checks(groups, [], TIER_DIRS)
    assert any("T-EXP-04" in f for f in findings)


def test_check_retired_row_unskipped_item_fails():
    groups = _group("G-EXP", "pending", [_row("T-EXP-04", status="retired", tier="R")])
    items = _item("T-EXP-04", path="tests/live/test_exp.py", skip=None)
    findings = run_checks(groups, items, TIER_DIRS)
    assert any("T-EXP-04" in f for f in findings)


def test_check_retired_row_wrong_reason_prefix_fails():
    groups = _group("G-EXP", "pending", [_row("T-EXP-04", status="retired", tier="R")])
    items = _item("T-EXP-04", path="tests/live/test_exp.py", skip="pending: T-EXP-04")
    findings = run_checks(groups, items, TIER_DIRS)
    assert any("T-EXP-04" in f for f in findings)
