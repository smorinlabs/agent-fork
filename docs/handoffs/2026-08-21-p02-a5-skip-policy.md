# Session handoff — P02 A5 skip policy — 2026-08-21

## 🎯 Outcome

**Goal:** Finish P02 fault **A5** — implement gate 4 steps 6–8, pass gate 6
(adversarial review of the implementation), then open and merge one PR.

**Out of scope:** issues #59 and #60 (filed, deliberately not fixed here), the
rest of issue #28, issue #45, and every other P02 fault. Do not reopen the two
owner-accepted known limits (see "Rejected approaches").

**Self-contained:** ⚠ **The branch is unpushed — 33 commits exist only on the
originating machine.** See preflight. Everything else travels.

## ⚠ Portability & dependency preflight — read first

- **Unpushed: 33 commits, no upstream configured.** On any other machine this
  work **does not exist**. Before this handoff can be used elsewhere:
  `git push -u origin worktree-p02-a5-parent-race-probe`
- **Uncommitted: none.** Working tree clean.
- **Stashes: none.**
- **The work lives in a git worktree**, not a normal checkout:
  `/Users/stevemorin/c/agent-fork/.claude/worktrees/p02-a5-parent-race-probe`.
  On another machine, clone the repo and check the branch out normally — the
  worktree path is not reproducible and does not matter.
- **Referenced docs:** design doc ✓ exists · committed · 712 lines · no
  placeholders. Register ✓ committed · 709 lines. Both travel once pushed.
- **This handoff doc is itself uncommitted until you commit it.**

## 🧭 Where you are

- **Repo:** agent-fork · origin `https://github.com/smorinlabs/agent-fork.git`
  · default branch `main`
- **Branch:** `worktree-p02-a5-parent-race-probe` @ `b06d366`
- **0 behind `main`** as of 2026-08-21 — but `main` moved **five times** during
  this item (A2, A4, A6a, A10, A3, A12). **Merge `main` before writing code**,
  and re-check test-row IDs after every merge; they have been taken out from
  under this branch four times.
- **Verify:** `just all` (≈7 min, currently **663 passed, 1 skipped**) and
  `just check-matrix`.

## 📎 Artifacts & sources of truth

