"""Production hardening for A6b's recursive submodule boundary.

These tests pin four fail-closed contracts found by the post-merge production
review: cold checkout content, ambient URL rewrites, exact remote URL fidelity,
and unmerged indexes below the top-level repository.
"""

from __future__ import annotations

import subprocess
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, cast

import pytest

from conftest import run_cli, submodule


def _git(world, repo: Path, *args: str, check: bool = True, input_bytes=None):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        env=world.env,
        input=input_bytes,
        capture_output=True,
        check=check,
    )


def _fork(
    world,
    name: str,
    *,
    env=None,
    with_state: bool = True,
    with_submodules: bool = True,
):
    from agent_fork.pipeline import ForkRequest, fork

    return fork(
        ForkRequest(
            parent=world.parent_path,
            destination=world.parent_path.parent / name,
            name=name,
            branch=f"fork/{name}",
            agent=None,
            with_state=with_state,
            with_submodules=with_submodules,
        ),
        env=world.env if env is None else env,
    )


def _assert_fork_absent(world, name: str) -> None:
    assert not (world.parent_path.parent / name).exists()
    branch = _git(
        world,
        world.parent_path,
        "show-ref",
        "--verify",
        "--quiet",
        f"refs/heads/fork/{name}",
        check=False,
    )
    assert branch.returncode != 0


def _repository_state(world) -> tuple[bytes, bytes, bytes, bytes]:
    return (
        _git(world, world.parent_path, "status", "--porcelain=v1", "-z").stdout,
        _git(world, world.parent_path, "diff", "--cached", "--binary").stdout,
        _git(world, world.parent_path, "diff", "--binary").stdout,
        _git(
            world,
            world.parent_path,
            "ls-files",
            "--others",
            "--exclude-standard",
            "-z",
        ).stdout,
    )


def _make_unmerged_index(world, checkout: Path, path: str = "tracked.txt") -> None:
    oids = []
    for content in (b"base\n", b"ours\n", b"theirs\n"):
        oids.append(
            _git(
                world,
                checkout,
                "hash-object",
                "-w",
                "--stdin",
                input_bytes=content,
            )
            .stdout.decode()
            .strip()
        )
    index_info = "".join(
        f"100644 {oid} {stage}\t{path}\n" for stage, oid in enumerate(oids, start=1)
    ).encode()
    _git(world, checkout, "update-index", "--index-info", input_bytes=index_info)


@contextmanager
def _request_counter() -> Iterator[tuple[str, list[str]]]:
    requests: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
            requests.append(self.path)
            self.send_response(404)
            self.end_headers()

        def log_message(self, format: str, *args: Any) -> None:
            del format, args

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = cast(tuple[str, int], server.server_address)
    try:
        yield f"http://{host}:{port}/rewritten/", requests
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def _rewrite_environment(world, target: str) -> tuple[dict[str, str], str]:
    source = str(world.parent_path / "vendor/submodule")
    config = world.parent_path.parent / "rewrite.gitconfig"
    config.write_text("")
    subprocess.run(
        [
            "git",
            "config",
            "--file",
            str(config),
            "--add",
            f"url.{target}.insteadOf",
            source,
        ],
        env=world.env,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        [
            "git",
            "config",
            "--file",
            str(config),
            "protocol.http.allow",
            "always",
        ],
        env=world.env,
        capture_output=True,
        check=True,
    )
    return {
        **world.env,
        "GIT_CONFIG_GLOBAL": str(config),
        "GIT_CONFIG_NOSYSTEM": "1",
    }, source


@pytest.mark.matrix("T-GRD-31")
def test_cold_submodule_with_content_refuses_before_mutation(repo_scenario):
    """A cold gitlink is safe only when its checkout directory is empty."""
    from agent_fork.errors import PreconditionError

    world = repo_scenario("plain@main", states=(submodule(dirty="uninit"),))
    checkout = world.parent_path / "vendor/submodule"
    checkout.mkdir(parents=True, exist_ok=True)
    (checkout / "loose.txt").write_text("content Git would overwrite\n")
    before = _repository_state(world)

    with pytest.raises(PreconditionError) as raised:
        _fork(world, "cold-content")

    assert raised.value.code == "submodule_cold_content"
    assert raised.value.details == {
        "submodule": "vendor/submodule",
        "entries": ["vendor/submodule/loose.txt"],
        "count": 1,
    }
    assert _repository_state(world) == before
    _assert_fork_absent(world, "cold-content")

    preview = run_cli(
        ["fork", "cold-content-preview", "--no-agent", "--dry-run", "--json"],
        world.env,
        world.parent_path,
    )
    assert preview.returncode == 5
    assert b'"code":"submodule_cold_content"' in preview.stderr
    _assert_fork_absent(world, "cold-content-preview")

    empty_world = repo_scenario("plain@main", states=(submodule(dirty="uninit"),))
    assert _fork(empty_world, "empty-cold-allowed").creation.path.exists()


