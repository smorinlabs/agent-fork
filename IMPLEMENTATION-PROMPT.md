# `agent-fork` — Implementation Kickoff (Claude Code prompt)

> **How to use:** open a NEW Claude Code session with `~/c/agent-fork` as the working directory and paste everything below the line. Session memory recalls the project state automatically. The session runs six **gated** phases (A–F) and stops for my review at each gate. It can be split across multiple sessions at any gate — memory + PROJECTS.md carry the state.

---

You are implementing **`agent-fork`**, whose design is complete and locked. Do not re-litigate design decisions — build to the spec.

## 1. The spec (read before anything else)

In precedence order (paths as given):

1. `DESIGN-DECISIONS.md` — all 14 decisions (D1–D14), final config schema, consolidated v1 surface, deferred list.
2. `REQUIREMENTS.md` — REQ-01..43 (amended with A1–A14), the full CLI interface spec pinned to **CLI Design Standard v1.4.14**, exit codes, pipeline, cleanup semantics, test-first plan (§9).
3. `docs/superpowers/specs/2026-08-08-test-architecture-design.md` — test architecture (§1–§7) and amendments A1–A14 (§8); corpus amended 2026-08-08 to match.
4. `docs/superpowers/plans/2026-08-08-test-architecture-skeletons.md` — skeleton-phase planning and ordered tasks for steps 0–5 (§10).
5. `RESEARCH.md` — the agent-deck port source map (exact `file:line` refs into `/Users/stevemorin/c/agent-deck`), the verbatim state-materialization command sequence (§2.2), detection matrix (§2.3), launch recipes (§5.2), remaining live experiments (§7).
6. `CONFORMANCE.md` — applicability map + the one standing waiver (R2.1 `cleanup`).
7. `research/reference/agent-session-fork-cli-recipes-2026-07-21.md` — the distilled per-agent fork recipes with version gates and gotchas.

Key locked facts: Python ≥3.11, `uv`-based packaging; PyPI + TestPyPI names **already reserved** (`0.0.0.dev0` placeholders — PEP 541 makes shipping a real v0.1.0 time-sensitive); v1 agents are Claude Code + Codex only; v1 refuses when native fork is impossible (D14 — no fallback ladder); `[agents.<name>] extra_args` ships in v1 (D11 — individually shell-quoted).

## 2. Method — non-negotiable

- **TDD throughout** (superpowers:test-driven-development): every task starts with a failing test; no implementation code before its test exists and fails. The §4 pipeline's oracle is the REQUIREMENTS §4 verification ladder run against disposable fixture repos (staged + unstaged + untracked + gitignored + symlink + exec-bit files; one test case per RESEARCH §4 matrix row).
- **Subagent-driven development** (superpowers:subagent-driven-development) with the house model matrix: haiku = mechanical (scaffolds, renames, doc flips) · sonnet = standard implementation/recon/CI · opus = tricky/mutating (pipeline core, rollback paths, debug loops) · codex = adversarial second-lens reviews and pre-mutation gates · fable = planning, phase gates, whole-branch reviews. Read-only tasks may run parallel; mutating tasks run sequential. Fable + codex must concur before any mutating sweep. Subagents never touch my live checkout — they work in their own worktrees.
- **Worktree discipline**: after Phase A's initial commit, no work ever lands directly on `main` — every change gets a worktree (session is inside the repo, so native `EnterWorktree` works) and merges via PR (`gh pr merge --merge`, conventional commits). Verify every mutation landed (non-empty diff, `git log -1`).
- **Scope**: only what REQUIREMENTS/DESIGN-DECISIONS specify. The deferred list (handoff ladder, `--clean` alias, jj, v2 agents) stays deferred.

## 3. PHASE A — Repo bootstrap *(gate: repo live + PROJECTS.md, then STOP)*

1. `git init`; initial commit = the existing design docs (this is the only direct-to-main commit, unavoidable on an empty repo). Create `smorinlabs/agent-fork` on GitHub, push, confirm the org merge-method ruleset applied.
2. Python scaffold per house conventions: `uv init --package`, `ruff` (lint+format), `ty` (typecheck), `just` (runner) + `make check` (deps), modeled on `smorinlabs/py-launch-blueprint`. Console script `agent-fork`; runtime deps minimal (`platformdirs`; stdlib `tomllib`).
3. Flox dev env per RESEARCH §6: pinned python + tier-1 toolchain; `claude-code`/`codex` in an isolated `agents` pkg-group (integration tests need the real binaries).
4. PROJECTS.md via the project harness: one project (P01, v0.1.0) whose tasks/tests map to REQ IDs and the phases below; include the repo welcome announcement in `.claude/settings.json` per my global rule.
5. Add the MIT LICENSE. *(Amended 2026-07-22: NOTICE + agent-deck attribution removed by owner — see REQ-37.)*

**STOP for my review.**

