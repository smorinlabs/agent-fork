# P02-A3 — Per-repository scoping of the fork registry

**Fault:** A3 — global flat fork registry clobbers across repositories
([P02 register](../../../projects/P02-agent-fork-fault-remediation.md)).

**Status:** gates 1, 3, 4, and 5 closed. Gate 4 ran four rounds, all
rejecting; the loop was stopped by owner decision and the design reshaped
around a single resolution rule rather than continuing to patch sites. Gate 5
(implementation) is complete: `just all` green at 430 passed, 1 skipped, and
`check_matrix.py` clean. Gate 6 (adversarial implementation review) open.

## Implementation outcome (gate 5)

Four slices landed as planned, in `9a39690` (A and B), `d7e6060` (C), and
`6470537` (D). Two things the implementation established that the plan did
not, both recorded here rather than left in commit messages:

- **`git worktree list` reports a hand-deleted worktree as `prunable`.** The
  predicate initially accepted such a record, and cleanup then died on a raw
  git error against the missing path — which is A7's registered symptom,
  reproduced from inside A3's own fix. `live_worktree_pairs` excludes it, so
  "freshly observed" means present, not merely listed. This turns A7's
  dead-end into a typed refusal as a side effect. *(Amended 2026-08-20: the
  exclusion is no longer done by reading the `prunable` field. Enumeration now
  goes through main's `list_worktrees`, and each listed path is probed for the
  repository and branch it currently has, which excludes a gone or replaced
  directory without parsing that field at all.)*
- **~~Migration costs less than the design assumed.~~** *(Retracted
  2026-08-20, gate 6 round 3.)* This said a v1 record with no repository was
  still cleanable from its own repository, because the predicate consults live
  state rather than stored identity. That was wrong: matching a live worktree
  shows the fork exists, not that it belongs here, and two repositories can
  hold one path on one branch name. Such a record now authorizes nothing. See
  the null-identity section under Design; `T-REG-23` and `T-REG-24` assert the
  corrected behaviour.

**One user-visible behavior change**, surfaced by an existing test that had
relied on the old global lookup: `cleanup <name>` now requires the invoking
directory to be inside the repository. A fork name is resolved against that
repository, and outside one there is nothing to resolve against. Documented in
`README.md`; `pty_run` gained a `cwd` argument so the consent-prompt test
exercises the intended usage.

**Worktree:** `worktree-p02-a3-registry-repo-scope`, based on `origin/main`
at `aefcda0`.

## Verification verdict and evidence

**Claim (as registered):** one machine-wide `forks.json` whose
`RegistryEntry` (`models.py:53-75`) carries no repository field. `add_entry`
(`registry.py:111`) deletes a same-named entry belonging to another
repository; `find_owned` (`registry.py:127-136`) matches a bare name or
branch across every repository, so cleanup can resolve another
repository's worktree; the auto-name collision check (`cli.py:490-516`)
never consults the registry.

**Empirical repro (Claude, 2026-08-17).** Throwaway repositories under one
`XDG_STATE_HOME`, `agent-fork fork … --no-agent`, CLI 1.0.0. Four probes,
all reproduced:

| # | Probe | Observed |
|---|---|---|
| 1 | `fork shared` in repoA, then in repoB | registry holds one entry; repoA's row is gone; no warning on either run |
| 2 | `fork alpha` in repoC only, then `cleanup alpha --dry-run --allow-unpushed` from repoD | `would remove worktree …/repoC-fork-alpha; branch: delete fork/alpha` — repoD has no such fork |
| 3 | `fork` with **no name argument** in two repos both on `main` | both derive name `main-0817` and branch `fork/main-0817`; second run clobbers the first's row silently |
| 4 | after probe 3, `cleanup main-0817 --dry-run --allow-unpushed` from repoE | `would remove worktree …/repoF-fork-main-0817; branch: delete fork/main-0817` |

**Two corrections to the register's framing, both raising severity:**

1. **The collision is on the default path, not an opt-in one.** The register
   implies a user-chosen duplicate name. Probe 3 shows `agent-fork fork`
   with no `NAME` derives `<branch>-<MMDD>`, so any two repositories on
   `main` forked on the same day collide by construction. No user error is
   required.
2. **The consequence is destructive, not merely lost bookkeeping.** Probe 4
   shows the clobbered repository's worktree survives on disk while its
   registry row does not; a later `cleanup` issued from that repository
   resolves and plans to delete *another* repository's worktree **and
   branch**. This is the fault's true impact and the reason its type is
   recorded as a data-safety fix.

**Codex adversarial pass: CONFIRMED-WITH-CORRECTIONS.** Corrections and
sharpenings adopted into the finding:

- **Root cause is a key mismatch, not the single file.** A flat global
  registry is safe if its keys carry repository identity. Locking is not at
  fault either — it atomically serializes the wrong replacement. Sharding
  into per-repository files is therefore the larger change, not the smaller
  one.
- **The register's `cli.py:487-514` citation is stale.** The checks live in
  `collision_state()` at `cli.py:477-488`; the omitted-name selection runs
  through `cli.py:490-516`.
