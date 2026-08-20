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
- The generated `agents/openai.yaml` metadata: it is generator-managed and
  its `short_description`/`default_prompt` remain accurate (not exhaustive)
  without a resume mention, so it is left untouched rather than hand-edited
  without the generator.
- Registry persistence / re-emitting a *past* fork's session ID (that is
  P03-B2) — this item only concerns the live `session` inspection command.

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
      for `fork_command`); regenerated `uv.lock` and the hardcoded
      `--version` test
- [x] [P04-T06] TEST-MATRIX.md: registered `T-EMT-11..13` and `T-SES-36..38`
      rows, marked the 6 new tests, updated the total-row count; `just
      check-matrix` (the CI gate at `.github/workflows/ci.yml:29`, not part
      of `just all`) is clean
- [x] [P04-T07] Companion skill: `--session` route in
      `.agents/skills/agent-fork/SKILL.md` now validates and presents
      `resume_command` alongside `fork_command` (own "predates the
      resume_command contract" upgrade path), `--session-only` stays
      fork-only per the confirmed route decision; both
      `references/output-{claude,codex}.md` gained a resume-command
      example; README's skill-routes table row updated to match
- [x] [P04-T08] Owner-requested targeted quality pass on `session.py`'s
      `SessionInspection(...)` construction: the six-field repetition across
      5 of 7 call sites (amplified by `resume_command`) was analyzed with
      Fable (fresh-context review, no prior bias toward a specific fix).
      Recommendation: consolidate the 5 shared-tail sites (Claude main +
      4 Codex sites) behind a local `_inspection(...)` closure — the real
      risk isn't the repetition itself but the two *defaulted* fields
      (`notices`, `agent_signal`), where a future site could omit them with
      no type error and silently drop notices; `dataclasses.replace()` was
      rejected (would freeze `notices` before the 7 later `.append()` calls
      and requires a semantically-false placeholder base instance). Leave
      the 2 early-return sites alone — different shape (literal
      fork/resume command values, no `current_session` yet), not worth
      forcing into the same helper. Implemented as recommended, scoped only
      to this function; `just all` re-run green with identical counts (461
      passed, 1 skipped, 9 deselected) before and after — pure refactor, no
      behavior change.
- [x] Regression Test Status: `just all` and `just check-matrix` green
      (fmt, lint, typecheck, hermetic tests incl. skill contract tests)

### Deliverable
`agent-fork session` (human and `--json`) reports both `fork_command` and
`resume_command`; `agent-fork session --help` documents both.

### Automated Verification
- `make check` passes; `just all` green
- New tests pass; no existing test's behavior changed (only two direct
  `SessionInspection(...)` constructions gained the new required argument)

### Manual Verification
- Ran `agent-fork session` in this worktree with real Claude Code session
  env vars set: output included both
  `fork command: cd <dir> && claude --session-id <fresh-uuid> --resume
  <this-session-id> --fork-session` and
  `resume command: cd <dir> && claude --resume <this-session-id>`.
  Codex's `-C` flag on `resume` was independently confirmed against the
  installed `codex resume --help` (not run end-to-end — no live Codex
  session in this conversation).
