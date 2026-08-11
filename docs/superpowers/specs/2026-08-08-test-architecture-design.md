# agent-fork — Test Architecture Design

**Date:** 2026-08-08 · **Status:** design complete, owner-approved section by section; input to `superpowers:writing-plans`.
**Method:** brainstorming session (owner + Claude) over the locked design corpus (REQUIREMENTS.md, RESEARCH.md, DESIGN-DECISIONS.md), hardened by **three adversarial review rounds** (Fable + Codex lenses, 57 findings total, every finding dispositioned — see §9) and a question-walkthrough that resolved all open rulings. Git-behavior claims in §6 were **empirically verified on both target platforms** (host git 2.50.1, Lima-guest git 2.43.0) on 2026-08-08.
**Owner sequencing decisions:** test design first (this doc) → skeletons committed → all implementation and test execution in the `agent-fork` Lima VM while the code is untrusted → same suite later runs on laptops/CI unchanged.

---

## 1. Purpose and scope

Define the complete test architecture for agent-fork v1 **before** implementation begins: the tier model, the scenario-group hierarchy, the test matrix (axes, IDs, traceability), the shared fixture infrastructure, the skeleton/workflow conventions, and the product-design amendments the reviews forced. TDD then proceeds red-green against this fixed target.

**This phase delivers** (in this order, next phase after spec approval):
- Corpus amendment edits (§8 executed — see Precedence below) and pyproject edits (register the `matrix` marker, enable `--strict-markers`) — both prerequisites of collection.
- `docs/testing/TEST-MATRIX.md` — the leading document, all rows (§4–§5 define its schema and content).
- The full stub tree (§7) — every live row's stub, skip-marked; conftest signatures with `NotImplementedError` bodies.
- `scripts/check-matrix.py` + `just check-matrix` — doc↔stub coverage validated locally; CI-ready (workflow lands at implementation start; see §7.6).
- P01 tracking rows for the above (TS-before-T per PROJECTS.md conventions).

**Explicitly not this phase:** fixture/oracle implementations, product code, CI workflow files.

**Precedence.** Where §8 amends the corpus, **this spec supersedes** DESIGN-DECISIONS.md / REQUIREMENTS.md / RESEARCH.md until the amendments are executed into those documents. Executing them is step 0 of §10 — restoring the corpus's own precedence chain (IMPLEMENTATION-PROMPT §1) before any implementation session starts, so its "stop on contradiction" guardrail never fires on an already-decided amendment.

---

## 2. Tiers and execution policy

Tiers describe **what a test touches**. Where tests run is a **lifecycle policy**, not a tier property.

| Tier | Name | Touches |
|---|---|---|
| U | Unit | pure logic, no FS/git |
| F | Fixture-repo integration | real git in isolated tmp dirs |
| C | CLI conformance | the built CLI as a subprocess (help/streams/exit codes/JSON); pty rows |
| R | Real-agent gated | host-managed `claude`/`codex` binaries; `requires_real_cli` marker; explicit `just test-live` executable/version/state/auth/network gate |