- **The destructive path has no repository-containment defense.**
  `_validate` (`cleanup.py:331-335`) refuses only when the invoking
  directory sits *inside* the selected target. The dirty and unpushed
  guards (`cleanup.py:336-356`) inspect the already-misresolved target, so a
  clean, pushed fork in the wrong repository passes with no override at
  all. Codex traced the real `cleanup()` with git calls recorded rather than
  executed and observed `git -C /tmp/repoF/.git worktree remove --force …`,
  `… branch -D fork/main-0817`, and `remove_entry("main-0817")` issued from
  a simulated cwd of `/tmp/repoE`. Severity: high, data-safety.
- **Probe 4 nuance.** That probe passed `--allow-unpushed` because the
  throwaway repositories had no remote. The flag is not what makes the fault
  reachable — an ordinary pushed fork branch clears the same guard
  unprompted.
- **Repro fairness upheld.** `--no-agent` only selects git-only mode
  (`cli.py:430-443`); registry insertion is unconditional after the common
  pipeline (`pipeline.py:154-163`) and `REQUIREMENTS.md:177` states git-only
  retains the registry pipeline. A shared `XDG_STATE_HOME` *is* the
  production condition — it models one user account (`registry.py:21-26`).
- **Partial mitigation, not a defence.** The companion skill proposes a
  conversation-derived name when on a default branch (`README.md:82-94`),
  which reduces collisions. The direct CLI remains a documented public
  interface, topic-branch omission still delegates to auto-naming, and
  `--dry-run` never reads the registry (`cli.py:546-585`).
- **Evidence limitation, recorded honestly.** Codex's sandbox denied
  `mktemp -d` under `/tmp`, so it did **not** independently re-run the four
  live-git repros and declined to count this document's run as its own
  observation. Its confirmations rest on source tracing plus non-writing
  execution probes that substituted in-memory stores for filesystem
  primitives. The live-git evidence above is single-source (Claude).

## Design

Reshaped 2026-08-17 (owner decision) around a single resolution rule, after
gate 4 round 4 found the fifth site where a destructive action was authorized
by recorded rather than observed state. Five site-specific guards are replaced
by one predicate that every destructive path is forced through.

### The resolution rule

`agent-fork` has exactly two sources of information when it decides whether it
may destroy something:

| Source | Tells you | Cannot tell you |
|---|---|---|
| A registry row | What was true when the row was written | Whether any of it is still true |
| A fresh observation — running git now | What is true at this moment | — |

`agent-fork` does not own the filesystem or git. Between a row being written
and being used, a user can delete the worktree, move the repository, recreate
the branch, or create an unrelated worktree at a path some old row still
names. Nothing notifies the registry. **A row is a memory, not a fact.**

The rule, applied everywhere:

> A registry row may be used to decide **what to look at**. It may never serve
> as evidence that what you find there is still what the row describes. Only a
> fresh observation establishes a present-tense fact, and it is fresh only if
> **every input to it** is also fresh.

That second clause is the one four review rounds walked past. The rejected
round-3 migration probe ran git and read the disk, yet was unsound because its
argument — the path to probe — came from the row. Freshness is a property of
the whole question, not of the last step.

### The actionability predicate

Resolution inverts. Today, and in every earlier version of this plan, it ran
outward from the row: `find_owned` produced a row, `_git_root` was called on
that row's stored path, and the result was compared to itself. Every input
after the first came from memory.

It now runs inward from live state:

```
_worktrees(cwd)          → live (path, branch) pairs   ← input: the user's cwd
inspect_repository(cwd)  → this repository's identity  ← input: the user's cwd
find_owned(target)       → candidate row(s)            ← memory: what to look for
CONFIRM each candidate against the live pairs          ← the predicate
act only on what live enumeration confirmed
```

**Predicate.** A row is *actionable in this repository* if and only if the
pair `(row.worktree, row.branch)` appears in the live worktree list of the
repository freshly identified from the user's working directory.

The primitive already exists: `_worktrees` (`cleanup.py:125-142`) runs
`git worktree list --porcelain` in a given directory and returns resolved
`(path, branch)` pairs. It is used today only on the `--force` path.

One predicate closes four of the five recorded sites:

| Site | Closed how |
|---|---|
| Path reuse by another repository | That path is not in *this* repository's live list, so the row is not actionable here |
| Cross-repository cleanup misresolution | Another repository's worktree never appears in this repository's live list |
| Fork-time replacement | A row is replaced only when the predicate confirms it belongs to the repository doing the forking |
| Worktree and branch deletion | The predicate confirms `(worktree, branch)` as a live **pair**, so neither is passed to git unverified |

