import pytest
from scripts.check_matrix import parse_matrix

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
