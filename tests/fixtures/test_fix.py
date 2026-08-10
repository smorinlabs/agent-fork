"""G-FIX — Fixture layer (tier F, the declared exception living in tests/fixtures/).

Matrix: docs/testing/TEST-MATRIX.md §G-FIX.
"""

import os
import subprocess

import pytest


@pytest.mark.parametrize(
    "topology",
    [
        pytest.param(
            "plain@branch", id="T-FIX-01", marks=pytest.mark.matrix("T-FIX-01")
        ),
        pytest.param("plain@main", id="T-FIX-02", marks=pytest.mark.matrix("T-FIX-02")),
        pytest.param("detached", id="T-FIX-03", marks=pytest.mark.matrix("T-FIX-03")),
        pytest.param(
            "linked-worktree", id="T-FIX-04", marks=pytest.mark.matrix("T-FIX-04")
        ),
        pytest.param("bare@bare", id="T-FIX-05", marks=pytest.mark.matrix("T-FIX-05")),
        pytest.param("bare@wt", id="T-FIX-06", marks=pytest.mark.matrix("T-FIX-06")),
        pytest.param(
            "dot-bare@wt", id="T-FIX-07", marks=pytest.mark.matrix("T-FIX-07")
        ),
        pytest.param(
            "nested-bare", id="T-FIX-08", marks=pytest.mark.matrix("T-FIX-08")
        ),
        pytest.param(
            "unborn(plain)", id="T-FIX-09", marks=pytest.mark.matrix("T-FIX-09")
        ),
        pytest.param(
            "unborn(bare)", id="T-FIX-10", marks=pytest.mark.matrix("T-FIX-10")
        ),
    ],
)
def test_builder_matches_declared_spec(repo_scenario, topology):
    """Builder-vs-spec verification: each topology's constructor matches its
    declared spec (linked-worktree is built with a divergent, separately-dirty
    main checkout). Source: spec §6.3; RESEARCH §2.3.
    """
    world = repo_scenario(topology)
    parent = world.parent_path

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(parent), *args],
            env=world.env,
            capture_output=True,
            text=True,
        )

    assert parent == parent.resolve()
    assert world.repo_root == world.repo_root.resolve()
    assert git("rev-parse", "--git-dir").returncode == 0

    unborn = topology.startswith("unborn")
    head = git("rev-parse", "--verify", "HEAD^{commit}")
    assert head.returncode == (128 if unborn else 0)

    is_bare = git("rev-parse", "--is-bare-repository").stdout.strip() == "true"
    assert is_bare is (topology in {"bare@bare", "nested-bare", "unborn(bare)"})

    git_dir = git("rev-parse", "--git-dir").stdout.strip()
    common_dir = git("rev-parse", "--git-common-dir").stdout.strip()
    linked = topology in {"linked-worktree", "bare@wt", "dot-bare@wt"}
    assert (os.path.realpath(git_dir) != os.path.realpath(common_dir)) is linked

    if topology == "plain@main":
        assert git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "main"
    elif topology == "plain@branch":
        assert git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "feature"
    elif topology == "detached":
        assert git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "HEAD"
    elif topology == "linked-worktree":
        assert world.main_path is not None
        main_head = subprocess.run(
            ["git", "-C", str(world.main_path), "rev-parse", "HEAD"],
            env=world.env,
            stdout=subprocess.PIPE,
            check=True,
            text=True,
        ).stdout.strip()
        assert main_head != head.stdout.strip()
        assert (world.main_path / "tracked.txt").read_text() == "dirty main\n"
        assert (parent / "linked-only.txt").read_text() == "dirty linked\n"


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param("flip-byte", id="T-FIX-11", marks=pytest.mark.matrix("T-FIX-11")),
        pytest.param("chmod", id="T-FIX-12", marks=pytest.mark.matrix("T-FIX-12")),
        pytest.param(
            "retarget-symlink", id="T-FIX-13", marks=pytest.mark.matrix("T-FIX-13")
        ),
        pytest.param(
            "add-untracked", id="T-FIX-14", marks=pytest.mark.matrix("T-FIX-14")
        ),
        pytest.param(
            "update-index", id="T-FIX-15", marks=pytest.mark.matrix("T-FIX-15")
        ),
    ],
)
def test_oracle_mutation_detected(repo_scenario, mutation):
    """Oracle mutation: an out-of-band change (byte flip, chmod, symlink retarget,
    added untracked file, or an update-index edit) is caught by exactly the
    corresponding oracle (manifest+hash, lstat mode, symlink target, manifest,
    or index-comparison) on exactly that entry. Source: spec §5; spec §6.5.
    """
    world = repo_scenario("plain@main")
    parent = world.parent_path
    link = parent / "tracked-link"
    link.symlink_to("tracked.txt")
    subprocess.run(
        ["git", "-C", str(parent), "add", "tracked-link"],
        env=world.env,
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(parent), "commit", "-m", "add oracle symlink"],
        env=world.env,
        check=True,
        stdout=subprocess.PIPE,
    )
    child = parent.parent / "oracle-child"
    subprocess.run(
        ["git", "clone", "--quiet", "--no-hardlinks", str(parent), str(child)],
        env=world.env,
        check=True,
    )

    assert world.manifest_diff(parent, child) == []
    assert world.index_diff(parent, child) == []

    expected_path = "tracked.txt"
    if mutation == "flip-byte":
        (child / expected_path).write_text("changed byte\n")
    elif mutation == "chmod":
        (child / expected_path).chmod(0o755)
    elif mutation == "retarget-symlink":
        expected_path = "tracked-link"
        (child / expected_path).unlink()
        (child / expected_path).symlink_to("different-target")
    elif mutation == "add-untracked":
        expected_path = "unexpected.txt"
        (child / expected_path).write_text("unexpected\n")
    elif mutation == "update-index":
        subprocess.run(
            ["git", "-C", str(child), "update-index", "--chmod=+x", "tracked.txt"],
            env=world.env,
            check=True,
        )
    else:  # pragma: no cover - parametrization is the closed vocabulary
        raise AssertionError(mutation)

    manifest = world.manifest_diff(parent, child)
    index = world.index_diff(parent, child)
    if mutation == "update-index":
        assert manifest == []
        assert len(index) == 1
        assert expected_path in index[0]
    else:
        assert len(manifest) == 1
        assert expected_path in manifest[0]
        assert index == []


