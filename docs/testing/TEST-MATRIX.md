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

---

## G-DET — Agent detection
Status: pending

Purpose: agent detection — the env-signal ladder, explicit-flags-win rule, and ambiguity → exit 3.

Varying axes: agent (claude/codex, must vary per §4); otherwise baseline pinned.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|

---

## G-PRE — Preflight & refusal
Status: pending

Purpose: preflight and refusal — the version matrix, Claude warn-band notices, Codex rollout-flush, and D14 refuse-with-diagnosis; plus the A14 git-floor refusal/`--force` override rows.

Varying axes: agent (claude/codex, must vary per §4) for warn-band vs rollout-flush rows; injected `git --version` strings for the A14 floor rows; otherwise baseline pinned.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|

---

## G-GRD — Fork guards
Status: pending

Purpose: fork guards — branch/worktree/path collisions, mid-operation, not-a-repo, unborn HEAD (A2), unmerged index (A4), and race-loss classification (A1).

Varying axes: topology (unborn(plain)/unborn(bare) for A2); markerless-unmerged fixture state for A4 (preflight refusal before materialize ever runs — exclusive to this group, never G-MAT); otherwise baseline pinned.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
| T-GRD-01 | branch already exists → refuse, exit 5, conflict_branch_exists, nothing created | baseline | F | live | REQ-19; RESEARCH §2.1 step 2 |
| T-GRD-02 | branch already has a worktree → refuse, exit 5, nothing created | baseline | F | live | REQ-19 |
| T-GRD-03 | worktree path exists → refuse, exit 5, nothing created | baseline | F | live | REQ-19; RESEARCH §2.1 step 3 |
| T-GRD-04 | parent mid-rebase → refuse, exit 5, abort hint asserted (`cd "<parent>" && git rebase --abort`) | baseline | F | live | REQ-19; RESEARCH §2.1 step 4 |
| T-GRD-05 | parent mid-merge → refuse, exit 5, abort hint asserted (`git merge --abort`) | baseline | F | live | REQ-19; RESEARCH §2.1 step 4 |
| T-GRD-06 | parent mid-cherry-pick → refuse, exit 5, abort hint asserted (`git cherry-pick --abort`) | baseline | F | live | REQ-19; RESEARCH §2.1 step 4 |
| T-GRD-07 | parent mid-revert → refuse, exit 5, abort hint asserted (`git revert --abort`) | baseline | F | live | REQ-19; RESEARCH §2.1 step 4 |
| T-GRD-08 | parent mid-bisect → refuse, exit 5, abort hint asserted (`git bisect reset`) | baseline | F | live | REQ-19; RESEARCH §2.1 step 4 |
| T-GRD-09 | not-a-repo → refuse, exit 5, nothing created | baseline | F | live | REQ-19 |
| T-GRD-10 | unborn HEAD, plain repo → refuse, exit 5, repo_no_commits, remedy text asserted (make an initial commit … and re-run) | topology=unborn(plain) | F | live | REQ-19 (A2) |
| T-GRD-11 | unborn HEAD, bare repo → refuse, exit 5, repo_no_commits, remedy text asserted | topology=unborn(bare) | F | live | REQ-19 (A2) |
| T-GRD-12 | unmerged index, conflict markers present → refuse, exit 5, unmerged_index, conflicted paths listed | baseline | F | live | REQ-19 (A4) |
| T-GRD-13 | unmerged index, markerless (no conflict markers) → refuse, exit 5, unmerged_index, conflicted paths listed | baseline | F | live | REQ-19 (A4) |
| T-GRD-14 | race loss — shim-barrier parks run A between guard-pass and `worktree add`; B completes first; A released → A exits 5, conflict_branch_exists, nothing left | baseline | F | live | REQ-11 (A1); spec §6.6 |

---

## G-ANC — Anchor & topology
Status: pending

Purpose: anchor and topology — parent-HEAD anchoring across every topology value, including bare split by invocation point.

