#!/usr/bin/env bash
set -euo pipefail

worktree_root=$(git rev-parse --show-toplevel)
common_dir=$(git rev-parse --git-common-dir)
if [[ "$common_dir" != /* ]]; then
  common_dir="$worktree_root/$common_dir"
fi
flox_root=$(cd "$(dirname "$common_dir")" && pwd -P)
uv_executable=$(command -v uv)
test_nodes=(
  tests/fixtures/test_fix.py::test_git_version_canary_ita_transport_supported
  tests/pipeline/test_mat.py::test_intent_to_add_file_transported_as_ita
)

if [[ $(uname -s) == Darwin ]]; then
  if ! /usr/bin/git --version | grep -q 'Apple Git'; then
    printf 'expected /usr/bin/git to be Apple Git on macOS\n' >&2
    exit 1
  fi
  /usr/bin/git --version
  env PATH=/usr/bin:/bin:/usr/sbin:/sbin \
    "$uv_executable" run pytest "${test_nodes[@]}" -q
else
  git --version
  "$uv_executable" run pytest "${test_nodes[@]}" -q
fi

flox activate -d "$flox_root" -- bash -c '
  set -euo pipefail
  cd "$1"
  git --version
  uv run pytest \
    tests/fixtures/test_fix.py::test_git_version_canary_ita_transport_supported \
    tests/pipeline/test_mat.py::test_intent_to_add_file_transported_as_ita -q
' -- "$worktree_root"
