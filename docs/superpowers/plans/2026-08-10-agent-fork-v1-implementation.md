# agent-fork v1 — Phase D implementation plan

**Date:** 2026-08-10  
**Status:** Owner-approved 2026-08-10 — Phase D execution contract
**Scope:** Phase D only; stop before Phase E and Phase F  
**Goal contract:** `docs/goals/agent-fork-v1-implementation.md`

## 1. Outcome

Implement the Python `agent-fork` CLI red-green against the leading test matrix,
cross-validate the Git-state and CLI contracts independently, resolve all
adversarial findings, and stop with the Phase D evidence package.

Completion is defined by matrix state and proof, not a frozen pass count:

- every live or unblocked row passes;
- no `pending:` lifecycle skip remains;
- T-EXP-04 remains the one intentional `retired:` skip;
- `requires_real_cli:` skips occur only when a binary is genuinely absent;
- all implementation groups are `done`;
- `make check`, `just all`, `just check-matrix`, strict collection,
  `git diff --check`, CI, cross-validation, and adversarial reviews are green;
- Phase E/F have not started.

At plan time the suite is 34 passed, 182 skipped: three G-EXP rows pass, 177
live rows remain pending, four G-PRE rows remain blocked until Task 2, and one
experiment remains retired. New regression tests may increase the pass total.

## 2. Locked method

For every task below:

1. Work in a dedicated branch/worktree; never mutate `main`.
2. Inspect the listed rows and stub signatures before editing.
3. Flip the owning group from `pending` to `tdd` when work on that group begins
   and remove its pending skip markers; keep matrix markers permanently.
4. Run the named first test and capture a real red failure caused by missing
   behavior, not fixture setup or collection drift.
5. Write the smallest complete implementation satisfying the locked contract.
6. Run the narrow row, then the full group, then affected dependency groups.
7. Flip the group to `done` only after all live/unblocked rows are green.
8. Update P01 and the goal progress log immediately.
9. Run `make check`, `just all`, `just check-matrix`, and `git diff --check`.
10. Commit intentionally, review the diff and tests, push, open a PR, resolve
    findings, merge with `--merge`, and verify updated clean `main`.

No `xfail`; no lifecycle skip may be weakened or replaced. Test-side
manifest/index/parent snapshots are the truth. Product porcelain is behavior
under test, never the oracle. Git must resolve through PATH on every call.

Implementation and tests are written fresh from the documented behavior. Do
not translate agent-deck source.

## 3. Proposed module boundaries

The exact names can be adjusted during red-green work when a smaller boundary
is clearer, but dependency direction must remain acyclic:

```text
src/agent_fork/
  __init__.py
  cli.py          argparse command tree and process boundary
  config.py       TOML discovery, precedence, tri-state resolver
  errors.py       typed failures, stable codes, exit mapping
  models.py       plans/results/registry records
  git.py          PATH-resolved subprocess primitive only
  repository.py   topology, guards, anchor, worktree creation
  naming.py       sanitization and collision-safe naming
  location.py     sibling/central/subdirectory/template placement
  materialize.py  staged -> unstaged -> untracked/ignored transport
  verify.py       runtime verification ladder
  rollback.py     rollback and signal coordination
  registry.py     XDG state, advisory lock, atomic writes
  agents.py       detection, versions, rollout preflight, templates
  include.py      .worktreeinclude and setup hook
  cleanup.py      cleanup resolution, guards, mutations
  output.py       human/JSON rendering, notices, clipboard
```

Only introduce abstractions exercised by a current row. Centralize command
execution in `git.py` so shims, failure injection, and REQ-43 remain observable.

## 4. Ordered tasks

### Task 1 — blocking CI: matrix and strict collection

**Rows:** checker infrastructure; no product group flip  
**Files:** `.github/workflows/ci.yml`, `justfile`, `pyproject.toml`,
`scripts/check_matrix.py`, `tests/test_check_matrix.py`, P01  
**First failing test:** add a checker/CI-contract unit test proving strict
collection fails for an unregistered marker or broken collection, then run:

```bash
uv run pytest tests/test_check_matrix.py -k strict_collection -vv
```

**Implement:**

- Add the implementation-start blocking CI job required by spec §7.6.
- Run `just check-matrix` and strict `pytest --collect-only` before the test job.
- Run format, lint, typecheck, and tests through committed project commands.
- Keep P01-T18 reserved for the later full R9.14 conformance job; record the CI
  split in P01 without prematurely completing T18.
