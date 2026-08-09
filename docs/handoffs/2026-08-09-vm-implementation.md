# Session handoff — agent-fork v1 implementation (in-VM TDD) — 2026-08-09

## 🎯 Outcome
**Goal:** implement agent-fork v1 red-green against the committed test skeleton — Phase B live experiments (E1–E3), then G-FIX (the fixture layer), then the product pipeline — per IMPLEMENTATION-PROMPT.md's phase gates. Ends at the Phase D gate (build complete, `just all` + `just check-matrix` green with groups flipped to `done`).
**Out of scope:** VM setup (that is `docs/handoffs/2026-08-09-vm-setup.md`, run first on the host); Phase E (release) and Phase F (companion skill) — both return to the host later.
**Runs in:** the **`agent-fork` Lima VM**, inside `/work/agent-fork` on `main`. Start with `limactl shell agent-fork` (or `sandboxctl project shell agent-fork`) → `cd /work/agent-fork` → launch `claude`.
**Self-contained:** ✓ stands alone — every referenced doc is committed at the repo root or under `docs/`; the step skeleton and the rules that matter are inlined below.

## ⚠ Portability & dependency preflight — read first
- Prereq: the VM-setup handoff completed — flox installed, `project check` green, repo at post-merge `main`. If `just all` doesn't run, stop and do that handoff first.
- All referenced docs travel (committed): verify with `ls IMPLEMENTATION-PROMPT.md docs/testing/TEST-MATRIX.md scripts/check_matrix.py`.
- The VM has **no host mounts**: everything you produce leaves only via `git push` (guest gh auth required — re-run `auth-check` if pushes fail).

## 🧭 Where you are
- Repo: `agent-fork` · origin `https://github.com/smorinlabs/agent-fork.git` · default `main` · guest path `/work/agent-fork`
- Build/verify: `make check` · `just all` (format, lint, typecheck, test) · `just check-matrix` (doc↔stub drift guard, 8 checks)
- Expected baseline on arrival: `just all` → **28 passed, 185 skipped**, zero warnings; `just check-matrix` → exit 0
- State: design + skeleton phases complete (Phases 1–3 + A + C.5). The corpus already carries amendments **A1–A14** — do not re-derive or contradict them.

