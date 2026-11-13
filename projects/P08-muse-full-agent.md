# P08 — Muse as a full agent-fork agent

**References**
- **Trunk:** [PROJECTS.md](../PROJECTS.md)
- **Successor of:** [P07 — cross-tool message route](P07-cross-tool-message-route.md) (PR #76), which gave Muse detection and an address-only message route
- **Discussion:** [P09 — OpenCode as a full agent-fork agent](P09-opencode-full-agent-.md), scoped in parallel on `feat/p09-opencode-full-agent`; both touch `agents.py`, `cli.py`, and `session.py`
- **Prior art:** [`src/agent_fork/codex_app_server.py`](../src/agent_fork/codex_app_server.py), the bounded JSON-RPC stdio client the MSP client follows

## [~] Project P08: Muse as a full agent-fork agent (v1.5.0)
**Goal**: Detect Muse sessions and support fork, resume, and transcript the way Claude Code and Codex are supported. Messaging stays address-only.

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
- None open. Remaining unknowns are covered by `P08-TS06` (live verification).

### Resolved during decomposition (2026-11-13, executed probes)
- Version floor: none. 1.4.20 is recorded as observed, not as a floor, matching P09; the preflight checks capability instead (`muse --help` lists `resume` and `serve`).
- Hidden subcommand: `agent-fork muse-fork <parent-id>`. It prints only the fork ID on success; any failure is `muse_fork_failed` (exit 3) on stderr.
- Paste-command shape: `cd <dir> && muse resume "$('<agent-fork>' muse-fork <parent-id>)"`. `muse resume ""` refuses ("session name must not be empty", exit 2) with or without a TTY, so a failed fork never opens a session. The form is valid in bash, zsh, and fish 3.4+; `id=$(…)` is not valid in fish.
- Executable naming: the absolute path of the running `agent-fork`. Under `uvx --isolated` it lives in the uv cache (`~/.cache/uv/archive-v0/…/bin/agent-fork`) and still exists after exit; it disappears only if the uv cache is cleaned.
- Working directory: `muse serve` forks from a non-repository, untrusted directory (echo store), so the fork step may run inside the new worktree.
- Shutdown (real provider): with a session loaded, `muse serve` did not exit within 30 s of stdin EOF; SIGTERM ended it in 2.4 s (rc 143). After `session/leave` with `stop: true`, it exited 2.5 s after EOF with rc 0 and wrote `session.end`; without that record the next resume warns "ended abnormally". After `session/fork` only the new fork is loaded, so only the fork is left.
- Transcript lookup: glob `<muse data dir>/sessions/*/*/*/<id>/session.jsonl`, like the Codex rollout lookup; no dependency on the unpublished `session-index.db` schema.
- Re-paste idempotency: out of scope (Q3.A, parity).

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
- Signal precedence (Q4.A, 2026-11-13): `MUSE_SESSION_ID` together with Claude or Codex signals is `ambiguous`; automatic detection refuses with `agent_not_detected` and the user passes `--agent`. This changes the result for such mixed environments only.
- Live check (Q5.A, 2026-11-13): `P08-TS06` may create one more throwaway fork in the scratch pilot repository.
- Parity (Q3.A, 2026-11-13): match Claude Code and Codex. Re-pasting makes a second fork, as with them; Muse-only idempotency is out of scope.

### Tests & Tasks
- [x] [P08-T01] Pilot gate, before any implementation, with owner consent (it leaves a fork that cannot be deleted). Use a real-provider parent open in the Muse TUI. Run the fork step from the untrusted fork worktree, recording which provider and credentials `muse serve` needs. Accept the trust prompt and resume. Confirm that a real tool call such as `pwd` lands in the worktree, and that the invoking turn is present in the fork. If the pilot fails, fall back to option B: refuse `fork --agent muse` with a typed error.
      Passed 2026-11-13 (Muse 1.4.20, real provider `muse-spark-1.3-contributor`, owner decision Q1.A: throwaway session in a scratch repo). The parent `01a1d722-3e08-78b3-8ef6-9624efa87d7e` was open in the TUI and its invoking turn had finished. A stand-in for the hidden subcommand, run from the parent checkout (not from the worktree), ran `muse serve` with no provider flag and no trust flag, then `session/fork`, which created fork `00000000-0000-7e89-a143-57729763e0d9`. `cd <child> && muse resume <fork>` showed Muse's "Do you trust this workspace?" prompt; after "Trust and continue" the fork resumed with the invoking turn present. A tool call `pwd && git branch --show-current` printed the child path and `pilot-child`.
      Implementation findings: (1) with the real provider, `muse serve` did not exit within 10 s of stdin EOF; the client must bound the wait and terminate the host. (2) The resumed fork warned "the previous run of this session ended abnormally"; the client should shut the host down cleanly (check `session/leave`). (3) The `id=$(…) && …` form stopped correctly when the fork step failed. (4) Re-running the paste command makes another permanent fork.
- [ ] [P08-TS01] RED: detection. `MUSE_SESSION_ID` alone is detected as `muse`; together with Claude or Codex signals it is `ambiguous`, as in P07 and P09; `--agent muse` with `--parent-session`; `resolve_agent_mode` (T-DET rows)
- [ ] [P08-TS02] RED: preflight. `muse` missing from PATH; non-UUID parent refused; parent transcript missing is `session_not_found`; `muse --help` lacking `resume` or `serve` gives a notice (T-PRE rows)
- [ ] [P08-TS03] RED: MSP fork client against a fake `muse serve`. Success prints only the fork ID; an error reply, a timeout, an early exit, or oversized output is `muse_fork_failed` (exit 3); the client sends `session/leave` (`stop: true`) for the new fork before closing stdin, and a host that lingers is terminated within the bound (T-SES or new group rows)
- [ ] [P08-TS04] RED: commands and inspection. The paste command is `cd <dir> && muse resume "$('<agent-fork>' muse-fork <parent>)"` with every value quoted (`<agent-fork>` is the absolute path of the running executable) and `agents.muse.extra_args` appended; resume is `cd <dir> && muse resume <id>`; the transcript is `$XDG_DATA_HOME/muse/sessions/*/*/*/<id>/session.jsonl`; terminal-unsafe input refused (T-SES rows)
- [ ] [P08-TS05] RED: CLI surface. `fork --agent muse --dry-run --json`; `muse-fork` is absent from `--help`; completion lists `muse`; `config` accepts `agents.muse.extra_args`; `doctor` reports Muse; the README exit-code table lists `muse_fork_failed` (T-CLI, T-CFG, T-OUT rows)
- [ ] [P08-T02] GREEN: detection and `--agent` choices (`agents.py`, `cli.py`, `completion.py`)
- [ ] [P08-T03] GREEN: Muse preflight in `preflight_agent`
- [ ] [P08-T04] GREEN: bounded MSP client module, hidden `muse-fork` subcommand, `muse_fork_failed` in `ERROR_CATALOG`
- [ ] [P08-T05] GREEN: native-command rendering, session inspection, transcript lookup
- [ ] [P08-T06] GREEN: `agents.muse.extra_args` config, doctor row
- [ ] [P08-T07] TEST-MATRIX rows and recount; README (agent support, Muse section, exit-code table); skill references; version bump
- [ ] [P08-T08] Gate: `make check`, `just all`, `just check-matrix`, `just strict-collect`, `just clean-install`
- [ ] [P08-T09] Adversarial review gate: an independent Claude reviewer and Codex; fix or answer every finding
- [ ] [P08-TS06] Live verification: inside a real Muse session, `agent-fork fork --agent muse` (built from this branch) creates the worktree, and the printed paste command forks and resumes there
- [ ] [P08-T10] One PR (doc, flips, and implementation together), merge commit, tag
- [ ] Regression Test Status

### Probe findings (2026-11-13, Muse Code 1.4.20, `--provider echo`, isolated `XDG_DATA_HOME`)
- **Native fork exists, only over MSP.** `muse schema generate-json-schema` lists stable method `session/fork` (`SessionForkParams`: `commandId` UUIDv7, `sessionId`, optional `cutPoint.lastTurnId`, `excludeItems`). Reached via `muse serve` (newline-delimited JSON-RPC on stdio: `initialize`, then the `initialized` notification, then calls). No CLI `fork` verb. The real index's 4 existing forks all carry `msp_fork_command_id`.
- **Fork copies completed turns only.** With `cutPoint` omitted the fork takes "all completed turns", so an in-flight parent turn (the one running agent-fork) is not copied. Not yet confirmed against a live session.
- **Fork works while another host holds the parent.** Host A `session/resume`d the parent and held it; host B's `session/fork` succeeded.
- **Fork inherits the parent's workspace.** `session/fork` from a host whose cwd is the child worktree returned `workspaceRoot` = parent. `session/fork` and `session/resume` take no workspace parameter; only `session/start` does.
- **Rebinding the fork to the child worktree.** From the child's cwd, `muse exec --session-id <fork>` refuses ("was created in workspace <parent>; refusing to resume in workspace <child>"), with or without `--workspace <child>`. `--allow-workspace-switch` works for one run but does not persist, and is not a `resume` or root flag. From the **parent** cwd, `muse exec --session-id <fork> --worktree existing --worktree-existing <child>` binds the turn to the child and writes a durable `session.workspace_scope.activated` record. After that, plain `muse exec --session-id <fork>` from either cwd reports `workspace root: <child> (explicit)`.
- **Interactive `muse resume` binds to the cwd** (echo provider, `--trust-workspace`, parent made by `muse exec`; the exact paste command is unrun). Verified in real Rex terminal tabs, each on a fresh, never-resumed fork, with a turn submitted and the live `workspace_branch.observed` record (`probe_ran: true`) read back. `cd <child> && muse resume <fork>` bound the turn to the child (branch `child`) with no rebind flags. `cd <parent> && muse resume <fork> --worktree existing --worktree-existing <child>` also bound it to the child and wrote a durable `session.workspace_scope.activated` record. Only `muse exec` refuses a workspace change. (Bare pty attempts stalled at "Restoring conversation"; the resume-time records seen there replay stored metadata, with `command_id` equal to the session ID, and do not show the live binding.)
- **No delete method.** The MSP method list has no `session/delete`, so agent-fork cannot remove a fork it created.
- **Transcript.** `sessions/YYYY/MM/DD/<uuid>/session.jsonl` under the Muse data dir (`$XDG_DATA_HOME/muse`, default `~/.local/share/muse`). Also `Session.path` over MSP, `session_log_path` in `session-index.db`, and `muse export --session <uuid|path> --out <file>` (offline JSON, `export_schema_version` 1).
- **Workspace keys are per checkout path.** `workspace_key` equals the checkout path, so every git worktree is its own workspace.
- **Trust gate.** Headless subcommands (`muse export`, `muse resume --help`) refuse in a workspace whose trust is undecided ("pass --trust-workspace"). A fresh fork worktree is always such a workspace. `--trust-workspace` must come after the subcommand; before it, Muse starts the TUI.

