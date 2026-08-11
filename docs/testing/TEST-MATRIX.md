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
- Execution gates: `just all` excludes `requires_real_cli` and `requires_process_group_signals`; `just test-live` reports host executable identity/version and preflights auth/state/network before tier R; `just test-signals` runs T-RBK-03/04 with unrestricted process-group control; `just test-git-matrix` runs T-FIX-22 and T-MAT-12 with system Git and Flox Git.
- Total rows: 192 (18 groups; recount whenever a group's table changes — see spec §4's ~120–150 estimate, superseded by approved per-group density).
- Blocked rows carry pending stubs; counted by CHECK1 coverage like live rows; CHECK2 lifecycle invariants apply to live rows only (spec §7.2).
- Mapping rows (`row_status: n/a`, e.g. T-EXP-05) use `n/a` in their Tier and Axes columns — bookkeeping rows, never stubbed.
- When the first group flips to `tdd`: tighten CHECK2's exempt-reason handling to a whitelist (`retired:` prefix + requires_real_cli) — under-enforcement is harmless while all groups are pending, load-bearing after.

---

## G-CFG — Config resolution
Status: done

Purpose: config resolution — tri-state keys, the implication rule, precedence chain, and env vars (U); config-file walk-up/boundary rows (F); `config set`/`config validate` round-trip via the CLI (C).

