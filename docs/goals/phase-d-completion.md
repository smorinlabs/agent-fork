# Goal: finish Phase D and stop before Phase E

**Created:** 2026-08-10  
**Runtime goal:** `019fea2f-91cc-71b1-b29d-a43dfe4137b2`  
**Status:** active  
**Branch:** `feat/phase-d-implementation`  
**Worktree:** `/work/agent-fork-phase-d`

## Objective

Complete the approved Phase D implementation plan in full: implement the
`agent-fork` v1 CLI test-first, resolve every live or unblocked matrix row,
perform independent cross-validation and adversarial testing, prepare one final
Phase D pull request, and stop at the owner-review gate immediately before
Phase E.

This goal does not authorize release, publishing, package-registry changes,
Homebrew work, or the Phase F companion skill.

## Authority and execution contract

- The detailed task order is
  [the approved Phase D plan](../superpowers/plans/2026-08-10-agent-fork-v1-implementation.md).
- The broader quality contract is
  [the v1 implementation goal](agent-fork-v1-implementation.md).
- Design precedence remains `DESIGN-DECISIONS.md` → `REQUIREMENTS.md` → the
  approved test-architecture corpus → `IMPLEMENTATION-PROMPT.md` → research.
- Work only on `feat/phase-d-implementation`; keep `main` clean.
- Do not open intermediate pull requests. Make intentional checkpoint commits
  on the Phase D branch and open one PR only after all Phase D work is complete.
- Do not begin Phase E or Phase F, even if the final Phase D PR is green.

## Current state

- Phase B landed in PR #5 (`383c186`).
- The Phase C plan landed in PR #6 (`d7119f2`) and was owner-approved.
- Phase D Task 1 landed in PR #7 (`f87987b`): blocking matrix validation and
  strict pytest collection are active and green.
- The Phase D branch starts at `f87987b`.
- Next task: Task 2, the A9 Git feature audit and `PRODUCT_GIT_MIN` boundary.
- Latest Task 1 evidence: 35 passed, 182 skipped; `make check`, `just all`,
  `just check-matrix`, strict collection, CI, and `git diff --check` green.

## Required execution loop

For each dependency-safe group or infrastructure task:

1. Identify the exact matrix rows and locked requirements.
2. Flip a product group to `tdd` only when implementation begins and remove its
   lifecycle skip markers.
3. Observe the first narrow test failing for the intended missing behavior.
4. Implement the smallest complete behavior that satisfies the locked contract.
5. Run the row, group, affected dependencies, and full local gates.
6. Mark the group `done` only when all its live/unblocked rows are green.
7. Record red/green evidence, findings, and disposition in the goal ledger.
8. Commit the coherent checkpoint to the Phase D branch without opening a PR.

Never introduce `xfail`, weaken a test, use product output as its own oracle,
implement tombstone/n-a rows, or remove the retired T-EXP-04 skip.

## Checkpoint gates

| Gate | Scope | Required proof before continuing |
|---|---|---|
| D1 | Tasks 1–2: CI and Git floor | strict collection/matrix green; reproducible Git audit; no blocked matrix rows |
| D2 | Tasks 3–5: G-FIX | all 24 fixture rows green; independent oracle and environment-leak audit clean |
| D3 | Tasks 6–13: foundations and mutation core | config through rollback green; parent invariance, materialization, signal, and rollback cross-checks clean |
| D4 | Tasks 14–20: integration and commands | registry through CLI/output green; locking, quoting, cleanup, and real-template reviews clean |
| D5 | Task 21: conformance | blocking conformance CI and disposable clean-install validation green |
| D6 | Task 22: final Phase D gate | full matrix, requirements trace, adversarial sweep, real CLI regression, whole diff, CI, and final PR green |

A failed checkpoint stays inside Phase D: add a focused regression test, observe
it red, fix it, and repeat the gate. Stop for owner direction only on a genuine
corpus contradiction or a decision that changes locked scope or behavior.

## Completion criteria

This goal is complete only when all of the following are true:

- Every live or newly unblocked matrix row passes.
- Every implementation group is `done`; no `pending:` lifecycle skip remains.
- T-EXP-04 is the sole planned retired skip. A `requires_real_cli:` skip is
  allowed only when its corresponding binary is genuinely absent.
- `make check`, `just all`, `just check-matrix`, `just strict-collect`, the full
  verbose suite, and `git diff --check` pass.
- All REQ-01..43 and D1..D14 have an implemented, tested, waived, or explicitly
  inapplicable disposition in `CONFORMANCE.md`.
- Fixture/oracle, Git mutation, rollback/signal, registry race, shell quoting,
  CLI conformance, clean-install, and real Claude/Codex reviews have no open
  findings.
- P01 and the goal evidence accurately reflect the final implementation.
- One final Phase D PR is open and green with the complete evidence package.
- Work has stopped for owner review without starting any Phase E/F task.

Pass totals are evidence rather than a frozen contract; regression and
cross-validation tests may increase the total.

## Evidence ledger

| Checkpoint | State | Evidence | Commit/PR | Findings |
|---|---|---|---|---|
| Task 1 — blocking CI | landed | 35 passed, 182 skipped; matrix, strict collection, local gates and CI green | PR #7 / `f87987b` | none open |
| Task 2 — A9 Git floor | complete | audit selects 2.19.0; four rows changed blocked → live; matrix green | `02d4c6f` | owner approved deferring T-PRE-06..09 red-green to full G-PRE Task 15 |
| D2 — G-FIX | complete | all 24 rows green; 59 passed, 158 skipped overall; matrix, strict collection, lint, types, and oracle review green | Phase D branch | fixed absolute-path floor false-green and unmerged-stage index collapse during review |
| D3 — mutation core | in progress | pure foundations plus G-GRD 14/14 green; 105 passed, 112 skipped overall | Phase D branch | guard race repeated 3x; all refusals preserve destination; PRODUCT_GIT_MIN named in PATH Git primitive |
| D4 — integration | pending | — | — | — |
| D5 — conformance | pending | — | — | — |
| D6 — final Phase D gate | pending | — | final Phase D PR | owner review required |

## Terminal action

When the completion criteria are satisfied, open the single final Phase D PR,
attach the evidence package, verify all checks, and stop. Do not merge the final
PR or proceed to Phase E unless the owner gives a new explicit instruction.