**Execution policy:**
- Every tier is buildable and runnable anywhere (laptop, CI, VM). While the pipeline is untrusted, **all execution happens in the `agent-fork` Lima VM**; once the verify ladder and rollback are proven, the same suite runs everywhere unchanged.
- Ordinary `just all` is hermetic: tier R and unrestricted process-group signal rows have separate targets. `just test-live` reports the selected host executable/version and preflights agent authentication, writable state, and network reachability. `just test-signals` runs with unrestricted process-group control. `just test-git-matrix` runs ITA coverage against system Git and Flox Git.
- **Harness git floor:** `TEST_HARNESS_GIT_MIN = 2.43`. The gate applies **only to tiers that invoke real git (F/C/R)** and **hard-errors** (never skips) below the floor. Distinct constant from the product's own floor (see amendment A9). No pin to a newer git: the 2026-08-08 verification found the only 2.43↔2.50 behavioral difference (origin/HEAD auto-set on fetch) is neutralized by fixture design (§6.4).
- **Tier R gating:** auto-skip only where agent binaries are legitimately absent. In the VM/CI, the require-real toggle (a pytest option, `--require-real-cli`; **not** an `AGENT_FORK_*` env var — REQ-14's namespace is closed) turns absence into failure.
- **Subagent execution (owner directive):** during implementation, TDD and suite runs are dispatched to subagents per the SDD model matrix (sonnet: standard red-green; opus: tricky/mutating; codex: adversarial second lens at phase gates). The driving session orchestrates; it does not execute test runs inline.
- **Bootstrap order (explicit dependency chain):** G-FIX first, scoped to fixture-dependent groups (builder, canaries, oracle-mutation rows green — the fixture layer is proven before anything relies on it) → template-dependent rows finalized (G-EMT, G-OUT, G-PRE) → remaining product groups in pipeline order. **E1–E3 are fixture-independent** (their stubs request no `repo_scenario`) and may run from Phase B per IMPLEMENTATION-PROMPT's ordering, ungated by G-FIX; results recorded in `EXPERIMENTS.md` — these runs *are* P01-TS01..TS03, and the skeleton-phase T-EXP stubs become those tests when G-EXP flips to `tdd`.

---

## 3. Scenario groups (18)

Groups describe **what a test is about**. Every group's rows trace to corpus lines; anything not traceable is flagged as new and cited to its review finding.

| Group | Scope | Tiers | Primary sources |
|---|---|---|---|
| G-CFG | config resolution: tri-state keys, implication rule, precedence chain, env vars (U); config-file walk-up/boundary rows (F); `config set/validate` round-trip via the CLI (C) | U, F, C | REQ-12/13/14, RESEARCH §1, ruling A6 |
| G-DET | agent detection: env-signal ladder, explicit-flags-win, ambiguity → exit 3 | U, F | REQ-26 (as amended by A7), REQ-03 |
| G-PRE | preflight & refusal: version matrix, Claude warn-band notices, Codex rollout-flush, D14 refuse-with-diagnosis | U, F | REQ-27/29, RESEARCH §5.1 |
| G-GRD | fork guards: branch/worktree/path collisions, mid-operation, not-a-repo, **unborn HEAD (A2)**, **unmerged index (A4)**, race-loss classification (A1) | F | REQ-19, RESEARCH §2.1/§4 |
| G-ANC | anchor & topology: parent-HEAD anchoring across plain@branch, plain@main, detached, linked-worktree, bare (split by invocation point), `.bare`, nested-bare | F | REQ-20, RESEARCH §2.3/§4 |
| G-NAM | naming pipeline: sanitizer table, auto-name derivation incl. detached (A5), collision suffix vs explicit-name refusal, 1000-cap, name feed-through | U | D4, RESEARCH §2.4 |
| G-LOC | worktree location: `sibling`/`central`/`subdirectory`/template placeholders, mirror-parent heuristic + suppression, bare-at-root override | U, F | D5, RESEARCH §2.4 |
| G-MAT | materialize: staged→unstaged→untracked(+ignored) sequence, symlinks, exec-bit-only, binary, rename+edit, **ITA (A3)**, nested untracked dirs, empty-dir contract, submodules opaque | F | REQ-21, RESEARCH §2.2, review R2-F01/R2-C02 |
| G-VER | verify ladder: 6 base checks + per-topology conditional checks (branch≠default on main; common-dir match in worktrees; detached recorded); fault-injection rows | F | REQ-23, RESEARCH §4, reviews R1-F05/R2-F01 |
| G-RBK | rollback & signals: materialize-failure rollback, manual-recovery path, SIGINT/SIGTERM → 130/143; sole owner of the producer-pipe-failure rows | F | REQ-22, reviews R1-C04/R2-F03 |
| G-REG | registry & list: registry schema/ordering logic (U); XDG state, locking, atomic writes, different-name concurrent race (F); `list` command output incl. `-o json` (C) | U, F, C | REQ-12/31 (partial), D10, REQ-41 |
| G-CLN | cleanup: targets, guards, `--force`/`--yes`/`--no-input` semantics, consent prompt (pty), never-delete-session-files | F, C | REQ-31..34, D12/D13 |
| G-INC | `.worktreeinclude` precedence (materialized copies win) + setup-hook contract (cwd, env, non-fatal) | F | REQ-24, RESEARCH §2.1 steps 11–12 |
| G-EMT | emitted commands: templates, uniform quoting, `extra_args` boundary (spaces, quotes, `$`, `;`), fixed-prefix + quoted-suffix assertions | U | REQ-28/30/42, D11 |
| G-OUT | output contract: stdout purity, `-o json` schema fields (incl. `cwd_prompt_expected` per agent), error objects, `--dry-run`, notices, copy-failure-is-notice, non-C locale row, TTY-format stability | C | REQ-16/17/18, D9 |
| G-CLI | CLI conformance: bare→help exit 0, standard flags, exit-code catalog (incl. unknown `--agent` → 3), completion smoke, doctor content, version output | C | REQ-06/10/11/38 |
| G-EXP | live experiments: E1 (Claude flag combo), E2 (Codex cross-cwd + `-C`), E3 (Claude E2E); E4 **retired** (A8) | R | RESEARCH §7, REQ §9 |
| G-FIX | the fixture layer itself: builder-vs-spec verification, **oracle mutation rows**, env-seal assertion, git-version canaries, shim-interception canary, realpath rule | F | reviews R2-F05..F12, R3-F08 |

---

## 4. The matrix: axes, explosion control, IDs

**Shared axes** (crossed selectively, never a full cartesian product):

| Axis | Values |
|---|---|
| `mode` | three resolved-plan tokens: **`exact`** (state ✓, ignored ✗ — the baseline) · **`exact+ignored`** (✓ ✓) · **`no-state`** (✗ ✗, clean-from-HEAD) — always reached via the real toggles (`--no-with-state`, `--with-ignored`, config keys); no `--clean` exists (D2). The three config-vs-flag conflict scenarios are **G-CFG rows**, not axis values, with outcomes pinned by **A12** (cross-source rule: the flag-bearing source wins and its own implications apply; dependent settings from lower-precedence sources are suppressed): config `with_state=false` + `--with-ignored` flag → `exact+ignored` (the flag's implication forces state on); config `with_ignored=true` + `--no-with-state` flag → **`no-state`** (flag wins; the config's `with_ignored` is suppressed with it); all-unset → `exact`. Within a single source the RESEARCH §1.1 implication rule applies unchanged: `--no-with-state --with-ignored` typed together still resolves to `exact+ignored`. |
| `topology` | plain@branch · plain@main · detached · linked-worktree · bare-at-root/invoked-at-bare · bare-at-root/invoked-from-worktree · `.bare`/invoked-from-worktree · nested-bare · unborn-HEAD (plain + bare) |
| `agent` | claude · codex — **must vary** in G-DET, G-PRE, G-EMT, G-OUT, G-EXP (codex-only obligations: rollout-flush, `cwd_prompt_expected`; claude-only: warn-band notice) |
| `backend` | git (v1). `jj` is a reserved axis slot for v2 — schema carries it, no v1 values. |

**Explosion control.** Each group's matrix section declares which axes vary for it; all other axes pin to the baseline `plain@branch × exact × claude`. A **mandatory interaction set** covers high-risk cross terms — at minimum: linked-worktree × dirty-both-checkouts (a fixture-state variant, not an axis value: distinct staged/unstaged/untracked in parent worktree AND main checkout; only the parent worktree's state may travel), linked-worktree × `exact+ignored`, and a G-CFG row at linked-worktree topology (walk-up boundary, A6). Meaningless cells are marked **N/A** in the row table; the checker excludes N/A cells from coverage and errors if any stub cites one. Expected volume: **~120–150 rows**.

