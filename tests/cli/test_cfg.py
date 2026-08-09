"""G-CFG — Config resolution (tier C rows only; U rows in tests/unit/, F rows in
tests/pipeline/).

Matrix: docs/testing/TEST-MATRIX.md §G-CFG.
"""

import pytest


@pytest.mark.matrix("T-CFG-12")
@pytest.mark.skip(reason="pending: T-CFG-12")
def test_config_set_then_validate_round_trips(repo_scenario):
    """T-CFG-12 — `config set` followed by `config validate` round-trips a written
    value.

    Given:  `config set <key> <value>` followed by `config validate`
    Expect: the written value round-trips through the CLI
    Source: REQUIREMENTS §3.2
    """
    raise NotImplementedError
