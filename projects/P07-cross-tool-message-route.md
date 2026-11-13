# P07 — cross-tool message route

**References**
- **Trunk:** [PROJECTS.md](../PROJECTS.md)
- **Prior art:** [P06 — session messaging name](P06-session-messaging-name.md)
- **Discussion:** owner request 2026-11-12, option A: report how to message the
  current session for Codex, Muse, and OpenCode as well as Claude Code, without
  making Muse or OpenCode full agents (that is P08 and P09).

## [x] Project P07: cross-tool message route (v1.4.0)
**Goal**: `agent-fork session` reports a new `message_route` object saying how
another session can send this session a message, for Claude Code, Codex, Muse,
and OpenCode. The P06 `messaging` object keeps its shipped contract.

Evidence (probed 2026-11-12 with clean environments; installed versions Codex
0.167.2, Muse Code 1.4.18, OpenCode 2.2.7):
- Codex: `codex queue --thread <session UUID or exact name> --message <text>`
  queues a message; the thread reads it when it next runs.
- Muse sets `MUSE_SESSION_ID` (and `MUSE_THREAD_ID`, same value) for its
  commands and no Claude variables. `muse session-message send --target
  <uuid-or-name>` reads the body on stdin, but refuses senders it cannot
  verify (`sender_unverified`, from a shell and from `muse exec`), so Muse is
  reported as address only. `muse sessions --json` lists running
  sessions with `sessionId` and `name`.
- OpenCode sets `OPENCODE=1` and `OPENCODE_SESSION_ID` (`ses_` plus letters and
  digits). It has no messaging command; `opencode run --session <id>` starts a
  model turn and creates the session if the ID is unknown, so it is not
  reported as a send command.

`message_route` fields: `agent` (`claude`, `codex`, `muse`, `opencode`, or
null), `status`, `address`, `name`, `channel`, `command`, `message_via`.
Statuses:
- `available`: `command` is an exact shell command; the message goes as its
  final argument (`message_via: argument`) or on stdin (`message_via: stdin`)
- `address_only`: an address but no shell command (Claude: the `SendMessage`
  tool; OpenCode: no verified delivery command)
- `not_running`: Claude session with no live registry entry
- `not_detected`, `ambiguous` (signals from more than one tool, since presence
  alone cannot show which session is nested in which), `unsafe_input`

Also: when Muse or OpenCode signals are present, P06 `messaging` reports
`not_applicable` instead of the outer Claude session's name.

**Out of Scope**
- Making Muse or OpenCode agents for fork, resume, or transcript (P08, P09).
- Changing `agent`, `fork_command`, `resume_command`, or `messaging` statuses.
- Proving which Codex version introduced `codex queue` (documented as present
  in 0.167.2, not as a minimum).

### Tests & Tasks
- [x] [P07-TS01] RED: route detection truth table (none, each tool alone,
      mixed signals ambiguous, unsafe IDs, OpenCode `ses_` pattern), and P06
      `messaging` becoming `not_applicable` under Muse/OpenCode signals (T-SES-54)
- [x] [P07-TS02] RED: Muse name lookup via a fake `muse sessions --json`:
      found, absent, timeout, malformed output (T-SES-55)
- [x] [P07-TS03] RED: CLI `message route:` line and `--json` object with exact,
      quoted commands and terminal escaping (T-SES-56); `document()` shape (T-SES-57)
- [x] [P07-T01] GREEN: `SessionMessageRoute` and resolver in `session.py`
- [x] [P07-T02] GREEN: CLI line and help epilog
- [x] [P07-T03] Version bump to 1.4.0; TEST-MATRIX rows; `just check-matrix`
- [x] [P07-T04] Skill: show `message_route` when present; unknown status shown
      raw, never fatal; output references gain the row
- [x] [P07-T05] README section
- [x] Regression Test Status: `just all` (769 passed, 1 skipped), `make check`, and `just check-matrix` green
- [x] [P07-TS04] Live verification 2026-11-12: inside a real Muse session the CLI printed the Muse route with the name `wood-fenrir` from `muse sessions --json`; inside a real OpenCode session it printed the `ses_` address; `codex queue` queued a message to a throwaway thread (exit 0). `muse session-message send` to an interactive session (`dawn-asteroid`, opened by the owner) found the target but returned `sender_unverified` from a shell and from `muse exec`, so the Muse route was changed to `address_only`
- [x] [P07-T06] PR merged (#76, merge 33c294d, tag v1.4.0)