The fifth — the interval between the predicate passing and git running — is a
time-of-check-to-time-of-use gap. **Re-evaluated 2026-08-20:** A3 was written
expecting A8 to close that family, but A8 was closed **will-not-fix** on
2026-08-18 — the plan-token remedy was judged too complex for this CLI and
confirmation-boundary drift is now an accepted limitation. So nothing later
will close it, and A3's own handling is the whole of what exists: the
post-consent revalidation below closes the **registry** half of the window
(the record cannot change between consent and mutation), while the residual
filesystem interval between the final check and Git's own work is accepted,
not deferred. The post-consent revalidation
below narrows it; nothing in A3 closes it, and this document does not claim
otherwise.

### Two jobs, deliberately separated

The `repository` field and the predicate are often confused because both
concern repository identity. They do different work, and keeping them distinct
is what makes the rest of this design small:

- **The `repository` field makes bookkeeping correct.** It gives fork-time
  replacement a per-repository key, so two repositories can each hold a fork
  named `main-0817` without one deleting the other's row. This is A3's
  registered fault.
- **The predicate makes destruction safe.** It decides whether a row may
  authorize removing anything. Cleanup scoping falls out of it for free: a
  candidate belonging to another repository simply fails.

Consequently `find_owned` does **not** filter candidates by stored identity.
It returns every row matching the target by name, branch, or resolved path,
and the predicate filters them. Scoping by a stored field would be the same
error this design exists to remove.

### Identity key

The `repository` field stores the resolved output of
`git rev-parse --git-common-dir` — the administrative directory every worktree
of one repository shares. Chosen over the origin remote URL, which is absent
for remote-less repositories, multi-valued per clone, split across SSH and
HTTPS spellings, and would wrongly collapse two independent clones that have
separate local branch namespaces. Chosen over a generated repository UUID,
which would mean mutating the user's git directory plus its own locking,
clone-copy, and recovery rules.

Because the field now serves only fork-time bookkeeping, its known weaknesses
carry far less weight than in earlier revisions — a wrong or stale value can
cause a redundant row, never a wrong deletion:

| Case | Behavior |
|---|---|
| Linked worktrees | Correct by construction — all share one common directory |
| Submodules | Correct; a submodule is its own repository with its own branch namespace |
| Bare repositories | Works if the helper reads the common directory directly; requiring `--show-toplevel` would regress bare support (`repository.py:105-115`) |
| Moved repositories | Stored value goes stale. Harmless: the predicate governs destruction, and the safe backfill below repairs the field |
| Mount aliases, case-aliased paths | Residual weakness; `Path.resolve()` handles symlinks, not every mount-level alias |
| `GIT_DIR` / `GIT_COMMON_DIR` in the environment | **Empirically refuted as a threat, not deferred.** See the A2 note below |

### Rebased on A2 (merged 2026-08-17, `ba34a74`, PR #36)

A2 landed while this plan was in review and changed three things it assumed.
Corrections, not refinements — the earlier text was wrong on each:

- **The environment claim is refuted, not deferred.** This document twice said
  `GIT_DIR` / `GIT_COMMON_DIR` redirection was "A2's territory". A2 probed 12
  canonical inputs against the fork path **and the cleanup path**, with
  controls and bystander comparison, and found **zero wrong-repository
  mutations, zero wrong-target deletions, and zero silent divergences
  attributable to agent-fork**. Where behavior did change, plain
  `git worktree add` behaves identically. A3 therefore inherits no
  outstanding environment risk and defers nothing to A2.
- **`run_git` is no longer a raw passthrough.** It now calls
  `without_config_injection(env)`, which strips the `GIT_CONFIG_COUNT` /
  `GIT_CONFIG_KEY_<n>` / `GIT_CONFIG_VALUE_<n>` triple and
  `GIT_CONFIG_PARAMETERS`. `GIT_CONFIG_GLOBAL` and `GIT_CONFIG_SYSTEM` are
  **deliberately preserved**, because they name configuration *files* — the
  supported way tooling controls git, including this project's own harness.
  Any statement in this document that `run_git` forwards the environment
  unchanged is stale.
- **Use `inspect_repository`, not a bespoke helper.** It returns a resolved
  `common_dir`, resolves relative git paths against the probed parent, and
  handles bare repositories by skipping `--show-toplevel`. The predicate's
  fresh identification of the invoking repository uses it rather than
  `cleanup.py`'s local `_git_root`, which duplicates a subset of it.

**Gate-1 coverage note.** A2 also introduced a process rule this item predates:
gate 1 is now *validation-first*, requiring an exhaustive probe matrix —
every implicated input crossed with every affected operation — because A2's
register entry proved overstated when probed. A3's gate 1 ran four targeted
live-git probes, not a matrix. The exposure is asymmetric and worth stating
plainly: A2 was **overstated** and probing shrank it, whereas A3's four probes
each **reproduced**, and the Codex pass *raised* severity rather than lowering
it. Overstatement is therefore not the live risk here; unprobed adjacent
surface is. Specifically unprobed: registry behavior under concurrent forks in
two repositories, and cleanup against a worktree moved by `git worktree move`.
Both are covered by slice C's staleness matrix, which is where the matrix
discipline lands for this item rather than retrofitting gate 1.

### Ambiguity and removal

