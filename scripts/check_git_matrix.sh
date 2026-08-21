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
  tests/pipeline/test_a6b_carry.py::test_carry_honours_update_policy_none_via_the_checkout_flag
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
    tests/pipeline/test_mat.py::test_intent_to_add_file_transported_as_ita \
    tests/pipeline/test_a6b_carry.py::test_carry_honours_update_policy_none_via_the_checkout_flag -q
' -- "$worktree_root"

# Clone-cost measurement (A6b step 7). Fork a fixture with one large
# submodule versus a size-matched fixture with none, wall-clock both, and
# report the delta. No numeric gate: one data point is not a regression
# budget. But an unrecorded number is the same silent-"acceptable" failure
# gate-4 pass 1 finding 3 already complained about, in a different shape --
# so the number gets measured and written down, not assumed.
#
# Measured 2026-08-20, this machine, system Git (Apple Git), a 50,002-object
# submodule (50,000 tracked files, one commit, gc.auto disabled so the
# object count stays representative rather than getting silently packed):
# with-submodule fork = 40-43s, without-submodule fork = 1s, delta = ~40s.
# Re-run this function and update the comment if the recipe's cost profile
# changes materially.
measure_clone_cost() {
  local tmp agent_fork_bin
  tmp=$(mktemp -d)
  agent_fork_bin="$worktree_root/.venv/bin/agent-fork"

  local sub="$tmp/big-submodule"
  git init -q "$sub"
  git -C "$sub" config user.email bench@example.com
  git -C "$sub" config user.name bench
  # 50k loose objects exceeds the default gc.auto threshold (~6700): the
  # commit below spawns a background `git gc --auto`, which races the
  # submodule-add clone immediately after it and intermittently fails with
  # "failed to copy file ... No such file or directory" when gc prunes a
  # loose object the clone is mid-copy on. Disable it in this throwaway
  # fixture rather than fixing the race by ordering (found by running this
  # script for real: 3/3 failures until this fix, 0/N after).
  git -C "$sub" config gc.auto 0
  local i
  for i in $(seq 1 50000); do
    printf '%d' "$i" >"$sub/file-$i.txt"
  done
  git -C "$sub" add -A
  git -C "$sub" commit -q -m 'seed 50k objects'

  local with_sub="$tmp/parent-with-submodule"
  git init -q "$with_sub"
  git -C "$with_sub" config user.email bench@example.com
  git -C "$with_sub" config user.name bench
  git -C "$with_sub" -c protocol.file.allow=always submodule add -q "$sub" vendor/big
  git -C "$with_sub" commit -q -m 'add big submodule'

  local without_sub="$tmp/parent-without-submodule"
  git init -q "$without_sub"
  git -C "$without_sub" config user.email bench@example.com
  git -C "$without_sub" config user.name bench
  printf 'placeholder\n' >"$without_sub/placeholder.txt"
  git -C "$without_sub" add placeholder.txt
  git -C "$without_sub" commit -q -m 'placeholder, no submodule'

  local t0 t1 with_elapsed without_elapsed
  t0=$(date +%s)
  (
    cd "$with_sub"
    GIT_AUTHOR_NAME=bench GIT_AUTHOR_EMAIL=bench@example.com \
      GIT_COMMITTER_NAME=bench GIT_COMMITTER_EMAIL=bench@example.com \
      "$agent_fork_bin" fork bench-with --no-agent -o json >/dev/null
  )
  t1=$(date +%s)
  with_elapsed=$((t1 - t0))

  t0=$(date +%s)
  (
    cd "$without_sub"
    GIT_AUTHOR_NAME=bench GIT_AUTHOR_EMAIL=bench@example.com \
      GIT_COMMITTER_NAME=bench GIT_COMMITTER_EMAIL=bench@example.com \
      "$agent_fork_bin" fork bench-without --no-agent -o json >/dev/null
  )
  t1=$(date +%s)
  without_elapsed=$((t1 - t0))

  printf 'clone-cost: with-submodule=%ss without-submodule=%ss delta=%ss\n' \
    "$with_elapsed" "$without_elapsed" "$((with_elapsed - without_elapsed))"

  # Deregister before removing $tmp: agent-fork's own cleanup needs the
  # worktree path to still exist, so this must run first or it leaves an
  # orphaned registry entry with no path left to clean it up by (the
  # cleanup command needs to cd into the target).
  "$agent_fork_bin" cleanup bench-with --force --yes >/dev/null 2>&1 || true
  "$agent_fork_bin" cleanup bench-without --force --yes >/dev/null 2>&1 || true

  rm -rf "$tmp"
}

measure_clone_cost