@pytest.mark.matrix("T-FIX-16")
def test_env_seal_leaks_no_agent_or_git_prefixed_keys(tmp_path, monkeypatch):
    """T-FIX-16 — the sealed subprocess env leaks no undeclared agent/git-prefixed key.

    Given:  a sealed subprocess env built by sealed_env()
    Expect: no key prefixed CLAUDE, CODEX, AI_AGENT, or GIT_ is present outside the
            declared whitelist
    Source: spec §6.2
    """
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "ambient-claude")
    monkeypatch.setenv("CODEX_THREAD_ID", "ambient-codex")
    monkeypatch.setenv("AI_AGENT", "ambient-agent")
    monkeypatch.setenv("GIT_EXTERNAL_DIFF", "ambient-diff")

    from conftest import sealed_env

    env = sealed_env({"HOME": str(tmp_path / "home")})
    forbidden = ("CLAUDE", "CODEX", "AI_AGENT", "GIT_")
    allowed_git = {"GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM", "GIT_TERMINAL_PROMPT"}
    leaks = sorted(
        key for key in env if key.startswith(forbidden) and key not in allowed_git
    )
    assert leaks == []


@pytest.mark.matrix("T-FIX-17")
def test_realpath_rule_holds_for_every_handle_path(repo_scenario):
    """T-FIX-17 — every fixture handle path is already realpathed.

    Given:  a built WorldHandle
    Expect: handle.parent_path == realpath(handle.parent_path); same for
            handle.child_path when it is not None
    Source: spec §6.5
    """
    world = repo_scenario("linked-worktree")
    assert world.parent_path == world.parent_path.resolve()
    assert world.repo_root == world.repo_root.resolve()
    assert world.main_path == world.main_path.resolve()
    assert world.git_dir == world.git_dir.resolve()
    if world.child_path is not None:
        assert world.child_path == world.child_path.resolve()


@pytest.mark.matrix("T-FIX-18")
def test_git_version_canary_filter_divergence(repo_scenario):
    """T-FIX-18 — git-version canary: filter-divergence is identical on git 2.43/2.50.

    Given:  a non-idempotent clean filter applied to a staged new file
    Expect: the filter diverges identically on git 2.43 and git 2.50
    Source: spec §6.6; spec §5
    """
    from conftest import filter_divergence_probe

    results = filter_divergence_probe()
    assert len(results) >= 1
    assert len(set(results.values())) == 1
    assert next(iter(results.values())) == ("A  sample.txt", "AM sample.txt")


