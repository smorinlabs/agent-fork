# P08 — Muse as a full agent-fork agent

Detect Muse sessions and support fork, resume, transcript, and messaging.

### Open questions
- Does Muse have a native fork command, or must agent-fork fork the transcript itself? (`muse export --help` says exports include "fork/subagent lineage", so Muse has a fork concept; no `fork` subcommand is listed in `muse --help`.)
- Where is a Muse session's transcript file, and is `muse export` the supported read path?

### Notes
Muse sets MUSE_SESSION_ID and MUSE_THREAD_ID (same value) for commands; no Claude variables (probed 2026-11-12, Muse Code 1.4.18, clean environment).
Sessions: ~/.local/share/muse/session-index.db; resume with `cd <workspace> && muse resume <uuid>` (`muse resume --help`: takes "an exact session UUID or Session Name", scoped to the current workspace; not run interactively). Running sessions via `muse sessions --json`: verified 2026-11-12, a live `muse exec` session listed itself with `sessionId` equal to its MUSE_SESSION_ID and `name` `gold-asteroid`.

### Probe findings (2026-11-13, Muse Code 1.4.20, `--provider echo`, isolated `XDG_DATA_HOME`)
- **Native fork exists, only over MSP.** `muse schema generate-json-schema` lists stable method `session/fork` (`SessionForkParams`: `commandId` UUIDv7, `sessionId`, optional `cutPoint.lastTurnId`, `excludeItems`). Reached via `muse serve` (newline-delimited JSON-RPC on stdio: `initialize`, then the `initialized` notification, then calls). No CLI `fork` verb. The real index's 4 existing forks all carry `msp_fork_command_id`.
- **Fork copies completed turns only.** With `cutPoint` omitted the fork takes "all completed turns", so an in-flight parent turn (the one running agent-fork) is not copied. Not yet confirmed against a live session.
- **Fork works while another host holds the parent.** Host A `session/resume`d the parent and held it; host B's `session/fork` succeeded.
- **Fork inherits the parent's workspace.** `session/fork` from a host whose cwd is the child worktree returned `workspaceRoot` = parent. `session/fork` and `session/resume` take no workspace parameter; only `session/start` does.
- **Rebinding the fork to the child worktree.** From the child's cwd, `muse exec --session-id <fork>` refuses ("was created in workspace <parent>; refusing to resume in workspace <child>"), with or without `--workspace <child>`. `--allow-workspace-switch` works for one run but does not persist, and is not a `resume` or root flag. From the **parent** cwd, `muse exec --session-id <fork> --worktree existing --worktree-existing <child>` binds the turn to the child and writes a durable `session.workspace_scope.activated` record. After that, plain `muse exec --session-id <fork>` from either cwd reports `workspace root: <child> (explicit)`.
- **Interactive `muse resume` binding is unverified.** Under a bare pty, `muse resume <fork>` from the child stalled at "Restoring conversation" and no turn could be submitted. Needs a real terminal.
- **Transcript.** `sessions/YYYY/MM/DD/<uuid>/session.jsonl` under the Muse data dir (`$XDG_DATA_HOME/muse`, default `~/.local/share/muse`). Also `Session.path` over MSP, `session_log_path` in `session-index.db`, and `muse export --session <uuid|path> --out <file>` (offline JSON, `export_schema_version` 1).
- **Workspace keys are per checkout path.** `workspace_key` equals the checkout path, so every git worktree is its own workspace.
- **Trust gate.** Headless subcommands (`muse export`, `muse resume --help`) refuse in a workspace whose trust is undecided ("pass --trust-workspace"). A fresh fork worktree is always such a workspace. `--trust-workspace` must come after the subcommand; before it, Muse starts the TUI.

<!-- Idea state. Minimal by convention.
     Promote with `project-refine P08` when ready. -->