Varying axes: topology (the full set: plain@branch, plain@main, detached, linked-worktree, bare@bare, bare@wt, dot-bare@wt, nested-bare); otherwise baseline pinned.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
| T-ANC-01 | plain@branch — anchor == parent `HEAD^{commit}` resolved at the parent's own path | baseline | F | live | REQ-20; RESEARCH §2.3 |
| T-ANC-02 | plain@main — anchor == parent `HEAD^{commit}`; fork branch ≠ default branch recorded (feeds G-VER's conditional check) | topology=plain@main | F | live | REQ-20; RESEARCH §4 |
| T-ANC-03 | detached HEAD — anchor == parent `HEAD^{commit}` (a commit, not a ref); parent-detached recorded in fork metadata | topology=detached | F | live | REQ-20; RESEARCH §4 |
| T-ANC-04 | linked-worktree — anchor == this worktree's own HEAD (not main's); `git -C <fork> rev-parse --git-common-dir` == parent's common dir | topology=linked-worktree | F | live | REQ-20; RESEARCH §4 |
| T-ANC-05 | bare@bare (invoked at the bare repo root) — anchor == bare HEAD `^{commit}` | topology=bare@bare | F | live | REQ-20; RESEARCH §2.3/§4 |
| T-ANC-06 | bare@wt (invoked from a worktree of a bare project) — anchor == the invoking worktree's `HEAD^{commit}` | topology=bare@wt | F | live | REQ-20; RESEARCH §2.3/§4 |
| T-ANC-07 | dot-bare@wt (`.bare/` layout, invoked from a worktree) — anchor == the invoking worktree's `HEAD^{commit}` | topology=dot-bare@wt | F | live | REQ-20; RESEARCH §2.3 |
| T-ANC-08 | nested-bare — anchor == `HEAD^{commit}` resolved through the nested bare child | topology=nested-bare | F | live | REQ-20; RESEARCH §2.3 |

---

## G-NAM — Naming pipeline
Status: pending

Purpose: naming pipeline — sanitizer table, auto-name derivation including detached (A5), collision suffix vs explicit-name refusal, the 1000-cap, and name feed-through.

Varying axes: none of the shared four vary (pure unit-level logic, tier U); detached-HEAD is exercised as an input value for auto-naming (A5), not a fixture topology.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|

---

## G-LOC — Worktree location
Status: pending

Purpose: worktree location — `sibling`/`central`/`subdirectory`/template placeholders, the mirror-parent heuristic and its suppression, and the bare-at-root override.

Varying axes: topology (bare-at-root override row); otherwise baseline pinned.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
| T-LOC-01 | `sibling` default path derivation — worktree placed at `<repo>-<branch>` | baseline | U | live | D5; RESEARCH §2.4 |
| T-LOC-02 | `central` location — worktree placed under the XDG data path `~/.local/share/agent-fork/worktrees/<repo>/<slug>` | baseline | U | live | D5 |
| T-LOC-03 | `subdirectory` location — worktree placed at `<root>/.worktrees/<slug>` | baseline | U | live | D5 |
| T-LOC-04 | path template — `{repo-name}`, `{repo-root}`, `{branch}` placeholders each substitute correctly | baseline | U | live | D5; RESEARCH §2.4 |
| T-LOC-05 | explicit `worktree_location` config value suppresses the mirror-parent heuristic | baseline | U | live | D5 |
| T-LOC-06 | mirror-parent heuristic — parent is a linked worktree → fork mirrors the parent's observed placement pattern | topology=linked-worktree | F | live | D5; RESEARCH §4 |
| T-LOC-07 | bare-at-root placement override — fork worktree placed as a child of the bare dir | topology=bare@bare | F | live | D5; RESEARCH §2.4 |

---

## G-MAT — Materialize
Status: pending

Purpose: materialize — the staged→unstaged→untracked(+ignored) sequence, symlinks, exec-bit-only, binary, rename+edit, ITA (A3), nested untracked dirs, the empty-dir contract, and submodules-opaque.

