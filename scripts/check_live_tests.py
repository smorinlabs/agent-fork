"""Preflight authenticated real-agent tests before they spend model calls."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )


def _cli_identity(label: str, executable: str) -> tuple[str | None, str | None]:
    result = _run([executable, "--version"])
    version = result.stdout.strip() or result.stderr.strip()
    if result.returncode != 0:
        detail = version or f"exit {result.returncode} with no output"
        return None, f"{label} version check failed for {executable}: {detail}"
    if not version:
        return None, f"{label} version check returned no output for {executable}"
    selected = Path(executable)
    return (
        f"{label}: executable={selected}; resolved={selected.resolve()}; "
        f"version={version.splitlines()[0]}",
        None,
    )


def _check_claude(executable: str) -> str | None:
    result = _run([executable, "auth", "status", "--json"])
    try:
        status = json.loads(result.stdout)
    except json.JSONDecodeError:
        return "Claude authentication status was not valid JSON"
    if result.returncode != 0 or status.get("loggedIn") is not True:
        return "Claude is not authenticated; run `claude auth login`"
    return None


def _check_codex(executable: str) -> str | None:
    result = _run([executable, "login", "status"])
    output = f"{result.stdout}\n{result.stderr}"
    if result.returncode != 0 or "Logged in" not in output:
        return "Codex is not authenticated; run `codex login`"
    return None


def _check_state_directory(label: str, directory: Path) -> str | None:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=directory, prefix=".agent-fork-live-preflight-"
        ):
            pass
    except OSError as error:
        return f"{label} state directory is not writable: {directory} ({error})"
    return None


def _check_network(host: str) -> str | None:
    try:
        connection = socket.create_connection((host, 443), timeout=5)
        connection.close()
    except OSError as error:
        return f"network preflight failed for {host}:443 ({error})"
    return None


def main() -> int:
    failures: list[str] = []
    identities: list[str] = []
    claude = shutil.which("claude")
    codex = shutil.which("codex")
    if claude is None:
        failures.append("Claude CLI is not on PATH")
    else:
        identity, identity_error = _cli_identity("Claude", claude)
        if identity:
            identities.append(identity)
        if identity_error:
            failures.append(identity_error)
        auth_error = _check_claude(claude)
        if auth_error:
            failures.append(auth_error)
    if codex is None:
        failures.append("Codex CLI is not on PATH")
    else:
        identity, identity_error = _cli_identity("Codex", codex)
        if identity:
            identities.append(identity)
        if identity_error:
            failures.append(identity_error)
        auth_error = _check_codex(codex)
        if auth_error:
            failures.append(auth_error)

    claude_state = Path(
        os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))
    )
    codex_state = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    for label, directory in (("Claude", claude_state), ("Codex", codex_state)):
        state_error = _check_state_directory(label, directory)
        if state_error:
            failures.append(state_error)

    hosts = os.environ.get(
        "AGENT_FORK_LIVE_NETWORK_HOSTS", "api.anthropic.com,chatgpt.com"
    )
    for host in (value.strip() for value in hosts.split(",")):
        if host:
            network_error = _check_network(host)
            if network_error:
                failures.append(network_error)

    output = sys.stderr if failures else sys.stdout
    print("real-agent CLI identities:", file=output)
    for identity in identities:
        print(f"- {identity}", file=output)
    if failures:
        print("real-agent test preflight failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(
        "real-agent test preflight passed: executable versions, auth, state, "
        "and network"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