**IDs.** `T-<GRP>-NN`, numbered within group, **never renumbered**. Axis variants of one scenario are pytest parametrizations; each cell's param ID equals its row ID. Retired/tombstoned IDs keep their numbers forever.

**Row statuses** (machine-readable `row_status` column in every table): `live` · `n/a` · `tombstone` (removed — never returns; no stub may exist; e.g. the pre-0.95 detection ladder, A7) · `retired` (returns at a named milestone; keeps an exempt skip stub; e.g. E4, A8) · `blocked` (awaiting a ruling). **One blocked class exists at spec time**: rows asserting behavior at specific `PRODUCT_GIT_MIN` boundary values (gate: A9's implementation-time git-feature audit fixes the value; the assertion *shape* — doctor reports, fork refuses, `--force` overrides — is already decided by A14). The formerly blocked G-REG lock rows are live: A13 fixed their semantics.

**Group states** (machine-readable `Status:` field in every group header): `pending` · `tdd` · `done`. See §7.2 for the invariants.

---

## 5. Row-table content rules for TEST-MATRIX.md

One section per group: purpose → `Status:` field → varying axes → row table (`ID | scenario | axis values | tier | row_status | source`). Content obligations carried over from the reviews:

- **G-GRD** includes: the race-loss row (shim-barrier positioned between guard-pass and `worktree add`; loser must exit 5 per A1, leaving nothing behind), unborn-HEAD refusal (A2: message contains the remedy; error code `repo_no_commits`), unmerged-index refusal (A4: `ls-files -u` preflight; error code `unmerged_index`; message lists conflicted paths).
- **G-MAT** includes: ITA transport rows (A3 — both platforms verified: naive transport leaves the child `??` vs parent ` A`, so the ladder catches it; the portable fix uses `--ita-invisible-in-index`, plain `apply`, then `add --intent-to-add`), empty-dir contract row (documented absence — "git-visible state copy"), nested-untracked-dir rows, submodule rows (gitlink OIDs compared, contents pruned from manifest).
- **G-VER** includes: the fault-injection row (non-idempotent clean filter on a **staged new file** — verified to diverge porcelain identically on git 2.43 and 2.50) asserting verify-fail → rollback → exit 1 → `verify_failed`.
- **G-RBK** includes: signal rows using the parent-side step-2 diff stall (unambiguous window: step 1 applied, step 2 not), CLI run in its own process group; and the producer-pipe-failure rows (sole owner — fake `git` where `diff --cached` exits 1 with empty stdout), asserted with verify on AND off.
- **G-REG** includes: the different-name concurrent registry-write race (the true REQ-41 atomicity row), asserted against A13's semantics — OS advisory lock (self-clearing on process death), bounded wait ≤ ~5s, then `registry_busy` error — plus a timeout row (lock held past the bound → clean failure: fork rolled back, `cleaned up` reported; the manual-recovery command appears only if that rollback itself fails, per REQ-22).
- **G-PRE** additionally includes the A14 rows: `fork` below `PRODUCT_GIT_MIN` → exit 5 refusal naming installed version, floor, and upgrade remedy; `fork --force` → proceeds with a stderr warning (verify ladder still on — a genuinely broken old git fails safely with rollback); `--force` does **not** override correctness refusals (unborn HEAD, unmerged index, mid-rebase, agent version matrix). **G-CLI** gains the doctor exit-semantics row (failing checks → non-zero exit).
- **G-INC** pins the **normative pipeline order**: guards → anchor → create → materialize → **verify** → `.worktreeinclude` copy → setup hook → registry write → emit. Include/hook run **after** verification and their changes are excluded from the verify comparison (running them earlier would break the byte-equal oracle). Hook contract under test: path `.agent-fork/worktree-setup.sh`, cwd = the new worktree, env vars carrying repo root + worktree path (RESEARCH §2.1 steps 11–12), non-fatal on failure with a stderr notice.
- **G-CLN/G-OUT** pty rows follow §6.6 (per-fd wiring; never byte-compare a cooked pty stream).
- **G-EXP**: E1–E3 live with stable IDs; E4's retired row cites A8; E5 and E6 get mapping rows (E5 → absorbed into G-MAT/G-VER as core TDD; E6 → tombstoned with the pre-0.95 ladder, A7) so neither can be "restored" from the stale RESEARCH §7 list; results additionally recorded in `EXPERIMENTS.md` per the corpus.
- **G-FIX** includes: one canary per version-sensitive mechanism (filter divergence, origin/HEAD determinism, unborn-HEAD rc, ITA flags), the shim-interception canary, the env-seal leak assertion (no `^(CLAUDE|CODEX|AI_AGENT|GIT_)` key outside the whitelist), `handle.path == realpath(handle.path)`, and **oracle mutation rows** — perturb one property out-of-band (flip a byte, chmod, retarget a symlink, add a file, `update-index` one entry) and assert the oracle fails on exactly that cell.

---

## 6. Fixture infrastructure (`RepoScenario`)

### 6.1 Declarative spec
Tests state the world they need via dataclass specs (introspectable, reusable across parametrizations); the builder returns a handle with paths and oracles. Tests state their baseline explicitly. Any setup shared by two tests becomes a named state constructor. Stub-phase rule: **parametrize lists are literals** (a stub calling conftest helpers at import kills collection).

### 6.2 Sealed environment — whitelist from empty
The subprocess env is **composed from empty**, never `os.environ.copy()` minus a blacklist:
`{PATH (explicit), HOME (per-test), LC_ALL=C, pinned XDG_CONFIG/STATE/DATA_HOME, XDG_CONFIG_DIRS (pinned), GIT_CONFIG_GLOBAL (per-test), GIT_CONFIG_NOSYSTEM=1, TERM=dumb, COLUMNS/LINES (pinned), TMPDIR (per-test), GIT_TERMINAL_PROMPT=0}` + row-declared vars only.
Pinned git config: identity, `init.defaultBranch=main`, `core.quotePath`, `core.autocrlf`, `core.symlinks`. Everything `git rev-parse --local-env-vars` reports is absent by construction, as are `GIT_CONFIG_COUNT/KEY/VALUE_n`, `GIT_EXTERNAL_DIFF`, `GIT_EXEC_PATH`, and — critically, since the harness itself runs under Claude Code — `CLAUDECODE`, `CLAUDE_CODE_SESSION_ID`, `AI_AGENT`, `CODEX_THREAD_ID`. One G-OUT row runs under a non-C locale (R9.4).

### 6.3 Repo construction
Topology constructors per §4's axis (linked-worktree built with a divergent, separately-dirty main checkout). State vocabulary: staged / unstaged / both-same-file / untracked (incl. nested dirs) / ignored / symlink (rel+abs) / exec-bit-only / binary (staged+unstaged) / rename+edit / intent-to-add / markerless-unmerged / empty dirs / submodule / `.worktreeinclude` / dirty-vs-clean combos. Bare constructors seed via push (unborn bare is its own topology value). Submodule fixtures are constructed with command-scoped `-c protocol.file.allow=always` (modern git's `user` default blocks local-path submodule setup); never via ambient/global config.

