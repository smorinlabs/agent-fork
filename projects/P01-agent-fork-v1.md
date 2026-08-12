# P01 — agent-fork v1

**References**
- **Trunk:** [PROJECTS.md](../PROJECTS.md)
- **Spec:** [REQUIREMENTS.md](../REQUIREMENTS.md) — REQ-01..48 implemented; REQ-49 approved in the direct companion-skill plan; pinned to CLI Design Standard v1.4.14
- **Design:** [DESIGN-DECISIONS.md](../DESIGN-DECISIONS.md) — D1–D19 implemented; D20 approved in the direct companion-skill plan
- **Plan:** [Phase D implementation plan](../docs/superpowers/plans/2026-08-10-agent-fork-v1-implementation.md) — owner-approved 2026-08-10; [worktree destination controls](../docs/superpowers/plans/2026-08-10-worktree-destination-controls.md) — complete 2026-08-10; [Codex renamed-session resolution](../docs/superpowers/plans/2026-08-10-codex-renamed-session-resolution.md) — complete 2026-08-10; [session inspection and assertion](../docs/superpowers/plans/2026-08-11-session-inspection-validation.md) — implemented through SES-G5; [Claude parent inference design](../docs/superpowers/plans/2026-08-11-claude-parent-inference.md), [implementation plan](../docs/superpowers/plans/2026-08-11-claude-parent-inference-implementation.md), and [implementation-plan adversarial review](../docs/superpowers/plans/2026-08-11-claude-parent-inference-implementation-adversarial-review.md) — complete through CPI-G8; [direct companion skill and repository-aware session context](../docs/superpowers/plans/2026-08-11-direct-companion-skill-session.md) and [adversarial review](../docs/superpowers/plans/2026-08-11-direct-companion-skill-session-adversarial-review.md) — owner-approved 2026-08-11
- **Tracking:** [CONFORMANCE.md](../CONFORMANCE.md) — applicability map + waivers
- **Prior art:** [RESEARCH.md](../RESEARCH.md) — agent-deck port source map; [recipes leaf](../research/reference/agent-session-fork-cli-recipes-2026-07-21.md)

## [~] Project P01: agent-fork v1 (v1.0.0)
**Goal**: Ship `agent-fork` v1.0.0 — a Python CLI + companion skill that forks a
running coding-agent session (Claude Code, Codex) into a new branch + verified
git worktree carrying the current file state, and emits the exact paste command
to continue in a forked session. Built strictly to the locked design corpus
(precedence: DESIGN-DECISIONS.md → REQUIREMENTS.md → RESEARCH.md → CONFORMANCE.md).