| What | Repo-relative path (canonical) | Abs (this machine) | Status |
|---|---|---|---|
| Design doc + plan (normative) | `docs/superpowers/plans/2026-08-20-p02-a5-skip-and-race-policy.md` | `/Users/stevemorin/c/agent-fork/.claude/worktrees/p02-a5-parent-race-probe/docs/…` | ✓ committed & substantive |
| Fault register (A5 entry) | `projects/P02-agent-fork-fault-remediation.md` | same worktree | ✓ committed & substantive |
| Tests written so far | `tests/pipeline/test_a5_skip.py` | same worktree | ✓ committed |
| Test matrix | `docs/testing/TEST-MATRIX.md` | same worktree | ✓ committed |
| Routed-out findings | GitHub issues [#59](https://github.com/smorinlabs/agent-fork/issues/59), [#60](https://github.com/smorinlabs/agent-fork/issues/60) | — | ✓ filed |

## 📋 Plan · inlined skeleton

*Full detail in the design doc; this skeleton is enough to start cold.*

**What A5 fixes:** `agent-fork` must not refuse to work because of one entry it
cannot copy. Before A5, a single unreadable untracked file made the whole fork
fail with a raw `[Errno 13]`.

**The governing rule (normative — do not paraphrase from summaries):** a skip
requires **all three** preconditions, or the entry raises `entry_unreadable`:

1. the entry is **untracked or ignored** (tracked paths never skip),
2. its **`lstat` succeeded**, so a stability sentinel exists,
3. the fork **carries no deletion** (collected via `--diff-filter=D`).

A parent change during the fork still **fails and reverts** — unchanged
behaviour. `--strict` turns every skip into a refusal.

**Steps 0–5: DONE.** Contract amendments (D3, D8, REQ-11/17/21/23), typed
`entry_unreadable`, `absent` narrowed to `ENOENT`/`ENOTDIR`, deletion facet,
transport skipping, query-boundary verification filtering, sentinel at
finalization, `skipped[]` in JSON.

**Step 6 — NEXT.** `--strict` (CLI-only boolean, false default, **no config
key, no env var, no precedence chain**), `strict_skip_refused` catalog code at
exit 1 published in `ERROR_CATALOG` **and** `README.md`, and cross-phase
aggregation so capture + materialize + include skips raise **one** error naming
every path, byte-wise ordered.
Rows: `T-CLI-68`, `T-MAT-31`, `T-INC-23`, `T-OUT-29`, `T-OUT-30`.

**Step 7.** `T-INC-22` (include readability guard, non-strict), `T-OUT-31`
(A13 notice contract: absent from stdout, on stderr exactly once, retained in
JSON `notices[]`), `T-MAT-37` (`--strict --with-ignored` across three distinct
gated paths), `T-MAT-38` (`--no-verify` skips, where capture is bypassed).

**Step 8.** Matrix totals recount, README documents `skipped[]` and both codes,
known limits documented where users meet them.

**Also outstanding:**
- Step 0 leftover: `CONFORMANCE.md` entry recording the R6.3 judgment (a fork
  with skips exits 0, because `fork` creates one named resource and carried
  paths are internal transport state — confirmed correct by review).
- **`T-VER-42`** — the hook-mutated-sentinel row. The behaviour works and was
  verified manually with a control, but **no test protects it.** Highest-value
  remaining row.
- **Gate 6** — one Codex adversarial pass on the implementation diff.

## 🔧 State to resume

- **Done:** steps 0–5, verified end to end after the A12 merge:
  `exit 0 | fork created | other files carried | unreadable file skipped`,
  notice on stderr, `skipped[]` in JSON.
- **The sentinel window is proven closed**, with a control:
  `hook mutates the skipped file → exit 1, verify_failed: a skipped entry
  changed during the fork` versus `inert hook → exit 0`.
- **In flight:** nothing broken. `just all` green at 663.
- **CI/PR:** no PR exists; branch never pushed.

## 🧠 Critical context that won't survive a fresh window

**Decisions and why**
- **Skip is best-effort, verification is the arbiter.** The copy loop never
  classifies *why* an entry is uncopyable; it skips qualifying entries and
  warns. Verification independently fails the fork if a mid-fork change caused
  it. This dissolved a contradiction that blocked three review rounds.
- **The sentinel runs at finalization**, after include copying and the setup
  hook, before the registry write — because the hook receives `REPO_ROOT` and
  can mutate the parent. Checking it during verification leaves a window that
  produces a *registered successful* fork over mutated data.
- **Exit 1, not 5,** for `strict_skip_refused`: exit 5 in this codebase is the
  guard family that refuses *before* doing work; a strict refusal judges a
  completed attempt, which is `verify_failed`'s shape.
- **A5 changed product requirements.** `IMPLEMENTATION-PROMPT.md` ranks
  `DESIGN-DECISIONS.md` and `REQUIREMENTS.md` above plans, and both required
  byte-equal parent/child status. They were amended (D3, D8, REQ-11/17/21/23).
  Keep them consistent with the design doc or an implementer must reject the plan.

**Gotchas**
- **Summaries have contradicted the normative section four separate times.**
  Always implement from "Skip preconditions", never from a summary table.
- **`_manifest_entry` used to report every `OSError` as kind `absent`**, so a
  `PermissionError` masqueraded as a deletion. Fixed, but the interaction is
  subtle: absence is *legitimate* (deletions and rename endpoints are kept on
  purpose, guarded by `T-VER-26`), so anything that can fake absence silently
  drops data.
- **Test-row IDs are a shared mutable counter across concurrent branches.**
  `check-matrix` validates what exists, not what is planned. Re-check every
  group's next free ID immediately before writing tests.
- **Multi-edit scripts that assert per replacement can silently discard earlier
  successful edits** when a later assertion fails. This produced three
  falsely-reported fixes. One write per edit.

**Rejected approaches — do not redo**
- **Retry after a parent change** — dropped. Needed an attempt boundary with
  guaranteed rollback, and a stateful transport filter defeats its classifier.
- **Skipping tracked paths via `:(exclude,literal)`** — rejected. `--no-renames`
  splits `old → new` into unassociated endpoints; excluding one silently drops
  the other.
- **Drift-only retry trigger** — refuted by a reverting writer producing a lone
  `content-match` failure from a genuine race.
- **Treating manifest kind `absent` as a failure** — would roll back every fork
  containing an ordinary deletion. `T-VER-26` guards this.
- **Post-processing porcelain to filter skips** — rejected in favour of A6a's
  query-boundary shape (one shared status command, `:(exclude,literal)`), which
  also defeats pathspec-looking filenames. `parent-untouched` is deliberately
  **never** filtered.
- **Making `--strict` configurable** — rejected; CLI-only.
- **Fixing the silent-omission and cleanup faults inside A5** — routed to #59
  and #60.
- **Closing the ancestor race** (descriptor traversal or ancestor sentinels) —
  **owner-accepted as a known limit.** Do not reopen. Same for the
  `.worktreeinclude` copy race.

**Conventions agreed this session**
- One PR per item: the branch stays unpushed until A5 is fully done, then a
  single PR carries doc + flips + implementation.
- Merge `main` into the branch (do not rebase) — twenty-plus doc commits
  conflict repeatedly under rebase; A4/A6/A3 set the merge precedent.
- Cite code by **symbol**, not line number — citations went stale three times.

## 👉 First action

Merge `main`, run `just all`, re-check the next free `T-CLI`/`T-OUT`/`T-INC`
IDs, then write step 6's RED rows for `--strict` before touching `cli.py`.

## ℹ How this was made

digest: ok · gathered 2026-08-21 · repo agent-fork · self-contained: ⚠ pending
`git push`