@pytest.mark.matrix("T-FIX-19")
def test_git_version_canary_origin_head_determinism(repo_scenario):
    """T-FIX-19 — git-version canary: origin/HEAD is deterministic across git 2.43/2.50.

    Given:  `git remote set-head origin -a` applied by the remote constructor
    Expect: origin/HEAD is deterministic across git 2.43 and git 2.50
    Source: spec §6.4
    """
    from conftest import origin

    world = repo_scenario("plain@main", remote=origin(pushed=1))
    result = subprocess.run(
        [
            "git",
            "-C",
            str(world.parent_path),
            "symbolic-ref",
            "refs/remotes/origin/HEAD",
        ],
        env=world.env,
        stdout=subprocess.PIPE,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "refs/remotes/origin/main"


@pytest.mark.matrix("T-FIX-20")
def test_git_version_canary_origin_head_deletion_fallback(repo_scenario):
    """T-FIX-20 — git-version canary: detection fallback fires when origin/HEAD is
    absent.

    Given:  origin/HEAD deleted after being set
    Expect: the detection fallback is exercised, consistent across git 2.43/2.50
    Source: spec §6.4
    """
    from conftest import origin

    world = repo_scenario("plain@main", remote=origin())
    subprocess.run(
        [
            "git",
            "-C",
            str(world.parent_path),
            "symbolic-ref",
            "-d",
            "refs/remotes/origin/HEAD",
        ],
        env=world.env,
        check=True,
    )
    missing = subprocess.run(
        [
            "git",
            "-C",
            str(world.parent_path),
            "symbolic-ref",
            "refs/remotes/origin/HEAD",
        ],
        env=world.env,
        capture_output=True,
    )
    assert missing.returncode != 0
    branches = subprocess.run(
        [
            "git",
            "-C",
            str(world.parent_path),
            "show-ref",
            "--verify",
            "refs/heads/main",
        ],
        env=world.env,
        stdout=subprocess.PIPE,
    )
    assert branches.returncode == 0


@pytest.mark.matrix("T-FIX-21")
def test_git_version_canary_unborn_head_rc_128(repo_scenario):
    """T-FIX-21 — git-version canary: unborn-HEAD repos return rc=128 consistently.

    Given:  an unborn(plain) topology repo
    Expect: git commands return rc=128 consistently across git 2.43 and git 2.50
    Source: spec §5
    """
    world = repo_scenario("unborn(plain)")
    result = subprocess.run(
        ["git", "-C", str(world.parent_path), "rev-parse", "--verify", "HEAD^{commit}"],
        env=world.env,
        capture_output=True,
    )
    assert result.returncode == 128


@pytest.mark.matrix("T-FIX-22")
def test_git_version_canary_ita_flags_supported(repo_scenario):
    """T-FIX-22 — git-version canary: ITA flags are present/supported on both floors.

    Given:  a staged intent-to-add entry
    Expect: `--ita-invisible-in-index` and `apply --intent-to-add` are present/supported
            on both git 2.43 and git 2.50
    Source: spec §5; REQ-21 (A3)
    """
    from conftest import intent_to_add

    world = repo_scenario("plain@main", states=(intent_to_add(),))
    parent = world.parent_path
    patch = subprocess.run(
        ["git", "-C", str(parent), "diff", "--binary", "--ita-invisible-in-index"],
        env=world.env,
        stdout=subprocess.PIPE,
        check=True,
    ).stdout
    assert b"intent.txt" in patch
    child = parent.parent / "ita-child"
    subprocess.run(
        [
            "git",
            "-C",
            str(parent),
            "worktree",
            "add",
            "-b",
            "ita-child",
            str(child),
            "HEAD",
        ],
        env=world.env,
        stdout=subprocess.PIPE,
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(child), "apply", "--intent-to-add"],
        env=world.env,
        input=patch,
        check=True,
    )
    cached = subprocess.run(
        ["git", "-C", str(child), "diff", "--cached", "--quiet"], env=world.env
    )
    unstaged = subprocess.run(
        ["git", "-C", str(child), "diff", "--quiet"], env=world.env
    )
    assert cached.returncode == 0
    assert unstaged.returncode == 1


@pytest.mark.matrix("T-FIX-23")
def test_shim_interception_canary_logs_nonempty_argv(repo_scenario):
    """T-FIX-23 — the producer-failure git shim logs non-empty argv per intercepted
    call.

    Given:  shim_git() intercepting a call during materialize
    Expect: every intercepted call is logged with non-empty argv
    Source: spec §6.6; REQ-43 (A10)
    """
    from conftest import shim_git

    world = repo_scenario("plain@main")
    with shim_git(fail_call="diff --cached") as shim:
        env = dict(world.env)
        env["PATH"] = f"{shim.directory}{os.pathsep}{env['PATH']}"
        subprocess.run(
            ["git", "-C", str(world.parent_path), "status", "--porcelain"],
            env=env,
            check=True,
        )
        failed = subprocess.run(
            ["git", "-C", str(world.parent_path), "diff", "--cached"], env=env
        )
        assert failed.returncode == 1
        calls = shim.calls()
        assert calls
        assert all(call for call in calls)
        assert any("diff --cached" in " ".join(call) for call in calls)


@pytest.mark.matrix("T-FIX-24")
def test_harness_git_floor_gate():
    """T-FIX-24 — F/C/R-tier collection hard-errors below TEST_HARNESS_GIT_MIN;
    U-tier does not.

    Given:  an installed git below TEST_HARNESS_GIT_MIN (2.43)
    Expect: F/C/R-tier collection hard-errors; unit tests remain collectible on any
            git version
    Source: spec §7.5; spec §2
    """
    from conftest import _harness_floor_error

    assert _harness_floor_error(["tests/unit/test_x.py"], "git version 2.42.9") is None
    error = _harness_floor_error(["tests/pipeline/test_x.py"], "git version 2.42.9")
    assert error is not None
    assert "2.42.9" in error
    assert "2.43" in error
    assert (
        _harness_floor_error(["tests/fixtures/test_x.py"], "git version 2.43.0") is None
    )
    assert (
        _harness_floor_error(
            ["/checkout/project/tests/cli/test_x.py"], "git version 2.42.9"
        )
        is not None
    )