### 6.4 Remote
`origin(pushed=N, unpushed=M)`: local bare repo wired and fetched; **constructor always runs `git remote set-head origin -a`** (verified version-divergent otherwise: auto-set on 2.50, unset on 2.43); one dedicated row deletes origin/HEAD to test the detection fallback. Zero network anywhere.

### 6.5 Oracles — test-side, stronger than the product's
1. **Manifest + hash**: walk both worktrees — file list, content hash, `lstat` mode, symlink target. **lstat-only** (never open non-regular files — an untracked FIFO must not hang the oracle); directories recorded explicitly; gitlink dirs pruned (mode-160000 OIDs compared instead); empty-dir expectation declared per mode.
2. **Index comparison**: `git ls-files --stage -z` both sides (blob IDs + modes), plus an ITA-aware check.
3. **Parent inviolate**: full manifest+index snapshot before/after, byte-identical.
4. The product's porcelain ladder is asserted **as behavior under test**, never used as the truth source.
All handle paths are realpathed at build; comparisons against git-emitted paths resolve both sides (macOS `/tmp`→`/private/tmp`).

### 6.6 Hostile machinery
- **Verify-failure injection**: non-idempotent clean filter, scenario pinned to include a staged new file (empirically diverges: parent `A ` vs child `AM`, both gits), backed by the manifest oracle.
- **Producer-failure shim**: fake `git` first on PATH delegating all but one call (`diff --cached` → exit 1, empty stdout). Requires the recorded product testability rule: *git is resolved via PATH per invocation* (A10). Shim-interception canary in G-FIX.
- **Signal window**: parent-side step-2 diff clean-filter stall with readiness file; CLI in its own process group; killpg; filter self-terminates on orphaning.
- **Race barrier**: git-shim parks run A between guard-pass and `worktree add`; B completes; release A; assert exit 5 + nothing left (A1). Held-lock scenario re-tasked to the different-name registry race (G-REG).
- **pty harness**: explicit `openpty` per assertion; only the fd under test on the pty (others on pipes); ECHO/ONLCR cleared; Linux `EIO` vs macOS EOF normalized in the harness, never in the product bytes.
- **Clock**: not mocked — `<mmdd>` rows compute expectations at call time; midnight retry **rebuilds a fresh world** and reruns (never reruns in place).