@pytest.mark.matrix("T-GRD-32")
def test_nested_cold_submodule_content_reports_qualified_path(repo_scenario):
    """Cold-content inspection recurses and identifies the full nested path."""
    from agent_fork.errors import PreconditionError

    world = repo_scenario(
        "plain@main", states=(submodule(nested=True, committed=True),)
    )
    outer = world.parent_path / "vendor/submodule"
    _git(world, outer, "submodule", "deinit", "-f", "--", "inner")
    inner = outer / "inner"
    inner.mkdir(exist_ok=True)
    (inner / ".hidden").write_text("preserve me\n")

    with pytest.raises(PreconditionError) as raised:
        _fork(world, "nested-cold-content")

    assert raised.value.code == "submodule_cold_content"
    assert raised.value.details == {
        "submodule": "vendor/submodule/inner",
        "entries": ["vendor/submodule/inner/.hidden"],
        "count": 1,
    }
    _assert_fork_absent(world, "nested-cold-content")


@pytest.mark.matrix("T-GRD-33")
def test_matching_insteadof_refuses_without_network_or_mutation(repo_scenario):
    """An effective `url.*.insteadOf` match cannot rewrite the local source."""
    from agent_fork.errors import PreconditionError

    world = repo_scenario("plain@main", states=(submodule(committed=True),))
    with _request_counter() as (target, requests):
        env, source = _rewrite_environment(world, target)
        with pytest.raises(PreconditionError) as raised:
            _fork(world, "unsafe-rewrite", env=env)
        preview = run_cli(
            ["fork", "unsafe-rewrite-preview", "--no-agent", "--dry-run", "--json"],
            env,
            world.parent_path,
        )

    assert raised.value.code == "submodule_transport_unsafe"
    assert raised.value.details == {
        "submodule": "vendor/submodule",
        "source": source,
        "rewrite_prefix": source,
    }
    assert requests == []
    _assert_fork_absent(world, "unsafe-rewrite")
    assert preview.returncode == 5
    assert b'"code":"submodule_transport_unsafe"' in preview.stderr
    _assert_fork_absent(world, "unsafe-rewrite-preview")


@pytest.mark.matrix("T-MAT-71")
def test_carry_protocol_backstop_blocks_http_after_preflight_bypass(repo_scenario):
    """Mutation-time pins still prohibit network if a caller skips guards."""
    from agent_fork.git import GitCommandError
    from agent_fork.repository import create_worktree_at_anchor
    from agent_fork.submodules import carry_submodules, snapshot_submodules

    world = repo_scenario("plain@main", states=(submodule(committed=True),))
    plans = snapshot_submodules(world.parent_path, with_state=True, env=world.env)
    child = world.parent_path.parent / "transport-backstop"
    create_worktree_at_anchor(
        world.parent_path,
        "fork/transport-backstop",
        child,
        env=world.env,
    )

    with _request_counter() as (target, requests):
        env, _source = _rewrite_environment(world, target)
        with pytest.raises(GitCommandError):
            carry_submodules(
                world.parent_path,
                child,
                plans,
                with_state=True,
                env=env,
            )

    assert requests == []


def _remote_urls(world, checkout: Path) -> bytes:
    return _git(
        world,
        checkout,
        "config",
        "--local",
        "--null",
        "--get-all",
        "remote.origin.url",
        check=False,
    ).stdout


@pytest.mark.matrix("T-MAT-72")
def test_carry_preserves_all_remote_origin_urls_in_order(repo_scenario):
    """A multivalue `remote.origin.url` is copied as one exact ordered tuple."""
    from agent_fork.repository import create_worktree_at_anchor
    from agent_fork.submodules import carry_submodules, snapshot_submodules

    world = repo_scenario("plain@main", states=(submodule(committed=True),))
    parent_checkout = world.parent_path / "vendor/submodule"
    _git(
        world,
        parent_checkout,
        "config",
        "--add",
        "remote.origin.url",
        "ssh://example.invalid/secondary.git",
    )
    expected = _remote_urls(world, parent_checkout)
    plans = snapshot_submodules(world.parent_path, with_state=True, env=world.env)
    child = world.parent_path.parent / "remote-multivalue"
    create_worktree_at_anchor(
        world.parent_path, "fork/remote-multivalue", child, env=world.env
    )
    carry_submodules(world.parent_path, child, plans, with_state=True, env=world.env)

    assert _remote_urls(world, child / "vendor/submodule") == expected


