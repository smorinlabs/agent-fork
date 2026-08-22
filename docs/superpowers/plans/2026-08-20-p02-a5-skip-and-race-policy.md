# P02-A5 — Skip policy for bad entries, and the parent-change race

**Status:** gates 1–6 complete locally; publication is pending. Gate 6 absorbed
four implementation defects and the missing evidence rows. The final
repository gate passed with 681 tests, 1 expected skip, and 20 deselections.

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

**Narrowed to Option A by owner decision, 2026-08-20.** A5 fixes exactly one
thing: *`agent-fork` must not refuse to work because of one entry it cannot
copy.* Everything else in the original bullet either already behaves correctly
or is routed elsewhere.

The rule, stated as behaviour rather than as timing:

> **The copy loop never fails the fork on a *qualifying* entry.** An entry that
> meets all three conditions in "Skip preconditions" is skipped and named.
> **Verification remains the sole arbiter** of whether the result is
> acceptable.
>
> Every other uncarryable entry — a tracked path, a failed `lstat`, or any
> entry while the fork carries a deletion — raises `entry_unreadable`.
> "Skip preconditions" governs; this is a summary of it.

This is what dissolves the earlier collision between "skip bad entries" and
"fail on parent changes". The copy loop is not asked to classify *why* an
entry is uncopyable; it records and continues. If the entry became uncopyable
because the parent changed mid-fork, the manifest recorded a regular file with
a digest, the parent now presents a different kind or different bytes, and
`parent-content` and `content-match` fire and revert the fork exactly as they
do today. If it was uncopyable from the start, verification sees consistent
state and the fork succeeds carrying a warning.

### The policy, in full

**Skipping applies to untracked and ignored entries only** (owner decision,
2026-08-20). A path Git tracks is never skipped; see "Why tracked paths do not
skip" below.

**This table is a summary, not the contract.** "Skip Preconditions" below is
the single normative statement: a skip additionally requires that `lstat`
succeeded and that the fork carries no deletion. An implementer must read that
section; following this table alone reintroduces both the unprovable skip and
the rename-endpoint loss.

| Condition met while copying | Default | `--strict` |
|---|---|---|
| Untracked or ignored file cannot be read | skip, warn, name every skipped path | fail, with the same warning |
| Untracked or ignored entry is a socket, FIFO, or other non-regular type | skip, warn, name every skipped path | fail, with the same warning |
| **Tracked** file cannot be read | **fail**, with a typed error naming the path | same |
| Parent changed during the fork | **fail and revert** — today's behaviour, unchanged | same |

Exit status is 0 when only skips occurred, non-zero under `--strict`.

**The non-regular case is defensive, and expected never to fire.** Git does
not list sockets or FIFOs, so such an entry cannot enter the inventory; the
probe matrix reached that branch only by swapping a regular file mid-fork,
which verification then fails. The change is still worth making because it
costs one branch and removes a crash path, and because a guard that never
fires is preferable to a `MaterializeError` that destroys a fork.

## Design

### Skipping, and the four sites it must reach

A path that fails to read at capture time **and meets all three skip
preconditions** is marked skipped and reported at the end of the run. A read
failure alone is not sufficient — see "Skip preconditions", which governs.
Shrinking `Inventory` alone is not enough: the
verification contract resolves paths in places that never consult it, so the
skipped set must be threaded through all four.

| Site | Why the skip must reach it |
|---|---|
| Initial `capture_state` | Where an unreadable path is discovered and marked. |
| Transport in `materialize` | The skipped path is simply not copied by the untracked or ignored loop. No patch exclusion is needed, because tracked paths never skip. |
| Verify-phase re-capture | `verify_fork` re-resolves a fresh inventory and re-runs `capture_state` on the parent, which would otherwise re-open the unreadable file and raise at verification time. |
| `exact-copy-status` | It compares live porcelain, not the inventory, so a skipped path appears in the parent and not the child. Known-skipped paths are filtered from both sides before comparison. This rung requests `--untracked-files=all`, so its paths are already expanded and the collapsed `?? d/` form does not arise. The raw `parent-untouched` bracket is **not** normalized. |

**No skip is ever triggered by absence.** Only a failed read or an
unsupported entry type marks a path skipped. This is deliberate:
`collect_inventory` keeps deletion and rename endpoints on purpose and
`_manifest_entry` renders them as kind `absent`, so treating absence as a skip
condition, or as a failure, would break ordinary deletions. `T-VER-26` guards
that behaviour and an unstaged deletion forks cleanly today.