- Do not require real CLIs in generic CI unless the workflow actually installs
  the agents group; conditional R-tier skips remain legitimate there.

**Proof:** synthetic broken collection fails locally; normal collection and
matrix pass; workflow syntax is valid; PR check is blocking and green.

### Task 2 — A9 Git feature audit and `PRODUCT_GIT_MIN`

**Rows:** unblock T-PRE-06..09; feeds T-CLI-06/T-CLI-11  
**Files:** new `docs/testing/PRODUCT-GIT-MIN-AUDIT.md`, `REQUIREMENTS.md`,
`docs/testing/TEST-MATRIX.md`, `src/agent_fork/git.py`,
`tests/unit/test_pre.py`, `tests/pipeline/test_pre.py`, `tests/cli/test_cli.py`  
**First failing test:** after the audit fixes the version, unskip T-PRE-06 and
run:

```bash
uv run pytest tests/pipeline/test_pre.py -k product_git_min -vv
```

**Audit before implementation:** inventory every production Git command and
flag required by REQ-19..25, D5, A1..A4, A10, and cleanup. Probe official Git
documentation and both available target versions (guest 2.43 and a newer Git
when available). Record command/flag introduction versions, behavioral
differences, mitigations, and the selected lowest defensible product floor.
Do not conflate it with `TEST_HARNESS_GIT_MIN`.

**Implement:**

- Add named `PRODUCT_GIT_MIN` in product code and REQ-38.
- Change T-PRE-06..09 from `blocked` to `live` after the audit.
- Add a PATH-resolved version probe that accepts injected version strings.
- Lock just-below and at/above comparisons; leave fork/doctor integration for
  Tasks 14 and 19 while keeping the pure boundary green.

**Proof:** audit is reproducible; all four rows are live and collected; no
blocked row remains; matrix is green.

**Owner-approved amendment (2026-08-10):** G-PRE lifecycle transitions remain
group-atomic. Task 2 fixes and records the floor and changes T-PRE-06..09 from
`blocked` to `live`, but their red-green product implementation moves to the
dependency-ready full G-PRE task (Task 15). This avoids partially unskipping a
`pending` group or prematurely starting the other agent/orchestration rows.

### Task 3 — G-FIX foundation A: sealed environment and basic worlds

**Rows:** T-FIX-01..10, T-FIX-16..17, T-FIX-24  
**Files:** `tests/conftest.py`, `tests/fixtures/test_fix.py`  
**First failing test:** T-FIX-16:

```bash
uv run pytest tests/fixtures/test_fix.py -k env_seal -vv
```

**Implement:**

- Whitelist-from-empty subprocess environment exactly per spec §6.2.
- Per-test HOME/TMP/XDG roots and global Git config; no ambient agent/Git vars.
- State constructors and plain, detached, linked, bare-at-root, bare-worktree,
  `.bare`, nested-bare, and unborn topology builders.
- Linked topology has divergent commits and separately dirty main/parent trees.
- Realpath every handle path.
- Enforce the 2.43 harness floor for F/C/R while U remains collectible.
- Register hardened finalizers early: go-files, process groups, no-Git teardown,
  chmod retry, and orphan detection.

**Proof:** each topology is asserted structurally rather than merely built;
sealed-env leak test and floor behavior pass.

### Task 4 — G-FIX foundation B: state vocabulary, remote, and oracles

**Rows:** T-FIX-11..15, T-FIX-19..22  
**Files:** `tests/conftest.py`, `tests/fixtures/test_fix.py`  
**First failing test:** T-FIX-11:

```bash
uv run pytest tests/fixtures/test_fix.py -k oracle_mutation -vv
```

**Implement:**

- All state constructors from spec §6.3, including ITA, markerless unmerged,
  symlinks, exec bits, binary, rename/edit, empty dirs, submodules, and include.
- Local bare origin with pushes/fetch and explicit `remote set-head origin -a`.
- Lstat-only manifest: path, type, mode, hash/target; never open non-regular
  files; prune mode-160000 gitlink directories.
- NUL-safe `ls-files --stage` index snapshot with ITA-aware comparison.
- Parent full manifest+index snapshot.
- Oracle mismatch reports name the exact perturbed cell.
- Version canaries for origin/HEAD, unborn rc, and ITA flags.

**Proof:** five out-of-band mutations each fail exactly one oracle cell; FIFO
walk cannot hang; origin fallback works after origin/HEAD deletion.