@pytest.mark.matrix("T-MAT-73")
def test_carry_preserves_remote_url_trailing_spaces_byte_for_byte(repo_scenario):
    """Snapshotting must not strip legal trailing spaces from a config value."""
    from agent_fork.repository import create_worktree_at_anchor
    from agent_fork.submodules import carry_submodules, snapshot_submodules

    world = repo_scenario("plain@main", states=(submodule(committed=True),))
    parent_checkout = world.parent_path / "vendor/submodule"
    _git(
        world,
        parent_checkout,
        "config",
        "--replace-all",
        "remote.origin.url",
        "ssh://example.invalid/with-space.git  ",
    )
    expected = _remote_urls(world, parent_checkout)
    plans = snapshot_submodules(world.parent_path, with_state=True, env=world.env)
    child = world.parent_path.parent / "remote-spaces"
    create_worktree_at_anchor(
        world.parent_path, "fork/remote-spaces", child, env=world.env
    )
    carry_submodules(world.parent_path, child, plans, with_state=True, env=world.env)

    assert _remote_urls(world, child / "vendor/submodule") == expected


@pytest.mark.matrix("T-VER-58")
def test_recursive_verification_detects_remote_url_corruption(
    repo_scenario, monkeypatch
):
    """A post-carry URL fault fails verification and rolls the fork back."""
    from agent_fork import pipeline
    from agent_fork.errors import VerificationError

    world = repo_scenario("plain@main", states=(submodule(committed=True),))
    original_carry = pipeline.carry_submodules

    def corrupt_after_carry(parent, child, plans, **kwargs):
        result = original_carry(parent, child, plans, **kwargs)
        _git(
            world,
            child / "vendor/submodule",
            "config",
            "--add",
            "remote.origin.url",
            "ssh://example.invalid/corrupt.git",
        )
        return result

    monkeypatch.setattr(pipeline, "carry_submodules", corrupt_after_carry)
    with pytest.raises(VerificationError) as raised:
        _fork(world, "remote-corruption")

    assert raised.value.details is not None
    assert raised.value.details["failed_checks"] == [
        {
            "check": "submodule-content-match",
            "primary": True,
            "total": 1,
            "differences": [
                {
                    "path": "vendor/submodule",
                    "kind": "submodule-remote-url",
                    "detail": "remote.origin.url values differ from the frozen plan",
                }
            ],
        }
    ]
    _assert_fork_absent(world, "remote-corruption")


@pytest.mark.matrix("T-GRD-34")
def test_recursive_unmerged_index_refuses_real_fork_before_mutation(repo_scenario):
    """An initialized submodule's unmerged stages are a pre-mutation refusal."""
    from agent_fork.errors import PreconditionError

    world = repo_scenario("plain@main", states=(submodule(committed=True),))
    checkout = world.parent_path / "vendor/submodule"
    _make_unmerged_index(world, checkout)
    assert _git(world, world.parent_path, "ls-files", "-u", "-z").stdout == b""
    assert _git(world, checkout, "ls-files", "-u", "-z").stdout

    with pytest.raises(PreconditionError) as raised:
        _fork(world, "recursive-unmerged")

    assert raised.value.code == "unmerged_index"
    assert "vendor/submodule/tracked.txt" in str(raised.value)
    _assert_fork_absent(world, "recursive-unmerged")


@pytest.mark.matrix("T-GRD-35")
def test_recursive_unmerged_index_refuses_dry_run_before_mutation(repo_scenario):
    """Dry-run applies the same recursive conflict guard as a real fork."""
    world = repo_scenario("plain@main", states=(submodule(committed=True),))
    _make_unmerged_index(world, world.parent_path / "vendor/submodule")

    completed = run_cli(
        ["fork", "recursive-unmerged-preview", "--no-agent", "--dry-run", "--json"],
        world.env,
        world.parent_path,
    )

    assert completed.returncode == 5
    assert b'"code":"unmerged_index"' in completed.stderr
    assert b"vendor/submodule/tracked.txt" in completed.stderr
    _assert_fork_absent(world, "recursive-unmerged-preview")


@pytest.mark.matrix("T-GRD-36")
def test_nested_unmerged_index_is_qualified_and_opt_outs_remain_allowed(
    repo_scenario,
):
    """The recursive guard reaches depth two but stays scoped to both flags."""
    from agent_fork.errors import PreconditionError

    world = repo_scenario(
        "plain@main", states=(submodule(nested=True, committed=True),)
    )
    inner = world.parent_path / "vendor/submodule/inner"
    _make_unmerged_index(world, inner)

    with pytest.raises(PreconditionError) as raised:
        _fork(world, "nested-unmerged")
    assert raised.value.code == "unmerged_index"
    assert "vendor/submodule/inner/tracked.txt" in str(raised.value)
    _assert_fork_absent(world, "nested-unmerged")

    assert _fork(
        world, "nested-unmerged-no-submodules", with_submodules=False
    ).creation.path.exists()
    assert _fork(
        world, "nested-unmerged-no-state", with_state=False
    ).creation.path.exists()
