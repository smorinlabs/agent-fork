# P09 — OpenCode as a full agent-fork agent

**References**
- **Trunk:** [PROJECTS.md](../PROJECTS.md)
- **Depends on:** P07 — [cross-tool message route](P07-cross-tool-message-route.md); P09 changes its OpenCode row
- **Discussion:** https://github.com/smorinlabs/agent-fork/pull/76 (P07 merge, where the OpenCode `address_only` route shipped)
- **Prior art:** [P04 — session resume command](P04-session-resume-command.md) (the `resume_command` contract OpenCode fills)
- **Prior art:** [P05 — session transcript path](P05-session-transcript-path.md) (the `transcript` contract; OpenCode has no transcript file)
- **Prior art:** [README `message_route` section](../README.md) (its OpenCode row and "no messaging command" text change)

## [ ] Project P09: OpenCode as a full agent-fork agent (v1.5.0)
**Goal**: agent-fork treats OpenCode the way it treats Claude Code and Codex:
it detects an OpenCode session, then forks it, resumes it, reports how to read
its transcript, and reports an exact command to message it.

### Scope
1. **Detection.** `opencode` becomes an agent in the single
   `assess_agent_signals` assessment (`agents.py`), from `OPENCODE=1` or
   `OPENCODE_SESSION_ID`. OpenCode signals together with another tool's
   signals are `ambiguous`, as in P07. `fork --agent` accepts `opencode`. IDs
   are validated by `OPENCODE_SESSION_ID` (`ses_…`); the shared
   `SAFE_SESSION_ID` stays unchanged.
2. **Existence preflight.** Before a fork or resume, `opencode api
   session.get --param sessionID=<id>` must succeed. A refusal is a new typed
   error in `ERROR_CATALOG` (`errors.py`) and in the README exit-code table.
   Reason: `opencode --session <unknown>` silently creates a new session.
3. **Fork (owner decision 2026-11-13, design A).** After the worktree exists,
   agent-fork calls `session.fork` and then `session.move` into the worktree,
   and prints `cd <worktree> && opencode --session <child>`. No model turn
   runs. If a later pipeline step fails, rollback deletes the child session.
   This is the first fork in which agent-fork changes agent state itself;
   Claude and Codex forks happen only when the owner pastes the command.
4. **Resume.** `resume_command` is `cd <session directory> && opencode
   --session <id>`, after the existence preflight.
5. **Transcript (owner decision, option C).** `transcript` gains a `command`
   field. OpenCode reports `{path: null, exists: true, command: "opencode
   session export <id>"}`; Claude and Codex report `command: null`. The
   `SessionTranscript` invariant changes from "exists needs a path" to
   "exists needs a path or a command".
6. **Messaging (owner decision, option B).** OpenCode's `message_route`
   becomes `available` with `command: opencode api session.prompt --param
   sessionID=<id> -d` and a new `message_via: json_body`: the final argument
   is the JSON object `{"text": <message>, "delivery": "queue"}`.

### Out of scope
- Muse (P08).
- The P02 fault register.
- Changing Claude or Codex behavior, beyond the additive `transcript.command: null`.
- `--standalone` and custom `--server` OpenCode servers; only the background service.
- `steer` delivery (injecting into a running turn).
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
  the background service. The probe message was then cancelled
  (`session.inbox.cancel`). `session.active` stayed empty while the TUI was
  idle, so it reports running turns, not open TUIs.

### Open questions
- [answered 2026-11-13] Is there a supported way to deliver a message into a
  running OpenCode session? Yes: `opencode api session.prompt` with
  `delivery: queue`, which lands in `session_inbox` (see Evidence).
- [answered 2026-11-13] Does a client reach an already-open TUI session
  through the background service, or a separate copy? The same session: a
  queued message appeared in the owner's open TUI.
- [answered 2026-11-13] Fork through the API or through a paste command?
  Through the API (design A); `run --fork` requires a message and a model turn.
- What does `opencode api` do when the background service is stopped:
  auto-start it, or fail? Not probed, to avoid stopping the owner's service.
  Cover both cases with fakes and probe during implementation.

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