### 6.7 Teardown
Finalizer order: touch all go-files → killpg every spawned group → **no git commands during teardown** → rmtree with chmod-retry → suite-level orphan sweep (no surviving processes with cwd under the tmp root — a leak fails the run). No template-caching of worktree-bearing worlds (worktree registrations are absolute; only pre-worktree snapshots may ever be cached, with `git worktree repair` if that optimization is ever taken).

---

## 7. Skeletons, matrix doc, checker, workflow

### 7.1 Layout — one file per (group, tier)
```
tests/
  conftest.py            # RepoScenario, sealed-env composer, oracles, pty/shim/barrier
                         #   helpers — signatures + docstrings, bodies NotImplementedError
  test_package.py        # packaging smoke — out of scope for direction-2 (see below)
  test_check_matrix.py   # checker unit tests — out of scope for direction-2 (see below)
  fixtures/test_fix.py   # G-FIX
  unit/                  # tier U: test_cfg.py test_nam.py test_loc.py test_emt.py test_det.py
                         #   test_pre.py test_reg.py
  pipeline/              # tier F: test_grd.py test_anc.py test_mat.py test_ver.py test_rbk.py
                         #   test_reg.py test_cln.py test_inc.py test_det.py test_pre.py
                         #   test_loc.py test_cfg.py
  cli/                   # tier C: test_out.py test_cli.py test_cln.py test_cfg.py test_reg.py
  live/                  # tier R: test_exp.py
docs/testing/TEST-MATRIX.md
scripts/
  __init__.py
  check_matrix.py        # parsers + cross-checks (logic)
  check-matrix.py         # thin runner invoked by `just check-matrix`
  collect_dump.py         # pytest plugin dumping collected items for the checker
```
Group identity comes from filename + marker; tier from directory. A group with rows in several tiers has one file **per tier** (`unit/test_det.py` and `pipeline/test_det.py` are both legal). `tests/fixtures/` is a declared exception: it is G-FIX's dedicated home and maps to tier F in the checker's directory table. The checker cross-checks each collected item's directory against its row's tier column. `tests/test_package.py` (packaging smoke) and `tests/test_check_matrix.py` (the checker's own unit tests, out of scope for Direction 2 of this design) both sit outside the tier dirs and outside the checker's direction-2 scope.

### 7.2 Stub anatomy and the three-state lifecycle (no xfail)
Every stub: one `@pytest.mark.matrix("T-GRP-NN")` per collected item (multi-cell functions use per-param `pytest.param(id="T-GRP-NN", marks=pytest.mark.matrix("T-GRP-NN"))`; marker arg must equal param ID). The `matrix` marker is registered in pyproject; `--strict-markers` is on.

Lifecycle, driven by the group's `Status:` field in TEST-MATRIX.md (the single source of truth):
- **pending** → all stubs `skip(reason="pending: T-GRP-NN")`.
- **tdd** → **skip markers removed** (`matrix` markers are permanent — they carry the row mapping); failing tests are genuinely red (fixture `NotImplementedError` errors are loudly red, not masked). Empirical basis: `xfail(strict=True)` absorbs fixture-*setup* errors as green XFAIL (verified on pytest 9.1.1) — hence no xfail anywhere in the lifecycle; `xfail` is reserved for documented known-defect rows only.
- **done** → zero lifecycle skips, all green.
Checker invariants apply to **live rows only**: pending ⇒ every live-row stub skipped; tdd ⇒ zero lifecycle-skip stubs; done ⇒ zero lifecycle skips, flip per-row visible (per-param skips are collection-visible, verified). Two skip classes are exempt and distinguished by reason prefix: retired-row stubs (`retired: …`) and tier-R `requires_real_cli` conditional skips — so G-EXP can still reach `done` on a machine legitimately lacking agent binaries.

### 7.3 TEST-MATRIX.md conventions
Per §5, plus: tombstone rows are the registry of removed IDs (checker errors if any collected test cites one); retired rows keep an exempt skip stub whose reason cites the ruling; revival is a doc edit flipping `retired`→`live`, which re-arms freshness automatically; N/A cells excluded from coverage and illegal to cite.

### 7.4 The checker
`scripts/check-matrix.py` (run via `just check-matrix`): (1) cell-level diff both directions — every `live` cell has exactly one collected param ID; every collected test inside the tier directories cites a real live (or retired) cell; (2) lifecycle invariants per §7.2 (skip-reason classifier included); (3) experiment accounting — **E1–E6** all mapped (E1–E3 live, E4 → retired, E5 → absorbed into G-MAT/G-VER, E6 → tombstoned with A7); (4) tombstone/N-A citation errors; (5) directory-vs-tier cross-check.

### 7.5 Version gates
`TEST_HARNESS_GIT_MIN = 2.43` — hard error, F/C/R tiers only (unit tests run on any git). Product-floor behavior (doctor, preflight) is tested exclusively through injected `git --version` strings — the only possibility by construction. See A9.

### 7.6 CI posture
This phase is **CI-ready**: the `just` target exists and the checker runs locally. The CI workflow splits conformance from the matrix/test job. The matrix/test job runs hermetic `just all` plus the dedicated unrestricted-Linux `just test-signals` gate; authenticated real-agent tests remain an explicit developer/VM gate because hosted CI has no user subscriptions or local session state. The **check-matrix + strict-collection job** is a named, blocking deliverable of the implementation session's *first* task (corpus-sanctioned: REQ-38 "scaffold at implementation start"; this is a deliberate P01 re-ordering — P01 currently parks CI at P01-T18, late in Phase D — executed with §10's tracking step), while P01-T18 keeps the full R9.14 conformance job. Owner: the implementation session, per the queue in REQUIREMENTS §10.