### Task 5 — G-FIX foundation C: hostile process machinery

**Rows:** T-FIX-18, T-FIX-23; infrastructure for G-GRD/G-VER/G-RBK/G-REG and
CLI pty rows  
**Files:** `tests/conftest.py`, `tests/fixtures/test_fix.py`  
**First failing test:** T-FIX-23:

```bash
uv run pytest tests/fixtures/test_fix.py -k shim_interception -vv
```

**Implement:**

- PATH-first Git shim delegating every non-target call and logging non-empty
  argv; producer failure and park/release modes.
- Non-idempotent clean filter on a staged new file.
- Parent-side step-2 stall with readiness/go files and self-termination.
- Per-fd `openpty`: only selected fd on pty, ECHO/ONLCR cleared, EIO/EOF
  normalized without byte-normalizing product streams.
- Process-group tracking and orphan sweep.

**Proof and fixture gate:** run all 24 G-FIX rows, flip G-FIX to `done`, then
perform an adversarial fixture review for false-green oracles, environmental
leaks, process leaks, and platform assumptions. No fixture consumer proceeds
until findings are resolved.

### Task 6 — G-CFG: configuration resolver and discovery

**Rows:** T-CFG-01..13  
**Files:** `src/agent_fork/config.py`, `src/agent_fork/models.py`,
`tests/unit/test_cfg.py`, `tests/pipeline/test_cfg.py`, `tests/cli/test_cfg.py`  
**First failing test:** T-CFG-01:

```bash
uv run pytest tests/unit/test_cfg.py::test_with_state_unset_defaults_true -vv
```

**Implement:** tri-state defaults, within-source implication, A12 dependent
suppression across sources, flags > env > project > user > system, curated env,
branch-prefix normalization, XDG paths, `--config` replacement, plain and
linked-worktree walk-up boundaries, and config set/validate round-trip. Invalid
TOML/key/type diagnostics must be deterministic and contain no secrets.

**Proof:** all U/F/C CFG rows; add property cases for the resolved mode truth
table without expanding public scope.

### Task 7 — G-DET: agent and parent-session detection

**Rows:** T-DET-01..05; T-DET-06..08 remain tombstones  
**Files:** `src/agent_fork/agents.py`, `src/agent_fork/errors.py`,
`tests/unit/test_det.py`, `tests/pipeline/test_det.py`  
**First failing test:** T-DET-01:

```bash
uv run pytest tests/unit/test_det.py::test_claude_detected_via_env_signals -vv
```

**Implement:** Claude conjunction, Codex `CODEX_THREAD_ID` only, explicit flags
win, ambiguity/neither stable exit-3 failure. Never restore ancestry/fd/newest
rollout fallbacks.

### Task 8 — G-NAM: naming

**Rows:** T-NAM-01..07  
**Files:** `src/agent_fork/naming.py`, `tests/unit/test_nam.py`  
**First failing test:** T-NAM-01:

```bash
uv run pytest tests/unit/test_nam.py::test_sanitizer_rules_asserted_individually -vv
```

**Implement:** Git-safe lowercase slug, date-based branch/detached auto-names,
collision suffixes through the 1000 cap, explicit-name non-suffix behavior, and
identity feed-through. Compute date at call time; midnight retry rebuilds the
world instead of mutating a stale one.

### Task 9 — G-LOC: worktree placement

**Rows:** T-LOC-01..07  
**Files:** `src/agent_fork/location.py`, `tests/unit/test_loc.py`,
`tests/pipeline/test_loc.py`  
**First failing test:** T-LOC-01:

```bash
uv run pytest tests/unit/test_loc.py::test_sibling_default_path_derivation -vv
```

**Implement:** sibling, central XDG data, subdirectory, approved template
placeholders, explicit-config mirror suppression, linked-parent mirroring, and
bare-root child override. Reject unresolved/unsafe templates deterministically.

### Task 10 — G-GRD: repository detection and pre-mutation guards

**Rows:** T-GRD-01..14  
**Files:** `src/agent_fork/git.py`, `src/agent_fork/repository.py`,
`src/agent_fork/errors.py`, `tests/pipeline/test_grd.py`  
**First failing test:** T-GRD-01:

```bash
uv run pytest tests/pipeline/test_grd.py::test_branch_already_exists_refuses -vv
```

