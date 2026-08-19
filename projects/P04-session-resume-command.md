# P04 — session resume (rehydrate) command

**References**
- **Trunk:** [PROJECTS.md](../PROJECTS.md)
- **Discussion:** owner request 2026-08-18 — add a resume/"rehydrate" command
  alongside the existing fork command in `agent-fork session`, scoped and
  confirmed in conversation (no separate design doc)

## [x] Project P04: session resume (rehydrate) command (v1.1.0)
**Goal**: `agent-fork session` already prints a **fork command** — the
paste-ready command that creates a *new* session (new session ID, new Git
branch/worktree, current files copied forward). Add a sibling **resume
command** ("rehydrate"): the paste-ready command that re-enters the *same*
session in place — same session ID, same directory, same branch/worktree,
continuing the same transcript, nothing new created. This is the command you
run to pick a session back up after setting it aside.

- Claude: `cd <dir> && claude --resume <session-id>`
- Codex: `codex resume <thread-id> -C <dir>` (verified against installed
  `codex resume --help`, which documents both the positional `[SESSION_ID]`
  and `-C, --cd <DIR>`)

New JSON field `resume_command` (status/command, same status enum as
`fork_command`), folded into the existing `--session` route only — no new
CLI subcommand, no new skill argument.

**Out of Scope**
- Companion skill (`.agents/skills/agent-fork/SKILL.md`) surfacing
  `resume_command` in its `--session` presentation, and the generated
  `agents/openai.yaml` metadata. Deferred: `openai.yaml` is generator-managed
  and regenerating it without the generator risks drift; flagged to the owner
  as a follow-up rather than hand-edited.
- Registry persistence / re-emitting a *past* fork's session ID (that is
  P03-B2) — this item only concerns the live `session` inspection command.
- TEST-MATRIX.md row registration (`docs/testing/TEST-MATRIX.md` /
  `scripts/check_matrix.py`) — new tests were written and pass under
  `just all`, but were not registered as `T-EMT-11..`/`T-SES-3x` rows to keep
  this change proportionate to its scope; `check-matrix` is not part of
  `just all` so this does not fail the standard gate.

### Tests & Tasks
- [x] [P04-TS01] RED: byte-exact resume-command template tests
      (`tests/unit/test_emt.py`: Claude, Codex, and the shell-injection/
      terminal-control-rejection proof, mirroring T-EMT-08/09/10)
- [x] [P04-TS02] RED: `SessionResumeCommand`/`resume_command` status-ladder
      and `.document()` tests (`tests/unit/test_session.py`, mirroring
      T-SES-28) plus two existing direct-construction tests updated for the
      new required field
- [x] [P04-TS03] RED: CLI `session` human + `--json` resume-command output
      tests (`tests/cli/test_session.py`, mirroring T-SES-30)
- [x] [P04-T01] GREEN: `build_session_resume_command` +
      `_render_native_command(..., mode="resume")` in `agents.py`
      (existing `fork`-mode callers untouched — default parameter)
- [x] [P04-T02] GREEN: `SessionResumeCommand` dataclass + `resume_command`
      field on `SessionInspection`, wired through every construction site
      and `.document()` in `session.py`
- [x] [P04-T03] GREEN: `resume command: ...` CLI text line + `--json`
      passthrough + `session --help` epilog/description in `cli.py`
- [x] [P04-T04] README: document `resume_command`, the fork-vs-resume
      distinction, and the two native command shapes
- [x] [P04-T05] Version bump `1.0.0` → `1.1.0` in `pyproject.toml` (additive
      JSON field, same class of contract change SKILL.md already documents
      for `fork_command`)
- [x] Regression Test Status: `just all` green (fmt, lint, typecheck,
      hermetic tests) — 460 passed, 1 skipped, 9 deselected

### Deliverable
`agent-fork session` (human and `--json`) reports both `fork_command` and
`resume_command`; `agent-fork session --help` documents both.

### Automated Verification
- `make check` passes; `just all` green
- New tests pass; no existing test's behavior changed (only two direct
  `SessionInspection(...)` constructions gained the new required argument)

### Manual Verification
- Not yet performed against a real Claude Code / Codex install — the new
  commands are read-only string templates verified via the existing
  shell-injection proof (subprocess execution of the rendered command against
  a fake `claude`/`codex` binary), the same technique the fork command uses
