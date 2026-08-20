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

> A condition that was already present when the path was **observed** is
> **skipped**. A condition that appears after that observation is a **parent
> change**, and a parent change fails the fork.

**Observation is per path, not global** (revised 2026-08-20 after the Codex
review). There is no single instant at which the whole tree is snapshotted:
`collect_inventory` enumerates paths, then `_manifest_entry` captures each one
with an `lstat` followed by a later digest `open`. A path's recorded
observation is whatever its own `_manifest_entry` saw. A permission change
landing between enumeration and that capture therefore counts as
**pre-existing**, and is skipped. This is accepted rather than fought: closing
that gap would require locking a tree Git itself does not lock, and the
consequence of the accepted case is a named skip, not a silent one.

`_copy_entry` compares against the recorded observation rather than guessing
from the failure site:

- recorded unreadable, already dropped, never reaches transport;
- recorded regular but now absent, non-regular, or unreadable, **parent
  change, fail**.

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

**Marking, not silence.** A path that cannot be read at observation time is
marked skipped and reported at the end of the run.

**Shrinking the inventory is necessary but nowhere near sufficient** (revised
2026-08-20 after the Codex review, which rated the original design a high
finding). The verification contract resolves paths in three places that never
consult the initial inventory, so the skip must be threaded through every one:

| Site | Why the skip must reach it |
|---|---|
| Initial `capture_state` | Where the unreadable path is discovered and dropped. |
| Transport in `materialize` | Staged and unstaged patches are repository-wide `diff-index` and `diff-files` calls that never consume `Inventory.staged` or `.unstaged`. A tracked path could otherwise be reported skipped while still being transported. |
| Verify-phase re-capture | `verify_fork` re-resolves a fresh inventory and re-runs `capture_state` on the parent, which would **re-open the still-unreadable file and raise the same error at verification time**. |
| `exact-copy-status` | It compares complete live porcelain from parent and child, not the inventory. A skipped untracked path still appears in the parent's status and is absent from the child, producing a mismatch and a rollback. Known-skipped paths must be filtered from both porcelains before comparison, minding the NUL-delimited format and the collapsed `?? d/` directory form. |

The design is therefore an **original inventory plus an explicit skipped set**,
carried through all four sites, rather than a quietly shrunk inventory.

**Reporting.** Every skipped path is named — in `notices` for humans, and in a
`skipped` array in the JSON output for machines. A count alone is not
sufficient.

**Typed error.** The raw `runtime_error` carrying a bare errno string is
replaced by a typed error naming the step and the path.

**`.worktreeinclude` is scoped to a plain readability guard.** Its copies run
after verification, so they have no snapshot to compare against and cannot
carry race semantics. The minimal remediation is the readability guard
`include.py` never had, matching the file-type guard beside it: skip with a
notice. The pipeline ordering is left alone.

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

**Retry is a classifier, and fires on any content or drift failure** (revised
2026-08-20 after the Codex review). The earlier design retried only on
observed parent drift, reasoning that a lone `content-match` failure must be
an A1-class transport defect. A reverting writer refutes that: snapshot an
already-modified file holding bytes A, let a writer change it to B before
materialization so the child receives B, then let it restore A before
verification. Porcelain never changes and the parent matches its snapshot, so
no drift is observed, yet the child differs. The runtime cannot distinguish
that genuine race from a transport defect, so the old trigger suppressed the
retry for exactly the case retrying was meant to fix.

Retrying does not mask a transport defect, because a deterministic defect
**reproduces identically on the second attempt**. The retry is the diagnostic:

| Second attempt | Classification | Reported as |
|---|---|---|
| Succeeds | transient parent drift | success, with a notice that a retry occurred |
| Fails, drift observed | continuous writer | named cause plus the continuous-writer message |
| Fails, same content-only mismatch | probable transport defect | failure identifying it as reproducible, not a race |

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

## Gate 1 — probe matrix, executed 2026-08-20

Machine: macOS 25.4 (APFS), system Git, `agent-fork` built from `46201c1` plus
this branch. Every cell below was executed and its output captured. A cell is
recorded as a problem only where a probe demonstrated one.

### Static shapes, present before the fork

