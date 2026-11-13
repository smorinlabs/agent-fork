# P08 — Muse as a full agent-fork agent

Detect Muse sessions and support fork, resume, transcript, and messaging.

### Scope
agent-fork treats a Muse (Muse Code) session the way it treats Claude Code and Codex: detect it, fork it with its project files, resume it in place, and locate its transcript.
- **Detection:** `MUSE_SESSION_ID` joins the single shared assessment `assess_agent_signals` in `agents.py`. It is not a parallel copy (P02-A9 consolidated five of those into one). The extension point is shaped so a fourth agent (P09, OpenCode) is one more table entry.
- **CLI:** `fork --agent muse` and `--parent-session` for Muse, in `cli.py` and `detect_agent`.
- **Preflight:** the `muse` binary is on PATH, its version meets a floor, and the parent session exists in the Muse store. Each refusal is a typed error in `errors.py` `ERROR_CATALOG` and in the README exit-code table.
- **Fork (lazy, at paste time):** a hidden agent-fork subcommand starts `muse serve` with bounded timeouts and output caps (the `codex_app_server.py` pattern), calls `initialize`, sends the `initialized` notification, calls `session/fork` for the parent, and prints the new session ID. The paste command is `cd <worktree> && muse resume "$(agent-fork <hidden-subcommand> <parent-id>)"`. The pipeline itself creates no Muse state, so `--dry-run` and rollback stay git-only.
- **Resume in place:** `cd <dir> && muse resume <id>`.
- **Session inspection:** Muse sessions report `agent: "muse"`, a transcript path (`session.jsonl`), and fork and resume commands, through `--session` and `--session-only`.
- **Docs:** README agent support, exit codes, and the Muse section; TEST-MATRIX rows for every new test.

### Out of scope
- Messaging: Muse stays address-only, as P07 shipped it (`sender_unverified`). An MSP `turn/start` route would inject input as the target's own user; the owner declined it on 2026-11-13.
- OpenCode (P09, scoped in parallel); expect a merge on the shared extension point.
- Any change to Claude or Codex behavior; the P02 fault register.
- Auto-trusting the fork worktree: the paste command does not pass `--trust-workspace`, so Muse asks the user.
- Deleting forks: MSP has no `session/delete`.

### Open questions
- Version floor: only 1.4.20 has been probed (the idea notes saw 1.4.18). Should the floor be 1.4.20, or should an older version be probed?
- Live confirmation: does a paste-time fork of a real (non-echo) session include the turn that invoked agent-fork? The schema says it copies completed turns only.
- Hidden subcommand: its name, its visibility in `--help`, and its exit-code contract when `muse serve` or `session/fork` fails at paste time.
- Transcript lookup: deterministic path, `session-index.db` (an unpublished schema), or MSP `session/read` `Session.path`.
- Signal precedence when `MUSE_SESSION_ID` coexists with Claude or Codex variables (nested agents). Coordinate with P09.

### Resolved day-1 questions
- Native fork? Yes, the MSP method `session/fork` via `muse serve`; there is no CLI verb. See the probe findings.
- Transcript? `sessions/YYYY/MM/DD/<uuid>/session.jsonl`; `muse export --session <uuid> --out <file>` is the supported export.

### Notes
Muse sets MUSE_SESSION_ID and MUSE_THREAD_ID (same value) for commands; no Claude variables (probed 2026-11-12, Muse Code 1.4.18, clean environment).
Running sessions via `muse sessions --json`: verified 2026-11-12, a live `muse exec` session listed itself with `sessionId` equal to its MUSE_SESSION_ID and `name` `gold-asteroid`.

### Decisions (scoping with the owner, 2026-11-13)
- References: all three candidates (below).
- Fork method: full native fork (MSP `session/fork`); the real-terminal resume gate passed.
- Messaging: keep address-only.
- Fork timing: lazy, at paste time.

### Probe findings (2026-11-13, Muse Code 1.4.20, `--provider echo`, isolated `XDG_DATA_HOME`)
- **Native fork exists, only over MSP.** `muse schema generate-json-schema` lists stable method `session/fork` (`SessionForkParams`: `commandId` UUIDv7, `sessionId`, optional `cutPoint.lastTurnId`, `excludeItems`). Reached via `muse serve` (newline-delimited JSON-RPC on stdio: `initialize`, then the `initialized` notification, then calls). No CLI `fork` verb. The real index's 4 existing forks all carry `msp_fork_command_id`.
- **Fork copies completed turns only.** With `cutPoint` omitted the fork takes "all completed turns", so an in-flight parent turn (the one running agent-fork) is not copied. Not yet confirmed against a live session.
- **Fork works while another host holds the parent.** Host A `session/resume`d the parent and held it; host B's `session/fork` succeeded.
- **Fork inherits the parent's workspace.** `session/fork` from a host whose cwd is the child worktree returned `workspaceRoot` = parent. `session/fork` and `session/resume` take no workspace parameter; only `session/start` does.
- **Rebinding the fork to the child worktree.** From the child's cwd, `muse exec --session-id <fork>` refuses ("was created in workspace <parent>; refusing to resume in workspace <child>"), with or without `--workspace <child>`. `--allow-workspace-switch` works for one run but does not persist, and is not a `resume` or root flag. From the **parent** cwd, `muse exec --session-id <fork> --worktree existing --worktree-existing <child>` binds the turn to the child and writes a durable `session.workspace_scope.activated` record. After that, plain `muse exec --session-id <fork>` from either cwd reports `workspace root: <child> (explicit)`.
- **Interactive `muse resume` binds to the cwd.** Verified in real Rex terminal tabs, each on a fresh, never-resumed fork, with a turn submitted and the live `workspace_branch.observed` record (`probe_ran: true`) read back. `cd <child> && muse resume <fork>` bound the turn to the child (branch `child`) with no rebind flags. `cd <parent> && muse resume <fork> --worktree existing --worktree-existing <child>` also bound it to the child and wrote a durable `session.workspace_scope.activated` record. Only `muse exec` refuses a workspace change. (Bare pty attempts stalled at "Restoring conversation"; the resume-time records seen there replay stored metadata, with `command_id` equal to the session ID, and do not show the live binding.)
- **No delete method.** The MSP method list has no `session/delete`, so agent-fork cannot remove a fork it created.
- **Transcript.** `sessions/YYYY/MM/DD/<uuid>/session.jsonl` under the Muse data dir (`$XDG_DATA_HOME/muse`, default `~/.local/share/muse`). Also `Session.path` over MSP, `session_log_path` in `session-index.db`, and `muse export --session <uuid|path> --out <file>` (offline JSON, `export_schema_version` 1).
- **Workspace keys are per checkout path.** `workspace_key` equals the checkout path, so every git worktree is its own workspace.
- **Trust gate.** Headless subcommands (`muse export`, `muse resume --help`) refuse in a workspace whose trust is undecided ("pass --trust-workspace"). A fresh fork worktree is always such a workspace. `--trust-workspace` must come after the subcommand; before it, Muse starts the TUI.

<!-- Idea state. Minimal by convention.
     Promote with `project-refine P08` when ready. -->
