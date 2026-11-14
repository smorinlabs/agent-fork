# P09 — OpenCode as a full agent-fork agent

**References**
- **Trunk:** [PROJECTS.md](../PROJECTS.md)
- **Depends on:** P07 — [cross-tool message route](P07-cross-tool-message-route.md); P09 changes its OpenCode row
- **Discussion:** https://github.com/smorinlabs/agent-fork/pull/76 (P07 merge, where the OpenCode `address_only` route shipped)
- **Prior art:** [P04 — session resume command](P04-session-resume-command.md) (the `resume_command` contract OpenCode fills)
- **Prior art:** [P05 — session transcript path](P05-session-transcript-path.md) (the `transcript` contract; OpenCode has no transcript file)
- **Prior art:** [README `message_route` section](../README.md) (its OpenCode row and "no messaging command" text change)

## [~] Project P09: OpenCode as a full agent-fork agent (v1.6.0)
**Goal**: agent-fork treats OpenCode the way it treats Claude Code and Codex:
it detects an OpenCode session, forks it, and resumes it. Owner decision
2026-11-13: same capabilities as Claude Code and Codex, mapped the same way,
with no contract extensions. The report fields that already exist for every
agent (`transcript`, `message_route`, `messaging`) keep their contracts.

### Scope
1. **Detection (Codex rule, decided 2026-11-13 for least change).**
   `opencode` becomes an agent in the single `assess_agent_signals`
   assessment (`agents.py`). `OPENCODE_SESSION_ID` alone detects it, as
   `CODEX_THREAD_ID` alone detects Codex; `OPENCODE=1` alone is `absent`, so
   the Claude-only `incomplete` state is untouched. `OPENCODE_SESSION_ID`
   together with any Claude or Codex signal is `ambiguous`. `fork --agent`
   accepts `opencode`. IDs are validated by `OPENCODE_SESSION_ID` (`ses_…`);
   the shared `SAFE_SESSION_ID` stays unchanged. P07's `message_route` keeps
   its own rule (either variable counts).
2. **Existence preflight.** Before a fork, `opencode api session.get
   --param sessionID=<id>` must succeed; otherwise the fork refuses with
   `session_not_found` (see item 8). Reason: `opencode --session <unknown>`
   silently creates a new session.
3. **Fork as the last step (owner decision 2026-11-13, design A, lighter
   ordering).** The worktree, file copy, submodules, setup hook, and fork
   registry run unchanged first. Only after they all succeed does agent-fork
   call `session.fork` and then `session.move` into the worktree. It then
   builds the paste command `cd <worktree> && opencode --session <child>`
   from the child ID. No model turn runs. The only compensation is: if
   `session.move` fails, delete the just-created child. Worktree rollback
   (`run_with_rollback`) needs no OpenCode knowledge. This is the first fork
   in which agent-fork changes agent state itself; Claude and Codex forks
   happen only when the owner pastes the command. The OpenCode paste command
   is built after the fork, not before; Claude and Codex keep their order.
4. **Resume and the session report's commands.** `resume_command` is
   `cd <dir> && opencode --session <id>`. `fork_command` (owner decision
   2026-11-13) is one copy-paste line that forks the conversation through
   the API and then opens the child:
   `cd <dir> && child=$(opencode api session.fork --param sessionID=<id> -d '{}' | sed -n 's/^{"data":{"id":"\(ses_[A-Za-z0-9]*\)".*/\1/p') && [ -n "$child" ] && opencode --session "$child"`.
   `sed` instead of `jq` adds no dependency. The `[ -n "$child" ]` guard
   is required because the pipeline hides `opencode api`'s exit status;
   probed: an unknown parent stops the line with exit 1.
7. **Name and lineage, as for Codex (owner decision 2026-11-13).** The
   session report's `current_session` name and `parent_session` come from
   `opencode api session.get` (`title`, `fork.sessionID`), as Codex reads
   `name` and `forked_from_id` from its app server. A failed call reports
   `unavailable` with a notice, as Codex does.
