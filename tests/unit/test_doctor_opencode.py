"""P09 — doctor's OpenCode row is bounded and escaped (tier U).

Matrix: docs/testing/TEST-MATRIX.md §G-CLI.
"""

import pytest


@pytest.mark.matrix("T-CLI-75")
def test_doctor_bounds_and_escapes_an_unselected_opencode(
    repo_scenario, tmp_path, monkeypatch
):
    """T-CLI-75 — a hanging or escape-printing `opencode` cannot hang doctor or
    reach the terminal raw, and stays optional for a Claude user."""
    import agent_fork.doctor as doctor

    world = repo_scenario()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "opencode"
    env = {**world.env, "PATH": f"{bin_dir}:{world.env['PATH']}"}
    monkeypatch.setattr(doctor, "DOCTOR_PROBE_TIMEOUT", 1)

    stub.write_text("#!/bin/sh\nsleep 5\n")
    stub.chmod(0o755)
    checks, _ = doctor.run_doctor(world.parent_path, env)
    row = next(check for check in checks if check.name == "OpenCode CLI")
    assert row.ok is True
    assert "timed out" in row.detail and "(optional)" in row.detail

    stub.write_text("#!/bin/sh\nprintf 'opencode \\033[31m2.2.7\\n'\n")
    checks, _ = doctor.run_doctor(world.parent_path, env)
    row = next(check for check in checks if check.name == "OpenCode CLI")
    assert "\x1b" not in row.detail
