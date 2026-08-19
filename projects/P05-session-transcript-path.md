# P05 — session transcript path

**References**
- **Trunk:** [PROJECTS.md](../PROJECTS.md)
- **Plan:** [2026-08-19-session-transcript-path.md](../docs/superpowers/plans/2026-08-19-session-transcript-path.md)
- **Prior art:** [P04 — session resume (rehydrate) command](P04-session-resume-command.md)
- **Discussion:** owner request 2026-08-19 — expose the active session's
  transcript file path through the companion skill, scoped and confirmed in
  conversation with four explicit decisions (Codex rollout file; `--session`
  surface only; `path` plus `exists` flag; investigation merged into one plan)

## [x] Project P05: session transcript path (v1.2.0)
**Goal**: `agent-fork session` already reports the session's identity, its
repository context, and its fork and resume commands. Add the **transcript
path**: the absolute path and filename of the file where the active session's
conversation is stored on disk, so the companion skill can hand it to the user
or to a downstream tool.

- Claude Code: `<CLAUDE_CONFIG_DIR|~/.claude>/projects/<encoded-directory>/<session-id>.jsonl`,
  where `<encoded-directory>` is the resolved invocation directory with every
  non-alphanumeric character replaced by `-`
- Codex: `<CODEX_HOME|~/.codex>/sessions/<YYYY>/<MM>/<DD>/rollout-<timestamp>-<thread-id>.jsonl`,
  located by glob because the filename embeds a timestamp

New JSON field `transcript` (`path` plus `exists`), folded into the existing
`--session` route only — no new CLI subcommand, no new skill argument.

**Out of Scope**
- Reading, parsing, summarizing, copying, or truncating transcript contents.
  This item reports a location only.
- Correcting the directory-encoding limitation: the Claude path is derived
  from the directory `agent-fork` was invoked in, so invoking it outside the
  session's own working directory derives a path that does not exist and
  reports `exists: false`. This is pre-existing behavior shared with
  session-name resolution; it is documented, not changed. (Verified
  2026-08-19: Claude Code re-keys its transcript folder when the session's
  directory changes, so an in-session invocation from a linked worktree the
  session moved into resolves correctly — the failure mode is invoking from
  an unrelated directory.)
- `--session-only`, which by design prints only `fork_command.command`.
- The generated `agents/openai.yaml` metadata, which is generator-managed.

### Tests & Tasks
- [x] [P05-TS01] RED: `codex_rollout_path()` resolves the matching rollout file
      deterministically and stays consistent with `codex_rollout_exists()`
      (`tests/unit/test_codex_resolution.py`)
- [x] [P05-TS02] RED: transcript resolution truth table — Claude derived path
      present and absent, Codex glob hit and miss, terminal-unsafe ID, and no
      ambient identity (`tests/unit/test_session.py`)
- [x] [P05-TS03] RED: `document()` includes the additive `transcript` object
      (`tests/unit/test_session.py`)
- [x] [P05-TS04] RED: CLI `session` human line and `--json` object, with
      terminal escaping (`tests/cli/test_session.py`)
- [x] [P05-T01] GREEN: `codex_rollout_path()` in `agents.py`;
      `codex_rollout_exists()` delegates to it
- [x] [P05-T02] GREEN: `SessionTranscript` dataclass, `_session_transcript()`
      resolver, and the `transcript` field wired through every
      `SessionInspection` construction site and `document()` in `session.py`
- [x] [P05-T03] GREEN: `transcript: ...` CLI line and `session --help` epilog
      in `cli.py`
- [x] [P05-T04] Version bump `1.1.0` to `1.2.0` via `just bump minor`
- [x] [P05-T05] TEST-MATRIX.md: register `T-SES-39..42`, mark the four new
      tests, update the total-row count; `just check-matrix` clean
- [x] [P05-T06] Companion skill: `--session` route presents and validates
      `transcript` with its own "predates the transcript contract" upgrade
      path; `--session-only` untouched; both
      `references/output-{claude,codex}.md` gained a transcript row
- [x] [P05-T07] README: document the field, both storage layouts, and the
      directory-encoding caveat
- [x] Regression Test Status: `just all` and `just check-matrix` green

### Deliverable
`agent-fork session` (human and `--json`) reports the active session's
transcript path alongside `fork_command` and `resume_command`.

### Automated Verification
- `make check` passes; `just all` green — 479 passed, 1 skipped, 9 deselected
  (fmt, lint, ty, version-check, hermetic tests)
- `just check-matrix` clean at 408 rows
- 5 tests added (4 matrix-marked plus the unmarked skill-contract test); the
  only existing tests changed are the two direct `SessionInspection(...)`
  constructions that gained the new required argument

### Manual Verification
- Ran `agent-fork session` in this worktree inside a live Claude Code session
  (`0636761f-8126-4dd7-8be5-9fcfd995e16d`). Output:
  `transcript: /Users/stevemorin/.claude/projects/-Users-stevemorin-c-agent-fork--claude-worktrees-p05-session-transcript-path/0636761f-8126-4dd7-8be5-9fcfd995e16d.jsonl (exists)`.
  `ls -l` confirmed the file (1,917,373 bytes); parsing it confirmed 1,380
  records whose only non-null `sessionId` is that session's own ID — so the
  reported path is genuinely this conversation's transcript, not a
  coincidentally-named file.
- The `exists: false` branch was verified live by invoking the same binary from
  an unrelated directory (the session scratchpad), which reported `(missing)`
  against a path under that directory's encoding.
- **This run refuted a claim in the plan's first draft.** That draft asserted
  the `exists: false` case arises when a session started in a main checkout is
  inspected from a linked worktree. It does not: Claude Code re-keys its
  transcript folder when the session's directory changes, and no file remained
  under the original directory's encoded folder. The README, SKILL.md, this
  file, and the plan were corrected to name the real trigger — invoking the
  CLI from a directory other than the session's own.
- Codex was not exercised end-to-end (no live Codex session in this
  conversation); its rollout resolution is covered by T-SES-42 and the Codex
  branch of T-SES-39 against a fixture `CODEX_HOME`.