**Implement:** PATH-resolved Git primitive, repo/git-dir/common-dir detection,
branch/worktree/path collisions, mid-operation sentinels and exact abort hints,
not-repo, unborn, unmerged index, and race-loss mapping. All refuse before
mutation except the explicitly atomic race loser, which rolls back and maps to
exit 5 `conflict_branch_exists`.

**Adversarial proof:** shim-barrier race repeated enough to prove deterministic
positioning; assert branch, path, registration, and registry absence after
every refusal.

### Task 11 — G-ANC: anchor and atomic worktree creation

**Rows:** T-ANC-01..08  
**Files:** `src/agent_fork/repository.py`, `src/agent_fork/models.py`,
`tests/pipeline/test_anc.py`  
**First failing test:** T-ANC-01:

```bash
uv run pytest tests/pipeline/test_anc.py -k 'plain_branch' -vv
```

**Implement:** resolve `HEAD^{commit}` at the invoking parent path, project
root/common-dir detection for every topology, atomic `worktree add -b` at the
anchor, and metadata for new-branch ownership/detached/default/common-dir.

### Task 12 — G-MAT: exact state materialization

**Rows:** T-MAT-01..20  
**Files:** `src/agent_fork/materialize.py`, `src/agent_fork/git.py`,
`tests/pipeline/test_mat.py`  
**First failing test:** T-MAT-01:

```bash
uv run pytest tests/pipeline/test_mat.py::test_staged_only_file_transported_byte_identical -vv
```

**Implement in fixed order:**

1. cached binary diff with `--ita-invisible-in-index` into `apply --index`;
2. uncached binary diff into plain `apply`;
3. ITA paths through `apply --intent-to-add` as required;
4. NUL-safe untracked copy;
5. separate ignored pass only for `exact+ignored`.

Use lstat/readlink/copy with modes; never mutate parent; preserve staged vs
unstaged split; treat submodules as opaque gitlinks; document empty-dir
absence; no-state is a true no-op. Treat producer exit status as authoritative
even with empty stdout.

**Adversarial review:** after all 20 rows, independently compare parent/child
with manifest/index oracles across hostile states and both linked checkouts.

### Task 13 — G-VER and G-RBK: verification, rollback, and signals

**Rows:** T-VER-01..11 and T-RBK-01..06  
**Files:** `src/agent_fork/verify.py`, `src/agent_fork/rollback.py`,
`src/agent_fork/repository.py`, `tests/pipeline/test_ver.py`,
`tests/pipeline/test_rbk.py`  
**First failing tests:** T-VER-01, followed before rollback code by T-RBK-01:

```bash
uv run pytest tests/pipeline/test_ver.py::test_verify_anchor_check -vv
uv run pytest tests/pipeline/test_rbk.py::test_materialize_failure_triggers_rollback -vv
```

**Implement:** six base ladder checks, conditional topology checks,
`--no-verify`, typed `verify_failed`, precise worktree/branch rollback,
manual-recovery text only on rollback failure, and SIGINT/SIGTERM process
handling producing 130/143 after cleanup. Pipe producers and consumers must
both be checked.

**Pipeline-core gate:** run G-CFG, G-DET, G-NAM, G-LOC, G-GRD, G-ANC, G-MAT,
G-VER, and G-RBK together. Cross-validate state independently, inject filter
divergence and producer failure with verification both on/off, inspect orphan
processes and parent snapshots, and resolve all findings before continuing.

### Task 14 — G-REG: XDG registry and list model

**Rows:** T-REG-01..07  
**Files:** `src/agent_fork/registry.py`, `src/agent_fork/models.py`,
`tests/unit/test_reg.py`, `tests/pipeline/test_reg.py`, `tests/cli/test_reg.py`  
**First failing test:** T-REG-01:

```bash
uv run pytest tests/unit/test_reg.py::test_registry_write_populates_schema_fields -vv
```

**Implement:** stable schema, UTC creation time, deterministic ordering, XDG
state file, same-directory temp+fsync+atomic replace, advisory lock with bounded
approximately-five-second wait, self-clearing death semantics, `registry_busy`,
and ownership lookup. Registry failure after creation invokes rollback.

**Adversarial proof:** simultaneous different-name writes, held-lock timeout,
process death, corrupt/truncated input, and rollback-failure diagnostics.

### Task 15 — G-PRE: agent and Git preflight

