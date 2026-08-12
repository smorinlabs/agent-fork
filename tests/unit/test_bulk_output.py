import os
import stat
from typing import cast

import pytest

from agent_fork.bulk_output import MAX_CANDIDATES, BulkSpool, compact_result


@pytest.mark.matrix("T-CPI-34")
def test_bulk_projection_caps_candidate_details_and_scalar_lengths():
    candidates = [
        {
            "session_id": f"candidate-{index}",
            "shared": index,
            "substantive": index,
            "boundary": "b",
            "older": True,
            "clocks": 1,
        }
        for index in range(1000)
    ]
    compact = compact_result(
        {
            "session_id": "x" * 10_000,
            "relationship": {"status": "ambiguous"},
            "candidates": candidates,
            "notices": ["n"] * 100,
            "recorded": False,
        }
    )

    assert compact["candidate_count"] == 1000
    assert len(cast(list[object], compact["candidates"])) == MAX_CANDIDATES
    assert compact["candidates_truncated"] is True
    assert len(cast(str, compact["session_id"])) == 512
    assert compact["notices_truncated"] is True


@pytest.mark.matrix("T-CPI-35")
def test_bulk_spool_is_private():
    with BulkSpool() as spool:
        mode = os.fstat(spool.stream.fileno()).st_mode
        assert stat.S_IMODE(mode) == 0o600