---

## 8. Product design amendments (decided in the 2026-08-08 walkthrough)

| # | Amendment | Ruling |
|---|---|---|
| A1 | Both-past-guards race: the atomic `worktree add`/branch-create collision loss is caught and mapped to **exit 5** with `conflict_branch_exists`; exit 5 means "conflict — nothing left behind" (rollback still runs). *(Amends: REQ-11 exit table note + REQ-41.)* | Owner: classify, no new lock |
| A2 | Unborn HEAD: new guard, **exit 5**, error code **`repo_no_commits`**, message must contain the remedy (`make an initial commit … and re-run`). *(Amends: REQ-19 guard list + the REQ-11/R7.12 error catalog.)* | Owner-approved incl. new code |
| A3 | Intent-to-add: **supported** — cached diff uses `--ita-invisible-in-index`; ITA paths transport via plain `git apply`, then `git add --intent-to-add -- <path>`; ITA-aware oracle. The 2026-08-10 portability correction forbids `git apply --intent-to-add` because Apple Git 2.50.1 can replace unrelated index entries. (REQ-21 amendment.) | Owner: support |
| A4 | Markerless unmerged index: **preflight refusal** via `git ls-files -u`, exit 5, error code **`unmerged_index`**, message lists conflicted paths + remedy. (REQ-19 amendment.) | Owner: refuse with remedy |
| A5 | Detached-HEAD auto-name: **`detached-<short-sha>-<mmdd>`**, collision-suffixed normally. (D4 amendment.) | Owner-approved |
| A6 | Project-config walk-up boundary in a linked worktree: **the worktree's own root**. (REQ-12 clarification.) | Owner-approved |
| A7 | Pre-0.95 Codex detection ladder: **removed** — detection is `CODEX_THREAD_ID`-only; below-matrix versions refuse per D14. REQ-26's fallback text is flagged for amendment; matrix keeps tombstone rows. | Owner: remove + update to new mechanism |
| A8 | E4 (.jsonl-copy experiment): **retired until v1.1** (D14 mooted its mechanism); the retired row is the guard against silent restoration. *(Amends: REQUIREMENTS §9's stale "E1–E4" text.)* | Owner: retire |
| A9 | Git floors: `TEST_HARNESS_GIT_MIN = 2.43` (suite infrastructure only — lives in the test conventions, never in REQUIREMENTS; hard gate, F/C/R only; **no pin** — 2026-08-08 verification found no unmitigated 2.43↔2.50 differences). **`PRODUCT_GIT_MIN` does not yet exist in the corpus** — value set during implementation via a git-feature audit. *(Amends: REQ-38's doctor spec, which gains the named `PRODUCT_GIT_MIN` constant.)* | Owner rule: verify first, pin only on differences → none found |
| A10 | Testability requirement: the product resolves `git` **via PATH at each invocation** (never a cached absolute path) — load-bearing for the shim rows and canaried in G-FIX. *(Amends: REQUIREMENTS §8 — new non-functional REQ.)* | Review-forced; recorded |
| A11 | Execution policy: implementation-phase TDD and suite runs are dispatched to **subagents** (SDD model matrix); the driving session orchestrates. *(Amends: REQUIREMENTS §9 test-first plan + the P01 process notes.)* | Owner directive 2026-08-08 |

| A12 | Cross-source conflict resolution: an explicit command-line flag beats the config file **and suppresses dependent config settings** (config `with_ignored=true` + `--no-with-state` → `no-state`); the RESEARCH §1.1 implication rule applies only within a single source. *(Amends: REQ-13's resolver-semantics note; documented UX note in the config docs.)* | Owner ruling 2026-08-08 (walkthrough Q1: flag wins) |
| A13 | Registry locking: OS advisory lock (self-clearing on process death — no stale-lock logic); a contending process waits bounded ≤ ~5s, then fails with new stable error code **`registry_busy`**. *(Amends: REQ-41/R5.8 + the REQ-11/R7.12 error catalog.)* | Owner ruling 2026-08-08 (walkthrough Q2: bounded wait) |
| A14 | Below-`PRODUCT_GIT_MIN` UX: `doctor` reports the failing check and exits non-zero; `fork` refuses exit 5 (precondition family) naming installed version, floor, and remedy; **`fork --force` overrides the git-floor refusal only** (stderr warning; verify ladder still on) — never the correctness refusals (unborn HEAD, unmerged index, mid-rebase, agent version matrix). *(Amends: A9's REQ-38 doctor spec + REQ §3.3 fork flag table + the error catalog.)* | Owner ruling 2026-08-08 (walkthrough Q3 + `--force` note) |

Executing A1–A14 into the corpus — including updating IMPLEMENTATION-PROMPT §1's precedence list — is **step 0 of §10**; until then this spec supersedes the corpus per §1. The only remaining open value (not behavior) is `PRODUCT_GIT_MIN` itself, owned by A9's implementation-time git-feature audit.

---

## 9. Review provenance

| Round | Scope | Findings | Outcome |
|---|---|---|---|
| 1 | Whole design (tiers/groups/matrix) | Fable 18 + Codex 6 | 3 new groups, axis corrections, oracle split, checker hardening, 4 owner rulings |
| 2 | Section 3 (fixtures) | Codex 6 + Fable 12 (empirical, git 2.50) | 4 mechanisms replaced (barrier, filter phase, pty, env seal→whitelist), 4 product amendments surfaced |
| 3 | Section 4 (skeletons/workflow) | Codex 6 + Fable 9 (empirical, pytest 9.1.1) | Lifecycle rebuilt without xfail, matrix-doc state fields, (group,tier) layout, namespace/floor separation |
| 4 | This spec as a document | Codex 7 + Fable 10 | Precedence statement, tier/layout reconciliation, mode vocabulary, blocked-row classes, amendment targets, ordering chain |

74 findings; every one has a disposition in this document. Stable finding IDs (`R<round>-<F|C><NN>`) resolve in the companion index committed beside this spec: [`2026-08-08-test-architecture-reviews.md`](2026-08-08-test-architecture-reviews.md). Cross-platform verification (git 2.43 vs 2.50) ran 2026-08-08 in the `agent-fork` Lima VM; the sole difference found (origin/HEAD auto-set) is neutralized at §6.4.

---

## 10. Handoff to planning

`superpowers:writing-plans` takes this spec and produces the skeleton-phase plan, whose ordered steps are:

0. **Execute §8's amendments (A1–A14) into the corpus** — REQUIREMENTS.md, DESIGN-DECISIONS.md, and IMPLEMENTATION-PROMPT §1's precedence list — restoring corpus precedence (§1).
1. **pyproject edits**: register the `matrix` marker, enable `--strict-markers` (collection prerequisite for everything after).
2. **Author `docs/testing/TEST-MATRIX.md`** per §4–§5.
3. **Stub tree + conftest signatures** per §7.1–7.2.
4. **`scripts/check-matrix.py` + `just check-matrix`** per §7.4; checker green against the stub tree.
5. **P01 tracking rows** (TS-before-T) for steps 0–4; reconcile P01-TS01..TS03 with the G-EXP stubs (§2's chain: the stubs *become* those tests) and record the T18 CI split (§7.6).

Gate: checker green + spec cross-check + owner review. Implementation then follows in the VM per §2's dependency chain (G-FIX for fixture-dependent groups → template-dependent rows → the rest), with the fixture-independent E1–E3 experiments runnable from Phase B, ungated by G-FIX.