| Entry state | Listed by `ls-files --others` | Fork exit | Worktree | Result |
|---|---|---|---|---|
| Regular untracked file (control) | yes | 0 | kept | pass |
| **Unreadable untracked file** | yes | 1 | none | **fails in `capture_state`** |
| **Unreadable tracked, modified file** | n/a (tracked) | 1 | none | **fails in `capture_state`** |
| Readable directory, mode 755 (control) | yes | 0 | kept | child **has** the file |
| **Unreadable directory, mode 000** | **no** — Git cannot traverse it | 0 | kept | child **lacks** the file, see N2 |
| FIFO | no | 0 | kept | pass, unreachable as predicted |
| Unix socket | no | 0 | kept | pass, unreachable as predicted |
| Symlink to regular file (control) | yes | 0 | kept | pass |
| Dangling symlink | yes | 0 | kept | pass |
| Unreadable ignored file, `--with-ignored` | yes | 1 | none | **fails; the flag widens exposure** |
| Unreadable ignored file, default mode | not carried | 0 | kept | pass |
| **Unreadable file matched by `.worktreeinclude`** | n/a | 1 | none | **fails after verification, see N3** |

The mode-000 directory row was re-probed on 2026-08-20 with a control, after
the Codex review correctly objected that the first harness recorded only the
exit code and never asserted the omission. One permission bit is the sole
difference between these two runs:

| | `git ls-files --others` | parent `status --porcelain` | fork exit | child has `d/secret.txt` | notices |
|---|---|---|---|---|---|
| Readable, 0755 | `d/secret.txt` | `?? d/` | 0 | **yes** | none |
| Unreadable, 0000 | *(empty)* | **`(clean)`** | 0 | **no** | none |

Git cannot traverse the directory, so it reports nothing. The parent's own
status is equally blind, so `exact-copy-status` compares two identical clean
listings and verification passes. The fork reports success while the child is
missing data.

### Mid-window shapes, applied between snapshot and copy

All five fail, which is what the governing rule requires.

| Mutation inside the window | Exit | Failure |
|---|---|---|
| File deleted | 1 | `runtime_error: [Errno 2] No such file or directory` |
| File made unreadable | 1 | `runtime_error: [Errno 13] Permission denied` |
| Regular file swapped to FIFO | 1 | `runtime_error: unsupported untracked file type: zzz_target.txt` |
| Tracked file edited | 1 | `verify_failed: parent-content, content-match` |
| New untracked file appears | 1 | `verify_failed: exact-copy-status, parent-content` |

The FIFO-swap row is the collision the owner decision resolved. It confirms
the prediction: the non-regular branch is unreachable from a pre-existing
entry and reachable only from a mid-fork swap, where failing is correct.

The unreadable-mid-window row confirms the design is implementable: a
pre-existing unreadable file fails inside `capture_state` before the worktree
exists, while the same condition arriving mid-window fails inside
`_copy_entry` afterwards. The two are distinguishable by site, which is what
lets one skip and the other fail.

### Cleanup operation

| Fork worktree contains | `cleanup` exit | Worktree removed |
|---|---|---|
| Nothing unusual (control) | 0 | yes |
| FIFO | 0 | yes |
| **Unreadable directory, mode 000** | **1** | **no, see N4** |

### Untestable on this machine

Recorded as gaps rather than passes, following the precedent A2 set for
`GIT_ATTR_NOSYSTEM`:

- Linux and other case-sensitive filesystems.
- Git versions other than the one installed here, in particular whether any
  version lists non-regular entries.
- Windows, which is out of scope for the project.

## Findings beyond A5's original three

| ID | Finding | Routing |
|---|---|---|
| N1 | An unreadable **tracked** file kills the fork identically. Skip semantics for a tracked path: exclude it from the `diff-index` and `diff-files` patches with `:(exclude,literal)`, the pathspec pattern A13's T13E established, so the child keeps the last-committed content and the entry is reported as "modification not carried". Gate 4 must verify that Git can generate a repository-wide patch at all with an unreadable file present. A5's title, "One bad **untracked** filesystem entry", is too narrow: the defect is in `capture_state`, which digests every carried path regardless of tracking state. | **Absorbed into A5.** Same site, same fix. |
| N2 | A mode-000 **directory** makes Git blind to its contents, so the fork reports success and the child silently lacks the data, with no notice. Parent `git status` is equally blind, so verification passes. | **Route to an issue.** Opposite failure mode — silent, not loud — and detecting it requires walking the tree independently of Git, which is a scope increase. |
| N3 | An unreadable file matched by `.worktreeinclude` kills the fork *after* verification, then rolls back. `include.py` skips on unsupported **type** but has no guard for **readability**, so it is not the clean policy exemplar the register claimed. | **Absorbed into A5.** The shared copy primitive must handle both conditions. |
| N4 | An unreadable directory inside a fork worktree makes `cleanup` fail with an untyped `runtime_error` carrying raw Git output, leaving the worktree and its registry entry behind. | **Route to an issue**, noted against A7, which covers uncleanable registry entries. |