**Rows:** T-PRE-01..10, now including unblocked T-PRE-06..09  
**Files:** `src/agent_fork/agents.py`, `src/agent_fork/git.py`,
`src/agent_fork/errors.py`, `tests/unit/test_pre.py`,
`tests/pipeline/test_pre.py`  
**First failing test:** T-PRE-01:

```bash
uv run pytest tests/pipeline/test_pre.py::test_agent_cli_entirely_missing_refuses_with_diagnosis -vv
```

**Implement:** executable discovery, robust version parsing, Claude 2.0.73 floor
and warn band, Codex 0.81 fork floor/0.95 env requirement, CODEX_HOME rollout
glob, D14 diagnosis and doctor pointer, selected product Git floor, and A14
`--force` override restricted to Git floor. Preflight occurs before every
mutation.

### Task 16 — G-EMT: locked launch templates and quoting

**Rows:** T-EMT-01..06; regress G-EXP-01..03  
**Files:** `src/agent_fork/agents.py`, `tests/unit/test_emt.py`,
`tests/live/test_exp.py`  
**First failing test:** T-EMT-01:

```bash
uv run pytest tests/unit/test_emt.py::test_claude_fixed_prefix_byte_exact -vv
```

**Implement:** `shlex.quote` every interpolated element, exact E1 Claude and E2
Codex templates, pre-generated UUID for Claude, name, and individually quoted
`extra_args` suffix. Do not string-split or interpolate configured arguments.

**Cross-validation:** parse/execute emitted commands in disposable hostile-path
worlds; rerun real E1-E3 after any template change.

### Task 17 — fork orchestrator and G-INC

**Rows:** T-INC-01..05 plus integrated rows already green in guards through EMT  
**Files:** new `src/agent_fork/pipeline.py`, `src/agent_fork/include.py`,
`src/agent_fork/cli.py`, `tests/pipeline/test_inc.py`  
**First failing test:** T-INC-01:

```bash
uv run pytest tests/pipeline/test_inc.py::test_worktreeinclude_copies_listed_gitignored_files -vv
```

**Implement normative order:** preflight -> guards -> anchor/create ->
materialize -> verify -> `.worktreeinclude` -> setup hook -> registry -> emit.
Include never overwrites materialized files. Hook path is
`.agent-fork/worktree-setup.sh`, cwd is child, documented repo/worktree env is
provided, and failure is a non-fatal notice. Include/hook changes remain outside
the state comparison by running after verify.

Add a narrow successful fork integration test only if an existing matrix row
cannot prove orchestration; map any new test to an approved matrix addition
rather than leaving it outside the leading document.

### Task 18 — G-CLN: cleanup domain service and command

**Rows:** T-CLN-01..15  
**Files:** `src/agent_fork/cleanup.py`, `src/agent_fork/cli.py`,
`tests/pipeline/test_cln.py`, `tests/cli/test_cln.py`  
**First failing test:** T-CLN-01:

```bash
uv run pytest tests/pipeline/test_cln.py::test_cleanup_target_accepts_name_branch_or_path -vv
```

**Implement:** name/branch/path resolution, ownership, worktree remove/prune,
optional branch preservation, registry update, dirty/unpushed/invoking-cwd
guards, force boundaries, consent/yes/no-input, dry-run, and session-file
preservation notice. The invoking-cwd guard is never overridable; force never
substitutes for consent.

### Task 19 — G-OUT: result/error rendering and clipboard

**Rows:** T-OUT-01..11  
**Files:** `src/agent_fork/output.py`, `src/agent_fork/errors.py`,
`src/agent_fork/cli.py`, `tests/cli/test_out.py`  
**First failing test:** T-OUT-01:

```bash
uv run pytest tests/cli/test_out.py::test_stdout_carries_only_requested_result -vv
```

**Implement:** stdout result purity, stderr progress/prompts/notices, final human
paste block, TTY-invariant format, stable open JSON schema,
`cwd_prompt_expected: false` for Codex and absent for Claude, stable error
objects/catalog, full dry-run plan, locale-independent UTF-8 JSON, and clipboard
OSC52 -> platform helper fallback. Clipboard failure is notice-only.

**Adversarial proof:** closed/redirected fds, TTY on each fd separately,
non-C locale, shell metacharacters, copy helpers missing/failing, and every
stable error code.

### Task 20 — G-CLI: full command tree, doctor, config, completion

**Rows:** T-CLI-01..12; completes CLI portions of G-CFG/G-REG/G-CLN/G-OUT  
**Files:** `src/agent_fork/cli.py`, relevant services, `tests/cli/test_cli.py`  
**First failing test:** T-CLI-01:

```bash
uv run pytest tests/cli/test_cli.py::test_bare_invocation_prints_help_exit_0 -vv
```

**Implement:** argparse without prefix abbreviation; bare help; global reserved
flags; fork/cleanup/list/doctor/config view|get|set|validate/completion/help;
result-output options where required; exit mapping; version string; doctor Git,
agents, env, config, and XDG checks with non-zero aggregate failure; bash/zsh/fish
completion; explicit rejection of `--clean`.

### Task 21 — R9.14 conformance CI and clean-install validation

**Rows:** existing G-CLI/G-OUT command-contract rows; P01-TS14/P01-T18  
**Files:** `.github/workflows/ci.yml`, `tests/cli/`, `CONFORMANCE.md`, README or
other existing user documentation where required  
**First failing test:** add the missing R9.14 fixture only after identifying a
specific uncovered standard obligation; first run the conformance selection:

```bash
uv run pytest tests/cli -vv
```

**Implement:** named blocking conformance job for help shape, bare/unknown
invocation, streams, exit codes, JSON, and packaging entry point. Build/install
the wheel into a disposable clean environment and exercise `agent-fork
--version` and help without publishing. Document no telemetry, ignored-file
secret-copy behavior, and deferred surfaces when required by REQ-15/38.

### Task 22 — full cross-validation, adversarial sweep, and Phase D gate

**Rows:** all non-tombstone rows; E1-E3 real CLI; T-EXP-04 retired  
**Files:** tests and product only for concrete findings; `CONFORMANCE.md`, P01,
goal progress log  
**First failing test:** each newly found defect gets a focused regression test
that is observed red before its fix.

**Required independent lenses:**

- matrix/strict-collection bidirectional audit;
- REQ-01..43 and D1..D14 trace audit;
- fixture/oracle false-green audit;
- Git mutation, signals, rollback, race, and registry stress;
- emitted-command shell-boundary audit;
- CLI standard/conformance and clean-install audit;
- real Claude/Codex template regression;
- whole-diff maintainability and scope review.

Run:

```bash
make check
just all
just check-matrix
uv run pytest -vv
uv run pytest --collect-only -q
git diff --check
```

Confirm every remaining skip reason explicitly, every matrix group status, CI,
commits/PRs, review findings/dispositions, and deferred items. Update P01 and
CONFORMANCE to current truth. Produce the Phase D evidence package and stop.
Do not begin release or companion-skill work.

## 5. Checkpoint and review map

| Checkpoint | Tasks | Required independent review |
|---|---:|---|
| CI and floor | 1–2 | workflow/collection audit; Git-feature evidence review |
| Fixture gate | 3–5 | oracle false-green, env/process leak, cross-platform review |
| Pure foundations | 6–9 | config truth table, detection tombstones, path/name safety |
| Mutation core | 10–13 | adversarial Git, parent invariance, rollback/signal review |
| Registry and agents | 14–16 | concurrency/locking and real-template review |
| Commands | 17–20 | orchestration order, destructive cleanup, streams/quoting review |
| Conformance | 21 | CLI standard and clean-install review |
| Phase D | 22 | whole-branch + adversarial second lens; owner gate |

When explicitly authorized and available, use separate-worktree subagents with
the kickoff model matrix: standard tasks to the standard implementation lens;
mutation/rollback/race work to the strongest mutating lens; mechanical doc and
status flips to a mechanical lens; independent adversarial and whole-branch
reviews to separate lenses. Mutating tasks remain sequential. The driving
session owns corpus precedence, integration, and gate decisions.

## 6. Tracking updates at plan approval

After owner approval of this plan:

- set the P01 `Plan` reference to this file;
- mark P01-T07 complete in the plan-approval PR;
- retain all Phase D TS-before-T pairs;
- record Task 1 as the implementation-start portion of P01-T18 without marking
  the full conformance task complete;
- initialize the row-level evidence ledger from the current matrix;
- begin Task 1 in a fresh implementation worktree.

No Phase D group status changes and no product implementation belong in the
Phase C plan PR.

## 7. Phase C gate

Owner approval must answer only whether this plan is an acceptable execution
contract for Phase D. On approval, land this plan by PR, update P01 as described,
then begin Task 1. Until approval, stop: do not flip another group to `tdd`, add
the CI workflow, select `PRODUCT_GIT_MIN`, implement fixtures, or edit product
code.
