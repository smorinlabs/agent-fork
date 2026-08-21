"""G-LOC — Worktree location (U-tier rows only; F rows land in Task 8).

Matrix: docs/testing/TEST-MATRIX.md §G-LOC.
"""

from pathlib import Path

import pytest


@pytest.mark.matrix("T-LOC-01")
def test_sibling_default_path_derivation(repo_scenario):
    """T-LOC-01 — sibling default path places the worktree at <repo>-<branch>.

    Given:  worktree_location=sibling (default)
    Expect: worktree placed at <repo>-<branch>
    Source: D5; RESEARCH §2.4
    """
    from agent_fork.location import derive_worktree_path

    root = repo_scenario("plain@main").parent_path
    path = derive_worktree_path(root, "fork/fix-auth", "fix-auth", "sibling")
    assert path == root.parent / f"{root.name}-fork-fix-auth"


@pytest.mark.matrix("T-LOC-02")
def test_central_location_uses_xdg_data_path(repo_scenario):
    """T-LOC-02 — central location places the worktree under the XDG data path.

    Given:  worktree_location=central
    Expect: worktree placed at ~/.local/share/agent-fork/worktrees/<repo>/<slug>
    Source: D5
    """
    from agent_fork.location import derive_worktree_path

    world = repo_scenario("plain@main")
    data = world.parent_path.parent / "data"
    path = derive_worktree_path(
        world.parent_path,
        "fork/fix-auth",
        "fix-auth",
        "central",
        xdg_data_home=data,
    )
    assert path == data / "agent-fork/worktrees" / world.parent_path.name / "fix-auth"


@pytest.mark.matrix("T-LOC-03")
def test_subdirectory_location(repo_scenario):
    """T-LOC-03 — subdirectory location places the worktree at <root>/.worktrees/<slug>.

    Given:  worktree_location=subdirectory
    Expect: worktree placed at <root>/.worktrees/<slug>
    Source: D5
    """
    from agent_fork.location import derive_worktree_path

    root = repo_scenario("plain@main").parent_path
    assert derive_worktree_path(root, "fork/topic", "topic", "subdirectory") == (
        root / ".worktrees/topic"
    )


@pytest.mark.matrix("T-LOC-04")
def test_path_template_placeholders_resolved_individually(repo_scenario):
    """T-LOC-04 — the path template resolves each supported placeholder.

    Given:  one templated worktree_location value using {repo-root},
            {repo-name}, {branch}, and {branch-escaped}
    Expect: {repo-root} -> parent dir of root, {repo-name} -> repo basename,
            {branch} -> fork branch slug, {branch-escaped} -> its escaped
            form, each asserted individually

    A11 amendment: {session-id} is no longer a renderable placeholder — no
    session ID exists when the destination is derived (D5/F4), and the
    `session_id` parameter this test used to pass was deleted along with it.
    Its rejection is covered separately by T-LOC-20.
    Source: D5; RESEARCH §2.4
    """
    from agent_fork.location import derive_worktree_path

    root = repo_scenario("plain@main").parent_path
    template = "{repo-root}/custom/{repo-name}/{branch}/{branch-escaped}"
    path = derive_worktree_path(root, "fork/fix-auth", "fix-auth", template)
    assert path == (
        root.parent / "custom" / root.name / "fork/fix-auth" / "fork-fix-auth"
    )


@pytest.mark.matrix("T-LOC-05")
def test_explicit_worktree_location_suppresses_mirror_parent_heuristic(repo_scenario):
    """T-LOC-05 — an explicit worktree_location value suppresses the mirror-parent
    heuristic.

    Given:  worktree_location explicitly set in config
    Expect: the mirror-parent heuristic is suppressed
    Source: D5
    """
    from agent_fork.config import resolve_config
    from agent_fork.location import derive_worktree_path

    world = repo_scenario("linked-worktree")
    data = world.parent_path.parent / "explicit-data"
    path = derive_worktree_path(
        world.repo_root,
        "fork/fix-auth",
        "fix-auth",
        "central",
        xdg_data_home=data,
        parent_path=world.parent_path,
        parent_is_linked=True,
        location_explicit=True,
    )
    assert path == data / "agent-fork/worktrees" / world.repo_root.name / "fix-auth"

    resolved = resolve_config(sources=({"worktree_location": "sibling"},))
    assert resolved.worktree_location_explicit is True
    explicit_sibling = derive_worktree_path(
        world.repo_root,
        "fork/fix-auth",
        "fix-auth",
        resolved.worktree_location,
        parent_path=world.parent_path,
        parent_is_linked=True,
        location_explicit=resolved.worktree_location_explicit,
    )
    assert explicit_sibling.parent == world.repo_root.parent
    assert explicit_sibling.parent != world.parent_path.parent


