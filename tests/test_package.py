"""Scaffold smoke tests: the package imports and exposes its metadata."""

import json
import tomllib
from importlib.metadata import version
from pathlib import Path

import agent_fork
from agent_fork.cli import main


def test_version_matches_metadata() -> None:
    assert agent_fork.__version__ == version("agent-fork")


def test_console_entry_point_is_callable() -> None:
    assert callable(main)


def test_flox_environment_uses_host_managed_agent_clis() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    manifest = tomllib.loads((repo_root / ".flox/env/manifest.toml").read_text())

    installed = manifest["install"]
    assert "claude-code" not in installed
    assert "codex" not in installed


def test_app_server_handshake_reports_installed_version(tmp_path) -> None:
    from agent_fork.codex_app_server import list_named_threads

    recorded = tmp_path / "requests.jsonl"
    server = tmp_path / "codex"
    server.write_text(
        "#!/usr/bin/env python3\n"
        "import json,sys\n"
        f"log=open({str(recorded)!r},'a')\n"
        "for line in sys.stdin:\n"
        " log.write(line); log.flush()\n"
        " request=json.loads(line)\n"
        " if 'id' not in request: continue\n"
        " result={} if request['id']==1 else {'data':[]}\n"
        " print(json.dumps({'id':request['id'],'result':result}),flush=True)\n"
    )
    server.chmod(0o755)
    assert list_named_threads(str(server), "hello", {}) == ()
    requests = [json.loads(line) for line in recorded.read_text().splitlines()]
    initialize = next(r for r in requests if r.get("method") == "initialize")
    assert initialize["params"]["clientInfo"] == {
        "name": "agent-fork",
        "version": version("agent-fork"),
    }
