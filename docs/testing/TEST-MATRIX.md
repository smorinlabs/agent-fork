# agent-fork TEST-MATRIX — the leading test document

Spec: docs/superpowers/specs/2026-08-08-test-architecture-design.md (§4–§5 define this file).
Stubs copy from this document, never the reverse. scripts/check-matrix.py enforces both directions.

## Conventions
- Row IDs `T-<GRP>-NN`, never renumbered. Retired/tombstoned IDs keep their numbers forever.
- `row_status`: live | n/a | tombstone (no stub may ever exist) | retired (exempt skip stub, returns at the named milestone) | blocked (named unblock gate).
- Group `Status:` field: pending | tdd | done — the single source of truth for the stub lifecycle (spec §7.2).
- Axes: mode = exact | exact+ignored | no-state · topology = plain@branch | plain@main | detached | linked-worktree | bare@bare | bare@wt | dot-bare@wt | nested-bare | unborn(plain) | unborn(bare) · agent = claude | codex · backend = git (jj reserved, no v1 values).
- Baseline (pinned unless a group varies it): plain@branch × exact × claude × git.
- Harness git floor: TEST_HARNESS_GIT_MIN = 2.43 (F/C/R tiers hard-error below; unit runs anywhere).

---

## G-CFG — Config resolution
Status: pending

Purpose: config resolution — tri-state keys, the implication rule, precedence chain, and env vars (U); config-file walk-up/boundary rows (F); `config set`/`config validate` round-trip via the CLI (C).