@pytest.mark.parametrize(
    ("base", "leaf", "expected"),
    [
        pytest.param(
            "base",
            None,
            "base/derived",
            id="T-LOC-08",
            marks=pytest.mark.matrix("T-LOC-08"),
        ),
        pytest.param(
            None,
            "Exact Name",
            "original/Exact Name",
            id="T-LOC-09",
            marks=pytest.mark.matrix("T-LOC-09"),
        ),
        pytest.param(
            "base",
            "Exact Name",
            "base/Exact Name",
            id="T-LOC-10",
            marks=pytest.mark.matrix("T-LOC-10"),
        ),
    ],
)
def test_partial_destination_composition(repo_scenario, base, leaf, expected):
    from agent_fork.location import compose_worktree_destination

    root = repo_scenario().parent_path.parent
    (root / "base").mkdir()
    derived = root / "original/derived"
    value = compose_worktree_destination(
        derived,
        invocation_cwd=root,
        base_dir=Path(base) if base else None,
        worktree_name=leaf,
    )
    assert value == root / expected


@pytest.mark.matrix("T-LOC-11")
def test_invalid_explicit_worktree_leaf_inventory(repo_scenario):
    from agent_fork.errors import PreconditionError
    from agent_fork.location import validate_worktree_name

    for value in ("", "   ", ".", "..", "a/b", "a\\b", "a\0b", "/absolute"):
        with pytest.raises(PreconditionError) as caught:
            validate_worktree_name(value)
        assert caught.value.code == "invalid_worktree_name"


@pytest.mark.matrix("T-LOC-14")
def test_template_destination_can_replace_parent_and_leaf(repo_scenario):
    from agent_fork.location import compose_worktree_destination, derive_worktree_path

    root = repo_scenario().parent_path
    base = root.parent / "base"
    base.mkdir()
    derived = derive_worktree_path(
        root, "fork/topic", "topic", "{repo-root}/custom/{branch}"
    )
    assert (
        compose_worktree_destination(
            derived, invocation_cwd=root, base_dir=base, worktree_name="leaf"
        )
        == base / "leaf"
    )


@pytest.mark.matrix("T-LOC-19")
def test_worktree_location_template_grammar_rejects_unsafe_field_forms(repo_scenario):
    """T-LOC-19 — the template grammar rejects everything but bare, allowed
    placeholder fields.

    Given:  an unknown field name, a positional/auto-numbered field, a
            conversion, a non-empty format spec, or an indexing subscript
    Expect: each is rejected via ConfigError before any rendering is
            attempted
    Source: A11 Gate-4 finding F5 — each of these renders successfully today
            and was found only by direct execution, not by reasoning about
            `str.format_map`'s documented behavior.
    """
    from agent_fork.config import ConfigError
    from agent_fork.location import derive_worktree_path

    root = repo_scenario("plain@main").parent_path
    for template in (
        "{bogus}/x",
        "{}/x",
        "{0}/x",
        "{repo-name!r}/x",
        "{repo-name:>10}",
        "{repo-root[0]}w",
    ):
        with pytest.raises(ConfigError) as caught:
            derive_worktree_path(root, "fork/x", "x", template)
        assert "invalid worktree location template" in str(caught.value)


@pytest.mark.matrix("T-LOC-20")
def test_worktree_location_session_id_permanently_rejected(repo_scenario):
    """T-LOC-20 — {session-id} is rejected with a message naming the key, the
    value, and the permanent (not deferred) reason.

    A8 — the only tracked work that would have made a session ID available
    at destination-derivation time — closed WILL NOT FIX on 2026-08-18,
    so this is a permanent contract, not a stopgap (outcome 7).
    """
    from agent_fork.config import ConfigError
    from agent_fork.location import derive_worktree_path

    root = repo_scenario("plain@main").parent_path
    for template in ("{session-id}/w", "~/worktrees/{session-id}"):
        with pytest.raises(ConfigError) as caught:
            derive_worktree_path(root, "fork/x", "x", template)
        message = str(caught.value)
        assert "session-id" in message
        assert "not supported" in message


@pytest.mark.matrix("T-LOC-21")
def test_worktree_location_template_rejects_unsafe_renders(repo_scenario):
    """T-LOC-21 — an empty render, a CWD-relative render, a `..`-escaping
    render, control characters, and an unresolvable `~user` form are all
    rejected — found only by direct execution (F5/F6), not by reasoning
    about the grammar alone.
    """
    from agent_fork.config import ConfigError
    from agent_fork.location import derive_worktree_path

    root = repo_scenario("plain@main").parent_path
    for template in (
        "",
        ".",
        "{repo-name}-wt",
        "{repo-name}/..",
        "{repo-root}/x\x00y",
        "~nosuchuser46201c1/{repo-name}",
    ):
        with pytest.raises(ConfigError) as caught:
            derive_worktree_path(root, "fork/x", "x", template)
        assert "invalid worktree location template" in str(caught.value)