## 4. PHASE B — Live experiments *(gate: `EXPERIMENTS.md` + updated launch templates, then STOP)*

The three still-open empirical questions gate the launch-command templates (REQ-28). Codify each as a pytest integration test marked `requires_real_cli` (skipped when binaries absent), run them once for real, and record results:

- **E1 (Claude):** `--resume <id> --fork-session --session-id <pinned> -n <name>` in one non-interactive invocation — does any flag no-op? Decides whether `-n` stays in the template.
- **E2 (Codex):** explicit-UUID `codex fork` from a foreign cwd (bypasses cwd filtering?); `-C <worktree>` behavior; whether the TUI cwd-change prompt fires with `-C`. Decides the Codex template and what the emitted output must document.
- **E3 (Claude E2E):** full paste command in a real worktree — full context recall, fresh UUID, parent transcript untouched.

Spec amendments A7 (pre-0.95 Codex support removed, detection `CODEX_THREAD_ID`-only) and A8 (E4 retired until v1.1) supersede pre-phase-B E experiments. E5 (state fidelity) is Phase C's core TDD, not a standalone experiment. Update REQ-28/RESEARCH §7 and the research leaf with findings. **STOP.**

## 5. PHASE C — Implementation plan *(gate: plan review, then STOP)*

Use superpowers:writing-plans against the spec docs to produce the task breakdown, sized for subagent dispatch, in dependency order. Expected shape (adjust from the plan, not ad hoc): config resolver (REQ-13 tri-state semantics — port `Resolve()` verbatim incl. the implication rule) → git detection matrix (RESEARCH §2.3) → guards/anchor/worktree-create → materialize (§2.2 verbatim sequence) → verification ladder + rollback → registry (locked XDG state) → per-agent detection/preflight/templates (+ `extra_args` quoting boundary) → `fork` command → `cleanup`/`list`/`doctor`/`config`/`completion` → machine output + error catalog (R7.8/R7.12) → conformance fixtures (R9.14). Each task names its failing-test-first. **STOP for plan approval.**

## 6. PHASE D — Build *(gate: everything green + reviews clean, then STOP)*

Execute the plan with subagent-driven development + TDD per task (model matrix above). Continuous obligations:

- `just all` (format, lint, typecheck, test) green at every merge; CI from the start (GitHub Actions; ci-audit if it breaks).
- R9.14 conformance fixtures as CI tests (help shape, stream separation, exit codes, `--json`, bare/unknown invocation).
- CONFORMANCE.md and PROJECTS.md updated as tasks complete; new waivers only with recorded rationale.
- Every emitted-command code path covered by quoting tests (spaces, quotes, `$`, `;` in names/args).
- Phase-end: full-branch review (fable) + adversarial review (codex) + code-review skills before the gate.

**STOP for my review of the finished build.**

## 7. PHASE E — The `agent-fork` skill *(gate: end-to-end demo, then STOP)*

Build the companion skill via the skill-create pipeline (it handles placement for both Claude Code and Codex, docs, and the skill-quality gate): the skill detects the host agent from env (`CLAUDECODE`/`CLAUDE_CODE_SESSION_ID`; `CODEX_THREAD_ID`), invokes `agent-fork fork … --json` with explicit `--agent`/`--parent-session`, and renders the returned paste command prominently (REQ-02..04). It never re-implements git logic; if the CLI is missing it prints the install hint. Final acceptance: from a real Claude Code session, one word produces a verified fork and a paste command that works in a fresh terminal; same demo for Codex. **STOP — v1 complete.**

## 8. PHASE F — Ship v0.1.0 *(gate: released + installable, then STOP)*

1. cli-standards **audit** mode against the built binary; fix or waive findings; append the audit row to CONFORMANCE.md.
2. Release plumbing via repo-please-setup (release-please pattern; PyPI + TestPyPI trusted publishing; Homebrew tap; secrets via repo-secrets). Merge-commit rules per house policy; `merge_commit_title = MERGE_MESSAGE` for release-please.
3. Cut **v0.1.0** — replaces the PyPI placeholder (verify: `uv tool install agent-fork` and `pipx install agent-fork` both yield a working `agent-fork --version`). Homebrew + Flox/Nix packaging follow the difftree pattern.

**STOP — v1 complete.**

## Guardrails

- Stop at every gate and wait for me. Report failures verbatim — a red test or failed release step is a finding, not something to paper over.
- No design changes without surfacing them: if implementation contradicts a REQ or D-decision, stop and raise it (amendments go through me, and standard deviations through the cli-standards feedback loop).
- *(Amended 2026-07-22: attribution guardrail removed by owner — agent-deck is a behavioral reference only; implement from RESEARCH.md's documented semantics, never by translating agent-deck source. See REQ-37.)* Never run `claim-pypi reserve` or any publish step without the release pipeline or my explicit go.
