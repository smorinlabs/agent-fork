# Phase B live experiments — 2026-08-09

All experiments ran inside the isolated `agent-fork` guest against authenticated real
CLIs. Executable coverage is in `tests/live/test_exp.py` (T-EXP-01..03).

**Phase D template revalidation (2026-08-10):** after implementing the REQ-28
builders and shell-quoting boundary, E1–E3 were rerun together against the real
CLIs. The final D6 run passed all three experiments in 23.18 seconds (following
an earlier 24.23-second pass). The locked templates and conclusions below remain
unchanged.

## Environment

- Claude Code 2.1.220
- Codex CLI 0.147.0
- Git 2.43.0
- Linux aarch64 guest; disposable repositories and linked worktrees under `/tmp`

## E1 — Claude flag composition

From a disposable parent repo, a non-interactive parent session was created with a
known UUID. From its linked worktree, the fork ran with a pre-generated child UUID:

```bash
claude --session-id '<child-uuid>' --resume '<parent-uuid>' --fork-session \
  -n '<fork-name>' -p '<recall-prompt>' --output-format json --max-turns 1
```

Result: **pass**. The result and child transcript used the pinned child UUID. The child
transcript began with both `custom-title` and `agent-name` records containing the exact
fork name. No flag silently no-oped, so `-n` remains in REQ-28.

## E2 — Codex explicit UUID, foreign cwd, and `-C`

A real parent thread was created in a disposable repo with `codex exec --json`. Its
explicit `thread_id` was then passed to interactive `codex fork` under a PTY from a
foreign directory.

Result: **pass with a template decision**.

- `codex fork '<thread-id>'` found the explicit thread despite the foreign cwd, then
  displayed “Choose working directory” with the recorded session cwd and current cwd.
- `codex fork '<thread-id>' -C '<linked-worktree>'` opened the fork in that worktree and
  did not display the cwd-choice prompt.
- The locked REQ-28 template is therefore `codex fork '<thread-id>' -C '<worktree>'`.
  Codex machine output retains `cwd_prompt_expected`, fixed to `false` for this template.

The ordinary first-use directory-trust prompt is separate from the session cwd-choice
prompt and is not an agent-fork template hazard.

## E3 — Claude full paste-command E2E

The E1 child invocation doubled as the full E2E. The parent was prompted to remember a
fresh exact token; the linked-worktree fork was asked to reproduce it.

Result: **pass**.

- The child returned the exact parent token, demonstrating context recall.
- The child used the pre-generated fresh UUID and persisted its own transcript under
  the linked-worktree project path.
- The child transcript contained the copied parent turns plus the child turn.
- SHA-256 of the parent transcript was identical immediately before and after the fork,
  demonstrating the parent transcript was untouched.

## Disposition

E1-E3 are closed. E4 remains retired until v1.1 (A8/D14), E5 is the G-MAT/G-VER core
TDD obligation, and E6 is tombstoned with the removed pre-0.95 Codex ladder (A7).

## E7 — Codex renamed-session resolution

On 2026-08-10, Codex CLI 0.147.0 in the guest had a real thread renamed
`hello-codex`. A bounded stdio app-server session initialized successfully and
`thread/list` with `searchTerm: "hello-codex"`, active-thread filters, and
state-database-only lookup returned the exact name with canonical UUID
`019fed92-fa7e-7262-b93e-6bd73a38ac72`.

Result: **pass**. The app-server is a sufficient Codex-owned resolution path;
direct SQLite access is unnecessary. The implementation therefore resolves an
explicit non-UUID Codex parent through this protocol, handles pagination, and
requires exactly one exact-name match. Canonical UUID input bypasses app-server
startup. `--no-codex-session-name-resolution` and
`[agents.codex] session_name_resolution = false` retain a deterministic
UUID-only escape hatch. T-EXP-07 rechecks the real local path and performs no
repository mutation.