### Why tracked paths do not skip

Chosen by the owner on 2026-08-20 after the third review, which showed that
skipping a tracked path cannot be done safely without rename handling.
`collect_inventory` resolves with `--no-renames`, so a rename `old -> new`
becomes an unassociated deletion of `old` plus an addition of `new`. Excluding
only an unreadable `new` from transport leaves `old`'s deletion eligible, so
the child would silently lose `old` while the warning named only `new`.

Rather than add rename detection to the transport path, tracked paths are
excluded from skipping entirely. An unreadable tracked file still fails the
fork, but with a **typed error naming the path** instead of a raw errno
string, which is the part of that failure that was genuinely defective.

This also removes work from the fix: no patch exclusion, no rename pairing,
and the only records that can be filtered from `exact-copy-status` are
expanded untracked entries.

### Dependency on issue #28: absence must mean absence

Discovered 2026-08-20 while filing #59. `_manifest_entry` catches **every**
`OSError` from `lstat` and returns kind `absent`, so a `PermissionError` — the
error raised when an ancestor directory lacks traversal permission — is
recorded as a missing file rather than an unreadable one. Issue #28 documents
this and recommends treating only `ENOENT` and `ENOTDIR` as absent.

This is not cosmetic for A5. The design states that absence is always
legitimate, because deletions and rename endpoints are legitimately absent. If
an unreadable path can *masquerade* as absent, that rule silently swallows it:
the path is treated as a deletion, the child never receives it, the parent
after verification looks equally absent, and the fork succeeds while quietly
incomplete. That is precisely the failure mode being routed out as #59,
reintroduced through the back door.

**A5 therefore absorbs the narrow part of #28 it depends on:** classify only
`ENOENT` and `ENOTDIR` as absent. Every other `OSError` from `lstat` is the
typed failure `entry_unreadable`, for tracked and untracked entries alike,
because a path whose `lstat` failed yields no stability sentinel and so could
never be proven unchanged. It is **not** routed into the skip path. See "Skip
preconditions" below, which is the normative statement; this paragraph
describes only the `#28` boundary. The rest of #28 — root-confined traversal,
no-follow descriptors, rollback recovery preservation — stays in #28.

### Skip preconditions — all three must hold

Revised 2026-08-20 after the fourth review. A path is skipped **only** when
every one of these holds. Otherwise it is a typed failure, `entry_unreadable`.

1. **The entry is untracked or ignored.** Tracked paths never skip.
2. **`lstat` succeeded**, so a stability sentinel can be recorded. A path whose
   `lstat` itself fails with `EACCES`, `EIO`, or any non-absence error yields
   no metadata, so nothing could later prove it stayed unchanged. Such a path
   fails rather than skipping. This bounds the absorbed `#28` slice: only
   `ENOENT` and `ENOTDIR` mean absent; every other `lstat` error is a failure,
   not a skip.
3. **The fork carries no deletion that could pair with it**, determined from
   an explicit **deletion facet** rather than inferred from absence. `Inventory`
   currently records staged and unstaged paths name-only and discards status,
   so absence-based detection cannot see a staged `git rm --cached old` whose
   working file still exists and is unreadable: `lstat` succeeds, no path looks
   absent, materialization applies the cached deletion, the untracked
   replacement is skipped, and the child loses HEAD's file. The facet is
   collected explicitly from both cached and working-tree diffs with
   `--diff-filter=D` and frozen alongside the inventory. A plain
   filesystem `mv old new`, without `git mv`, puts `old` in the unstaged
   deletion listing and `new` in the untracked listing. Transport applies the
   repository-wide deletion patch, removing `old`, and skipping an unreadable
   `new` would leave the child holding **neither endpoint** while the warning
   named only `new`. Restricting skips to untracked paths did not close this,
   because the two endpoints live in different listings. Since the pairing
   cannot be recovered under `--no-renames`, the conservative rule applies:
   when the fork carries any deletion, an otherwise-skippable entry fails
   instead. Both paths are named in the error.

### The stability sentinel

Recorded at observation time for every skipped path, and re-checked **at
finalization** — after include copying and the setup hook, and before the
registry write. Any difference fails the fork.

The timing is load-bearing. Checking during verification leaves a window: the
pipeline runs include copying and then the setup hook, which receives
`REPO_ROOT` and can mutate the parent, so a skipped file could change after a
verification-time check and the fork would still be registered successful.

    (st_dev, st_ino, st_mode, st_size, st_mtime_ns, st_ctime_ns)