**Exactly one candidate.** After the predicate filters, exactly one row may
survive. Two or more rows claiming one live worktree is a refusal
(`cleanup_registry_ambiguous`), raised while the plan is built, before any git
mutation. Counting candidates is the check — not comparing whole records,
which round 3 showed is neither implementable nor responsive to the question,
since `_decode` builds dataclasses and discards the JSON representation.

**Removal is a compare-and-swap.** The selected row carries an opaque token
derived from its persisted representation. Removal re-decodes under the
registry lock, finds the row still matching that token, removes exactly it, or
fails without removing anything.

**The transaction window closes rather than moves.** Cleanup destroys the
worktree and branch (`cleanup.py:385-392`) before `remove_entry` takes the
lock (`registry.py:116-124`), with unbounded consent in between
(`cli.py:1087-1105`). After consent and **before any git mutation**, the lock
is re-acquired, the predicate and candidate count are revalidated inside it,
and exclusion is held through the registry commit. Revalidation failure and
lock timeout both refuse with nothing destroyed.

### Migration

A v1 row becomes a v2 row with `repository: null`, meaning *unknown*. Decoding
is purely structural: `_decode` accepts versions 1 and 2, rejects unknown
ones, and runs no subprocess. Read paths never write.

**A null identity authorizes nothing** (owner decision 2026-08-20, gate 6
round 3). An earlier revision of this section said the opposite: that the
predicate governs actionability without consulting the stored identity, so a
pre-upgrade fork could be cleaned up by name. That was wrong, and the reason
matters. Matching a live worktree does not establish *ownership*, because two
repositories can hold one path on one branch name — ordinary rather than
exotic under the `central` worktree layout, which keys on a repository's
basename alone, so two checkouts named alike collide by configuration.

**No backfill, for the same reason.** An earlier revision wrote the current
repository onto any null row whose pair was live here, and argued this was
"the probe done correctly" because the enumeration started from the user's
working directory rather than from the row's stored path. The direction was
indeed better; the conclusion still did not follow. A live pair is consistent
with the row belonging here, and consistent with it belonging to a repository
that used the path first. Writing an identity on that evidence manufactures
the ownership it cannot prove.

**What a user with pre-upgrade records does.** By name, cleanup refuses and
names `prune`. By explicit path it works — a path the user typed is fresh
input, and a null row vetoes nothing, so the target reaches confirmed
discovery with the dirty and unpushed guards intact and no `--force` needed.
`prune` then clears the records; it never touches a worktree, so either order
is safe. Removing backfill also removed `add_entry`'s `live` parameter: with
no backfill, its replacement rule is purely `(repository, name)`.

Two consequences are documented rather than engineered around: rows already
clobbered under v1 are unrecoverable, and once a v2 write lands, older
binaries reject the file.

### Errors

Two codes, both exit 5, joining the `cleanup_*` refusal family
(`errors.py:33-47`) whose members all refuse before an unsafe mutation. Both
enter `ERROR_CATALOG` **before** any code raises them, because `T-OUT-14`
(`tests/cli/test_out.py:442-469`) requires exact catalog equality and
`PreconditionError` degrades an uncatalogued code to
`ValueError("uncataloged precondition error code")` (`errors.py:77-86`).

| Code | Raised when | Message states |
|---|---|---|
| `cleanup_registry_stale` | The target's row fails the predicate — its recorded worktree and branch are not a live pair in this repository | The recorded worktree and branch, that they are not live here, and that `prune` removes rows whose worktree no longer exists |
| `cleanup_registry_ambiguous` | More than one row survives the predicate for one target | Each surviving candidate, and that the registry needs repair |

`cleanup_registry_mismatch` from the previous revision is **removed**. Under
the predicate, "belongs to a different repository" and "is stale" are the same
observable condition — the pair is not live here — and cannot be distinguished
without knowing whether the row is actionable somewhere else, which is not
cheaply knowable. One accurate code replaces two inaccurate ones.

**`--force` does not override either code.** Its two existing meanings are
untouched: target something unregistered (`cleanup.py:158-179`) and override
the dirty and unpushed guards (`cleanup.py:337-356`, `REQUIREMENTS.md:153`).
Neither concerns whether a row still describes reality. A user passing
`--force` for the unpushed reason must not thereby suppress the only proof
that a worktree belongs to the repository its record names.

### `prune` — the exit for rows the predicate rejects

The predicate makes a row that no longer matches disk permanently
unactionable. Without a way to remove such a row, A3 would leave every user a
growing set of entries that cannot be used and cannot be cleared — the
dead-end recorded as fault A7. The owner directed that A3 ship the exit.

`agent-fork prune` removes two kinds of row, and never runs a destructive git
command or touches a worktree — it only deletes bookkeeping:

- rows whose recorded worktree path **does not exist on disk**;
- rows carrying **no repository** (added 2026-08-20 with the null-identity
  decision). Such a row can never authorize anything and can never gain an
  identity, so it is inert by construction. Clearing it destroys no work: a
  worktree still at that path stays on disk and remains removable by explicit
  path.