**Owner amendment (2026-08-10):** Raise the first release target from v0.1.0 to
v1.0.0 after completing the implementation, companion-skill, and real-agent
verification gates. Historical plans retain the original v0.1.0 target.

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
- [x] [P01-T03] Four-system Flox development toolchain with host-managed real-agent CLI prerequisites (REQ-39)
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
- [x] [P01-TS05] Git repository/topology detection matrix tests (RESEARCH §2.3 rows) — all eight anchor topologies plus guard topology cases green
- [x] [P01-T09] Detection module — agent/session detection plus PATH-resolved plain/linked/bare Git metadata and pre-mutation guard detection complete
- [x] [P01-TS06] Guards + anchor + worktree-create tests (REQ-19, REQ-20) — G-GRD 14/14 and G-ANC 8/8 green
- [x] [P01-T10] Guards, parent-HEAD anchor, atomic worktree create — PATH-resolved Git, metadata, and race-loss mapping implemented
- [x] [P01-TS07] Materialization fixture tests — §2.2 verbatim sequence; one case per RESEARCH §4 matrix row incl. symlink + exec-bit (REQ-21) — G-MAT 20/20 green
- [x] [P01-T11] Materialize (staged → unstaged → untracked [+ignored]) — exact, exact+ignored, and no-state preserve the declared Git-visible state
- [x] [P01-TS08] Verification ladder + rollback tests (REQ-22, REQ-23) — G-VER 11/11 and G-RBK 6/6 green, including real filter divergence, producer failure, and signal stalls
- [x] [P01-T12] Verify ladder + rollback — typed verification failure, precise cleanup, exact manual recovery, and SIGINT/SIGTERM exit mapping implemented
- [x] [P01-TS09] Registry locking/concurrency tests (REQ-41) — G-REG 7/7 green with atomicity, real different-name fork races, timeout, and lock-death proofs
- [x] [P01-T13] Fork registry in XDG state (REQ-12) — stable schema, deterministic ordering, atomic locked writes, ownership lookup, and list rendering implemented
- [x] [P01-TS10] Agent detection/preflight/template tests incl. extra_args quoting boundary (REQ-26..30, D11) — G-DET, G-PRE, and G-EMT green; hostile shell execution and real E1–E3 rerun pass
- [x] [P01-T14] Per-agent detection, preflight, launch templates — locked Claude/Codex REQ-28 builders and individually quoted extra_args implemented
- [x] [P01-TS11] `fork` command end-to-end tests — human/JSON, Claude/Codex, dry-run, streams, clipboard failure, and schema paths exercised through the installed console script
- [x] [P01-T15] `fork` command — discovery, naming/location, preflight, normative pipeline, registry, locked launch command, and output wired end to end
- [x] [P01-TS12] `cleanup` / `list` / `doctor` / `config` / `completion` tests (REQ-31..34, R9.10) — G-REG, G-CLN, and G-CLI command rows green through the installed console script
- [x] [P01-T16] `cleanup` / `list` / `doctor` / `config` / `completion` — full command tree, standard flags, completion scripts, aggregate doctor, and stable exit mapping implemented
- [x] [P01-TS13] Machine output + error catalog tests (REQ-16, REQ-17, R7.8/R7.12) — G-OUT 11/11 green across TTY, locale, error catalog, and minimum schema
- [x] [P01-T17] Output layer (`-o json`, stream separation, error objects) — stable locale-independent renderer and notice-only clipboard fallback implemented
- [x] [P01-TS14] Conformance fixtures in CI (R9.14: help shape, streams, exit codes, `--json`, bare/unknown invocation) — blocking job plus closed-fd/SIGPIPE and disposable wheel-install checks implemented and green locally
- [x] [P01-T18] GitHub Actions CI green from the start — implementation-start matrix + strict collection landed in Phase D Task 1; final R9.14 conformance and clean-install jobs green in PR #8

Phase E — companion skill (gate: end-to-end demo)
- [x] [P01-TS15] Acceptance: real `/agent-fork` and `$agent-fork` invocations created verified disposable forks; emitted commands returned `PHASE_E_CLAUDE_PASTE_OK` and `PHASE_E_CODEX_PASTE_OK`
- [x] [P01-T22] `agent-fork` skill via skill-creator — shared Claude/Codex placement, explicit env identity, validated `--json` contract, ambiguity refusal, and install hint green

Phase E.5 — separable worktree destination controls (gate: D15 + TDD implementation + compatibility proof)
- [x] [P01-T30] SDD/TDD implementation plan with matrix IDs, dependency order, adversarial checks, and WTD-G0..G5 gates authored for owner review
- [x] [P01-TS18] Approve D15 and add T-LOC-08..17, T-NAM-08..12, T-CLI-13..14, T-OUT-12..13 to the leading matrix
- [x] [P01-T25] Implement and validate pure base-directory/leaf-name composition
- [x] [P01-TS19] Add parser, precondition, relative-base, and dry-run tests
- [x] [P01-T26] Wire `--worktree-base-dir` and `--worktree-name` with exact-path mutual exclusion
- [x] [P01-TS20] Add derived-versus-explicit collision provenance tests
- [x] [P01-T27] Implement resource-aware automatic-name collision planning
- [x] [P01-TS21] Add topology, pipeline, output, registry, rollback, and cleanup tests
- [x] [P01-T28] Complete downstream integration without schema expansion
- [x] [P01-TS22] Add companion-skill passthrough and managed-option protection tests
- [x] [P01-T29] Close documentation, conformance, full gates, and real-agent proof — 246 passed/1 retired skip, clean install, disposable Codex fork and orphan-free cleanup green

