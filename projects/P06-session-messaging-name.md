# P06 — session messaging name

**References**
- **Trunk:** [PROJECTS.md](../PROJECTS.md)
- **Prior art:** [P05 — session transcript path](P05-session-transcript-path.md)
- **Discussion:** owner request 2026-11-12. `agent-fork --session` reported a
  session's ID, but not the name other Claude Code sessions use to message it
  (`SendMessage`/`ListAgents`), so a forked session could not be addressed.
  Option A chosen: a separate "Message as" field read from Claude Code's
  live-session registry.

## [~] Project P06: session messaging name (v1.3.0)
**Goal**: `agent-fork session` reports the name the current Claude Code session
can be messaged by right now. Claude Code keeps one live-session registry file
per running process at `<CLAUDE_CONFIG_DIR|~/.claude>/sessions/<pid>.json`;
the entry whose `sessionId` matches holds that name (for example `c-87`, with
`nameSource: derived`). The existing "Session name" stays as it is: it reports
a `/rename` title from the transcript, which is a different value.

New JSON field `messaging` (`name`, `status`, `name_source`), folded into the
existing `--session` route only, and one human line `message as: ...`.
Statuses:
- `live`: a registry entry matches and its process is running
- `not_running`: no matching entry, or the matching entry's process has exited
- `unavailable`: the registry exceeds agent-fork's read bounds
- `not_applicable`: not a Claude Code session (Codex, no agent, ambiguous)

**Out of Scope**
- Codex: it has no cross-session messaging registry.
- Treating the name as stable: a derived name can change and exists only while
  the session runs. Output says "currently addressable as", not identity.
- Requiring the field in the companion skill's contract: older CLIs simply
  omit it, and the skill shows it only when present.
- `--session-only`, which prints only `fork_command.command`.

### Tests & Tasks
- [x] [P06-TS01] RED: registry resolution truth table: live match, dead pid,
      no entry, malformed and oversized files skipped, non-string name,
      Codex and no-agent `not_applicable` (`tests/unit/test_session.py`, T-SES-51)
- [x] [P06-TS02] RED: `document()` includes the additive `messaging` object
      (`tests/unit/test_session.py`, T-SES-52)
- [x] [P06-TS03] RED: CLI `message as:` human line and `--json` object, with
      terminal escaping of a hostile registry name (`tests/cli/test_session.py`, T-SES-53)
- [x] [P06-T01] GREEN: `SessionMessaging` and `_session_messaging()` in `session.py`,
      wired through every `SessionInspection` construction site
- [x] [P06-T02] GREEN: `message as:` CLI line and `session --help` epilog in `cli.py`
- [x] [P06-T03] Version bump `1.2.1` to `1.3.0` via `just bump minor`
- [x] [P06-T04] TEST-MATRIX.md: register T-SES-51..53, update the total; `just check-matrix` clean
- [x] [P06-T05] Companion skill: `--session` shows `messaging` when present
      (optional field, no new "predates" diagnostic); `references/output-claude.md`
      gains the row
- [x] [P06-T06] README: document the field and its liveness caveat
- [x] Regression Test Status: `just all` (765 passed, 1 skipped) and `just check-matrix` green; `make check` green. Live check in Claude Code session `shelf-0c`: `message as: shelf-0c (live)`
- [ ] [P06-T07] PR merged; tag `v1.3.0`
