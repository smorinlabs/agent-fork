# P05 — session transcript path

**References**
- **Trunk:** [PROJECTS.md](../PROJECTS.md)
- **Plan:** [2026-08-19-session-transcript-path.md](../docs/superpowers/plans/2026-08-19-session-transcript-path.md)
- **Prior art:** [P04 — session resume (rehydrate) command](P04-session-resume-command.md)
- **Discussion:** owner request 2026-08-19 — expose the active session's
  transcript file path through the companion skill, scoped and confirmed in
  conversation with four explicit decisions (Codex rollout file; `--session`
  surface only; `path` plus `exists` flag; investigation merged into one plan)

## [ ] Project P05: session transcript path (v1.2.0)
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
- Correcting the directory-encoding limitation: a Claude session started in a
  main checkout and inspected from a linked worktree derives a path under the
  original directory's encoded folder and reports `exists: false`. This is
  pre-existing behavior shared with session-name resolution; it is documented,
  not changed.
- `--session-only`, which by design prints only `fork_command.command`.
- The generated `agents/openai.yaml` metadata, which is generator-managed.

### Tests & Tasks
- [ ] [P05-TS01] RED: `codex_rollout_path()` resolves the matching rollout file
      deterministically and stays consistent with `codex_rollout_exists()`
      (`tests/unit/test_codex_resolution.py`)
- [ ] [P05-TS02] RED: transcript resolution truth table — Claude derived path
      present and absent, Codex glob hit and miss, terminal-unsafe ID, and no
      ambient identity (`tests/unit/test_session.py`)
- [ ] [P05-TS03] RED: `document()` includes the additive `transcript` object
      (`tests/unit/test_session.py`)
- [ ] [P05-TS04] RED: CLI `session` human line and `--json` object, with
      terminal escaping (`tests/cli/test_session.py`)
- [ ] [P05-T01] GREEN: `codex_rollout_path()` in `agents.py`;
      `codex_rollout_exists()` delegates to it
- [ ] [P05-T02] GREEN: `SessionTranscript` dataclass, `_session_transcript()`
      resolver, and the `transcript` field wired through every
      `SessionInspection` construction site and `document()` in `session.py`
- [ ] [P05-T03] GREEN: `transcript: ...` CLI line and `session --help` epilog
      in `cli.py`
- [ ] [P05-T04] Version bump `1.1.0` to `1.2.0` via `just bump minor`
- [ ] [P05-T05] TEST-MATRIX.md: register `T-SES-39..42`, mark the four new
      tests, update the total-row count; `just check-matrix` clean
- [ ] [P05-T06] Companion skill: `--session` route presents and validates
      `transcript` with its own "predates the transcript contract" upgrade
      path; `--session-only` untouched; both
      `references/output-{claude,codex}.md` gained a transcript row
- [ ] [P05-T07] README: document the field, both storage layouts, and the
      directory-encoding caveat
- [ ] Regression Test Status: `just all` and `just check-matrix` green

### Deliverable
`agent-fork session` (human and `--json`) reports the active session's
transcript path alongside `fork_command` and `resume_command`.

### Automated Verification
- `make check` passes; `just all` green
- `just check-matrix` clean
- New tests pass; the only existing tests to change are the two direct
  `SessionInspection(...)` constructions that gain the new required argument

### Manual Verification
- Run `agent-fork session` inside a real Claude Code session and confirm the
  printed `transcript:` path is the session's actual JSONL file, verified with
  `ls -l` on the printed path.