Phase F — ship v1.0.0 (gate: released + installable)
- [x] [P01-T32] Codex renamed-session resolution — bounded app-server lookup, UUID-only escape hatch, canonical identity flow, documentation, matrix coverage, and real VM E7 gate completed (2026-08-10)
- [x] [P01-T31] Adaptive terminal/agent operation (D16/REQ-45) — `auto`, `strict`, and `git-only` modes; mode-aware doctor/output/registry; strict companion skill; full TDD gates green
- [x] [P01-T19] CLI Design Standard v1.4.14 audit and approved second-level hardening — semantic help/diagnostics, authoritative error catalog, functional Bash/Zsh/Fish completions, and installed-wheel checks green; existing R2.1 waiver unchanged; no new waivers
- [ ] [P01-T20] Release plumbing: release-please, PyPI + TestPyPI trusted publishing, Homebrew tap
- [ ] [P01-T21] Cut v1.0.0 replacing the PyPI placeholder; verify `uv tool install` + `pipx install`

Session inspection follow-up (gate: owner-approved design, TDD, real-agent proof)
- [x] [P01-TS23] Add G-SES TDD matrix for agent-neutral inspection, assertion constraints, evidence sources, and real Claude/Codex acceptance — 22 canonical rows green
- [x] [P01-T33] Implement `agent-fork session` and `session validate` per the 2026-08-11 plan — hermetic and real-agent gates green; stopped at SES-G6 before PR

Claude parent inference follow-up (gate: CPI-G0..G8; stop before PR)
- [x] [P01-TS24] Lock D19/REQ-48, performance architecture, evidence thresholds, and G-CPI plan
- [x] [P01-TS25] Add RED structural, screening/index, persistence, CLI, safety, and real-Claude matrix coverage — G-CPI canonical rows green
- [x] [P01-T34] Implement bounded Claude structural extraction and polynomial relationship inference
- [x] [P01-T35] Implement sharded superficial screening index with cold/warm/incremental performance contracts
- [x] [P01-T36] Implement separate inferred-lineage persistence and ordinary inspection integration
- [x] [P01-T37] Implement `session claude-parent list|show|infer|delete`, output, completions, and deletion safety
- [x] [P01-T38] Complete hermetic, performance, real-Claude, correctness, and adversarial gates; stopped at CPI-G8

Direct companion skill and repository-aware session follow-up (gate: approved plan, TDD, real-agent proof; stop before release)
- [ ] [P01-TS26] Lock D20/REQ-49, repair the related corpus and conformance drift, extend T-SES-22, and add T-SES-23..27 as behavior-RED tests with matrix tracking intact
- [ ] [P01-T39] Extend the existing `session` result with additive invocation-directory, repository-topology, default-branch, worktree, and Git-status context across every identity outcome
- [ ] [P01-T40] Replace `scripts/fork_session.py` with direct agentic-skill routing for session inspection, explicit names, and CLI-owned automatic topic-branch naming while preserving diagnostic and output contracts
- [ ] [P01-T41] Close README, corpus, conformance, skill metadata, placement, full local gates, and fresh Claude Code/Codex forward tests; stop before release or publish work

- [x] Regression Test Status — Phase D final suite 218 passed with only retired T-EXP-04 skipped; conformance fixtures and clean-install checks green in PR #8

### Deliverable
```bash
$ uv tool install agent-fork && agent-fork --version
agent-fork 1.0.0
```

### Automated Verification
- `make check` passes; `just all` (format, lint, typecheck, test) green
- CI conformance fixtures (R9.14) green
- `uv tool install agent-fork` and `pipx install agent-fork` yield a working `agent-fork --version`

### Manual Verification
- From a real Claude Code session: one word produces a verified fork and a paste command that works in a fresh terminal
- Same demo for Codex, incl. documented cwd-prompt behavior per E2 findings
