# P01 — agent-fork v1

**References**
- **Trunk:** [PROJECTS.md](../PROJECTS.md)
- **Spec:** [REQUIREMENTS.md](../REQUIREMENTS.md) — REQ-01..42, pinned to CLI Design Standard v1.4.14
- **Design:** [DESIGN-DECISIONS.md](../DESIGN-DECISIONS.md) — D1–D14 locked 2026-07-21
- **Plan:** [Phase D implementation plan](../docs/superpowers/plans/2026-08-10-agent-fork-v1-implementation.md) — owner-approved 2026-08-10
- **Tracking:** [CONFORMANCE.md](../CONFORMANCE.md) — applicability map + waivers
- **Prior art:** [RESEARCH.md](../RESEARCH.md) — agent-deck port source map; [recipes leaf](../research/reference/agent-session-fork-cli-recipes-2026-07-21.md)

## [~] Project P01: agent-fork v1 (v0.1.0)
**Goal**: Ship `agent-fork` v0.1.0 — a Python CLI + companion skill that forks a
running coding-agent session (Claude Code, Codex) into a new branch + verified
git worktree carrying the current file state, and emits the exact paste command
to continue in a forked session. Built strictly to the locked design corpus
(precedence: DESIGN-DECISIONS.md → REQUIREMENTS.md → RESEARCH.md → CONFORMANCE.md).

- v1 refuses when native fork is impossible (D14 — no fallback ladder)
- `[agents.<name>] extra_args` ships in v1, individually shell-quoted (D11)
- TDD throughout; subagent-driven development with the house model matrix

**Out of Scope** (deferred list — DESIGN-DECISIONS.md)
- Handoff-file degradation ladder, `--clean` alias, jj backend
- Pi / OpenCode / Kilo agents (v2), Docker/Flox isolation, Windows

### Tests & Tasks

Phase A — repo bootstrap (gate: repo live + PROJECTS.md)
- [x] [P01-T01] git init; design-docs initial commit; create smorinlabs/agent-fork; verify org merge-method ruleset
- [x] [P01-T02] Python scaffold: uv package, ruff, ty, `just all`, `make check` (REQ-35, REQ-39)
- [x] [P01-T03] Flox dev env, tiered manifest with `agents` pkg-group (REQ-39)
- [x] [P01-T04] MIT LICENSE (REQ-37 — attribution removed 2026-07-22 by owner amendment)
- [x] [P01-T05] PROJECTS.md via project harness + repo welcome announcement

Phase B — live experiments (gate: EXPERIMENTS.md + updated launch templates)
- [x] [P01-TS01] E1: Claude flag combo `--resume --fork-session --session-id -n` as `requires_real_cli` test (REQ-28) — passed on Claude Code 2.1.220; G-EXP done
- [x] [P01-TS02] E2: Codex explicit-UUID fork from foreign cwd; `-C` behavior; cwd-prompt (REQ-28) — passed on Codex CLI 0.147.0; `-C` suppresses the cwd-choice prompt
- [x] [P01-TS03] E3: Claude full paste-command E2E in a real worktree (context recall, fresh UUID, parent untouched) — passed on Claude Code 2.1.220
- [x] [P01-T06] Record EXPERIMENTS.md; update REQ-28 / RESEARCH §7 / recipes leaf with findings

Phase C — implementation plan (gate: plan review)
- [x] [P01-T07] Task breakdown via superpowers:writing-plans, dependency-ordered, each task naming its failing-test-first — owner-approved 2026-08-10; landed in PR #6

Phase C.5 — test architecture skeleton (gate: matrix + stub tree + checker green)
- [x] [P01-TS16] Test architecture spec + matrix authored (docs/testing/TEST-MATRIX.md, 190 rows, 18 groups) — spec docs/superpowers/specs/2026-08-08-test-architecture-design.md
- [x] [P01-TS17] Stub tree committed (tiers U/F/C/R, pending lifecycle) + conftest signatures
- [x] [P01-T23] Corpus amendments A1–A14 executed (REQUIREMENTS/DESIGN-DECISIONS/IMPLEMENTATION-PROMPT)
- [x] [P01-T24] check-matrix drift guard + just check-matrix