8. **Parity surfaces.** `session validate --agent` accepts `opencode`.
   `agent-fork doctor` checks the OpenCode version and that `opencode --help`
   declares `--session`, as it does for the Claude and Codex recipe flags.
   A missing parent session reuses `AgentPreflightError` (`session_not_found`,
   exit 3), the error Codex uses for a missing rollout, so no new error code
   is added. `[agents.opencode] extra_args` mirrors the Claude and Codex
   tables (appended to the paste command; survives `config set`).
9. **Fork boundary: full copy (owner decision 2026-11-13).** A fork run from
   inside an OpenCode turn copies the history as it stands, ending on the
   unanswered prompt that asked for the fork; no "stop before the current
   turn" logic.
5. **Transcript: existing contract.** OpenCode has no per-session file, so
   `transcript` reports `{path: null, exists: false}`. No new field.
6. **Messaging: unchanged.** `message_route` stays `address_only`, the
   same status Claude reports (P07). `messaging` stays Claude-only.

### Out of scope
- Muse (P08).
- The P02 fault register.
- Changing Claude or Codex behavior, beyond the additive `transcript.command: null`.
- `--standalone` and custom `--server` OpenCode servers; only the background service.
- Contract extensions (owner decision 2026-11-13): a transcript `command`
  field (`opencode session export <id>`) and a `message_via: json_body`
  route for `opencode api session.prompt`. Both were proven by probes (see
  Evidence) and can return as a separate idea.
- A minimum OpenCode version: 2.2.7 is recorded as observed, not as a floor.
  The server describes its API as an "Experimental HttpApi surface".

### Evidence
Probed 2026-11-13 with OpenCode 2.2.7 (`/Users/stevemorin/.opencode/bin/opencode`),
background service at `http://127.0.0.1:49374`. Throwaway sessions were
created through the API and deleted afterwards; no model turn ran.
- `opencode session list` lists only the current project's sessions (an empty
  list in a new worktree), so it cannot serve as the existence check.
- `opencode api` exits 1 on any HTTP error and on an unreachable server
  (`Could not reach server … ECONNREFUSED`). An unknown ID returns
  `SessionNotFoundError` (HTTP 404).
- `session.prompt` with `delivery` `queue` or `steer` and `resume:false`
  admits the message into the session inbox (`session_inbox` table) without a
  model turn; to an unknown ID it returns 404 and creates nothing. The body
  must be a `-d` argument: `-d @-` from stdin fails with `Expected a valid JSON body`.
- Fork: `opencode run` refuses to start without a message (`You must provide
  a message`), so the day-1 recipe `opencode run --session <id> --fork`
  always starts a model turn. `session.fork` copied all 4 messages of a
  session into a child with no model turn; `session.move` re-homed the child
  into a linked worktree (same project ID as the main checkout) and left the
  parent unchanged. An empty session cannot be forked (HTTP 400,
  `Cannot fork empty session`).
- `opencode session export <id>` prints JSON with top-level keys `info` and
  `messages`; an unknown ID exits 1 with `Session not found`.
- Live TUI (owner opened one): a `queue` message sent with `session.prompt`
  appeared in the open TUI, so the TUI and the API share one session through
  the background service. `session.inbox.cancel` then exited 0 and the
  inbox listed empty, yet the message was delivered about 51 seconds later
  and ran a model turn: once a TUI shows a queued message, cancelling it
  through the API does not stop it. `session.active` stayed empty while the
  TUI was idle, so it reports running turns, not open TUIs.
- Stopped service (isolated `HOME` and XDG directories, own port 49991):
  `opencode api` starts the background service itself (about 1 second) and
  leaves it running; on a port already in use it fails after about 21
  seconds. `opencode service status` reports `stopped` or the URL and starts
  nothing. The owner's service was untouched.