## Verification of the implementation

To be completed at gates 5 and 6.

## Review outcomes

### Gate 1 — Codex second lens, 2026-08-20

Verdict: **needs-attention**, four findings, one high. Codex session
`01a02185-d0e0-7971-9a67-2945217efaeb`. All four were accepted after
independent verification against the source. None reopened an owner decision,
because every fix is mechanism rather than policy.

| Finding | Accepted | Resolution |
|---|---|---|
| **High.** Shrinking `Inventory` cannot deliver the skip: `exact-copy-status` uses live porcelain, the content rungs re-resolve fresh inventories, and tracked transport ignores `Inventory.staged` and `.unstaged`. | yes, confirmed by reading `verify.py` and `materialize.py` | D1 redesigned as an original inventory plus an explicit skipped set threaded through four sites. Verifying the finding surfaced a fifth consequence the review did not name: the verify-phase re-capture would re-open the unreadable file and raise at verification time. |
| A lone `content-match` failure can still be caused by parent drift, via a reverting writer, so the drift-only retry trigger suppresses the retry for a real race. | yes, counterexample traced and found sound | Retry redesigned as a classifier firing on any content or drift failure. |
| No single observable snapshot instant: a mid-capture permission change raises at the same site as a pre-existing one, and `.worktreeinclude` has no snapshot at all. | yes | Boundary redefined as per-path observation time, with the residual gap stated and accepted. `.worktreeinclude` scoped to a plain readability guard. |
| The N2 cell was a false problem under the gate's evidence standard, because the probe never asserted the omission. | yes, correct about the committed record | Re-probed with a readable-directory control; evidence recorded above. The finding stands and is now demonstrated. |

### Gate 1 — Codex second lens, second pass, 2026-08-20

Verdict: **needs-attention** again. Three high, two medium. Codex session
`01a02191-1956-7e21-909f-0e01d23e44a8`. The N2 re-probe was accepted as now
meeting the evidence standard. The five open findings are recorded here
because they change the size of the item, which is an owner question.

| # | Finding | Status |
|---|---|---|
| 1 | **High.** The rule "manifest kind `absent` fails" rejects **legitimate tracked deletions**. `collect_inventory` deliberately keeps deletion and rename endpoints, and `_manifest_entry` renders their missing working-tree paths as `absent`. Verified empirically: an unstaged deletion forks cleanly today, exit 0, and `T-VER-26` is an explicit positive guard for it. | **Accepted.** The rule as written would break tested behavior. Requires distinguishing Git-recorded intentional absence from observed-then-deleted. |
| 2 | **High.** A full retry has no rollback-and-recreate boundary. Worktree creation precedes `finish`, so catching the verification error inside `finish` replays patches against an already-mutated child. Separately, a stateful transport filter can fail once and succeed on retry with no parent drift, so second-attempt success does not prove the classifier's "transient drift" verdict. | **Accepted.** Needs an explicit attempt boundary with successful rollback between attempts, and a weaker classification claim. |
| 3 | **High.** The accepted observation gap can still be **silent**, contradicting the claim that its worst case is a named skip. If a directory loses readability while `ls-files` is traversing, its descendants never enter `_manifest_entry` or the skipped set at all. The N2 evidence is itself the proof. | **Accepted.** The guarantee must be narrowed to paths Git already enumerated, with the pre-enumeration blind spot kept in the race model. |
| 4 | Status normalization targets the wrong stream: `exact-copy-status` requests `--untracked-files=all`, so it never sees the collapsed `?? d/` form. That form appears in the raw `parent-untouched` bracket, which must **not** be normalized, because subtracting one skipped descendant from a collapsed record can hide drift in non-skipped siblings. | **Accepted.** Needs a record-aware NUL porcelain parser on expanded paths only. |
| 5 | Post-verification `.worktreeinclude` copying remains an unchecked race. It resolves paths independently and runs after all verification, so a writer changing a file after `lstat` or during `copy2` yields torn or stale child content that nothing later detects. | **Accepted.** A plain readability guard does not close it; a per-copy stability bracket would. |

### Gates 4 and 6

To be completed.