- **Its predicate is deliberately different from the actionability
  predicate.** Actionability is repository-scoped: a row belonging to another
  repository is not actionable *here*, but it is perfectly valid *there*, and
  pruning it would be wrong. Non-existence is repository-independent and safe
  to act on from anywhere.
- A row whose path exists but hosts something other than the recorded fork is
  **reported and left alone**. It may be another repository's live worktree.
  Deciding its fate needs evidence `prune` does not have.
- It reports what it will remove and requires confirmation, matching
  `cleanup`'s existing consent pattern; `--yes` skips the prompt and
  `--dry-run` previews.
- It operates on the whole registry, consistent with `list`, and runs under
  the registry lock with the same atomic replacement as every other mutation.

**Scope note.** `prune` is registered against **A7**, which owns stale-entry
remediation (`prune` / `cleanup --missing`). A3 absorbs the `prune` half
because A3's predicate creates the need for it; A7 retains
`cleanup --missing`, moved-worktree repair, and the reused-path reporting case
this design leaves open. A7's entry is amended to say so rather than left to
imply work that has already shipped.

### `list` stays global and unfiltered

Duplicate names across repositories are legal and expected once scoping is
correct; the text output already carries the worktree path, so rows remain
distinguishable. No new filter flag — P02 forbids new features.

One correction to an earlier claim in this document: `worktree_exists` derives
from `Path.exists()` alone (`models.py:77-85`, `cli.py:1143-1155`), so a row
whose historical path is now occupied by an unrelated worktree reports `true`.
`list` reports path existence, not fork liveness, and the documentation says
so.

### Two serialization contracts

`to_dict()` (`models.py:77-85`) currently feeds the on-disk registry
(`registry.py:70-74`), the public `list --json` payload (`cli.py:1143-1155`),
**and** the public `cleanup --json` target (`cli.py:1116-1129`). `to_dict()`
stays exactly as it is and remains the public serializer for all of them; a
new `to_registry_dict()` always emits `repository`, including null; only
`_atomic_write()` switches to it. The registry file moves to version 2 while
public output keeps `"version": 1`.

Schema assertions must not be self-referential. `tests/cli/test_reg.py:43-51`
builds its expected rows from the same `to_dict()` production uses, so a
change moves actual and expected together; `tests/unit/test_reg.py:58-65`
manufactures its v1 fixture by serializing a current entry and deleting
`mode`. Raw v1, raw v2, public `list`, and public `cleanup` payloads are each
pinned with literal dictionaries instead.

### Owner decisions

1. **Auto-naming is left untouched.** Once uniqueness is `(repository, name)`,
   two repositories each holding a fork named `main-0817` is correct.
   Consulting the registry would impose an artificial machine-wide namespace.
   The register's bullet is recorded as over-broad, not unfixed.
2. **`list` is left unchanged** — global, unfiltered, public JSON at
   `"version": 1`.
3. **Migration is retained; v1 registries are not refused.** Silently breaking
   a shipped tool's state file is the worse trade. Standing, not conditional
   on review outcomes.
4. **Migration is conservative — no identity is inferred from a stored path.**
   Superseded in part by decision 5: identity is now backfilled from live
   enumeration, which is evidence, whereas probing a stored path is not.
5. **The plan is reshaped around the actionability predicate**, with a typed
   refusal when a row does not match disk and a `prune` verb to clear such
   rows. Replaces five site-specific guards with one mechanism.

## Implementation plan (TDD; subagent-driven)

Four deployable slices. The registry API and all of its callers are one slice,
because changing `remove_entry` and `find_owned` breaks twelve call sites at
once and `just all` runs `ty check` (`justfile:22-28`, `justfile:55-56`), so a
signature-broken tree is not a clean intermediate gate.

Behavioral tests drive the CLI through a subprocess, depend on no internal
signature, and genuinely land first. Signature-aware unit tests land inside
their own slice, still written before the implementation they cover.

### Slice A — model, serialization, structural decode

- `RegistryEntry` gains `repository: str | None = None` appended **last**, so
  existing positional construction is not rebound. `RegistryEntry.create()`
  (`models.py:64-75`) gains and persists the parameter.
- `to_dict()` unchanged and still public; new `to_registry_dict()`; only
  `_atomic_write()` switches to it.
- The row token used by compare-and-swap removal is defined here, derived from
  the persisted representation.
- `_decode` accepts raw v1 and v2, rejects unknown, runs no subprocess;
  null-safe ordering key `(item.repository is None, item.repository or "")`,
  which avoids the `TypeError` a bare `None` in a sort tuple would raise.
- Tests: raw v1, raw v2, public `list`, and public `cleanup` payloads pinned
  with literal dictionaries; a null-versus-string ordering tie.

### Slice B — the predicate, the registry API, and every caller

Call sites that must change together:

| Symbol | Sites |
|---|---|
| `remove_entry` | `pipeline.py:182`, `cleanup.py:394` — no direct test callers |
| `find_owned` | `cleanup.py:152`, plus nine test callers: `tests/cli/test_cln.py:108`, `tests/pipeline/test_cln.py:130`, `tests/pipeline/test_inc.py:110`, `tests/pipeline/test_inc.py:142`, `tests/pipeline/test_reg.py:132`, `:135`, `:136`, `:137`, `:143` |

- One function returns an actionable row: it takes the invoking directory,
  enumerates live worktrees, freshly identifies the repository, matches
  candidates, applies the predicate, and refuses on zero or several. **No
  destructive path may obtain a row from anywhere else.**
- `find_owned` keeps its existing single-pass, creation-ordered scan and
  selector precedence, and does **not** filter by stored identity.
- `add_entry` replacement identity is `(repository, name)`, with a non-null
  guard on both sides so two null rows never compare equal, and it replaces a
  row only when the predicate confirms that row belongs to this repository.
- No backfill of null identities: a live pair is consistent with the record
  belonging elsewhere, so it cannot establish ownership.
- Removal is compare-and-swap on the row token.
- `pipeline.py` builds one named entry from `creation.common_dir`
  (`repository.py:336-343`) and hands that same object to the lineage-failure
  compensation, which must not delete a row it did not create.
- `tests/pipeline/test_reg.py:139-143` is rewritten deliberately: it asserts
  `_decode` raises `ValueError` on a corrupt registry, and a changed signature
  would otherwise make it fail before decoding, destroying its oracle.

### Slice C — cleanup, prune, and the refusals

- `cleanup_registry_stale` and `cleanup_registry_ambiguous` enter
  `ERROR_CATALOG` before any code raises them.
- Cleanup obtains its row only from the slice-B function; re-acquires the lock
  after consent and before any git mutation; revalidates predicate and count
  inside it; holds exclusion through the registry commit. `--force` overrides
  neither refusal.
- `prune` as specified: removes rows whose recorded worktree path does not
  exist, reports and leaves everything else, confirmation required,
  `--dry-run` and `--yes` supported, under the registry lock.
- Behavioral tests, written first — each asserting the **complete expected
  final registry document**, row count and identities included:
  - the four TS03 repros;
  - **staleness matrix**, one case per destructive site, each making a stored
    value deliberately wrong and requiring a refusal: path reused by another
    repository; branch deleted and recreated; worktree removed by hand;
    worktree replaced by a different worktree of the same repository on a
    different branch;
  - non-dry-run cleanup from repoE cannot touch repoF;
  - a pre-upgrade (null-identity) fork whose worktree exists is cleaned **by
    name, without `--force`, with the dirty and unpushed guards intact**;
  - safe backfill writes an identity into a live null row, and does **not**
    write one into a row whose path is occupied by another repository;
  - fork-time replacement removes a same-name row only when the predicate
    confirms it, and a lineage failure afterwards leaves any pre-existing row
    intact — the existing compensation test starts from an empty registry
    (`tests/pipeline/test_reg.py:146`) and cannot detect this;
  - ambiguity: two rows surviving the predicate for one target refuse and
    destroy nothing;
  - transaction window: planned row replaced, planned row removed, and
    post-consent lock timeout — each refuses with nothing destroyed;
  - `prune` removes only non-existent paths, leaves an occupied-path row and
    reports it, and leaves another repository's live rows untouched;
  - successful same-name cleanup in repo A leaves repo B intact;
  - exact-path cleanup from a non-repository working directory;
  - bare repository and linked-worktree identity.

### Slice D — documentation, matrix, gate

`REQUIREMENTS.md` and `README.md`: cleanup acts only on a row confirmed
against live state; the two refusals and what they mean; `prune` and its
narrower predicate; conservative migration, safe backfill, and the
older-binary no-downgrade consequence; `list` reports path existence, not fork
liveness. New `T-REG` rows in `docs/testing/TEST-MATRIX.md` under G-REG.

**Amend A7** in the P02 register: A3 ships `prune`; A7 retains
`cleanup --missing`, moved-worktree repair, and the reused-path reporting
case.

**Gate 6 exit criteria.** `just all` green; the four repros pass as tests;
every row of the staleness matrix refuses; the pre-upgrade-fork cleanup works
without `--force`; the fork-time replacement and lineage-failure test passes;
public `list` and `cleanup` payloads match their literal fixtures with
`repository` absent, and raw v2 rows carry it.

## Adversarial plan review (gate 4) — round 1 outcome

**Codex verdict: REJECT** (11 required changes). All 11 absorbed; none
declined. The substantive ones, and what changed:

| # | Finding | Resolution |
|---|---|---|
| 1 | The null-identity exact-path exception is destructive: a stale null row keeps its historical path, and a later unrelated worktree at that path would be removed on the dead row's authority | Exception removed. Null rows authorize nothing. Stale-row remediation routed to A7 |
| 2 | Exact removal keyed on the derived `repository` field fails for a live v1 row — it backfills at plan time, re-decodes to null after the worktree is deleted, and the row survives a successful cleanup | Removal keys on the persisted `(name, worktree)` pair; regression test added |
| 3 | Structural decode and live probing were conflated; probing under the lock lets one slow row block all writers with `registry_busy` (`run_git` has no timeout) | Separated. Probe → lock → re-decode → merge → write. Per-row failure classification defined; v2 nulls re-probed |
| 4 | Signature change and callers split across steps leaves the tree knowingly broken; `ty check` runs in `just all` | Collapsed into one atomic slice with all twelve call sites enumerated |
| 5 | `RegistryEntry.create()` was never scheduled for update | Explicit in slice A |
| 6 | Error raised in step 5, catalogued in step 7 — `T-OUT-14` and `PreconditionError` make that unconditionally red | Catalogued before first raise, in the same slice |
| 7 | Serialization split had three callers, not two — `cleanup --json` was missed | `to_dict()` frozen as the public serializer; `to_registry_dict()` added; only `_atomic_write()` switches |
| 8 | Public-contract proof was self-referential — the test builds expectations from the serializer under test | Literal-dictionary fixtures for all four payloads |
| 9 | Fifteen missing test cases | All folded into slices A and C |
| 10 | `cleanup_foreign_repository` misreports a moved repository as "another repository" | Renamed `cleanup_repository_mismatch` with neutral wording; moved repositories documented as an accepted typed limitation |
| 11 | Standalone step 6 was a no-op verification, not an implementation step | Folded into slice A's acceptance criteria |

Also recorded from the review, not as changes but as accurate scoping: the
containment check is a **guard, not a durable guarantee** (the resolve-then-
mutate window belongs to A8), and A3 narrows the stale-row surface that A7
owns rather than widening it — the only reason a stale row resolved before
was the unscoped bare-name match that *is* this fault.

## Adversarial plan review (gate 4) — round 2 outcome

**Codex verdict: REJECT** (7 remaining changes; 3 P0). Round 1 findings 4–9
and 11 were verified as fully absorbed. Four were only partial, and the
revision introduced new defects of its own. All absorbed; none declined.

| Finding | Resolution |
|---|---|
| **P0** — the plan declared null rows inert *because* historical path equality is not proof of ownership, then re-probed them, letting an unrelated worktree at that path graft its identity onto the stale row. Also A7 scope drift, contradicting A3's own exclusion list | Re-probing removed. Null rows are never re-probed in A3. With no consumer left, the permanent-versus-transient failure classifier was deleted too — both outcomes persist identically as null, and the distinction could not have been drawn anyway since an invalid worktree *is* observed as a nonzero git exit |
| **P0** — `(name, worktree)` is not unique, would naturally become an all-matches filter, and stored path spellings are not normalized (resolved on create, verbatim on v1 decode), so several stored rows can resolve to one live path | Replaced with a protocol: match the complete persisted record byte-for-byte, require **exactly one**, refuse otherwise via `cleanup_registry_ambiguous` — checked while the plan is built, before any git mutation |
| **P0** — "merge" was named but never defined; a pre-lock probe merged naively loses a concurrently-added row or resurrects a concurrently-removed one. And "transient row unchanged on disk" is contradictory, since every write rewrites the whole document | Merge rule stated: the under-lock document is authoritative, probe results apply only to byte-for-byte unchanged rows, additions preserved, removals never re-appended. Both interleavings added as tests with explicit expected final documents |
| **P1** — exact-path-first matching is a new targeting policy `REQ-31` does not define, silently changes behavior for a token that is both a name and a relative path, and existing tests would stay green through it | Reverted. `find_owned` keeps its existing single-pass creation-ordered scan and selector precedence; the only change is that name and branch matches additionally require a non-null invoking identity |
| **P1** — `cleanup_repository_mismatch` still described the wrong comparison; the check is live-versus-stored on the target, so it also fires for an explicit path used outside any repository | Renamed `cleanup_registry_mismatch` with an accurate description; the message names both the stored and the live identity |
| **P1** — migration and concurrency tests lacked explicit expected final registry state | Every such test now asserts the full expected document, row count and identities included |
| **P2** — the moved-repository "manual remedy" was promised but never named; the status line was stale | Remedy named: `--force` downgrades the mismatch refusal to a notice, per its existing "extend targeting" meaning, leaving the stale row to A7. Status line corrected |

## Adversarial plan review (gate 4) — round 3 outcome

**Codex verdict: REJECT** (4 P0, 3 lower). Round-2 findings 1 and 5 verified
fully absorbed; the rest were textually present but unsound, incomplete, or
self-contradictory. All absorbed; none declined.

