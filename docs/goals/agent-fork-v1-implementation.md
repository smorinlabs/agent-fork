# Goal: complete agent-fork v1 through the Phase D gate

> Active execution contract: [complete the Phase E companion skill](phase-e-companion-skill.md).

## Objective

Implement `agent-fork` v1 test-first against the committed test matrix, validate
the finished behavior through independent cross-checks and adversarial cases,
and stop with a complete evidence package at the Phase D owner-review gate.

This is one coherent implementation objective. It does not authorize release,
publishing, or companion-skill work.

## Verifiable stopping condition

The goal is complete only when all of the following are true:

1. Phase B has been owner-approved and landed through the required worktree/PR
   workflow.
2. The Phase C implementation plan has been written, owner-approved, and
   followed or explicitly amended with owner approval.
3. Every live or unblocked row in `docs/testing/TEST-MATRIX.md` passes.
4. No `pending:` lifecycle skip remains.
5. Every group except the intentionally retired experiment group obligations is
   `done`; G-EXP remains `done`.
6. T-EXP-04 remains skipped with its `retired:` reason until v1.1. A
   `requires_real_cli:` skip is permitted only when the corresponding binary is
   genuinely absent.
7. `make check`, `just all`, `just check-matrix`, strict collection, and
   `git diff --check` pass.
8. CI is green and the cross-validation and adversarial reviews below have no
   undispositioned findings.
9. `PROJECTS.md`, `projects/P01-agent-fork-v1.md`, and `CONFORMANCE.md` match the
   implemented state.
10. A Phase D gate report has been produced and work has stopped before Phase E.

Pass totals are evidence, not the contract. At goal creation, the expected
shape in this real-CLI guest is approximately 215 passing tests and one retired
skip, plus any new regression or cross-validation tests added during
implementation.

## Current baseline

- Repository: `/work/agent-fork`
- Phase B merge: PR #5, merge commit `383c186`.
- Phase A and Phase C.5 are complete.
- Phase B is owner-approved, merged, and verified on clean `main`.
- Current verified suite after Phase B: 34 passed, 182 skipped.
- The original 185 stubs comprise:
  - 3 completed G-EXP rows;
  - 177 pending live implementation rows;
  - 4 G-PRE rows blocked on the A9 Git-floor audit;
  - 1 retired T-EXP-04 row that must remain skipped.
- The project-harness plugin may be unavailable in some sessions. When it is
  unavailable, preserve its documented `PROJECTS.md` and P01 conventions
  directly and report that fallback.

## Authoritative sources and precedence

Read these completely before planning or implementing:

1. `DESIGN-DECISIONS.md`
2. `REQUIREMENTS.md`
3. `docs/superpowers/specs/2026-08-08-test-architecture-design.md`
4. `docs/superpowers/specs/2026-08-08-test-architecture-reviews.md`
5. `docs/testing/TEST-MATRIX.md`
6. `IMPLEMENTATION-PROMPT.md`
7. `docs/handoffs/2026-08-09-vm-implementation.md`
8. `RESEARCH.md`
9. `CONFORMANCE.md`
10. `projects/P01-agent-fork-v1.md`

Precedence is the order locked by `IMPLEMENTATION-PROMPT.md`. Do not silently
resolve a contradiction by changing the design. Stop and present the exact
conflict to the owner.

## Scope

- Phase B review and clean landing.
- Phase C dependency-ordered implementation plan.
- Phase D fixture layer, product implementation, tests, CI, documentation,
  cross-validation, adversarial testing, and whole-branch review.
- Claude Code and Codex behavior specified for v1.
- All REQ-01..43 and amendments A1..A14 applicable through Phase D.

## Explicit exclusions

- Phase E companion skill.
- Phase F release, publishing, PyPI/TestPyPI, Homebrew, or release-please work.
- Handoff-file degradation ladder.
- `--clean` alias.
- jj backend.
- Pi, OpenCode, Kilo, Windows, or other v2 targets.
- Any design change not explicitly approved by the owner.

## Non-negotiable invariants

- TDD: no implementation behavior before its test exists and has been observed
  failing for the intended reason.
- Matrix lifecycle: `pending` keeps pending skips; `tdd` has no lifecycle skips;
  `done` has no lifecycle skips and is fully green.
- No `xfail`.
- G-FIX must be implemented and proven before fixture-dependent product groups.
- Test oracles outrank product output. Never use product porcelain as the test
  oracle where the architecture requires manifest/hash or index comparison.
- Resolve `git` through PATH per invocation.
- Run `just all` and `just check-matrix` at every landed checkpoint.
- Preserve a clean `main`. After Phase A, changes use a dedicated worktree,
  intentional commits, a PR, review, and merge.