Phase D — build (gate: everything green + reviews clean; every T preceded by its TS)
- [x] Phase D fixture gate — G-FIX 24/24 green; sealed environment, topology worlds, manifest/index oracles, version canaries, PATH shim, pty/stall machinery, and hardened teardown reviewed
- [x] [P01-TS04] Config resolver tests: tri-state semantics + implication rule (REQ-13) — G-CFG 13/13 green
- [x] [P01-T08] Config resolver — tri-state/A12 precedence, discovery boundaries, XDG env, and config set/validate implemented fresh from the locked behavior
- [ ] [P01-TS05] Git repository/topology detection matrix tests (RESEARCH §2.3 rows) — agent detection G-DET is complete; repository detection remains with anchor/topology work
- [ ] [P01-T09] Detection module — agent/session detection complete (G-DET 5/5); Git repository detection remains
- [ ] [P01-TS06] Guards + anchor + worktree-create tests (REQ-19, REQ-20)
- [ ] [P01-T10] Guards, parent-HEAD anchor, worktree create
- [ ] [P01-TS07] Materialization fixture tests — §2.2 verbatim sequence; one case per RESEARCH §4 matrix row incl. symlink + exec-bit (REQ-21)
- [ ] [P01-T11] Materialize (staged → unstaged → untracked [+ignored])
- [ ] [P01-TS08] Verification ladder + rollback tests (REQ-22, REQ-23)
- [ ] [P01-T12] Verify ladder + rollback
- [ ] [P01-TS09] Registry locking/concurrency tests (REQ-41)
- [ ] [P01-T13] Fork registry in XDG state (REQ-12)
- [ ] [P01-TS10] Agent detection/preflight/template tests incl. extra_args quoting boundary (REQ-26..30, D11)
- [ ] [P01-T14] Per-agent detection, preflight, launch templates
- [ ] [P01-TS11] `fork` command end-to-end tests
- [ ] [P01-T15] `fork` command
- [ ] [P01-TS12] `cleanup` / `list` / `doctor` / `config` / `completion` tests (REQ-31..34, R9.10)
- [ ] [P01-T16] `cleanup` / `list` / `doctor` / `config` / `completion`
- [ ] [P01-TS13] Machine output + error catalog tests (REQ-16, REQ-17, R7.8/R7.12)
- [ ] [P01-T17] Output layer (`-o json`, stream separation, error objects)
- [ ] [P01-TS14] Conformance fixtures in CI (R9.14: help shape, streams, exit codes, `--json`, bare/unknown invocation)
- [ ] [P01-T18] GitHub Actions CI green from the start — implementation-start matrix + strict-collection job landed in Phase D Task 1; T18 remains reserved for the full R9.14 conformance job

Phase E — ship v0.1.0 (gate: released + installable)
- [ ] [P01-T19] cli-standards audit vs built binary; fix/waive; CONFORMANCE.md audit row
- [ ] [P01-T20] Release plumbing: release-please, PyPI + TestPyPI trusted publishing, Homebrew tap
- [ ] [P01-T21] Cut v0.1.0 replacing the PyPI placeholder; verify `uv tool install` + `pipx install`

Phase F — companion skill (gate: end-to-end demo)
- [ ] [P01-TS15] Acceptance: one word in a real Claude Code session → verified fork + working paste command; same for Codex
- [ ] [P01-T22] `agent-fork` skill via skill-create (env detection, `--json` contract, install hint)

- [ ] Regression Test Status — `just all` green at every merge; conformance fixtures in CI from Phase D

### Deliverable
```bash
$ uv tool install agent-fork && agent-fork --version
agent-fork 0.1.0
```

### Automated Verification
- `make check` passes; `just all` (format, lint, typecheck, test) green
- CI conformance fixtures (R9.14) green
- `uv tool install agent-fork` and `pipx install agent-fork` yield a working `agent-fork --version`

### Manual Verification
- From a real Claude Code session: one word produces a verified fork and a paste command that works in a fresh terminal
- Same demo for Codex, incl. documented cwd-prompt behavior per E2 findings