`st_mode` and `st_ctime_ns` are load-bearing, not padding. Changing an
unreadable file from mode `000` to `0644` preserves inode, size, and mtime,
and its porcelain record stays `?? path`, so without the mode field a file
that *became readable* mid-fork would be silently omitted while every check
reported agreement. `st_ctime_ns` catches a same-size rewrite whose mtime was
restored.

### The strict-skip error contract

Specified here because "typed error with JSON details" admits incompatible
implementations, and `ERROR_CATALOG` is asserted exactly by `tests/cli/test_out.py`.

| Field | Value |
|---|---|
| Catalog code | `strict_skip_refused` |
| Exit status | `1` |
| Summary | `--strict refused a fork with skipped entries` |
| Companion code | `entry_unreadable`, exit `1`, for a carried entry that could not be read and could not be skipped |

**Not yet implemented — this is a gate 4 requirement.** Neither code exists in
`ERROR_CATALOG` or in the published catalog in `README.md` today. Both must be
added in step 0, and the README entry matters because the exact-catalog test
polices `errors.py` only.

`entry_unreadable` carries its own stable `details` schema, because it names a
path that was *not* skipped and may have to name the deletion blockers that
prevented the skip:

```json
{"entry": {"path": "<escaped>", "reason": "unreadable|lstat-failed|tracked",
           "phase": "capture|materialize|include"},
 "deletion_blockers": ["<escaped>", "..."]}
```

`deletion_blockers` is byte-wise ordered and empty when the failure had another
cause. Without this schema an implementation can satisfy the existing
catalog-membership and generic-rendering tests while exposing the blocking
paths only inside an unstable human message.

`details` schema, stable within a major version under R7.2:

```json
{"skipped": [{"path": "<escaped>", "reason": "unreadable|unsupported-type",
              "phase": "capture|materialize|include"}],
 "count": 2}
```

Paths are escaped with `escape_terminal_text` and sorted byte-wise so output
is deterministic. **Aggregation boundary:** capture-phase and materialize-phase
skips are collected and raised together, so one run reports every skipped path
rather than only the first. `.worktreeinclude` copying runs after verification
and is aggregated into the same error, which still rolls back because it
precedes the registry write.

The exit status is `1`, not `5`. Exit `5` in this codebase is the
precondition-guard family — `cleanup_dirty_worktree`, `conflict_branch_exists`
— which refuse before doing work. A strict-skip refusal happens after the fork
has run and its result was judged unacceptable, which is `verify_failed`'s
shape, and `verify_failed` is exit `1`.

### `.worktreeinclude`

The same readability guard is added beside the file-type guard `include.py`
already has, so an unreadable ignored file no longer kills the fork.

**Known limit, accepted by the owner.** Include copying runs after all
verification and resolves its own paths, so a file that becomes unreadable
after selection is skipped as though it had always been unreadable, and a file
mutated during `copy2` can land torn with nothing detecting it. This race
exists today; the guard neither creates nor closes it. Closing it would need a
per-copy stability bracket, which is out of A5's narrowed scope.

### Known limits, accepted by the owner

Both are recorded so an implementer does not mistake them for oversights, and
so a future reader knows they were seen and priced.

**1. Ancestor permission and rename races defeat the sentinel.** Accepted
2026-08-20. A pre-existing unreadable file and a mid-fork ancestor permission
change produce an identical runtime signature: `lstat` succeeds, the later
`open` returns `EACCES`. Distinguishing them needs descriptor-based traversal
or a sentinel on every ancestor. The consequence when it occurs is a
**misattributed skip, not a silent omission** — the run still warns and names
the path, which matches the requirement that an unreadable file be skipped and
named. Triggering it requires a directory's permissions to change and change
back inside the fork's roughly one-second window. Closing it properly is
`#28`'s root-confined descriptor traversal.

**2. `.worktreeinclude` copying is unbracketed.** Accepted 2026-08-20. Include
copies run after all verification and resolve their own paths, so a file that
becomes unreadable after selection is skipped as though it had always been
unreadable, and a file mutated during `copy2` can land torn with nothing
detecting it. This race exists today; the readability guard neither creates
nor closes it.

**Accuracy correction, 2026-08-20 (sixth review).** An earlier version of this
section claimed that neither limit is introduced by A5 and that both fail
toward a warning. Both halves were overstated. Corrected:

| Limit | Pre-existing? | Fails toward |
|---|---|---|
| Ancestor race — the underlying TOCTOU | yes, exists today | — |
| Ancestor race — the warn-and-omit *outcome* | **no, A5 introduces it.** Today `capture_state` performs `lstat` then an uncaught digest `open`, before the worktree exists, so this `EACCES` currently **fails** the fork. A5 converts that failure into a skip | a warning naming the path |
| `.worktreeinclude` — unreadable after selection | yes | a warning naming the path |
| `.worktreeinclude` — mutation during `copy2` | yes | **silence.** A torn copy can land with nothing detecting it |

So one subcase is genuinely silent, and one consequence is new. The owner's
acceptance of both limits stands and is not reopened by this correction; what
changes is only that the record now states the tradeoff accurately rather than
more comfortably than the evidence supports.

### Dropped from A5 by the narrowing

| Dropped | Why | Where it goes |
|---|---|---|
| Retry after a parent change | Parent changes already fail and revert correctly. The retry needed an attempt boundary with guaranteed rollback, and its classifier is defeated by stateful transport filters. | Future item, if wanted |
| Timing classification in the copy loop | Verification already arbitrates. | Not needed |
| Enumeration blind spot | A directory that loses readability during `ls-files` hides its descendants entirely. | Already routed as N2 |
| Per-copy stability brackets | Architectural, not a fault fix. | Recorded as the known limit above |

## Owner decisions

| ID | Decision | Owner, date |
|---|---|---|
| D1 | Skip is implemented by marking paths and shrinking the carried inventory; skipped paths are listed at the end. Skipping covers pre-existing unreadable entries only. A change in the parent fails the fork. | 2026-08-17, refined 2026-08-20 |
| D2 | **Superseded 2026-08-20.** Retry is dropped; a parent change fails and reverts, which is today's behaviour. Original decision was retry-once. | 2026-08-20 |
| D4 | Non-regular entries (socket, FIFO) are skipped with a warning, not treated as a failure, **subject to the three conditions in "Skip preconditions"**. Supersedes the earlier fail-on-swap resolution. | 2026-08-20 |
| D5 | `.worktreeinclude` gains the readability guard; its residual post-verification race is accepted as a known limit. | 2026-08-20 |
| D6 | A5 is narrowed to Option A: only the refuses-to-work defect is fixed. | 2026-08-20 |
| D3 | Exit 0 with notices by default; a strict flag makes skips fail. | 2026-08-20 |

**Assumption, correctable in one line:** the default tolerates any number of
skipped entries, not exactly one. Basis: the owner's instruction to report
"exactly which ones", plural.

**Collision resolved 2026-08-20, the other way.** The owner chose the
defensive skip. The collision dissolves because the copy loop no longer
classifies: it skips and warns, and verification independently fails the fork
if the entry became uncopyable through a mid-fork change. Both rules hold
without either overriding the other.

**Assumption carried forward, correctable in one line:** "we should fail and
revert, I think we've already done that" is read as keeping today's behaviour
with no retry, which is what the narrowing assumes.

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