## 📎 Artifacts & sources of truth (all repo-relative, all committed)
| What | Path |
|---|---|
| Phase gates + precedence (START HERE) | `IMPLEMENTATION-PROMPT.md` |
| Test-architecture spec (tiers, fixtures §6, lifecycle §7, amendments §8) | `docs/superpowers/specs/2026-08-08-test-architecture-design.md` |
| Review-findings index (74 findings, resolves the spec's R*-* citations) | `docs/superpowers/specs/2026-08-08-test-architecture-reviews.md` |
| **The leading test document** — 190 rows, 18 groups, per-group `Status:` field | `docs/testing/TEST-MATRIX.md` |
| Stub tree — 185 pending stubs | `tests/{fixtures,unit,pipeline,cli,live}/` |
| Fixture-layer signatures (implement these; names are the contract) | `tests/conftest.py` |
| Drift guard | `scripts/check_matrix.py` (+ `check-matrix.py` runner, `collect_dump.py` plugin), tests in `tests/test_check_matrix.py` |
| Skeleton-phase plan (historical record of how this was built) | `docs/superpowers/plans/2026-08-08-test-architecture-skeletons.md` |
| Task tracking | `PROJECTS.md` → `projects/P01-agent-fork-v1.md` |

## 📋 Plan · inlined skeleton
1. **Phase B — live experiments (fixture-independent, may run first):** flip G-EXP to `tdd` (see lifecycle below), implement/run E1–E3 for real against the guest's Claude 2.1.218 / Codex 0.145.0 — E1: does `-n` compose with `--resume --fork-session --session-id`? E2: explicit-UUID `codex fork` from foreign cwd; `-C` vs the TUI cwd prompt. E3: full paste-command E2E. Record results in a new `EXPERIMENTS.md`; fold into REQ-28 and the G-EMT/G-OUT template rows (their pending cells cite E1/E2). Flip P01-TS01..TS03. **STOP at the Phase B gate for owner review.**
2. **Early: `PRODUCT_GIT_MIN` git-feature audit** (A9) — pick the value, land it in REQ-38, unblock the 4 blocked rows (T-PRE-06..09).
3. **G-FIX first for all fixture-dependent work:** flip G-FIX to `tdd`; implement `tests/conftest.py` bodies per spec §6 — whitelist-from-empty sealed env (§6.2), topology constructors incl. divergent-dirty linked-worktree (§6.3), local-bare origin with explicit `set-head` (§6.4), test-side oracles: lstat-only manifest+hash, `ls-files --stage`, parent snapshot (§6.5), hostile machinery: git-shim barrier/fault injection, parent-side smudge-stall, per-fd pty, teardown order (§6.6–6.7). The G-FIX canaries and oracle-mutation rows prove the layer before anything uses it.
4. **Phase C — implementation plan:** `superpowers:writing-plans` from the spec, dependency order per IMPLEMENTATION-PROMPT §5 (config resolver → detection → guards/anchor/worktree → materialize → verify+rollback → registry → per-agent preflight/templates → fork → cleanup/list/doctor/config/completion → machine output/error catalog → conformance fixtures). **First implementation task: the check-matrix + strict-collection CI workflow** (spec §7.6; P01-T18 keeps the full R9.14 conformance job). Gate: plan review.
5. **Phase D — subagent-driven TDD build** per the plan, group by group: flip a group to `tdd` → red → implement → green → flip to `done`. `just all` + `just check-matrix` green at every merge; worktree discipline inside the guest repo (never commit to `main`; branch → PR → merge). **STOP at the Phase D gate.**

## 🔧 Lifecycle mechanics (get these right or the checker fights you)
- A group's **`Status:` line in TEST-MATRIX.md is the single source of truth**: `pending` → stubs keep `skip(reason="pending: <id>")`; **`tdd` → remove the skip markers** (the `matrix` markers are permanent); `done` → zero skips, all green. **No `xfail` anywhere** (it swallows fixture-setup errors as green — empirically proven).
- At the **first** `tdd` flip: tighten CHECK2's exempt-reason handling to a whitelist (`retired:` + `requires_real_cli`) — the trigger is documented in the matrix Conventions; under-enforcement is only harmless while everything is pending.
- Tombstone rows (T-DET-06..08, T-EXP-06) must never gain stubs; retired T-EXP-04 keeps its exempt skip stub until v1.1; blocked rows unblock via the A9 audit (step 2).
- Testability requirement (A10 / REQ-43): the product resolves `git` via PATH per invocation — the shim rows and the G-FIX canary depend on it.

## 🧠 Critical context that won't survive a fresh window
- **A1–A14 are decided and already executed into the corpus** — highlights: race-loss → exit 5 `conflict_branch_exists` (A1) · unborn HEAD → guard, `repo_no_commits` (A2) · ITA supported via `--ita-invisible-in-index` + `apply --intent-to-add` (A3) · unmerged index → refusal `unmerged_index` (A4) · detached auto-name `detached-<short-sha>-<mmdd>` (A5) · config boundary = worktree root (A6) · pre-0.95 Codex ladder REMOVED (A7) · E4 retired (A8) · git floors split, harness 2.43 (A9) · flag-beats-config incl. dependent-setting suppression (A12) · registry advisory lock, ~5s bounded wait, `registry_busy` (A13) · below-floor: doctor reports/fork refuses/`--force` git-floor-only (A14).
- **`--force` on cleanup** (adjudicated D12 > REQ-32, 2026-08-09): overrides dirty/unpushed guards only; the invoking-cwd refusal is **never** overridable; `--yes` is the only consent bypass. `--clean` does not exist in v1 (rejected, exit 2).
- **Oracles outrank the product:** tests never use the product's porcelain ladder as truth — manifest+hash and index comparison are the oracle (porcelain is blind to content, exec bits, files inside untracked dirs, empty dirs).
- Verified on both gits (2.43 guest / 2.50 host): the clean-filter porcelain-divergence trick works; naive ITA transport diverges (`??` vs ` A`); unborn HEAD → rc 128; `origin/HEAD` auto-set differs (fixture runs `set-head` explicitly — keep it).
- Rejected approaches (don't redo): xfail lifecycle · blacklist env seal · registry-lock race barrier (use the git-shim barrier) · byte-equal pty assertion (per-fd wiring only) · clock mocking (compute `<mmdd>` at runtime, rebuild on midnight rollover).
- Subagent execution (A11): dispatch TDD to subagents (sonnet standard, opus tricky, codex adversarial at gates); the driving session orchestrates.

## 👉 First action
Inside the VM: `cd /work/agent-fork && claude`, then: *"Read IMPLEMENTATION-PROMPT.md and docs/handoffs/2026-08-09-vm-implementation.md, verify `just all` and `just check-matrix` are green, then start Phase B per the handoff. STOP at the Phase B gate."*

## ℹ How this was made
Composed live from the 2026-08-08/09 design+skeleton session (spec/plan/skeleton all landed on this branch; 4 adversarial review rounds on the design + 2 on the branch, 90 findings total, all dispositioned) · self-contained: ✓.