Varying axes: topology (a linked-worktree row exercises the project-config walk-up boundary at the worktree's own root, A6); otherwise baseline pinned. Tier varies U/F/C per REQ-12/13/14.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

---

## G-DET — Agent detection
Status: pending

Purpose: agent detection — the env-signal ladder, explicit-flags-win rule, and ambiguity → exit 3.

Varying axes: agent (claude/codex, must vary per §4); otherwise baseline pinned.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

---

## G-PRE — Preflight & refusal
Status: pending

Purpose: preflight and refusal — the version matrix, Claude warn-band notices, Codex rollout-flush, and D14 refuse-with-diagnosis; plus the A14 git-floor refusal/`--force` override rows.

Varying axes: agent (claude/codex, must vary per §4) for warn-band vs rollout-flush rows; injected `git --version` strings for the A14 floor rows; otherwise baseline pinned.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

---

## G-GRD — Fork guards
Status: pending

Purpose: fork guards — branch/worktree/path collisions, mid-operation, not-a-repo, unborn HEAD (A2), unmerged index (A4), and race-loss classification (A1).

Varying axes: topology (unborn(plain)/unborn(bare) for A2); otherwise baseline pinned.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

---

## G-ANC — Anchor & topology
Status: pending

Purpose: anchor and topology — parent-HEAD anchoring across every topology value, including bare split by invocation point.

Varying axes: topology (the full set: plain@branch, plain@main, detached, linked-worktree, bare@bare, bare@wt, dot-bare@wt, nested-bare); otherwise baseline pinned.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

---

## G-NAM — Naming pipeline
Status: pending

Purpose: naming pipeline — sanitizer table, auto-name derivation including detached (A5), collision suffix vs explicit-name refusal, the 1000-cap, and name feed-through.

Varying axes: none of the shared four vary (pure unit-level logic, tier U); detached-HEAD is exercised as an input value for auto-naming (A5), not a fixture topology.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

---

## G-LOC — Worktree location
Status: pending

Purpose: worktree location — `sibling`/`central`/`subdirectory`/template placeholders, the mirror-parent heuristic and its suppression, and the bare-at-root override.

Varying axes: topology (bare-at-root override row); otherwise baseline pinned.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

---

## G-MAT — Materialize
Status: pending

Purpose: materialize — the staged→unstaged→untracked(+ignored) sequence, symlinks, exec-bit-only, binary, rename+edit, ITA (A3), nested untracked dirs, the empty-dir contract, and submodules-opaque.

Varying axes: mode (exact / exact+ignored / no-state) plus the full file-state inventory from §6.3 (staged, unstaged, untracked incl. nested dirs, ignored, symlink rel+abs, exec-bit-only, binary, rename+edit, ITA, markerless-unmerged, empty dirs, submodule); otherwise baseline pinned.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

---

## G-VER — Verify ladder
Status: pending

Purpose: verify ladder — the 6 base checks plus per-topology conditional checks (branch≠default on main; common-dir match in worktrees; detached recorded); fault-injection rows.

Varying axes: topology (drives the conditional checks: plain@main, linked-worktree, detached); otherwise baseline pinned.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

---

## G-RBK — Rollback & signals
Status: pending

Purpose: rollback and signals — materialize-failure rollback, the manual-recovery path, SIGINT/SIGTERM → 130/143; sole owner of the producer-pipe-failure rows.

Varying axes: none of the shared four vary (baseline pinned); scenario varies by trigger (verify on vs off, signal type, producer-pipe failure).

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

---

## G-REG — Registry & list
Status: pending

Purpose: registry and list — registry schema/ordering logic (U); XDG state, locking, atomic writes, the different-name concurrent race (F); `list` command output incl. `-o json` (C).

Varying axes: none of the shared four vary (baseline pinned); concurrency scenario (different-name registry-write race, A13) is fixture-state, not an axis. Tier varies U/F/C.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

---

## G-CLN — Cleanup
Status: pending

Purpose: cleanup — targets, guards, `--force`/`--yes`/`--no-input` semantics, the consent prompt (pty), and never-delete-session-files.

Varying axes: none of the shared four vary (baseline pinned); CLI flag combinations and pty consent-prompt rows vary within the group.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

---

## G-INC — Include & setup hook
Status: pending

Purpose: `.worktreeinclude` precedence (materialized copies win) plus the setup-hook contract (cwd, env, non-fatal).

Varying axes: none of the shared four vary (baseline pinned).

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

---

## G-EMT — Emitted commands
Status: pending

Purpose: emitted commands — templates, uniform quoting, the `extra_args` boundary (spaces, quotes, `$`, `;`), fixed-prefix + quoted-suffix assertions.

Varying axes: agent (claude/codex, must vary per §4 — templates differ by agent); otherwise baseline pinned.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

---

## G-OUT — Output contract
Status: pending

Purpose: output contract — stdout purity, `-o json` schema fields (incl. `cwd_prompt_expected` per agent), error objects, `--dry-run`, notices, copy-failure-is-notice, a non-C locale row, TTY-format stability.

Varying axes: agent (claude/codex, must vary per §4 — `cwd_prompt_expected` differs by agent); locale (one non-C locale row, R9.4); otherwise baseline pinned.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

---

## G-CLI — CLI conformance
Status: pending

Purpose: CLI conformance — bare→help exit 0, standard flags, the exit-code catalog (incl. unknown `--agent` → exit 3), completion smoke, doctor content, version output.

Varying axes: none of the shared four vary (baseline pinned); the unknown `--agent` row exercises an invalid input value, not the agent axis.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

---

## G-EXP — Live experiments
Status: pending

Purpose: live experiments — E1 (Claude flag combo), E2 (Codex cross-cwd + `-C`), E3 (Claude E2E); E4 retired (A8).

Varying axes: agent (claude/codex, must vary per §4 — E1/E3 claude, E2 codex); otherwise baseline pinned.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

---

## G-FIX — Fixture layer
Status: pending

Purpose: the fixture layer itself — builder-vs-spec verification, oracle mutation rows, the env-seal assertion, git-version canaries, the shim-interception canary, the realpath rule.

Varying axes: topology (builder-vs-spec verification spans the topology set); mode plus file-state inventory (oracle mutation rows perturb properties across state types); otherwise baseline pinned.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
|  |  |  |  |  |  |