The unreadable-mid-window row records **current behaviour**, not intended
policy: today a pre-existing unreadable file fails inside `capture_state`
before the worktree exists, while the same condition arriving mid-window fails
inside `_copy_entry` afterwards. An earlier draft of this design read that
difference as a way to classify cause by failure site. That reading was
abandoned — the governing rule is that the copy loop does not classify at all.
See "Skip preconditions".

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
| N1 | An unreadable **tracked** file kills the fork identically. ~~Skip semantics for a tracked path: exclude it from the `diff-index` and `diff-files` patches with `:(exclude,literal)`.~~ **Superseded 2026-08-20 by owner Option A:** tracked paths are never skipped, because a rename's endpoints land in different listings and excluding one would silently drop the other. An unreadable tracked file raises `entry_unreadable`, implemented and guarded by `T-MAT-33`. A5's title, "One bad **untracked** filesystem entry", is too narrow: the defect is in `capture_state`, which digests every carried path regardless of tracking state. | **Absorbed into A5.** Same site, same fix. |
| N2 | A mode-000 **directory** makes Git blind to its contents, so the fork reports success and the child silently lacks the data, with no notice. Parent `git status` is equally blind, so verification passes. | **Filed as [#59](https://github.com/smorinlabs/agent-fork/issues/59)** on 2026-08-20. The owner's requirement is recorded there: walk the worktree independently of Git, carry what can be carried, warn by default and fail under `--strict`. |
| N3 | An unreadable file matched by `.worktreeinclude` kills the fork *after* verification, then rolls back. `include.py` skips on unsupported **type** but has no guard for **readability**, so it is not the clean policy exemplar the register claimed. | **Absorbed into A5.** The shared copy primitive must handle both conditions. |
| N4 | An unreadable directory inside a fork worktree makes `cleanup` fail with an untyped `runtime_error` carrying raw Git output, leaving the worktree and its registry entry behind. | **Filed as [#60](https://github.com/smorinlabs/agent-fork/issues/60)** on 2026-08-20, cross-referenced to A7. |

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

### Effect of the Option A narrowing on the open findings

Recorded 2026-08-20, after the owner narrowed the item.

| Finding from pass 2 | Status under the narrowed scope |
|---|---|
| 1. `absent` rule rejects legitimate deletions | **Closed.** No skip is ever triggered by absence; only a failed read or an unsupported entry type marks a path. Deletion behaviour is untouched. |
| 2. Retry has no rollback-and-recreate boundary | **Closed.** The retry is dropped. |
| 3. The observation gap can still be silent | **Out of scope, recorded.** The enumeration blind spot is N2, already routed to its own issue. The design no longer claims the gap yields a named skip. |
| 4. Status normalization targets the wrong stream | **Reduced.** Only `exact-copy-status` is normalized, and it requests `--untracked-files=all`, so paths are expanded and the collapsed form never arises. `parent-untouched` is left alone. |
| 5. Post-verification include race | **Accepted as a known limit**, by owner decision. The guard neither creates nor closes it. |

### Gate 1 — Codex second lens, third pass, 2026-08-20

Verdict: **needs-attention**, two high, two medium. Codex session
`01a021a1-4b67-7532-90b8-cac7924f793b`.

**The central claim was verified sound.** A regular file swapped for a FIFO
mid-fork and skipped by the copy loop is still caught: `compare_states`
reports the type or membership loss, both content rungs fail, and rollback
runs. Skipping cannot make verification pass on an incomplete child by that
route.

| # | Finding | Resolution |
|---|---|---|
| 1 | **High.** The register still specified the superseded policy: copy-time failures, `absent`/`other` failures, and the retry. An implementer following it would ship the opposite behaviour. | **Fixed.** The register's decided direction is rewritten to state the narrowed policy verbatim. |
| 2 | **Resolved by owner decision, Option A.** Skipping is restricted to untracked and ignored entries, so no tracked path is ever excluded from transport and the rename decomposition cannot lose an endpoint. The finding as stated: `--no-renames` decomposes `old -> new` into unassociated delete and add endpoints, so excluding only an unreadable `new` still lets `old`'s deletion transport. The child loses `old` while the warning names only `new`. | **Closed.** Owner chose to restrict skipping to untracked and ignored entries. Unreadable tracked files keep failing, with a typed error naming the path. |
| 3 | Parent changes to an initially skipped path can pass verification. An already-modified tracked file that is unreadable and then atomically replaced by different unreadable bytes is omitted from both normalized and content comparisons, while raw porcelain still reads ` M path`, so `parent-untouched` sees no change. | **Accepted, fix specified.** Record `lstat` metadata — size, mtime, inode — as a sentinel for each skipped path, which requires no read, and fail when the sentinel changes. This keeps "every parent change fails" honest. |
| 4 | Strict failure has no route to emit the promised warning. Notices accumulate inside `fork()` and render only after it returns successfully; a strict exception reaches the generic handler, which prints only `render_error`. | **Accepted, fix specified.** A typed strict-skip error carries every escaped skipped path in both its human message and its JSON details. Tested at capture time, materialize time, and `.worktreeinclude`, in text and JSON modes. |

### Gate 1 — Codex second lens, fourth pass, 2026-08-20

Verdict: **needs-attention**, two high, two medium. Codex session
`01a0221e-18aa-7613-9cb3-a5cb2279d4bf`. Confirmed sound: the errno premise for
the `#28` slice, retaining `ENOTDIR` as absence, and the four-site threading
against the current call graph.

| # | Finding | Resolution |
|---|---|---|
| 1 | **High.** Option A does not close the rename hole. A plain `mv old new` puts `old` in the unstaged deletion listing and `new` in the untracked listing, so restricting skips to untracked paths still lets the child end with neither endpoint. | **Accepted.** Third skip precondition added: an entry does not skip when the fork carries any deletion. |
| 2 | **High.** An absorbed `lstat` failure cannot produce the required sentinel, so verification could never prove such a path stayed stable. | **Accepted.** Second skip precondition added: `lstat` must have succeeded. Otherwise it is a typed failure. |
| 3 | The sentinel omitted mode and ctime, so a file going from mode `000` to `0644` was undetectable. | **Accepted.** Sentinel widened to device, inode, mode, size, `mtime_ns`, `ctime_ns`. |
| 4 | The strict-skip error was not a defined contract: no catalog code, exit status, details schema, ordering, or aggregation boundary. | **Accepted.** Contract specified in full, including the exit-status rationale. |

**Disagreement recorded and resolved against my earlier reading.** The CLI
standard check concluded exit `5` for the strict refusal, reasoning from this
repository's guard-refusal family. The review argued exit `1`. The review is
right: exit `5` refuses *before* doing work, while a strict-skip refusal
judges a completed attempt, which is `verify_failed`'s shape at exit `1`.

### Gate 1 — Codex second lens, fifth pass, 2026-08-20

Verdict: **needs-attention**. Codex session
`01a02229-d1d5-7d61-9925-d83522271653`. Asked directly whether findings were
new defects or refinements, the review answered: **one new defect, three
refinements** — the first quantitative sign the loop is converging.

Confirmed sound: exit `1` over exit `5`, against R6.1/R6.3 and
`REQUIREMENTS.md`; and that an include-phase strict error raised before the
registry write still enters rollback.

| # | Finding | Class | Resolution |
|---|---|---|---|
| 1 | The `#28` paragraph still routed non-absence `lstat` errors into the skip path, contradicting the preconditions added in the same commit, and the register did not mirror the new rules. | refinement | **Fixed.** The `#28` paragraph now defers to the preconditions as the normative statement, and the register mirrors all three plus the sentinel and error codes. |
| 2 | **NEW.** The sentinel is target-only, so an **ancestor** race defeats it: `lstat` on `d/file` succeeds, `d` becomes mode 000 before the separate open, the read fails and the entry is skipped, `d` is restored before verification, and every one of the six target fields is unchanged. The child omits a file that was readable at both boundaries. Renaming `d` away and back is the analogous path-identity race. | **new defect** | **Accepted as a known limit** by the owner, 2026-08-20. See "Known limits". |
| 3 | The deletion precondition had no detector: `Inventory` keeps staged and unstaged paths name-only and discards status, so a staged `git rm --cached old` with an unreadable untracked `old` is invisible to absence-based detection. | refinement | **Fixed.** Explicit `--diff-filter=D` deletion facet, frozen alongside the inventory. |
| 4 | `entry_unreadable` had no `details` schema and neither new code was added to the published `README.md` catalog, so an implementation could pass the catalog tests while exposing blocking paths only in an unstable message. | refinement | **Partly fixed.** The schema is specified. Publication was marked complete in error — neither code exists in `errors.py` or `README.md` yet; it is a gate 4 step 0 requirement. |

#### Why finding 2 was accepted rather than fixed

A pre-existing unreadable file and an ancestor-permission race produce an
**identical runtime signature**: `lstat` succeeds, the later open returns
`EACCES`. They cannot be told apart without either descriptor-based traversal
or sentinels on every ancestor. Three ways forward:

| Option | Closes the race | Cost |
|---|---|---|
| Absorb `#28`'s root-confined descriptor traversal into A5 | yes | Large. This is the architectural work deliberately left in `#28` |
| Sentinel every ancestor from the worktree root, rechecked at verification | mostly — `chmod` always bumps a directory's `ctime`, so the change is detectable, modulo `ctime` granularity | Modest. `O(depth)` extra `lstat` calls per skipped path |
| Accept as a documented known limit | no | None |

Note on severity: unlike N2, this failure is **not silent**. The run emits a
warning naming the skipped path, so the outcome is a *misattributed* skip
rather than an unreported omission, and the owner's own requirement is that an
unreadable file is skipped and named.

### Gate 1 — Codex second lens, sixth pass, 2026-08-20

Verdict: **needs-attention**, but **0 new defects and 3 refinements** — every
remaining item was documentation, which is the signal the design converged.
Codex session `01a02242-107b-7f73-90d4-ec5c52505484`.

Confirmed correct: the `--diff-filter=D` facet does cover the staged
`git rm --cached` case, the register mirrors the three preconditions, and both
`details` schemas are specified.

| # | Finding | Resolution |
|---|---|---|
| 1 | The "policy, in full" table and a stale probe passage both contradicted the normative preconditions, so an implementer following either could reintroduce an unprovable skip or the rename-endpoint loss. | **Fixed.** The table defers explicitly to "Skip preconditions", and the probe passage is relabelled as current behaviour with the abandoned by-site reading called out. |
| 2 | Catalog publication was claimed in the present tense and marked fixed in the ledger, but neither code exists in `errors.py` or `README.md`. | **Fixed.** Restated as a gate 4 step 0 requirement; the ledger row corrected to "partly fixed". |
| 3 | The accepted-limit summary overstated observability and provenance: include mutation during `copy2` is genuinely silent, and A5 *introduces* the ancestor race's warn-and-omit outcome, because that `EACCES` fails the fork today. | **Fixed.** Subcases split into a table stating which are pre-existing and which fail toward silence. Owner acceptance unchanged. |

**Gate 1 status: ready to close** once a pass returns clean. Six passes; new
defects per pass ran 1, 3, 2, 2, 1, 0.

## Gate 4 — implementation plan

Rewritten 2026-08-20 after its first review, which found the original order
not executable. Each slice is RED-first at the level it can actually fail;
scenario rows come only after the plumbing they exercise exists.

### Row numbering

`T-MAT-30..38`, `T-VER-40..45`, `T-INC-22..24`, `T-OUT-29..31`, `T-CLI-68`.
**Refreshed 2026-08-21 after the A12 merge:** `main` had taken `T-INC-08..21`,
`T-OUT-25..28`, and `T-CLI-61..67`. `T-MAT-33` and `T-MAT-34` were already
implemented and registered.
The plan's original `T-VER-44` was withdrawn because it duplicated existing
deletion guard `T-VER-26`. Gate 6 later assigned the now-free `T-VER-44` to the
same-`lstat` sentinel defect. Re-check every group's next free number
immediately before writing tests; `main` moved twice during this item and
collided twice.

### Step 0 — contract amendments and catalog, before any behaviour

1. **Check issue #45**, which edits the same transport path in
   `materialize.py`. Open and unassigned as of 2026-08-19.
2. **The higher-precedence amendments** to `DESIGN-DECISIONS.md` D3 and D8 and
   to `REQUIREMENTS.md` REQ-11, REQ-17, REQ-21, REQ-23. Repository precedence
   ranks those above plans, so without them an implementer must reject this
   plan. **Landed 2026-08-20.**
3. **`CONFORMANCE.md`** entry recording the R6.3 judgment: a fork that skipped
   entries exits `0`, because `fork` creates one named resource and its
   carried paths are internal transport state. Confirmed correct by review.
4. **Catalog last, with its consumers.** Adding `entry_unreadable` and
   `strict_skip_refused` to `ERROR_CATALOG` *before* anything raises them
   breaks the existing exact-catalog row `T-OUT-14`. Add the codes, the
   README catalog entries, and the classes that raise them in one commit.

### Step 1 — detection, unit level (`content.py`)

RED at unit level, not through a fork. Narrow `absent` to `ENOENT` and
`ENOTDIR`; every other `lstat` error raises `entry_unreadable`. A successful
`lstat` plus a failed digest `open` on an untracked or ignored path yields a
skip record carrying the sentinel.

| Row | Asserts |
|---|---|
| `T-MAT-33` | Unreadable **tracked** modified file raises `entry_unreadable` |
| `T-MAT-34` | A failing `lstat` raises `entry_unreadable`, never a skip, because no sentinel can be recorded |
| `T-VER-26` | **Reused as guard.** An ordinary unstaged deletion still transports and verifies |

### Step 2 — the deletion facet, unit level (`content.py`)

Collect deletions explicitly from cached and working-tree diffs with
`--diff-filter=D`, frozen alongside the inventory.

| Row | Asserts |
|---|---|
| `T-MAT-35` | An unstaged deletion blocks an otherwise valid skip; the error names the blocker |
| `T-MAT-36` | A staged `git rm --cached old` with an unreadable working `old` is detected, though nothing is absent |

### Step 3 — transport honours the skip (`materialize.py`)

Skipped paths are not copied; `_copy_entry`'s non-regular branch becomes a
skip with a notice. A pre-existing non-regular entry cannot reach the loop
naturally, so `T-MAT-32` drives it through an explicit unit seam with an
injected inventory rather than a constructed repository.

| Row | Asserts |
|---|---|
| `T-MAT-32` | A non-regular entry reaching the copy loop is skipped with a notice rather than raising, via injected inventory |

### Step 4 — verification honours the skip (`verify.py`)

**Reuse A6a's shape at the query boundary.** A6a filters submodule state by
building one shared `status_args` list used for both the parent and child
`exact-copy-status` reads, leaving `parent-untouched` as a separate raw query.
Do the same here: extend that shared command with literal path exclusions for
known-skipped paths, rather than post-processing porcelain output — the
existing parser returns a dictionary and loses raw record ordering. Thread the
skipped set into the verify-phase re-capture so it cannot re-open a skipped
file.

| Row | Asserts |
|---|---|
| `T-VER-40` | A skipped path is excluded from `exact-copy-status` **and a non-skipped sibling in the same directory remains visible**, so the filter is not overbroad |
| `T-VER-41` | The verify-phase re-capture does not re-open a skipped path |
| `T-VER-43` | A filename containing pathspec-looking characters is excluded literally, never as a pattern |

### Step 5 — the sentinel, checked at finalization (`pipeline.py`)

**Not in verification.** The pipeline runs include copying and the setup hook
after verification and before the registry write, and the hook receives
`REPO_ROOT` and can mutate the parent. A sentinel checked during verification
therefore leaves a window in which a skipped file changes and the fork is
still registered as successful. The recheck belongs at finalization, after the
hook, before `add_entry`.

| Row | Asserts |
|---|---|
| `T-VER-42` | A skipped file mutated **after verification, by the setup hook** fails the fork at finalization |
| `T-VER-45` | A same-size rewrite with restored mtime is caught by `st_ctime_ns` alone, which is why that field is in the tuple |

### Step 6 — strict, aggregation, and the error contracts (`cli.py`, `errors.py`)

`--strict` is **CLI-only** (owner decision, 2026-08-20): a false-default
boolean with no config key, no environment variable, and therefore no
precedence chain to assert. A persistent default for a safety flag is a
footgun, and keeping it off the config surface keeps `models.py`, `config.py`,
the config view, and the README schema unchanged. Completion parity is already
covered generically by `T-CLI-33` and is not restated.

Skips aggregate across capture, materialize, and include phases into one
error.

| Row | Asserts |
|---|---|
| `T-CLI-68` | `--strict` parses and appears in help; no precedence claim |
| `T-MAT-31` | Two unreadable untracked files are both named, byte-wise ordered, in one error |
| `T-INC-23` | Under `--strict`, an unreadable `.worktreeinclude` match raises `strict_skip_refused` and rolls back, proving cross-phase aggregation reaches include |
| `T-OUT-29` | `strict_skip_refused` JSON `details` matches its schema exactly |
| `T-OUT-30` | `entry_unreadable` JSON `details` matches its schema, with ordered `deletion_blockers` |

### Step 7 — end-to-end behaviour, once the plumbing exists

These are the rows the original plan scheduled first, when nothing they
exercise had been built.

| Row | Asserts |
|---|---|
| `T-INC-22` | An unreadable `.worktreeinclude` match is skipped with a notice; the fork succeeds |
| `T-OUT-31` | A successful fork with skips: notices absent from stdout, on stderr **exactly once**, and retained in JSON `notices[]`, per A13's contract |
| `T-MAT-37` | `--strict --with-ignored`: ignored capture, ignored transport, and `.worktreeinclude`'s independent re-enumeration are distinct gated paths and each must reach the aggregate |
| `T-MAT-38` | `--no-verify` with a materialize-time skip, where initial capture is bypassed entirely |

### Step 8 — documentation

`TEST-MATRIX.md` rows registered and the total recounted, or
`just check-matrix` fails. `README.md` catalog and the `skipped[]` result
field. Both accepted known limits documented where users meet them.

## Gate 6 — adversarial implementation review

Executed 2026-08-21 over the complete A5 branch, including steps 0–5 inherited
from the handoff. The review found four implementation defects:

1. Capture recorded a skipped path's sentinel with a second `lstat`, so a
   target swap between the failed read and that call could become the baseline.
2. Verification re-opened paths already skipped during capture.
3. `entry_unreadable.details.entry.reason` used values outside its documented
   stable vocabulary for tracked and deletion-blocked paths.
4. An unreadable ignored path matched by `.worktreeinclude` was re-opened,
   recorded twice, and announced twice under `--with-ignored`.

All four were reproduced RED before repair. Gate 6 also filled evidence gaps
left by the earlier implementation: `T-MAT-32`, `T-MAT-36`, `T-VER-40`,
`T-VER-41`, `T-VER-43`, and final-sentinel rows `T-VER-44..45`. `T-INC-24`
protects the duplicate-reporting repair. The focused rows and the full
repository gate pass; the exact full-gate result is recorded in the status.

### Not in this plan

The two accepted known limits, issues #59 and #60, and the remainder of #28.