- Do not remove, weaken, or skip a failing test to obtain green.
- Do not implement tombstone or n/a rows.
- Keep T-EXP-04 retired until v1.1.

## Owner-review gates

### Gate 0: Phase B review and landing

Before Phase C:

1. Show the owner the complete Phase B diff and verification evidence.
2. Obtain approval for the E1-E3 findings and REQ-28 template decisions.
3. Move or recreate the approved diff on a dedicated worktree branch without
   losing evidence.
4. Run `make check`, `just all`, `just check-matrix`, and `git diff --check`.
5. Commit, push, open a PR, complete review, merge, and verify clean updated
   `main`.
6. Record the merge commit in the progress log.

Stop for owner review if Phase B has not already been approved. Do not infer
approval merely because this goal was started.

### Gate 1: Phase C plan review

Produce a detailed dependency-ordered implementation plan. Every task must name
its first failing matrix row, its implementation boundary, its proof commands,
and its review checkpoint. Include the CI strict-collection workflow first, the
A9 audit before blocked G-PRE rows, and G-FIX before fixture consumers.

Stop for owner approval. Do not write product implementation code before this
gate is approved.

### Gate 2: fixture foundation review

After CI foundation, A9, and all 24 G-FIX rows are green, perform an independent
adversarial review of the fixture/oracle layer. Stop on any finding that could
invalidate downstream tests. Continue only after findings are fixed and the
foundation is green.

### Gate 3: pipeline-core review

After G-CFG through G-RBK are green, cross-validate materialization,
verification, and rollback independently. Resolve all findings before agent or
command integration continues.

### Gate 4: integration review

After registry, preflight, emitted-command, include/ignore, cleanup, output, and
CLI groups are green, run the whole-branch cross-validation and adversarial
suite.

### Gate 5: Phase D owner review

Produce the final evidence package and stop. Do not begin Phase E or Phase F.

## Row-by-row execution protocol

For every live or newly unblocked matrix row:

1. Identify the owning group, requirement, design decision, fixtures, and
   implementation boundary.
2. Confirm the group is the next dependency-safe group.
3. Flip the group from `pending` to `tdd` when its implementation begins and
   remove that group's pending skip markers.
4. Run the narrow test and record its failing output. The failure must prove
   missing behavior, not a broken fixture or collection error.
5. Implement the smallest complete behavior required by the row and its locked
   contract.
6. Run the narrow test to green.
7. Run the full group.
8. Run affected upstream and downstream groups.
9. Run `just all` and `just check-matrix`.
10. Update the progress log and P01 task immediately.
11. Commit a coherent checkpoint and obtain the required review.
12. Flip a group to `done` only when all of its live/unblocked rows pass and no
    lifecycle skip remains.

Never batch unchecked rows merely to reduce the skip count. A parametrized row
still needs each required axis and cell proven as specified by the matrix.

## Dependency and group order

The Phase C plan may refine task boundaries but must preserve these
dependencies:

1. CI strict collection and matrix enforcement.
2. A9 `PRODUCT_GIT_MIN` audit; update REQ-38 and unblock T-PRE-06..09.
3. G-FIX.
4. G-CFG.
5. G-DET.
6. G-GRD.
7. G-ANC.
8. G-NAM.
9. G-LOC.
10. G-MAT.
11. G-VER.
12. G-RBK.
13. G-REG.
14. G-PRE.
15. G-EMT.
16. G-INC.
17. G-CLN.
18. G-OUT.
19. G-CLI and end-to-end fork/conformance integration.

G-EXP is already done and remains a regression suite. Run it at relevant
template/preflight checkpoints and at the Phase D gate when real CLIs are
available.

## Cross-validation strategy

Cross-validation must be independent of the implementation path:

- Compare child and parent state with lstat-only manifest/hash and index-stage
  oracles, not the product verification result.
- Validate matrix-to-test collection in both directions with strict collection.
- Trace every applicable REQ and D1..D14 decision to implementation and tests.
- Validate emitted shell commands by parsing/executing safely in disposable
  repos with hostile paths, names, and arguments.
- Re-run E1-E3 against real Claude and Codex CLIs when template or preflight code
  changes.
- Exercise the suite on the guest's minimum supported Git and, when available,
  a second newer Git implementation environment.
- Verify machine output under TTY/non-TTY and C/non-C locale conditions.
- Build/install into a clean disposable environment and exercise the binary,
  without publishing.
- Compare CLI help, streams, JSON, exit codes, and unknown/bare invocation to
  the R9.14 conformance fixtures.

Any cross-validation discrepancy is a finding even if `just all` is green.

## Adversarial test strategy

At minimum, attack these boundaries:

- Signals at each mutation window and during rollback.
- Producer-pipe failures and partial/empty Git output.
- Branch/worktree race loss and pre-existing conflicts.
- Registry lock contention, timeout, corruption, and failed rollback.
- Dirty divergent linked worktrees and detached/unborn/bare repositories.
- Unmerged index, ITA, staged+unstaged same-file changes, ignored/untracked
  nested trees, symlinks, executable bits, binary files, renames, submodules,
  FIFOs, and empty directories.
- Smudge/filter stalls and porcelain divergence.
- Quoting attacks using spaces, quotes, `$`, semicolons, newlines, and option-like
  values in paths, names, IDs, and `extra_args`.
- Missing, stale, below-floor, or malformed Claude/Codex installations and
  missing Codex rollout files.
- TTY prompt routing, closed stdin/stdout/stderr, clipboard failure, and locale
  variance.
- Cleanup invoked from the target cwd; dirty/unpushed guards; `--force`,
  `--yes`, and `--no-input` boundaries.
- Verification failure followed by rollback failure, with manual-recovery
  diagnostics preserved.

Add regression tests for every real finding. Do not add speculative product
scope beyond the locked design.

## Review protocol

- Perform focused review after each coherent checkpoint.
- Use an independent adversarial lens at the fixture, materialization/rollback,
  emitted-command, and whole-branch gates.
- Reviews inspect tests as critically as product code: oracle independence,
  false-green risk, missing axes, skip leakage, timeouts, platform assumptions,
  and cleanup.
- A review finding is complete only when fixed or explicitly dispositioned by
  the owner. Record the disposition and proof.
- If subagents are explicitly authorized and available, they work in separate
  worktrees; mutating work remains sequential. Lack of subagents does not waive
  independent review requirements.

## Required verification

After every landed checkpoint:

```bash
make check
just all
just check-matrix
git diff --check
```

At group completion, also run the group's tests with verbose node IDs. At Phase
D completion, run at least:

```bash
make check
just all
just check-matrix
uv run pytest -vv
uv run pytest --collect-only -q
git diff --check
```

Record command, exit status, pass/skip totals, and any legitimate skip reasons.

## Progress log

Maintain a compact append-only checkpoint log in this file or in a companion
file linked here. `TEST-MATRIX.md` remains the lifecycle source of truth; do not
copy all scenario prose into the log.

### Checkpoints

| Checkpoint | State | Evidence | Commit/PR | Review/findings |
|---|---|---|---|---|
| Phase B review and landing | landed | 34 passed, 182 skipped; matrix green | PR #5 / `383c186` | owner-approved; CodeRabbit success |
| Phase C plan | landed and owner-approved | `docs/superpowers/plans/2026-08-10-agent-fork-v1-implementation.md` | PR #6 / `d7119f2` | owner approved Phase D execution on 2026-08-10 |
| CI + A9 audit | in progress | Task 1 red: missing `.github/workflows/ci.yml` | `ci/phase-d-strict-matrix` | strict-collection CI slice started |
| G-FIX | pending | — | — | — |
| Pipeline core through G-RBK | pending | — | — | — |
| Registry/agent integration | pending | — | — | — |
| Commands/output/conformance | pending | — | — | — |
| Whole-branch review | pending | — | — | — |
| Phase D gate | pending | — | — | — |

For row-level execution evidence, generate or maintain a compact ledger with:

```text
matrix ID | state | red evidence | green evidence | commit/PR | review
```

Allowed execution states are:

```text
pending -> red-confirmed -> implemented -> group-green -> reviewed -> landed
```

## Finding and contradiction protocol

Stop and request owner direction when:

- implementation evidence contradicts a requirement or D-decision;
- two authoritative sources conflict under the locked precedence;
- a requested change expands into deferred/v2 scope;
- a test appears to encode a false oracle or impossible contract;
- a destructive or external action needs authority not granted here;
- an owner-review gate is reached.

Report the exact files, rows, commands, output, and smallest decision required.
Do not paper over the issue with a skip, waiver, or implementation guess.

## Blocked-state protocol

Being difficult, slow, or red is not blocked. Continue with safe diagnostics,
narrow experiments, and dependency-safe work. Treat the goal as blocked only
when meaningful progress cannot continue without owner input or external state,
and report the concrete repeated condition and available choices.

## Final Phase D evidence package

The gate report must contain:

- final pass/skip totals and every remaining skip reason;
- matrix group/status table and confirmation of zero lifecycle skips;
- P01 task status;
- requirement and D1..D14 trace results;
- cross-validation results;
- adversarial findings and dispositions;
- CI status and proof commands;
- commits and PRs landed;
- known limitations and deferred items;
- explicit confirmation that Phase E and Phase F were not started.

## Stop condition

Stop immediately after presenting the Phase D evidence package for owner review.
Do not release, publish, configure release infrastructure, or build the companion
skill until the owner starts a separate approved phase.
