#!/usr/bin/env bash
set -euo pipefail

check_root="$(mktemp -d)"
trap 'rm -rf "$check_root"' EXIT

uv build --out-dir "$check_root/dist"
uv venv "$check_root/venv" --python python3
uv pip install --python "$check_root/venv/bin/python" "$check_root"/dist/*.whl

version_output="$($check_root/venv/bin/agent-fork --version)"
test "$version_output" = "agent-fork 0.1.0"
"$check_root/venv/bin/agent-fork" --help | grep -q '^usage: agent-fork'
"$check_root/venv/bin/agent-fork" | grep -q '^usage: agent-fork'
"$check_root/venv/bin/agent-fork" completion bash | grep -q agent-fork
"$check_root/venv/bin/agent-fork" completion bash | bash -n
if command -v zsh >/dev/null; then
  "$check_root/venv/bin/agent-fork" completion zsh | zsh -n
fi
if command -v fish >/dev/null; then
  "$check_root/venv/bin/agent-fork" completion fish | fish -n
fi
"$check_root/venv/bin/python" -c 'import agent_fork.cli'