Varying axes: mode (exact / exact+ignored / no-state) plus the full file-state inventory from §6.3 (staged, unstaged, untracked incl. nested dirs, ignored, symlink rel+abs, exec-bit-only, binary, rename+edit, ITA, empty dirs, submodule); otherwise baseline pinned.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
| T-MAT-01 | staged-only file → child index+worktree show `A `, content byte-identical (manifest oracle) | baseline | F | live | REQ-21; RESEARCH §2.2 step 1 |
| T-MAT-02 | unstaged-only file → child worktree shows ` M`, index untouched | baseline | F | live | REQ-21; RESEARCH §2.2 step 2 |
| T-MAT-03 | staged+unstaged edits to the same file → split preserved, child index/worktree shapes (`A `/`AM`/` M`) match the staged-vs-unstaged origin of each hunk | baseline | F | live | REQ-21; RESEARCH §2.2 |
| T-MAT-04 | untracked files incl. nested directories → copied byte-for-byte, manifest oracle proves inner files present | baseline | F | live | REQ-21; RESEARCH §2.2 step 3 |
| T-MAT-05 | ignored files, opt-in second pass → union of both `ls-files --others` passes copied | mode=exact+ignored | F | live | REQ-21; RESEARCH §2.2 step 3b |
| T-MAT-06 | symlink, relative target → recreated verbatim via readlink, target stays relative | baseline | F | live | REQ-21; RESEARCH §2.2 |
| T-MAT-07 | symlink, absolute target → recreated verbatim via readlink, target stays absolute | baseline | F | live | REQ-21; RESEARCH §2.2 |
| T-MAT-08 | exec-bit-only change (no content diff) → permission bit preserved in child, content identical | baseline | F | live | REQ-21; RESEARCH §2.2 |
| T-MAT-09 | binary file, staged → cached `--binary` diff applies with `--index`, child byte-identical | baseline | F | live | REQ-21; RESEARCH §2.2 step 1 |
| T-MAT-10 | binary file, unstaged → uncached `--binary` diff applies without `--index`, child byte-identical | baseline | F | live | REQ-21; RESEARCH §2.2 step 2 |
| T-MAT-11 | rename+edit → child reflects the rename with edited content; manifest oracle confirms old path absent and new path's content correct | baseline | F | live | REQ-21; RESEARCH §2.2 |
| T-MAT-12 | intent-to-add file transported → cached diff uses `--ita-invisible-in-index`, applied via `apply --intent-to-add`, child shows ` A` not `??` (ITA-aware oracle) | baseline | F | live | REQ-21 (A3) |
| T-MAT-13 | empty directory in parent → documented absence in child (git-visible state copy only; empty-dir expectation declared per mode) | baseline | F | live | REQ-21; spec §6.5 |
| T-MAT-14 | submodule present → treated opaque, gitlink OID (mode-160000) compared, submodule contents pruned from manifest; fixture built with command-scoped `-c protocol.file.allow=always` | baseline | F | live | RESEARCH §2.1 step 6; spec §6.3; RESEARCH §4 |
| T-MAT-15 | parent strictly read-only during materialize → full manifest+index snapshot before/after, byte-identical | baseline | F | live | REQ-21; spec §6.5 item 3 |
| T-MAT-16 | linked-worktree × dirty-both-checkouts — distinct staged/unstaged/untracked state in both the parent worktree and the main checkout; only the parent worktree's state travels | topology=linked-worktree | F | live | spec §4 mandatory interaction set; REQ-21 |
| T-MAT-17 | linked-worktree × exact+ignored — materialize plus the ignored pass are both scoped to the parent worktree only | topology=linked-worktree, mode=exact+ignored | F | live | spec §4 mandatory interaction set; REQ-21 |
| T-MAT-18 | mode=exact full-materialize — staged+unstaged+untracked copied, ignored excluded | mode=exact | F | live | REQ-21 |
| T-MAT-19 | mode=exact+ignored full-materialize — staged+unstaged+untracked+ignored all copied | mode=exact+ignored | F | live | REQ-21 |
| T-MAT-20 | mode=no-state full-materialize — worktree at parent HEAD, no materialization, child status clean | mode=no-state | F | live | REQ-21; RESEARCH §4 |

---

## G-VER — Verify ladder
Status: pending

Purpose: verify ladder — the 6 base checks plus per-topology conditional checks (branch≠default on main; common-dir match in worktrees; detached recorded); fault-injection rows.