| Finding | Resolution |
|---|---|
| **P0** — "match the complete persisted record byte-for-byte" is not implementable: `_decode` builds dataclasses (`registry.py:29-38`) and keeps no JSON bytes, key order, or field presence — an omitted `mode` and an explicit `"mode":"agent"` decode identically. It also answers the wrong question: `find_owned` returns the *first* match, so exactly one row still equals the selected record while several claim the target | Split into two mechanisms. **Selection ambiguity** is a lookup property: exactly one authorized *candidate*, counted, else `cleanup_registry_ambiguous`. **Removal identity** is a concurrency property: an opaque token plus compare-and-swap under the lock |
| **P0** — moving the ambiguity check earlier only relocated the TOCTOU. Consent is unbounded (`cli.py:1087-1105`), the worktree and branch are destroyed at `cleanup.py:385-392`, and only `remove_entry` takes the lock afterwards — so the row can be replaced, removed, or lock-timed-out after destruction | The lock is re-acquired **after consent, before any git mutation**, identity and cardinality revalidated inside it, exclusion held through the registry commit. Failure outcomes specified: revalidation failure and lock timeout both refuse with nothing destroyed |
| **P0** — probe-based v1 migration derives identity from the row's *stored historical path*, so an unrelated repository now occupying that path has its identity written onto the stale row, which then passes scoped lookup and the ownership check | Owner decision 4: migration is conservative and probes nothing. This also deleted the pre-lock probe, the merge rule, both interleaving race tests, and the failure-classification rule |
| **P0** — `--force` downgrading the ownership mismatch lets a user who passed it for the *unpushed* reason destroy another repository's worktree; widening a flag's meaning is also a new feature P02 forbids | `--force` no longer overrides `cleanup_registry_mismatch`. The moved-repository remedy is withdrawn and routed to A7 |
| **P1** — null became a permanent tombstone with no A7 remedy: a live, repaired worktree whose row is null is not "missing or moved", so A7's current scope does not cover it | Routed to A7 explicitly, naming both the stale-row and the live-but-null case. Pre-upgrade forks remain removable through `--force` live discovery |
| **P1** — exact-path precedence was rejected in slice B and still required as a test in slice C | Contradiction removed; the test now asserts the **existing** creation-ordered precedence is unchanged |
| **P2** — "every migration/concurrency test asserts a full expected document" was claimed in the outcome table but scoped to two tests in the operative text | Requirement now applies to the whole inventory, stated where the tests are listed |

## Adversarial plan review (gate 4) — round 4 outcome

**Codex verdict: REJECT** (4 P0). Narrowed round: an audit for sites where a
destructive action is authorized by stored, historical, derived, or cached
data instead of freshly observed state, plus verification of the round-3
claims. **A fourth ownership-principle site was found, and a fifth.**

Dispositions below are **proposed, pending owner sign-off** — this is the
first round whose findings are not all A3's to fix.

| Finding | Proposed disposition |
|---|---|
| **P0 — fork-time replacement (4th ownership site).** The new `(repository, name)` key compares a freshly observed identity against *stored* ones. An unrelated repository occupying a stale row's recorded path lets a same-name fork delete that row. Lineage-failure compensation then removes the new row without restoring the displaced one (`pipeline.py:154-182`); the existing test starts from an empty registry and cannot detect it (`tests/pipeline/test_reg.py:146`) | **Absorb.** This is A3's own new mechanism |
| **P0 — the null `--force` fallback is unreachable.** `find_owned` still matches a null row by path (`registry.py:127-136`), so `resolve_cleanup_target` takes the owned branch (`cleanup.py:152`) and returns before the fallback (`cleanup.py:158-179`); the mismatch check then refuses. Owner decision 4 collapses into the stricter variant it was chosen over | **Absorb.** Defect in this document's own mechanism |
| **P0 — the migration route strips safety guards.** `--force` also overrides the dirty and unpushed refusals (`cleanup.py:337-356`). A fork that `cleanup` refuses today is destroyed by the `--force` route recommended for migrated rows | **Absorb.** Target extension must be separable from guard override for this path |
| **P0 — worktree/branch association unverified (5th site).** Common-directory equality proves repository membership, not that live worktree `W` is still on stored branch `B`; `worktree remove W` and `branch -D B` then run on unverified associations (`cleanup.py:385-392`) | **Propose routing to A8.** Pre-existing; A3 neither creates nor widens it. Absorbing it means A3 re-verifies every git association cleanup already trusts |
| **P1 — name targeting lost on the fallback.** Live discovery matches resolved path or exact live branch (`cleanup.py:170`), so `cleanup alpha --force` cannot find `fork/alpha`; custom `--branch` / `--worktree-dir` prevent deriving them (`README.md:357`) | **Absorb** as part of the fallback rework |
| **P1 — Slice B still carries the rejected "complete persisted record" instruction** (superseded by candidate-count plus token compare-and-swap), and Slice A schedules no token representation | **Absorb.** Claim-drift; the round-3 resolution was recorded but only half-applied |
| **P2 — two false claims in this document.** `worktree_exists` derives from `Path.exists()` alone (`models.py:77-85`, `cli.py:1143-1155`), so a reused historical path reports `true`; and the `--force` fallback can inspect an explicit target's own repository when cwd is not one (`cleanup.py:165`), so "the repository the user is standing in" is too narrow | **Absorb** as corrections; extend the A7 note with the reused-path `list` case |

**Loop status.** Four rounds, four rejections. Per the pre-commitment made
before this round, the review loop stops here rather than running a fifth.