Varying axes: topology (a linked-worktree row exercises the project-config walk-up boundary at the worktree's own root, A6); otherwise baseline pinned. Tier varies U/F/C per REQ-12/13/14.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
| T-CFG-01 | tri-state accessor defaults — `with_state` unset resolves to `true`, `with_ignored` unset resolves to `false` (asserted individually) | baseline | U | live | REQ-13; RESEARCH §1.1 |
| T-CFG-02 | explicit `with_state=false` in a single source is honored, not silently coerced back to the tri-state default | baseline | U | live | REQ-13; RESEARCH §1.1 |
| T-CFG-03 | within-source implication — `--no-with-state --with-ignored` typed together on one source still resolves to `exact+ignored` | baseline | U | live | REQ-13; RESEARCH §1.1 |
| T-CFG-04 | A12 cross-source — config `with_state=false` + `--with-ignored` flag → `exact+ignored` (the flag's implication forces state on) | baseline | U | live | REQ-13 (A12); spec §4 |
| T-CFG-05 | A12 cross-source — config `with_ignored=true` + `--no-with-state` flag → `no-state` (flag wins; config's `with_ignored` suppressed with it) | baseline | U | live | REQ-13 (A12); spec §4 |
| T-CFG-06 | A12 cross-source — all sources unset → `exact` | baseline | U | live | REQ-13 (A12); spec §4 |
| T-CFG-07 | precedence chain — flags beat env beat config-file order, asserted with all three sources set to conflicting values | baseline | U | live | REQ-12; RESEARCH §1.1 |
| T-CFG-08 | `branch_prefix` set to a whitespace-only string resolves to the default `fork/` | baseline | U | live | REQ-13 |
| T-CFG-09 | `AGENT_FORK_CONFIG` and `AGENT_FORK_OUTPUT` env vars are read and applied to config-path and output-format resolution respectively | baseline | U | live | REQ-14 |
| T-CFG-10 | project config walk-up stops at the repo boundary, never escalates above it | baseline | F | live | REQ-12 |
| T-CFG-11 | A6 — in a linked worktree, the project-config walk-up boundary is the worktree's own root, not the main checkout's | topology=linked-worktree | F | live | REQ-12 (A6); spec §8 A6 |
| T-CFG-12 | `config set` followed by `config validate` round-trips a written value through the CLI | baseline | C | live | REQUIREMENTS §3.2 |
| T-CFG-13 | `--config <path>` replaces discovery entirely — the walk-up/XDG/system chain is not consulted | baseline | F | live | REQ-12 |
| T-CFG-14 | `agent_mode` defaults to `auto` | baseline | U | live | REQ-45; D16 |
| T-CFG-15 | agent-mode precedence is CLI > environment > config > `auto` | baseline | U | live | REQ-45; D16 |
| T-CFG-16 | invalid configured agent mode is rejected as `config_error` | baseline | U | live | REQ-45; D16 |
| T-CFG-17 | Codex session-name resolution defaults on and obeys CLI > config precedence | agent=codex | U | live | REQ-46; D17 |

---

## G-DET — Agent detection
Status: done

Purpose: agent detection — the env-signal ladder, explicit-flags-win rule, and ambiguity → exit 3.

Varying axes: agent (claude/codex, must vary per §4); otherwise baseline pinned.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
| T-DET-01 | Claude detected via `CLAUDECODE=1` ∧ `CLAUDE_CODE_SESSION_ID` present, no explicit flags → agent=claude | agent=claude | U | live | REQ-26; RESEARCH §5.0 |
| T-DET-02 | Codex detected via `CODEX_THREAD_ID` present, no explicit flags → agent=codex | agent=codex | U | live | REQ-26 (A7); RESEARCH §5.1 Q3 |
| T-DET-03 | explicit `--agent`/`--parent-session` flags win over a contradicting env signal | baseline | U | live | REQ-03; REQ-26 |
| T-DET-04 | both Claude and Codex env signals present, no explicit flags → ambiguity, exit 3 | baseline | F | live | REQ-26 |
| T-DET-05 | neither env signal present, no explicit flags → exit 3 | baseline | F | live | REQ-26 |
| T-DET-06 | tombstone — pre-0.95 Codex fallback: own-process-ancestry walk | agent=codex | F | tombstone | RESEARCH §3.2 (A7) |
| T-DET-07 | tombstone — pre-0.95 Codex fallback: open-fd probe | agent=codex | F | tombstone | RESEARCH §3.2 (A7) |
| T-DET-08 | tombstone — pre-0.95 Codex fallback: newest-rollout disk scan | agent=codex | F | tombstone | RESEARCH §3.2 (A7) |
| T-DET-09 | auto mode with no session signals selects Git-only mode | baseline | U | live | REQ-45; D16 |
| T-DET-10 | auto mode with exactly one session signal selects that agent | agent=claude | U | live | REQ-45; D16 |
| T-DET-11 | strict mode with no session signal refuses with exit 3 | baseline | U | live | REQ-45; D16 |
| T-DET-12 | auto mode with both session signals refuses as ambiguous | baseline | U | live | REQ-45; D16 |

---

## G-PRE — Preflight & refusal
Status: done

Purpose: preflight and refusal — the version matrix, Claude warn-band notices, Codex rollout-flush, and D14 refuse-with-diagnosis; plus the A14 git-floor refusal/`--force` override rows.

Varying axes: agent (claude/codex, must vary per §4) for warn-band vs rollout-flush rows; injected `git --version` strings for the A14 floor rows; otherwise baseline pinned.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
| T-PRE-01 | installed agent CLI entirely missing → refusal, exit 3, diagnosis names what was detected and what's missing | agent=claude | F | live | REQ-27; REQ-29 |
| T-PRE-02 | Claude below the pinned-ID fork floor (2.0.73) → refuse | agent=claude | U | live | REQ-27; RESEARCH §5.2 |
| T-PRE-03 | Claude warn-band (<~2.1.1xx) → warn-and-proceed, `notices[]` populated | agent=claude | U | live | REQ-27; RESEARCH §5.1 Q1 |
| T-PRE-04 | Codex below the fork-subcommand floor (0.81.0) → refuse | agent=codex | U | live | REQ-27; RESEARCH §5.1 Q4 |
| T-PRE-05 | Codex parent rollout file not yet flushed on disk → refuse before any mutation | agent=codex | F | live | REQ-27; RESEARCH §3.2 |
| T-PRE-11 | canonical Codex UUID input bypasses app-server resolution | agent=codex | U | live | REQ-46; D17 |
| T-PRE-12 | one exact Codex name match resolves once to its canonical UUID and preserves the display name | agent=codex | U | live | REQ-46; D17 |
| T-PRE-13 | disabled Codex name resolution rejects non-UUID input without spawning app-server | agent=codex | U | live | REQ-46; D17 |
| T-PRE-14 | zero exact Codex name matches refuse before mutation | agent=codex | U | live | REQ-46; D17 |
| T-PRE-15 | duplicate exact Codex names refuse with deterministically sorted candidate UUIDs | agent=codex | U | live | REQ-46; D17 |
| T-PRE-16 | malformed app-server protocol produces a typed bounded resolution failure | agent=codex | U | live | REQ-46; D17 |
| T-PRE-17 | resolved UUID without a flushed rollout refuses before mutation | agent=codex | U | live | REQ-46; D17 |
| T-PRE-18 | app-server lookup follows pagination and only accepts an exact name | agent=codex | U | live | REQ-46; D17 |
| T-PRE-19 | app-server notifications are tolerated and the subprocess is reaped | agent=codex | U | live | REQ-46; D17 |
| T-PRE-20 | an app-server notification flood is stopped by the pending-message bound | agent=codex | U | live | REQ-46; D17 |
| T-PRE-06 | PRODUCT_GIT_MIN boundary — injected `git --version` just below 2.19.0 → the named check fails | baseline | F | live | REQ-38 (A9); PRODUCT-GIT-MIN-AUDIT |
| T-PRE-07 | PRODUCT_GIT_MIN boundary — injected `git --version` at/above 2.19.0 → the named check passes | baseline | F | live | REQ-38 (A9); PRODUCT-GIT-MIN-AUDIT |
| T-PRE-08 | A14 — below-2.19.0 `fork` refusal, exit 5, remedy names installed version/floor/upgrade path | baseline | F | live | REQ-19 (A14); PRODUCT-GIT-MIN-AUDIT |
| T-PRE-09 | A14 — `fork --force` overrides the git-floor refusal only, stderr warning emitted, verify ladder still runs | baseline | F | live | REQUIREMENTS §3.3 (A14); PRODUCT-GIT-MIN-AUDIT |
| T-PRE-10 | D14 — nothing is created (no worktree, no branch) on any preflight refusal | baseline | F | live | DESIGN-DECISIONS D14; REQ-29 |

---

## G-GRD — Fork guards
Status: done

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
Status: done

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
Status: done

Purpose: naming pipeline — sanitizer table, auto-name derivation including detached (A5), collision suffix vs explicit-name refusal, the 1000-cap, and name feed-through.

Varying axes: none of the shared four vary (pure unit-level logic, tier U); detached-HEAD is exercised as an input value for auto-naming (A5), not a fixture topology.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
| T-NAM-01 | sanitizer strips git-illegal chars (`.. ~ ^ : ? * [ \ @{`), converts spaces to dashes, collapses repeated dashes, strips leading dots and a trailing `.lock` — each rule asserted individually against one crafted input | baseline | U | live | RESEARCH §2.4 |
| T-NAM-02 | auto-name derivation — bare `fork` (no positional) derives `<branch-slug>-<mmdd>` computed at call time; a run that spans midnight rebuilds a fresh world and reruns rather than reusing the stale date | baseline | U | live | D4; RESEARCH §2.4; spec §6.6 |
| T-NAM-03 | A5 — detached-HEAD auto-name derives `detached-<short-sha>-<mmdd>`, collision-suffixed like any other auto name | baseline | U | live | D4 (A5); spec §8 A5 |
| T-NAM-04 | collision suffix — auto-name mode escalates through `-2`, `-3`, … until a non-colliding name is found | baseline | U | live | D4; RESEARCH §2.4 |
| T-NAM-05 | an explicit name that collides with an existing branch/worktree is passed through unmodified — refusal, not an auto-suffix | baseline | U | live | D4; REQ-19 |
| T-NAM-06 | 1000-cap — the collision-suffix search hard-stops after 1000 attempts | baseline | U | live | D4; RESEARCH §2.4 |
| T-NAM-07 | the derived name feeds the fork branch (`<branch_prefix><name>`), the worktree directory, and the session display name — each feed-through asserted individually for one fork | baseline | U | live | REQUIREMENTS §3.3; D6 |
| T-NAM-08 | defaults still feed all identities unchanged | baseline | U | live | D15; REQ-44 |
| T-NAM-09 | explicit branch/leaf do not change fork or session display name | baseline | U | live | D15; REQ-44 |
| T-NAM-10 | derived-resource collision advances automatic name | baseline | U | live | D15; REQ-44 |
| T-NAM-11 | explicit branch/path collision refuses without suffix | baseline | C | live | D15; REQ-44 |
| T-NAM-12 | fixed explicit collision does not enter the 1000-candidate loop | baseline | U | live | D15; REQ-44 |

---

## G-LOC — Worktree location
Status: done

Purpose: worktree location — `sibling`/`central`/`subdirectory`/template placeholders, the mirror-parent heuristic and its suppression, and the bare-at-root override.

Varying axes: topology (bare-at-root override row); otherwise baseline pinned.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
| T-LOC-01 | `sibling` default path derivation — worktree placed at `<repo>-<branch>` | baseline | U | live | D5; RESEARCH §2.4 |
| T-LOC-02 | `central` location — worktree placed under the XDG data path `~/.local/share/agent-fork/worktrees/<repo>/<slug>` | baseline | U | live | D5 |
| T-LOC-03 | `subdirectory` location — worktree placed at `<root>/.worktrees/<slug>` | baseline | U | live | D5 |
| T-LOC-04 | path template resolves each placeholder — `{repo-name}` → repo basename, `{repo-root}` → parent dir of root, `{branch}` → fork branch slug — asserted individually in one templated location | baseline | U | live | D5; RESEARCH §2.4 |
| T-LOC-05 | explicit `worktree_location` config value suppresses the mirror-parent heuristic | baseline | U | live | D5 |
| T-LOC-06 | mirror-parent heuristic — parent is a linked worktree → fork mirrors the parent's observed placement pattern | topology=linked-worktree | F | live | D5; RESEARCH §4 |
| T-LOC-07 | bare-at-root placement override — fork worktree placed as a child of the bare dir | topology=bare@bare | F | live | D5; RESEARCH §2.4 |
| T-LOC-08 | base-only override preserves the derived leaf | baseline | U | live | D15; REQ-44 |
| T-LOC-09 | name-only override preserves the derived parent and exact leaf | baseline | U | live | D15; REQ-44 |
| T-LOC-10 | base and name compose to exactly `base/name` | baseline | U | live | D15; REQ-44 |
| T-LOC-11 | invalid explicit leaf inventory refuses | baseline | U | live | D15; REQ-44 |
| T-LOC-12 | relative base resolves from invocation cwd | baseline | C | live | D15; REQ-44 |
| T-LOC-13 | explicit base must exist and be a directory | baseline | C | live | D15; REQ-44 |
| T-LOC-14 | template result accepts parent/leaf replacement after derivation | baseline | U | live | D15; REQ-44 |
| T-LOC-15 | linked mirror-parent result accepts partial override after derivation | topology=linked-worktree | F | live | D15; REQ-44 |
| T-LOC-16 | bare-at-root result accepts partial override after derivation | topology=bare@bare | F | live | D15; REQ-44 |
| T-LOC-17 | symlinked base resolves once and remains contained | baseline | F | live | D15; REQ-44 |

---

## G-MAT — Materialize
Status: done

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
| T-MAT-12 | intent-to-add file transported → cached diff uses `--ita-invisible-in-index`, working-tree patch uses plain `apply`, child is marked via `add --intent-to-add`, child shows `␠A` (`␠` denotes the leading status-column space) not `??`, and existing index entries remain intact | baseline | F | live | REQ-21 (A3) |
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
Status: done

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
Status: done

Purpose: rollback and signals — materialize-failure rollback, the manual-recovery path, SIGINT/SIGTERM → 130/143; sole owner of the producer-pipe-failure rows.

Varying axes: none of the shared four vary (baseline pinned); scenario varies by trigger (verify on vs off, signal type, producer-pipe failure).

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
| T-RBK-01 | materialize failure → rollback removes the worktree, removes the branch only if it was created this call | baseline | F | live | REQ-22; RESEARCH §2.1 step 10 |
| T-RBK-02 | rollback itself fails → exact manual-recovery command text emitted (`rm -rf "<worktree>" && git -C "<root>" branch -D "<branch>"`) | baseline | F | live | REQ-22; RESEARCH §2.1 step 10 |
| T-RBK-03 | SIGINT mid-materialize (parent-side step-2 diff stall) → exit 130, clean rollback of partial work; owned by unrestricted Linux `just test-signals` gate | baseline | F | live | REQ-22; spec §6.6 signal window |
| T-RBK-04 | SIGTERM mid-materialize (parent-side step-2 diff stall) → exit 143, clean rollback of partial work; owned by unrestricted Linux `just test-signals` gate | baseline | F | live | REQ-22; spec §6.6 signal window |
| T-RBK-05 | producer-pipe-failure, verify on — fake `git` where `diff --cached` exits 1 with empty stdout → materialize fails, rollback runs, exit 1 | baseline | F | live | REQ-22; spec §5; spec §6.6 |
| T-RBK-06 | producer-pipe-failure, verify off (`--no-verify`) — same fake failure → still fails, rollback runs, exit 1 | baseline | F | live | REQ-22; spec §5; spec §6.6 |
| T-RBK-07 | interrupted Git cleanup observes an already-exited process before a redundant process-group signal, preserving the original interruption instead of masking it with macOS `EPERM` | baseline | U | live | REQ-22; macOS process-group regression |

---

## G-REG — Registry & list
Status: done

Purpose: registry and list — registry schema/ordering logic (U); XDG state, locking, atomic writes, the different-name concurrent race (F); `list` command output incl. `-o json` (C).

Varying axes: none of the shared four vary (baseline pinned); concurrency scenario (different-name registry-write race, A13) is fixture-state, not an axis. Tier varies U/F/C.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
| T-REG-01 | registry write on fork → schema fields populated (name, branch, worktree path, agent, creation time) | baseline | U | live | REQ-41; D10 |
| T-REG-02 | `list` output ordered by creation time — deterministic order asserted across repeated runs | baseline | U | live | D10 |
| T-REG-03 | locked-write atomicity — concurrent writers serialize, no torn/corrupt registry entries | baseline | F | live | REQ-41; REQ-12 |
| T-REG-04 | different-name concurrent race — two forks of one repo under different names both succeed, both entries present, bounded wait observed (≤~5s) | baseline | F | live | REQ-41 (A13) |
| T-REG-05 | timeout row — lock held past the bound → registry_busy, fork rolled back cleanly (`cleaned up` reported; the manual-recovery command appears only if that rollback itself fails, per REQ-22) | baseline | F | live | REQ-41 (A13); REQ-22 |
| T-REG-06 | registry ownership check feeds cleanup — `cleanup` refuses a target it didn't create unless `--force` | baseline | F | live | REQ-31; D12 |
| T-REG-07 | `list` renders registry entries (name, branch, worktree path, agent, worktree-still-exists) in creation-time order; `-o json` emits the stable schema | baseline | C | live | REQ-31; D10; REQ-17 |
| T-REG-08 | registry records mode and reads legacy records without mode as agent mode | baseline | U | live | REQ-45; D16 |

---

## G-CLN — Cleanup
Status: done

Purpose: cleanup — targets, bounded and terminal-safe dirty/unpushed reporting,
granular and `--force` overrides, human/JSON previews, `--yes`/`--no-input`
consent, the pty prompt, and never-delete-session-files.

Varying axes: none of the shared four vary (baseline pinned); risk kind/count,
CLI flag combinations, output format, and pty consent-prompt rows vary within
the group.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
| T-CLN-01 | `cleanup <TARGET>` accepts a fork name, a branch name, or a worktree path — each form resolves to the same fork | baseline | F | live | REQ-31 |
| T-CLN-02 | worktree removed via `git worktree remove` and pruned | baseline | F | live | REQ-31 |
| T-CLN-03 | fork branch deleted by default; `--keep-branch` preserves it | baseline | F | live | REQ-31 |
| T-CLN-04 | fork registry entry removed after cleanup | baseline | F | live | REQ-31 |
| T-CLN-05 | guard — dirty worktree (uncommitted changes) → refuse, exit 5 | baseline | F | live | REQ-32; DESIGN-DECISIONS D12 |
| T-CLN-06 | guard — commits not reachable from any upstream (unpushed) → refuse, exit 5 | baseline | F | live | REQ-32; DESIGN-DECISIONS D12 |
| T-CLN-07 | guard — target is the invoking cwd → refuse, exit 5; non-overridable (not even with `--force`) | baseline | F | live | REQ-32; DESIGN-DECISIONS D12 |
| T-CLN-08 | `--force` extends targeting beyond registry-recorded forks and overrides the dirty/unpushed guards only; the invoking-cwd guard is never overridden | baseline | F | live | DESIGN-DECISIONS D12 |
| T-CLN-09 | `--yes` bypasses the interactive consent prompt | baseline | C | live | REQ-33 |
| T-CLN-10 | `--no-input` without `--yes` → fail, exit 2; `--force` is not a consent bypass | baseline | C | live | REQ-33 |
| T-CLN-11 | TTY consent prompt on stderr names exactly what will be removed (pty row) | baseline | C | live | REQ-33; spec §6.6 |
| T-CLN-12 | session files are never deleted by cleanup; output notes the fork session remains resumable | baseline | F | live | REQ-34 |
| T-CLN-13 | `--dry-run` prints the removal plan without mutating | baseline | C | live | REQ-33; REQ-18 |
| T-CLN-14 | guard combination — target is the invoking cwd, run with `--force` → still refuse, exit 5 (cwd guard is non-overridable) | baseline | F | live | REQ-32; DESIGN-DECISIONS D12 |
| T-CLN-15 | flag combination — `--force` with `--no-input` and no `--yes` → fail, exit 2 (`--force` never substitutes for consent) | baseline | C | live | REQ-33; DESIGN-DECISIONS D12 |
| T-CLN-16 | `cleanup --force --dry-run` on a dirty worktree reports each at-risk path and performs no mutation | baseline | C | live | issue #16 sections 1–2; REQ-18; REQ-32 |
| T-CLN-17 | dirty-worktree refusal enumerates modified and untracked paths with porcelain statuses and names `--allow-dirty` | baseline | C | live | issue #16 sections 1 and 3; REQ-32 |
| T-CLN-18 | unpushed-commit refusal enumerates each abbreviated SHA and subject and names `--allow-unpushed` | baseline | C | live | issue #16 sections 1 and 3; REQ-32 |
| T-CLN-19 | dirty enumeration is capped at 10 entries with the remaining count reported in human and JSON errors | baseline | C | live | issue #16 sections 1 and 4; REQ-17 |
| T-CLN-20 | `--allow-dirty` and `--allow-unpushed` override only their named guard | baseline | C | live | issue #16 section 3; REQ-32; DESIGN-DECISIONS D12 |
| T-CLN-21 | JSON refusal and `--force --dry-run` result carry matching dirty and unpushed `details` objects | baseline | C | live | issue #16 section 4; REQ-17; REQ-18 |
| T-CLN-22 | `--allow-dirty` and `--allow-unpushed` never override the invoking-cwd refusal | baseline | C | live | issue #16 section 3; REQ-32; DESIGN-DECISIONS D12 |
| T-CLN-23 | Human cleanup diagnostics escape terminal control bytes in Git-controlled paths and commit subjects while JSON preserves the values | baseline | C | live | PR #17 late security review; issue #16 sections 1 and 4; REQ-17 |

---

## G-INC — Include & setup hook
Status: done

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
Status: done

Purpose: emitted commands — templates, uniform quoting, the `extra_args` boundary (spaces, quotes, `$`, `;`), fixed-prefix + quoted-suffix assertions.

Varying axes: agent (claude/codex, must vary per §4 — templates differ by agent); otherwise baseline pinned.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
| T-EMT-01 | Claude template byte-exact — `cd '<worktree>' && claude --session-id '<uuid>' --resume '<parent-id>' --fork-session -n '<name>'` (E1 verified) | agent=claude | U | live | REQ-28; EXPERIMENTS E1 |
| T-EMT-02 | Codex template byte-exact — `codex fork '<parent-thread-id>' -C '<worktree>'` (E2 verified; suppresses cwd prompt) | agent=codex | U | live | REQ-28; EXPERIMENTS E2 |
| T-EMT-03 | uniform quoting — a worktree path containing a space, a single quote, `$`, and `;` is each individually verified quoted safely | baseline | U | live | REQ-42; RESEARCH §3.1 |
| T-EMT-04 | `extra_args` — an element containing a space, a quote, `$`, and `;` is each individually shell-quoted at emission | baseline | U | live | REQ-13 D11; DESIGN-DECISIONS D11 |
| T-EMT-05 | `extra_args` values are visible in `--dry-run` output | agent=claude | U | live | REQ-13 D11; REQ-18 |
| T-EMT-06 | `extra_args` values are visible in the `-o json` `command` field | agent=codex | U | live | REQ-13 D11; REQ-17 |
| T-EMT-07 | a resolved Codex name emits the canonical UUID-based `codex fork` command | agent=codex | U | live | REQ-46; D17 |

---

## G-OUT — Output contract
Status: done

Purpose: output contract — stdout purity, `-o json` schema fields (incl. `cwd_prompt_expected` per agent), error objects, `--dry-run`, notices, copy-failure-is-notice, a non-C locale row, TTY-format stability.

Varying axes: agent (claude/codex, must vary per §4 — `cwd_prompt_expected` differs by agent); locale (one non-C locale row, R9.4); otherwise baseline pinned.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
| T-OUT-01 | stdout carries only the requested result; all progress/diagnostics/prompts go to stderr | baseline | C | live | REQ-16 |
| T-OUT-02 | human-format output ends with the paste command as the final stdout block | baseline | C | live | REQ-16 |
| T-OUT-03 | TTY does not change the output format (pty row) | baseline | C | live | REQ-16; spec §6.6 |
| T-OUT-04 | `-o json` includes `cwd_prompt_expected: false` for Codex because the E2-locked `-C` template suppresses the prompt | agent=codex | C | live | REQ-17; EXPERIMENTS E2 |
| T-OUT-05 | `-o json` omits the `cwd_prompt_expected` field for Claude | agent=claude | C | live | REQ-17; RESEARCH §5.1 Q4 |
| T-OUT-06 | error object shape on stderr — single `{"error":{"code","message"}}` under any machine format | baseline | C | live | REQ-17 |
| T-OUT-07 | every code in the authoritative stable error catalog round-trips correctly in the `-o json` error object — asserted individually | baseline | C | live | REQ-17 |
| T-OUT-08 | `--dry-run` output lists every planned mutation (branch, worktree path, files-to-carry counts, paste command) and states validation was local-only | baseline | C | live | REQ-18 |
| T-OUT-09 | clipboard copy failure emits a stderr notice; exit code is unaffected | baseline | C | live | DESIGN-DECISIONS D9 |
| T-OUT-10 | non-C locale row — `-o json` machine output is byte-identical regardless of process locale | locale=non-C | C | live | REQ-38 R9.4 |
| T-OUT-11 | `fork -o json` success object carries the REQ-17 minimum fields — `agent`, `parent_session_id`, `fork.branch`, `fork.worktree`, `fork.anchor_commit`, `fork.mode` (state-carry booleans), `verification` (per-check results), `command`, `notices[]` | baseline | C | live | REQ-17 |
| T-OUT-12 | dry-run reports exact composed destination and mutates nothing | baseline | C | live | D15; REQ-44 |
| T-OUT-13 | human and JSON success report their exact composed final paths | baseline | C | live | D15; REQ-44 |
| T-OUT-14 | production boundary-code inventory exactly matches the authoritative error catalog | baseline | C | live | CLI Design Standard R7.12; P01-T19 follow-up |
| T-OUT-15 | every catalog entry renders its JSON code and carries its documented exit family | baseline | C | live | CLI Design Standard R6/R7.12; P01-T19 follow-up |
| T-OUT-16 | handled configuration failure emits `config_error` with exit 2 under JSON output | baseline | C | live | CLI Design Standard R6/R7.8; P01-T19 follow-up |
| T-OUT-17 | Git-only JSON reports `mode=git-only` and omits agent/session fields | baseline | C | live | REQ-45; D16 |
| T-OUT-18 | managed-agent JSON reports `mode=agent` and preserves agent/session fields | agent=claude | C | live | REQ-45; D16 |
| T-OUT-19 | renamed Codex JSON preserves canonical `parent_session_id` and additively reports `parent_session_name` | agent=codex | C | live | REQ-46; D17 |
| T-OUT-20 | renamed Codex dry-run reports the resolution notice and UUID-based paste command | agent=codex | C | live | REQ-46; D17 |
| T-OUT-21 | `fork --dry-run -o json` and `fork --dry-run --json` emit the same parseable preview object with every planned mutation and perform no mutation | baseline | C | live | REQ-17; REQ-18; issue #14; R4.2; R8.6 |

---

## G-CLI — CLI conformance
Status: done

Purpose: CLI conformance — bare→help exit 0, standard flags, the exit-code catalog (incl. unknown `--agent` → exit 3), completion smoke, doctor content, version output.

Varying axes: none of the shared four vary (baseline pinned); the unknown `--agent` row exercises an invalid input value, not the agent axis.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
| T-CLI-01 | bare `agent-fork` → help on stdout, exit 0 | baseline | C | live | REQ-06; DESIGN-DECISIONS D1 |
| T-CLI-02 | standard global flags present — `-h/--help`, `-V/--version` (`agent-fork <semver>`), `-v` repeatable, `-q`, `--config`, `--debug` — each asserted individually | baseline | C | live | REQ-10 |
| T-CLI-03 | exit-code catalog — malformed usage → exit 2 | baseline | C | live | REQ-11 |
| T-CLI-04 | exit-code catalog — unknown `--agent` value → exit 3 | baseline | C | live | REQ-11; REQ-03 |
| T-CLI-05 | `completion` subcommand smoke-tested for `bash`, `zsh`, and `fish` — each shell asserted individually | baseline | C | live | REQUIREMENTS §3.2 |
| T-CLI-06 | doctor content — git version reported against the named `PRODUCT_GIT_MIN` check | baseline | C | live | REQ-38 (A9); spec §8 A9 |
| T-CLI-07 | doctor content — agent CLIs found + versions reported against the version matrix | baseline | C | live | REQ-38 |
| T-CLI-08 | doctor content — env signals visible (Claude/Codex detection env vars) reported | baseline | C | live | REQ-38 |
| T-CLI-09 | doctor content — config valid/invalid reported | baseline | C | live | REQ-38 |
| T-CLI-10 | doctor content — XDG paths writable reported | baseline | C | live | REQ-38 |
| T-CLI-11 | A14 — a failing doctor check produces a non-zero exit | baseline | C | live | REQ-38 (A14); spec §8 A14 |
| T-CLI-12 | `--clean` is rejected as an unknown flag in v1 — usage error, exit 2 (D2; alias deferred to v1.1+) | baseline | C | live | REQUIREMENTS §3.3 (D2) |
| T-CLI-13 | fork help exposes both partial destination flags | baseline | C | live | D15; REQ-44 |
| T-CLI-14 | exact and partial destination overrides are parser-mutually-exclusive | baseline | C | live | D15; REQ-44 |
| T-CLI-15 | publishable help describes commands and core arguments/options, destructive cleanup safety, and the stable exit-code contract | baseline | C | live | CLI Design Standard R7.9/R7.12; REQ-11; P01-T19 |
| T-CLI-16 | Bash completion covers nested actions, flags, and fixed choices and passes syntax validation | baseline | C | live | CLI Design Standard R9.1; P01-T19 follow-up |
| T-CLI-17 | Zsh completion has semantic parity and passes syntax validation when Zsh is installed | baseline | C | live | CLI Design Standard R9.1; P01-T19 follow-up |
| T-CLI-18 | Fish completion has semantic parity and passes syntax validation when Fish is installed | baseline | C | live | CLI Design Standard R9.1; P01-T19 follow-up |
| T-CLI-19 | semantic metavariables, config-view output help, and read-first config action order match the approved contract | baseline | C | live | CLI Design Standard R3/R7.9; P01-T19 follow-up |
| T-CLI-20 | display-only agent enum metadata preserves unknown-agent exit 3 behavior | baseline | C | live | REQ-03/REQ-11; P01-T19 follow-up |
| T-CLI-21 | `--require-agent` and `--no-agent` are mutually exclusive | baseline | C | live | REQ-45; D16 |
| T-CLI-22 | `--no-agent` conflicts with explicit agent/session inputs | baseline | C | live | REQ-45; D16 |
| T-CLI-23 | a real fork outside an agent succeeds in default auto mode as Git-only | baseline | C | live | REQ-45; D16 |
| T-CLI-24 | help, positive/negative flag spelling, and dotted config set/get expose the Codex-specific control | agent=codex | C | live | REQ-46; D17 |

---

## G-SES — Session inspection and assertions
Status: done

Purpose: agent-neutral current-session reporting, sourced parent evidence, and composable validation assertions.

Varying axes: agent (Claude/Codex), session evidence (none/current/parent), and output format.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
| T-SES-01 | no agent signals produce observational `not_detected` evidence | baseline | U | live | REQ-47; D18 |
| T-SES-02 | Claude environment conjunction identifies the current session and source | agent=claude | U | live | REQ-47; D18 |
| T-SES-03 | simultaneous Claude and Codex signals report ambiguity | baseline | U | live | REQ-47; D18 |
| T-SES-04 | exact Claude transcript metadata resolves the current display name | agent=claude | U | live | REQ-47; D18 |
| T-SES-05 | Claude lineage and planned name remain explicitly claimed evidence | agent=claude | U | live | REQ-47; D18 |
| T-SES-06 | versioned XDG lineage claims round-trip and replace deterministically | baseline | U | live | REQ-47; D18 |
| T-SES-07 | agent/current/parent/presence assertions compose with AND semantics | agent=codex | U | live | REQ-47; D18 |
| T-SES-08 | missing or mismatched assertions raise the typed validation failure | baseline | U | live | REQ-47; D18 |
| T-SES-09 | no-session JSON inspection succeeds with the stable evidence schema | baseline | C | live | REQ-47; D18 |
| T-SES-10 | unconstrained validate requires a detectable current session | baseline | C | live | REQ-47; D18 |
| T-SES-11 | CLI agent, current-ID, and no-parent assertions pass together | agent=claude | C | live | REQ-47; D18 |
| T-SES-12 | parent-ID plus no-parent is an exit-2 usage conflict | baseline | C | live | REQ-47; D18 |
| T-SES-13 | `session --json` is byte-identical to `session -o json` | baseline | C | live | REQ-47; D18 |
| T-SES-14 | Codex `thread/read` returns the current name and `forkedFromId` parent | agent=codex | U | live | REQ-47; D18 |
| T-SES-15 | cleanup removes the worktree registry entry but retains Claude lineage | agent=claude | F | live | REQ-47; D18 |
| T-SES-16 | lineage-write failure compensates the registry and rolls back Git resources | agent=claude | F | live | REQ-47; D18 |
| T-SES-17 | real Claude `-p` shell observation matches the outer result session ID | agent=claude | R | live | REQ-47; D18; EXPERIMENTS E8 |
| T-SES-18 | real Codex `exec --json` shell observation matches `thread.started` | agent=codex | R | live | REQ-47; D18; EXPERIMENTS E9 |
| T-SES-19 | human session output escapes terminal controls in agent-owned values | baseline | C | live | REQ-47; D18 |
| T-SES-20 | a real resumed Claude child observes its recorded parent claim | agent=claude | R | live | REQ-47; D18; EXPERIMENTS E10 |
| T-SES-21 | a hostile Claude session ID cannot escape the bounded transcript path | agent=claude | U | live | REQ-47; D18 |
| T-SES-22 | inspection works outside Git and performs no lineage-store write | baseline | C | live | REQ-47; D18 |

---

## G-EXP — Live experiments
Status: done

Purpose: live experiments — E1 (Claude flag combo), E2 (Codex cross-cwd + `-C`), E3 (Claude E2E); E4 retired (A8).

Varying axes: agent (claude/codex, must vary per §4 — E1/E3 claude, E2 codex); otherwise baseline pinned.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
| T-EXP-01 | E1 — Claude flag combo `--resume <id> --fork-session --session-id <pre-pinned> -n <name>` in one non-interactive invocation; asserts no flag silently no-ops | agent=claude | R | live | RESEARCH §7 E1; (EXPERIMENTS.md, Phase B) |
| T-EXP-02 | E2 — host-managed Codex cross-cwd fork `codex fork <explicit-uuid>` plus `-C <worktree>` variant; asserts explicit ID bypasses cwd filtering and documents the TUI cwd-change prompt behavior | agent=codex | R | live | RESEARCH §7 E2; RESEARCH §5.1 Q4; (EXPERIMENTS.md, Phase B) |
| T-EXP-03 | E3 — Claude E2E: full paste command run in a real worktree; asserts full context recall, fresh UUID, parent transcript untouched | agent=claude | R | live | RESEARCH §7 E3; (EXPERIMENTS.md, Phase B) |
| T-EXP-04 | E4 — `.jsonl`-copy last-resort fallback smoke test, retired until milestone v1.1 | agent=claude | R | retired | RESEARCH §7 E4; spec §8 A8 |
| T-EXP-05 | E5 — absorbed into G-MAT/G-VER core TDD (mapping row — prevents restoration from stale RESEARCH §7) | n/a | n/a | n/a | RESEARCH §7 E5 |
| T-EXP-06 | E6 — Codex pre-0.95.0 fallback disambiguation, tombstoned with the pre-0.95 detection ladder | n/a | n/a | tombstone | RESEARCH §7 E6 (A7) |
| T-EXP-07 | E7 — a real renamed Codex thread resolves through the installed app-server to the expected UUID without repository mutation | agent=codex | R | live | REQ-46; D17; EXPERIMENTS E7 |

---

## G-FIX — Fixture layer
Status: done

Purpose: the fixture layer itself — builder-vs-spec verification, oracle mutation rows, the env-seal assertion, git-version canaries, the shim-interception canary, the realpath rule.

Varying axes: topology (builder-vs-spec verification spans the topology set); mode plus file-state inventory (oracle mutation rows perturb properties across state types); otherwise baseline pinned.

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
| T-FIX-01 | builder-vs-spec verification — plain@branch topology constructor matches its declared spec | topology=plain@branch | F | live | spec §6.3; RESEARCH §2.3 |
| T-FIX-02 | builder-vs-spec verification — plain@main topology constructor matches its declared spec | topology=plain@main | F | live | spec §6.3; RESEARCH §2.3 |
| T-FIX-03 | builder-vs-spec verification — detached topology constructor matches its declared spec | topology=detached | F | live | spec §6.3; RESEARCH §2.3 |
| T-FIX-04 | builder-vs-spec verification — linked-worktree topology constructor matches its declared spec (built with a divergent, separately-dirty main checkout) | topology=linked-worktree | F | live | spec §6.3; RESEARCH §2.3 |
| T-FIX-05 | builder-vs-spec verification — bare@bare topology constructor matches its declared spec | topology=bare@bare | F | live | spec §6.3; RESEARCH §2.3 |
| T-FIX-06 | builder-vs-spec verification — bare@wt topology constructor matches its declared spec | topology=bare@wt | F | live | spec §6.3; RESEARCH §2.3 |
| T-FIX-07 | builder-vs-spec verification — dot-bare@wt topology constructor matches its declared spec | topology=dot-bare@wt | F | live | spec §6.3; RESEARCH §2.3 |
| T-FIX-08 | builder-vs-spec verification — nested-bare topology constructor matches its declared spec | topology=nested-bare | F | live | spec §6.3; RESEARCH §2.3 |
| T-FIX-09 | builder-vs-spec verification — unborn(plain) topology constructor matches its declared spec | topology=unborn(plain) | F | live | spec §6.3; RESEARCH §2.3 |
| T-FIX-10 | builder-vs-spec verification — unborn(bare) topology constructor matches its declared spec | topology=unborn(bare) | F | live | spec §6.3; RESEARCH §2.3 |
| T-FIX-11 | oracle mutation — flip a byte in a materialized file out-of-band → manifest+hash oracle fails on exactly that file | baseline | F | live | spec §5; spec §6.5 |
| T-FIX-12 | oracle mutation — chmod a materialized file out-of-band → oracle fails on exactly that file (lstat mode mismatch) | baseline | F | live | spec §5; spec §6.5 |
| T-FIX-13 | oracle mutation — retarget a symlink out-of-band → oracle fails on exactly that symlink | baseline | F | live | spec §5; spec §6.5 |
| T-FIX-14 | oracle mutation — add an untracked file out-of-band → manifest oracle fails on the unexpected entry | baseline | F | live | spec §5; spec §6.5 |
| T-FIX-15 | oracle mutation — `update-index` one entry out-of-band → index-comparison oracle fails on exactly that entry | baseline | F | live | spec §5; spec §6.5 |
| T-FIX-16 | env-seal leak assertion — no key prefixed `CLAUDE`, `CODEX`, `AI_AGENT`, or `GIT_` is present in the sealed subprocess env outside the declared whitelist | baseline | F | live | spec §6.2 |
| T-FIX-17 | realpath rule — every fixture handle path satisfies `handle.path == realpath(handle.path)` | baseline | F | live | spec §6.5 |
| T-FIX-18 | git-version canary — filter-divergence: the non-idempotent clean filter on a staged new file diverges identically on git 2.43 and 2.50 | baseline | F | live | spec §6.6; spec §5 |
| T-FIX-19 | git-version canary — origin/HEAD determinism: `git remote set-head origin -a`, applied by the remote constructor, makes origin/HEAD deterministic across git 2.43/2.50 | baseline | F | live | spec §6.4 |
| T-FIX-20 | git-version canary — origin/HEAD deletion row exercises the detection fallback when origin/HEAD is absent | baseline | F | live | spec §6.4 |
| T-FIX-21 | git-version canary — unborn-HEAD repo: git commands return rc=128 consistently across git 2.43/2.50 | topology=unborn(plain) | F | live | spec §5 |
| T-FIX-22 | git-version canary — `just test-git-matrix` proves the portable ITA sequence (`--ita-invisible-in-index`, plain `apply`, `add --intent-to-add`) preserves the ITA path and existing index entries with system Git and Flox Git | baseline | F | live | spec §5; REQ-21 (A3) |
| T-FIX-23 | shim-interception canary — the producer-failure git shim logs non-empty argv for every intercepted call | baseline | F | live | spec §6.6; REQ-43 (A10) |
| T-FIX-24 | harness git-floor gate — F/C/R-tier collection hard-errors when the installed git is below `TEST_HARNESS_GIT_MIN` (2.43); unit tests remain collectible on any git version | baseline | F | live | spec §7.5; spec §2 |