Varying axes: topology (drives the conditional checks: plain@main, linked-worktree, detached); otherwise baseline pinned.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
| T-VER-01 | anchor check — `git -C <fork> rev-parse --verify HEAD` == recorded parent anchor commit | baseline | F | live | REQ-23; RESEARCH §4 ladder item 1 |
| T-VER-02 | branch check — `git -C <fork> rev-parse --abbrev-ref HEAD` == expected new branch | baseline | F | live | REQ-23; RESEARCH §4 ladder item 2 |
| T-VER-03 | worktree-list check — `git worktree list --porcelain` (at root) contains the fork path↔branch pair | baseline | F | live | REQ-23; RESEARCH §4 ladder item 3 |
| T-VER-04 | exact-copy status check — child `status --porcelain=v1 -z` byte-equal to parent's (ignored excluded unless `--with-ignored`) | mode=exact | F | live | REQ-23; RESEARCH §4 ladder item 4 |
| T-VER-05 | clean-from-HEAD status check — fork `status --porcelain` output is empty | mode=no-state | F | live | REQ-23; RESEARCH §4 ladder item 5 |
| T-VER-06 | parent-untouched check — parent `status --porcelain -z` before == after | baseline | F | live | REQ-23; RESEARCH §4 ladder item 6 |
| T-VER-07 | conditional check, branch≠default — plain@main topology asserts fork branch ≠ default branch | topology=plain@main | F | live | REQ-23; spec §5 |
| T-VER-08 | conditional check, common-dir match — linked-worktree topology asserts fork's `git-common-dir` == parent's | topology=linked-worktree | F | live | REQ-23; spec §5 |
| T-VER-09 | conditional check, detached-recorded — detached topology asserts the parent-detached flag is recorded and checked | topology=detached | F | live | REQ-23; spec §5 |
| T-VER-10 | fault injection — non-idempotent clean filter on a staged new file → porcelain diverges → verify fails → rollback → exit 1, verify_failed (canary reference: G-FIX) | baseline | F | live | REQ-23; spec §5; spec §6.6 |
| T-VER-11 | `--no-verify` → the verify ladder is skipped entirely, fork proceeds unverified | baseline | F | live | REQ-23 (D8) |

---

## G-RBK — Rollback & signals
Status: pending

Purpose: rollback and signals — materialize-failure rollback, the manual-recovery path, SIGINT/SIGTERM → 130/143; sole owner of the producer-pipe-failure rows.

Varying axes: none of the shared four vary (baseline pinned); scenario varies by trigger (verify on vs off, signal type, producer-pipe failure).

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
| T-RBK-01 | materialize failure → rollback removes the worktree, removes the branch only if it was created this call | baseline | F | live | REQ-22; RESEARCH §2.1 step 10 |
| T-RBK-02 | rollback itself fails → exact manual-recovery command text emitted (`rm -rf "<worktree>" && git -C "<root>" branch -D "<branch>"`) | baseline | F | live | REQ-22; RESEARCH §2.1 step 10 |
| T-RBK-03 | SIGINT mid-materialize (parent-side step-2 diff stall) → exit 130, clean rollback of partial work | baseline | F | live | REQ-22; spec §6.6 signal window |
| T-RBK-04 | SIGTERM mid-materialize (parent-side step-2 diff stall) → exit 143, clean rollback of partial work | baseline | F | live | REQ-22; spec §6.6 signal window |
| T-RBK-05 | producer-pipe-failure, verify on — fake `git` where `diff --cached` exits 1 with empty stdout → materialize fails, rollback runs, exit 1 | baseline | F | live | REQ-22; spec §5; spec §6.6 |
| T-RBK-06 | producer-pipe-failure, verify off (`--no-verify`) — same fake failure → still fails, rollback runs, exit 1 | baseline | F | live | REQ-22; spec §5; spec §6.6 |

---

## G-REG — Registry & list
Status: pending

Purpose: registry and list — registry schema/ordering logic (U); XDG state, locking, atomic writes, the different-name concurrent race (F); `list` command output incl. `-o json` (C).

