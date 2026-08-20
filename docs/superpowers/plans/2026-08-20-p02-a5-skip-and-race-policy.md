# P02-A5 — Skip policy for bad entries, and the parent-change race

**Status:** gate 1 partially complete (register entry rewritten from executed
evidence; exhaustive probe matrix and Codex second lens still owed). Gate 3
design recorded below. Gates 4–6 not started.

**Register entry:** A5 in
[P02](../../../projects/P02-agent-fork-fault-remediation.md).

## The fault, as validated

A5 was registered as one fault — "One bad untracked filesystem entry destroys
the whole fork" — and probing split it into three with different verdicts.

| Sub-case | Verdict | Where it fails today |
|---|---|---|
| (a) Socket or FIFO present before the fork | **Refuted** | Nowhere. `git ls-files --others` never lists non-regular entries, so such a path cannot enter the inventory. |
| (b) Unreadable file present before the fork | **Confirmed** | `content.py:_digest` raises `PermissionError`, surfacing as an untyped `runtime_error`, before the worktree exists. |
| (c) Parent modified during the fork | **Confirmed** | `verify.py` rungs `parent-content`, `content-match`, `parent-untouched`. |

Evidence, window measurements, and the re-validation against `46201c1` are
recorded in the register entry and are not restated here.

## The governing rule

One rule decides every case, and it is a question about *time*, not about file
type:

> A condition that was already present when the snapshot was taken is
> **skipped**. A condition that appears after the snapshot is a **parent
> change**, and a parent change fails the fork.

The snapshot is `capture_state` in `pipeline.py`, taken before the worktree
exists. The rule follows from what the inventory means: it lists only paths
Git had just reported, so anything inconsistent with that at copy time proves
the working tree moved underneath the fork.

Applying the rule:

| Condition | Discovered at | Outcome |
|---|---|---|
| Unreadable file | snapshot (`_digest` open fails) | **skip**, drop from inventory, name it |
| Unreadable file | copy (`_copy_entry`) | **fail** — parent changed |
| Manifest kind `absent` | snapshot | **fail** — deleted inside the window |
| Manifest kind `other` (socket, FIFO, device) | snapshot | **fail** — swapped inside the window |
| Non-regular entry | copy (`_copy_entry` else branch) | **fail** — swapped inside the window |
| Any content or status drift in the parent | verification | **fail**, after one retry |

## Design

### (b) Skip unreadable entries, by default

**Marking, not silence.** A path that cannot be read at snapshot time is
marked skipped, removed from the carried inventory, and reported at the end of
the run. Removing it from the inventory is what makes the skip coherent:
A1 established that one path set drives both transport and verification, so a
path skipped by transport but retained in the inventory would fail
`content-match` on its absence and kill the fork anyway.

**Reporting.** Every skipped path is named — in `notices` for humans, and in a
`skipped` array in the JSON output for machines. A count alone is not
sufficient.

**Typed error.** The raw `runtime_error` carrying a bare errno string is
replaced by a typed error naming the step and the path.

**Shared primitive.** Pull request #53 consolidated duplicated primitives but
left `_copy_entry` and the `.worktreeinclude` copy loop in `include.py`
unmerged, although their only substantive divergence is the raise-versus-skip
policy this item is about. The remedy lands as one shared copy primitive that
takes the policy as a parameter, matching that pull request's pattern.

### (c) Retry the race once, then fail with a cause

**The rollback is correct and stays.** A write inside the window can tear the
copy, leaving the child matching no single moment of the parent.

**Retry is a full re-attempt.** Attempt two takes fresh `parent_status`, a
fresh inventory, and a fresh `capture_state`. Re-running verification against
the stale snapshot would be wrong, because the parent legitimately changed and
the second attempt must adopt the new state.

**Retry trigger is scoped to drift.** Retry only when parent drift was
detected, that is when `parent-content` or `parent-untouched` fired. A
`content-match` failure with no drift is an A1-class transport defect; a retry
would fail identically and hide it. The existing `primary=not drift` field
already distinguishes these two cases and is the trigger condition.

**Messages.** The failure names the cause — the parent changed during the fork
and nothing was lost — rather than only the check that fired. A retry that
fails the same way emits a distinct message identifying a continuous writer,
such as a development-server log or a watch build.

### The strict flag

One flag, not two. Default behavior skips and exits 0. Strict mode converts
every skip into a refusal with a non-zero exit. The flag's name and the
strict-mode exit code are both subject to the CLI Design Standard, checked
through the `cli-standards` skill before implementation, because the
repository is currently release-blocked on rules R4.1 and R9.3.

## Owner decisions

| ID | Decision | Owner, date |
|---|---|---|
| D1 | Skip is implemented by marking paths and shrinking the carried inventory; skipped paths are listed at the end. Skipping covers pre-existing unreadable entries only. A change in the parent fails the fork. | 2026-08-17, refined 2026-08-20 |
| D2 | Retry once, then fail with a named cause. | 2026-08-20 |
| D3 | Exit 0 with notices by default; a strict flag makes skips fail. | 2026-08-20 |

**Assumption, correctable in one line:** the default tolerates any number of
skipped entries, not exactly one. Basis: the owner's instruction to report
"exactly which ones", plural.

**Collision flagged, resolved as fail:** the owner asked for sockets and FIFOs
to be skipped, and separately for parent changes to fail. These collide at one
reachable point. Since Git never lists a non-regular entry, the only way
`_copy_entry` meets one is a mid-fork swap, which is a parent change. The
explicit fail-on-parent-change rule wins. Flipping this to a defensive skip is
a one-line change if the owner prefers it.

## Known dependencies

- **Issue #45** (A13(h1), bound staged-binary materialization memory) edits the
  same transport path in `materialize.py`. Open and unassigned as of
  2026-08-19. Sequence before implementation.
- **`TEST-MATRIX.md`** must register every new test row, or `just check-matrix`
  fails.

## Verification

To be completed at gates 1, 5, and 6.

## Review outcomes

To be completed at gates 4 and 6.