@pytest.mark.matrix("T-LOC-24")
def test_worktree_location_unknown_placeholder_name_is_escaped_in_the_message(
    repo_scenario,
):
    """T-LOC-24 — PR #62 review finding: an unknown placeholder name is
    attacker/repo-controlled (parsed straight out of the TOML template) and
    reached the raised `ConfigError` unescaped, unlike every other
    diagnostic in this codebase (`ConfigFinding.render()`). A bidi control
    character embedded in the placeholder name must render as a printable
    escape, not the raw control character.
    """
    from agent_fork.config import ConfigError
    from agent_fork.location import derive_worktree_path

    root = repo_scenario("plain@main").parent_path
    template = "{repo-name}/{evil‮name}"

    with pytest.raises(ConfigError) as caught:
        derive_worktree_path(root, "fork/x", "x", template)
    message = str(caught.value)
    assert "‮" not in message
    assert "\\u202e" in message


@pytest.mark.matrix("T-LOC-23")
def test_worktree_location_empty_home_rejected_but_unset_home_falls_back(
    repo_scenario, monkeypatch
):
    """T-LOC-23 — Gate-6 second-pass finding: a *present but empty* `HOME`
    must be rejected the same as a relative one (it satisfies
    `Path.is_absolute()` while still anchoring to the filesystem root
    instead of a real home directory), matching `xdg.py`'s documented
    convention that an empty value counts as unset. A genuinely *absent*
    `HOME` is different — `Path.expanduser()` then falls back to the pwd
    database and must not raise.

    PR #62 review finding: the unset-`HOME` half previously relied on the
    test runner's own UID having a resolvable passwd entry — `pwd.getpwuid()`
    raises `KeyError` without one, which `derive_worktree_path()` converts to
    `ConfigError`, failing this test for a reason unrelated to the code under
    test on a runner image with no such entry. `pwd.getpwuid` is patched here
    so the assertion holds regardless of the runner.
    """
    import pwd

    from agent_fork.config import ConfigError
    from agent_fork.location import derive_worktree_path

    root = repo_scenario("plain@main").parent_path

    monkeypatch.setenv("HOME", "")
    with pytest.raises(ConfigError) as caught:
        derive_worktree_path(root, "fork/x", "x", "~/{repo-name}")
    assert "empty HOME" in str(caught.value)

    monkeypatch.delenv("HOME", raising=False)
    fake_entry = pwd.struct_passwd(
        ("user", "x", 0, 0, "", "/nonexistent-fallback-home", "/bin/sh")
    )
    monkeypatch.setattr("pwd.getpwuid", lambda uid: fake_entry)
    path = derive_worktree_path(root, "fork/x", "x", "~/{repo-name}")
    assert path.is_absolute()
    assert str(path).startswith("/nonexistent-fallback-home")


@pytest.mark.matrix("T-LOC-22")
def test_worktree_location_template_accepts_safe_renders(repo_scenario):
    """T-LOC-22 — every template the widened grammar accepts renders without
    raising: absolute literals, a leading {repo-root} field, and a bare `~/`
    home-relative prefix all pass.
    """
    from agent_fork.location import derive_worktree_path

    root = repo_scenario("plain@main").parent_path
    for template in (
        "{repo-root}/custom/{repo-name}",
        "/tmp/explicit/{repo-name}",
        "~/worktrees/{repo-name}",
    ):
        path = derive_worktree_path(root, "fork/x", "x", template)
        assert path.is_absolute()


@pytest.mark.matrix("T-LOC-18")
def test_worktree_name_rejects_control_characters():
    """A newline is legal in a POSIX filename but ambiguous in Git porcelain.

    Refusing it here reports the problem against the argument the caller
    passed, before any branch or worktree is created, instead of surfacing
    later as a verification failure that rolls a valid fork back. This is a
    guard rather than the fix: paths reaching Git by other routes, such as
    `--worktree-dir`, are handled by the NUL-delimited parser instead.
    """
    from agent_fork.errors import PreconditionError
    from agent_fork.location import validate_worktree_name

    for value in ("wt\nname", "wt\tname", "wt\rname", "wt\x00name", "wt\x7fname"):
        with pytest.raises(PreconditionError) as caught:
            validate_worktree_name(value)
        assert caught.value.code == "invalid_worktree_name"

    assert validate_worktree_name("ordinary-name") == "ordinary-name"