Varying axes: none of the shared four vary (baseline pinned); concurrency scenario (different-name registry-write race, A13) is fixture-state, not an axis. Tier varies U/F/C.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
| T-REG-01 | registry write on fork → schema fields populated (name, branch, worktree path, agent, creation time) | baseline | U | live | REQ-41; D10 |
| T-REG-02 | `list` output ordered by creation time — deterministic order asserted across repeated runs | baseline | U | live | D10 |
| T-REG-03 | locked-write atomicity — concurrent writers serialize, no torn/corrupt registry entries | baseline | F | live | REQ-41; REQ-12 |
| T-REG-04 | different-name concurrent race — two forks of one repo under different names both succeed, both entries present, bounded wait observed (≤~5s) | baseline | F | live | REQ-41 (A13) |
| T-REG-05 | timeout row — lock held past the bound → registry_busy, fork rolled back with the manual-recovery message | baseline | F | live | REQ-41 (A13) |
| T-REG-06 | registry ownership check feeds cleanup — `cleanup` refuses a target it didn't create unless `--force` | baseline | F | live | REQ-31; D12 |

---

## G-CLN — Cleanup
Status: pending

Purpose: cleanup — targets, guards, `--force`/`--yes`/`--no-input` semantics, the consent prompt (pty), and never-delete-session-files.

Varying axes: none of the shared four vary (baseline pinned); CLI flag combinations and pty consent-prompt rows vary within the group.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|

---

## G-INC — Include & setup hook
Status: pending

Purpose: `.worktreeinclude` precedence (materialized copies win) plus the setup-hook contract (cwd, env, non-fatal).

Varying axes: none of the shared four vary (baseline pinned).

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
| T-INC-01 | `.worktreeinclude` copies files it lists that are gitignored | baseline | F | live | REQ-24; RESEARCH §2.1 step 11 |
| T-INC-02 | precedence — materialized copies win; `.worktreeinclude` skips a file that already exists in the fork | baseline | F | live | REQ-24; RESEARCH §2.1 step 11 |
| T-INC-03 | setup hook (`.agent-fork/worktree-setup.sh`) runs with cwd = new worktree, env vars carrying repo root + worktree path | baseline | F | live | REQ-24; RESEARCH §2.1 step 12; spec §5 |
| T-INC-04 | hook failure → non-fatal, stderr notice, fork still succeeds | baseline | F | live | REQ-24; RESEARCH §2.1 step 12 |
| T-INC-05 | pipeline order — include/hook run after verify; their filesystem changes are excluded from the verify comparison | baseline | F | live | spec §5 |

---

## G-EMT — Emitted commands
Status: pending

Purpose: emitted commands — templates, uniform quoting, the `extra_args` boundary (spaces, quotes, `$`, `;`), fixed-prefix + quoted-suffix assertions.

Varying axes: agent (claude/codex, must vary per §4 — templates differ by agent); otherwise baseline pinned.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|

---

## G-OUT — Output contract
Status: pending

Purpose: output contract — stdout purity, `-o json` schema fields (incl. `cwd_prompt_expected` per agent), error objects, `--dry-run`, notices, copy-failure-is-notice, a non-C locale row, TTY-format stability.

Varying axes: agent (claude/codex, must vary per §4 — `cwd_prompt_expected` differs by agent); locale (one non-C locale row, R9.4); otherwise baseline pinned.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|

---

## G-CLI — CLI conformance
Status: pending

Purpose: CLI conformance — bare→help exit 0, standard flags, the exit-code catalog (incl. unknown `--agent` → exit 3), completion smoke, doctor content, version output.

Varying axes: none of the shared four vary (baseline pinned); the unknown `--agent` row exercises an invalid input value, not the agent axis.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|

---

## G-EXP — Live experiments
Status: pending

Purpose: live experiments — E1 (Claude flag combo), E2 (Codex cross-cwd + `-C`), E3 (Claude E2E); E4 retired (A8).

Varying axes: agent (claude/codex, must vary per §4 — E1/E3 claude, E2 codex); otherwise baseline pinned.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|

---

## G-FIX — Fixture layer
Status: pending

Purpose: the fixture layer itself — builder-vs-spec verification, oracle mutation rows, the env-seal assertion, git-version canaries, the shim-interception canary, the realpath rule.

Varying axes: topology (builder-vs-spec verification spans the topology set); mode plus file-state inventory (oracle mutation rows perturb properties across state types); otherwise baseline pinned.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