- Mid-turn fork (owner's TUI ran `opencode api session.fork --param
  sessionID=$OPENCODE_SESSION_ID -d '{}'` from its shell tool): exit 0,
  child "Greeting (fork #1)" with boundary `through` the in-flight assistant
  message. The child's history excludes that unfinished assistant message
  and ends on the user prompt that asked for the fork, unanswered. Opening
  the child in a TUI started no turn and no second fork; the prompt simply
  shows as the last message. The child was deleted afterwards.

- Manual proof of the last-step fork (2026-11-13): scratch repo
  `~/tmp/p09-poc-repo` with linked worktree `~/tmp/p09-poc-wt` created first;
  then `session.fork` (child `ses_e28dc03bdffey68mUW28f9PNEU`) and
  `session.move` into the worktree both exited 0. `opencode session list`
  run inside the worktree lists the child. The child holds the parent's 1
  user and 2 assistant messages, plus `idle` and `location-switched` marker
  rows; the parent is unchanged. Failure path: `session.move` to a missing
  directory returns HTTP 400 `Directory does not exist` (exit 1), and
  `session.remove` then deletes the child. TUI check (run in a Rex tab with
  `cd ~/tmp/p09-poc-wt && opencode --session <child>`, no prompt sent): the
  TUI opened on the child "(fork #1)", showed the parent's conversation and
  the marker `Moved to /Users/stevemorin/tmp/p09-poc-wt`, and its status bar
  read `~/tmp/p09-poc-wt:poc-fork`. Child, repo, and worktree were deleted
  afterwards.

- Output streams (2026-11-13, read-only, real CLI): `opencode api
  session.get` for an unknown ID exits 1 with the JSON body
  (`SessionNotFoundError`) on stdout and `HTTP 404 Not Found` on stderr;
  `opencode service status` prints the URL on stdout. The first test fake
  printed the status line on stdout, which hid a bug where every refusal
  was treated as uncertain; the fake now matches the real streams.
- Integration with P08 (2026-11-13): P08 (Muse as a full agent, PR #80)
  merged first as 1.5.0, so P09 targets 1.6.0. OpenCode joins P08's
  agent tables (`AGENT_NAMES`, labels, session-ID variables); Muse plus
  OpenCode signals are `ambiguous`. P08 forks Muse inside the paste command
  (`muse resume "$(agent-fork muse-fork <id>)"`), so nothing changes until
  the owner pastes; P09 forks OpenCode as the pipeline's last step, as the
  owner chose before P08 landed.

### Open questions
- [answered 2026-11-13] Is there a supported way to deliver a message into a
  running OpenCode session? Yes: `opencode api session.prompt` with
  `delivery: queue`, which lands in `session_inbox` (see Evidence).
- [answered 2026-11-13] Does a client reach an already-open TUI session
  through the background service, or a separate copy? The same session: a
  queued message appeared in the owner's open TUI.
- [answered 2026-11-13] Fork through the API or through a paste command?
  Through the API (design A), as the last step; `run --fork` requires a
  message and a model turn.
- [answered 2026-11-13] What does `opencode api` do when the background
  service is stopped? It starts the service. So the fork path may start it,
  while the read-only session report first runs `opencode service status`
  and reports name and lineage `unavailable` when the service is stopped.
  Every `opencode api` call gets a time limit.

### Notes
OpenCode sets `OPENCODE=1` and `OPENCODE_SESSION_ID` (`ses_` plus letters and
digits) for commands (probed 2026-11-12, OpenCode 2.2.7, clean environment).
IDs contain `_`, which `SAFE_SESSION_ID` rejects, so they need their own pattern.
Sessions live in `~/.local/share/opencode/opencode.db` (tables `session_v2`,
`session`, `session_message`, `session_inbox`). Resume: `opencode --session
<id>` (creates the session if the ID is unknown). Fork: corrected 2026-11-13,
`opencode run --session <id> --fork` needs a message and starts a model turn;
use `session.fork` plus `session.move` instead. Transcript: `opencode session
export <id>` (JSON).

### Tests & Tasks
Test IDs are the next free rows in `docs/testing/TEST-MATRIX.md`; tests use a
fake `opencode` executable, never the real service.
- [x] [P09-TS01] RED: detection. `OPENCODE_SESSION_ID` (with or without
      `OPENCODE=1`) assesses as `detected`; `OPENCODE=1` alone is `absent`;
      OpenCode plus Claude or Codex signals are `ambiguous`; explicit
      `--agent opencode --parent-session <id>` wins (T-DET-27…31). Unsafe IDs
      are refused in preflight (T-PRE-34)
- [x] [P09-TS02] RED: preflight. Missing binary, version read, `session.get`
      404 and unreachable server both refuse with `session_not_found` (exit 3)
      before any mutation; help lacking `--session` adds a notice (T-PRE-31…)
- [x] [P09-TS03] RED: fork pipeline (tier F). The OpenCode fork runs only
      after the worktree, copy, hook, and registry succeed; the printed command
      is `cd <wt> && opencode --session <child>`; a failed `session.fork`
      rolls the worktree back; a failed `session.move` deletes the child and
      rolls the worktree back (T-RBK-17…, T-EMT-14…)
- [x] [P09-TS04] RED: session report. `fork_command` is the one-line API fork
      with the `[ -n "$child" ]` guard; `resume_command`; `transcript` is
      `{path: null, exists: false}`; name and parent from `session.get`, and
      `unavailable` plus a notice when it fails; `message_route` unchanged
      (T-SES-58…)
- [x] [P09-TS05] RED: CLI and doctor. `fork --agent opencode` and
      `session validate --agent opencode` accepted, help text names OpenCode;
      doctor reports the OpenCode version and its `--session` flag (T-CLI-71…)
- [x] [P09-T01] GREEN: `AgentName` gains `opencode`; `assess_agent_signals`
      and `detect_agent`
- [x] [P09-T02] GREEN: OpenCode branch in `preflight_agent`
- [x] [P09-T03] GREEN: last-step fork in `pipeline.fork` with child deletion
      on a failed move
- [x] [P09-T04] GREEN: session report commands, transcript, name and lineage
- [x] [P09-T05] GREEN: CLI choices, help, and doctor checks
- [x] [P09-T06] Version bump to 1.6.0 (P08 took 1.5.0); TEST-MATRIX rows and the `agent` axis;
      `just check-matrix`
- [x] [P09-T07] README (OpenCode as an agent, fork and resume rows) and the
      `agent-fork` skill
- [x] Regression Test Status (2026-11-13): `make check`, `just all` (801
      passed, 1 skipped), `just check-matrix`, `just strict-collect`,
      `just clean-install` (wheel), and `just test-signals` (16 passed)
- [ ] [P09-TS06] Live verification: from inside a real OpenCode session, run
      `agent-fork fork` and open the printed command; run the session
      report's `fork_command` line
- [~] [P09-T08] Adversarial review gate including Codex; fix findings.
      Round 1 (2026-11-13): Codex (7 findings) and a Fable whole-branch
      review (6 medium, 4 low). Fixed: dry run never starts a stopped
      service; fork compensation names an undeletable child with its
      recovery command, deletes a child with an invalid reply ID, and says a
      timed-out fork may have left one; the post-fork interrupt window is
      inside the compensation scope; whitespace-tolerant extraction in the
      session report's fork line, now executed in tests; move/remove replies
      not required to be objects; doctor's version probe bounded and
      escaped; tests strip every host `opencode` from PATH; a not-found
      session warns that its resume command would create one; stale docs.
      Documented, not fixed: an empty parent is refused only at the last
      step; `agent-fork cleanup` leaves the forked OpenCode session.
      (T-SES-62, T-RBK-21..22, T-CLI-75)
      Round 2 (2026-11-13), on fix commit 669673a: Codex marked 4 fixed and
      3 partial plus one new defect; Fable marked the rest fixed with three
      low items. Fixed: `fork_into` records the child in the caller's list as
      soon as its ID is known (T-RBK-23); an invalid-ID cleanup failure is
      reported; the "may have created a fork" hint appears only when the
      outcome is uncertain, not on an HTTP refusal; the doctor time limit
      applies only to OpenCode, so Git, Claude, and Codex probes are
      unchanged; tests shadow `opencode` with a failing stand-in instead of
      dropping PATH directories (which could drop Git); preflight failures
      point at `opencode service status`. Accepted as best effort and
      documented: an interrupt during `session.fork` itself, or in the few
      bytecodes before the ID is recorded, can leave a child that is not
      named. Remaining: Fable and Codex concurrence on this round's fixes is
      by inspection of the listed changes, not a third review run.
- [ ] [P09-T09] One PR, merge commit, tag v1.6.0
