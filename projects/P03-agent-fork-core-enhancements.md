# P03 — agent-fork core enhancements

**References**
- **Trunk:** [PROJECTS.md](../PROJECTS.md)
- **Depends on:** [P02 — agent-fork fault remediation](P02-agent-fork-fault-remediation.md) — owner sequenced faults first (2026-08-16); B2/B3 touch the registry schema that A3's fix migrates, so they must land after A3
- **Discussion:** enhancement analysis session 2026-08-16 (same three-agent sweep as P02's fault register)

## [ ] Project P03: agent-fork core enhancements (v1.x)
**Goal**: Ship the four core enhancements B1–B4 selected by the owner on
2026-08-16, each through the same gated process as P02: implementation plan
→ adversarial plan review (incl. Codex) → TDD + subagent-driven
implementation in its own worktree → adversarial post-implementation review
(incl. Codex). Auto-proceed on clean verdicts; pause and raise anything
that smells like scope creep or divergence from core functionality.

**Out of Scope**
- B5–B9 from the same analysis — dropped entirely by owner decision
  2026-08-16 (bulk/merged cleanup beyond what B1's `finish` needs, agent
  extensibility seam, JSON schema versioning, standalone test-coverage
  effort, Windows).
- Fault fixes — those are P02.
- jj backend, additional agents, handoff ladder — P01's deferred roadmap,
  unchanged.

### Enhancement register

- **B1 — Complete the fork lifecycle: `status`, `diff`, `sync`, and a
  merge-back/graduate verb.** The command tree today is creation and
  destruction with nothing in between; a fork that *worked* has no
  supported exit — no `merge|land|finish`, no `diff <name>` against parent,
  no `sync` onto a moved parent HEAD, no `status` answering "am I in a
  fork, of what, how far diverged". Users drop to raw git at the moment of
  success, and `cleanup` deletes the branch by default. Primitives already
  exist in `materialize.py`/`repository.py`. Proposed sequencing inside the
  item: `status` → `diff` → `finish/merge` → `sync`. Impact: high. Type:
  new capability.
- **B2 — Persist and re-emit the paste command.** The continuation command
  is print-once: `RegistryEntry` stores no session IDs, so lost scrollback
  means hand-reconstructing `claude --session-id … --resume …
  --fork-session`. Store parent/child session IDs at fork time; add
  `agent-fork command <name>` (or `resume <name>`). Also closes the gap
  where the `--session-only` route mints a fresh UUID per call and records
  nothing (`session.py:276-283`), making those forks invisible to lineage.
  Impact: high, low effort. Type: new capability. Depends on A3's registry
  migration.
- **B3 — Make `list` a real dashboard.** Today: name/branch/worktree/agent/
  exists (`cli.py:1156-1162`) — no ahead/behind, no dirty/merged state, no
  age, no lineage; the flat registry schema (no parent-fork field) makes a
  fork-of-fork tree impossible. Add a parent field plus per-row divergence,
  and dynamic shell completion of fork names for `cleanup` (static tuples
  today in `completion.py`). Impact: medium. Type: new capability + UX.
  Depends on A3's registry migration.
- **B4 — Auto-launch and terminal integration.** The entire hand-off is
  "open a new terminal and paste"; the only assist is the clipboard
  (`output.py:142-168`). Add at minimum `--exec` (replace current process)
  and/or a tmux window option; scope of terminal-emulator coverage is a
  plan-time decision to bring to the owner. Impact: medium (friction, not
  breakage). Type: new capability/UX.

### Tests & Tasks

Blocked on P02 (at minimum A3) per Depends on. Each item: plan + adversarial
plan review first, tests before implementation (TDD bias).

- [ ] [P03-T01] B1 implementation plan (`status`/`diff`/`finish`/`sync` scope + sequencing) with adversarial plan review incl. Codex
- [ ] [P03-TS01] B1 failing-test-first coverage per approved plan
- [ ] [P03-T02] B1 implementation + adversarial post-review incl. Codex
- [ ] [P03-T03] B2 implementation plan (registry session-ID fields, `command <name>` verb, `--session-only` recording) with adversarial plan review incl. Codex
- [ ] [P03-TS02] B2 failing-test-first coverage per approved plan
- [ ] [P03-T04] B2 implementation + adversarial post-review incl. Codex
- [ ] [P03-T05] B3 implementation plan (parent field, divergence columns, dynamic completion) with adversarial plan review incl. Codex
- [ ] [P03-TS03] B3 failing-test-first coverage per approved plan
- [ ] [P03-T06] B3 implementation + adversarial post-review incl. Codex
- [ ] [P03-T07] B4 implementation plan (launch surface scope — owner decision on emulator coverage) with adversarial plan review incl. Codex
- [ ] [P03-TS04] B4 failing-test-first coverage per approved plan
- [ ] [P03-T08] B4 implementation + adversarial post-review incl. Codex
- [ ] Regression Test Status

### Deliverable

`agent-fork` manages the full fork lifecycle: `status`/`diff`/`finish`/
`sync` verbs, a re-emittable continuation command, a divergence-aware
`list`, and an optional auto-launch — with `just all` green and the v1 JSON
compatibility policy respected (additive fields only within major 1).

### Automated Verification
- `make check` passes; `just all` green after every merged item
- New verbs covered in the conformance fixtures where the CLI standard applies

### Manual Verification
- Each verb exercised against a real fork in a live Claude Code session
- Owner sign-off on B4's terminal-coverage scope before its implementation starts
