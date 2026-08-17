# P02-A3 — Per-repository scoping of the fork registry

**Fault:** A3 — global flat fork registry clobbers across repositories
([P02 register](../../../projects/P02-agent-fork-fault-remediation.md)).

**Status:** gates 1 and 3 closed. Gate 4 (adversarial plan review) in its
third round. Gates 5 and 6 open.

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

**Identity key — resolved `git rev-parse --git-common-dir`.** Chosen over
the origin remote URL, which is absent for remote-less repositories,
multi-valued per clone, split across SSH and HTTPS spellings, and would
wrongly collapse two independent clones that have separate local branch
namespaces. Chosen over a generated repository UUID, which would mean
mutating the user's git directory plus its own locking, clone-copy, and
recovery rules — scope creep for A3. Known residual weaknesses, documented
rather than solved here:

| Case | Behavior |
|---|---|
| Linked worktrees | Correct by construction — every linked worktree of one repository resolves to the same common directory |
| Submodules | Correct under git semantics; a submodule is its own repository with its own branch namespace |
| Bare repositories | Works only if the helper reads the common directory directly; requiring `--show-toplevel` would regress bare support (`repository.py:105-115`) |
| Moved repositories | Identity continuity breaks. Auto-rebinding is unsafe because path reuse is indistinguishable from legitimate movement |
| Mount aliases, case-aliased paths | Residual weakness; `Path.resolve()` handles symlinks, not every mount-level alias |
| `GIT_DIR` / `GIT_COMMON_DIR` set in the environment | Redirects identity. This is A2's territory (`git.py:63-80` forwards the environment unchanged) and is explicitly **not** duplicated here |

**Scoping rules.** Replacement identity becomes `(repository, name)`.
Removal takes an exact entry rather than a bare name. `find_owned` requires
the invoking repository's identity for name and branch matches, while an
explicit resolved worktree path stays globally addressable — a path is
unambiguous on its own. Cleanup additionally requires the selected
worktree's live common directory to equal its stored identity before a plan
is built. Ordering gains repository and worktree tie-breakers
(`registry.py:41-42`).

**Null-identity rows are not ownership records.** Every migrated v1 row
carries `repository: null`, meaning *unknown*. Null never compares equal to
anything, including another null, so such a row is unreachable by name and by
branch, and it also fails the live-versus-stored ownership check that guards
cleanup by explicit path. It authorizes nothing.

Two earlier revisions tried to give these rows authority and both were
rejected for the same reason. Round 2 granted an explicit-path exception;
round 3 rejected identity backfilled by probing the row's stored path. In
both, an unrelated live worktree occupying a stale row's *historical* path
would end up removed on a dead row's authority. **A historical path is not
proof of current ownership** — this design's central rule, and the one place
each revision failed to apply it.

The row is therefore preserved and visible to `list` — which already reports
`worktree_exists: false` deliberately (`cli.py:1157-1162`) — and inert.
Pruning it is **A7's** registered scope (`prune` / `cleanup --missing`), noted
against A7 per the gate-6 routing rule.

**A pre-upgrade fork stays removable, through live git state.** Because a
null-identity row proves nothing, cleanup treats such a target as
*unregistered* rather than as an owned record. That engages behavior that
already exists: with `--force`, `resolve_cleanup_target`
(`cleanup.py:158-179`) finds the target by inspecting the **invoking
repository's live worktrees** and builds a plan marked not-owned, and
`cleanup.py:393-394` removes a registry row only when the plan *is* owned —
so the worktree is removed and the stale row survives for A7.

The authorization comes entirely from current git state in the repository the
user is standing in. The stale row contributes nothing but its own removal
being skipped. This is the distinction round 3 required: a stale name must
never authorize a fallback.

**Removal must delete exactly one row.** A persisted `(name, worktree)` pair
is **not** an identity, as
gate 4 round 2 showed: nothing makes the pair unique, the current
name-filtered removal (`registry.py:116-124`) would naturally be adapted into
an all-matches filter, and stored worktree strings are not normalized — new
entries resolve the path (`models.py:70-75`) while raw v1 rows are accepted
verbatim (`registry.py:29-38`), so several distinct stored spellings can
resolve to one live path.

Round 3 then rejected "match the complete persisted record byte-for-byte" on
two counts, both correct. It is **not implementable**: `_decode` constructs
dataclasses (`registry.py:29-38`) and keeps no JSON bytes, key order, or
field presence — an omitted `mode` and an explicit `"mode":"agent"` decode to
the same object because the dataclass supplies the default
(`models.py:53-62`). And it **answers the wrong question**: `find_owned`
returns the *first* match (`registry.py:127-136`), so when several rows claim
one target, exactly one row still equals the selected record and cleanup
proceeds — full-record cardinality detects duplicate serialization, not
ownership ambiguity.

The two concerns are therefore separated, because they are different
problems:

- **Selection ambiguity — a lookup property.** `find_owned` must return
  exactly one *authorized candidate*, counting every row that matches the
  target under the scoping rules. Two or more is a refusal
  (`cleanup_registry_ambiguous`), raised while the plan is built.
- **Removal identity — a concurrency property.** The selected row carries an
  opaque token derived from its persisted representation, and removal is a
  **compare-and-swap under the registry lock**: re-decode, find the row still
  matching that token, remove exactly it, or fail without removing anything.

**The transaction window must close, not move.** Round 3's second correction:
moving the ambiguity check earlier only *relocated* the race. Cleanup removes
the worktree and branch (`cleanup.py:385-392`) before `remove_entry` takes
the lock (`registry.py:116-124`), and consent sits in between
(`cli.py:1087-1105`) with no bound. Another writer can replace or remove the
row, add a competing claim, or hold the lock until `RegistryBusyError` — all
after the worktree is already gone. The plan therefore re-acquires the lock
**after consent and before any git mutation**, revalidates identity and
cardinality inside it, and holds cooperative exclusion through the registry
commit. Failure outcomes are specified rather than assumed: revalidation
failure refuses with nothing destroyed; a lock timeout at that point refuses
with `registry_busy` and nothing destroyed.

**Two serialization contracts, deliberately separated — three callers, not
two.** `to_dict()` (`models.py:77-85`) currently feeds the on-disk registry
(`registry.py:70-74`), the public `list --json` payload
(`cli.py:1143-1155`), **and** the public `cleanup --json` target
(`cli.py:1116-1129`), which the rejected revision missed. Resolution:
`to_dict()` stays exactly as it is and remains the public serializer for both
commands; a new `to_registry_dict()` always emits `repository`, including
null; only `_atomic_write()` switches to it. The registry file moves to
version 2 while public output keeps `"version": 1`.

**Schema assertions must not be self-referential.** The rejected revision
claimed an unchanged `tests/cli/test_reg.py:43-51` would prove the public
contract held — but that test builds its expected rows from the same
`to_dict()` production uses, so a change to `to_dict()` moves actual and
expected together and the test stays green. The same trap sits in
`tests/unit/test_reg.py:58-65`, which manufactures its v1 fixture by
serializing a *current* entry and deleting `mode`; if `to_dict()` gained
`repository`, that fixture would silently stop representing real v1. Raw v1,
raw v2, public `list`, and public `cleanup` payloads are each pinned with
literal dictionaries instead.

**Migration is conservative and purely structural — nothing is probed**
(owner decision 2026-08-17). A v1 row becomes a v2 row with
`repository: null`. No identity is inferred for it, ever.

- `_decode` accepts versions 1 and 2, keeps rejecting unknown ones, maps a v1
  row to `repository: null`, and **runs no subprocess**. Read paths —
  `read_registry`, `list` — stop here and never write. The rewrite to v2
  happens under the existing lock on the next `add_entry` or removal.
- **Ordering is null-safe.** The sort key wraps `repository` as
  `(item.repository is None, item.repository or "")` rather than placing a
  possibly-`None` value in a tuple, which would raise `TypeError` on a row
  pair that differs only by null-versus-string identity.

Two revisions of this section were rejected before arriving here, and what
they cost is worth recording, because the deletions are the point:

- Round 2 proposed backfilling identity by probing each row's stored worktree
  path, split permanent from transient probe failures, and claimed a
  transient row stayed "unchanged on disk". That last claim was
  self-contradictory — every mutation atomically rewrites the *whole*
  document (`registry.py:70-92`) — and the split was undrawable anyway, since
  an invalid worktree is normally *observed as* a nonzero git exit
  (`git.py:98-105`).
- Round 3 rejected the probe itself: the stored path is historical, so a
  worktree belonging to an unrelated repository that now occupies that path
  would have its identity written into the stale row, which would then pass
  scoped lookup and the ownership check and authorize deleting that unrelated
  worktree.
- Removing the probe removes, with it, the pre-lock probing step, the
  probe-versus-lock merge rule, both concurrent-interleaving race tests, and
  the failure-classification rule — none of which fixed A3's fault. They
  existed only to make probing safe, and probing is gone.

Three consequences are documented rather than engineered around: rows already
clobbered under v1 are unrecoverable; once a v2 write lands, older binaries
reject the file; and pre-upgrade rows never gain an identity, so cleaning up a
pre-upgrade fork goes through the unregistered `--force` path described above.

**`list` stays global and unfiltered.** After correct scoping, duplicate
names across repositories are legal and expected; the text output already
carries the worktree path, so rows stay distinguishable. No new filter flag
— P02 forbids new features.

**Deliberately excluded:** per-repository registry files, remote-URL or UUID
identity, new `list` filters, stale-entry repair or pruning (A7),
reconstruction of already-clobbered rows, A2's environment hardening, and
A8's TOCTOU redesign.

**Owner decisions (2026-08-17).** Both settled before gate 4 opened:

1. **Auto-naming is left untouched.** The register lists "auto-name collision
   check never consults the registry" as part of A3. Once uniqueness is
   `(repository, name)`, two repositories each holding a fork named
   `main-0817` is *correct* and nothing is lost, so the bullet is recorded as
   over-broad rather than left unfixed. Consulting the registry would impose
   an artificial machine-wide namespace and suffix names across unrelated
   repositories.
2. **`list` is left unchanged** — global, unfiltered, public JSON pinned at
   `"version": 1`.
3. **Migration is retained; v1 registries are not refused.** Raised after two
   review rounds established that migration and concurrency handling — the
   pre-lock probe, the merge rule, null-row semantics, exact-one removal —
   account for most of A3's risk surface while fixing none of A3's fault. The
   alternative was a typed refusal of v1 plus a one-time manual step for
   existing users, which would delete that whole class of defect from this
   item. The owner chose to keep migrating: silently breaking a shipped
   tool's state file is the worse trade. This is a **standing** decision, not
   conditional on the remaining review rounds — a further migration defect is
   to be fixed, not routed around by cutting migration.
4. **Migration is conservative: v1 rows migrate to a null identity, and
   nothing is probed.** Raised when gate 4 round 3 found the probe unsafe —
   identity derived from a row's stored historical path can be taken from an
   unrelated repository that now occupies that path. Strengthening the probe
   was considered and rejected: also requiring the branch to match fails
   precisely in A3's own scenario, where two repositories legitimately hold
   the same fork name and branch. Of the two safe variants, the owner chose
   the one that keeps pre-upgrade forks removable — a null-identity row is
   treated as unregistered, so existing `--force` live-worktree discovery
   authorizes the removal and leaves the row for A7 — over the stricter
   variant that would strand them entirely.

**Two new error codes**, both exit 5, both joining the `cleanup_*` refusal
family in `errors.py:33-47` whose members all refuse before an unsafe
mutation, and both added to the publishable-tier catalog (REQ-38 / R7.12):

| Code | Meaning |
|---|---|
| `cleanup_registry_mismatch` | the target worktree's **live** repository identity differs from the identity stored in its registry record |
| `cleanup_registry_ambiguous` | the selected record does not match exactly one persisted row — zero or several |

Naming went through two corrections. `cleanup_foreign_repository` ("belongs
to another repository") was false for the case that will produce it most
often: the same repository, moved on disk. `cleanup_repository_mismatch`
("does not match the invoking repository") was still wrong about *which two
things are compared* — the check is live-versus-stored on the target record,
which is why it also fires for an explicit path used from a non-repository
directory, where there is no invoking repository at all.

**Both must be catalogued before any code raises them.** `T-OUT-14`
(`tests/cli/test_out.py:442-469`) inventories literal production error codes
and requires exact equality with `ERROR_CATALOG`, and `PreconditionError`
degrades an uncatalogued code to
`ValueError("uncataloged precondition error code")` (`errors.py:77-86`).

**`cleanup_registry_mismatch` is not overridable by `--force`.** The rejected
revision made it so, and round 3 was right to call that unsafe and a new
behavior besides. `--force` today means two specific things — target
something unregistered (`cleanup.py:158-162`) and override the dirty and
unpushed guards (`cleanup.py:337-356`, `REQUIREMENTS.md:153`) — and a user
who passes it for the *unpushed* reason would silently also suppress the
only proof that the worktree still belongs to the repository its record
names. The concrete loss: row says repo A at path W, W is now repo B's
worktree, cleanup from A selects A's row, live identity correctly reports B,
and `--force` deletes B's worktree. Broadening a flag's meaning is also a new
feature, which P02 forbids.

**Moved repositories are an accepted limitation without an A3 remedy.**
Identity continuity across a repository move is not supported — path reuse is
indistinguishable from legitimate movement, the same reasoning that rules out
null-row rebinding and probe-based migration. The refusal names both the
stored and the live identity so the user can see what moved; repairing or
pruning the row is A7's registered scope, and this case is routed there
explicitly.

**The containment check is a guard, not a guarantee.** Target resolution
happens before CLI consent (`cli.py:1087-1105`) and mutation happens later
(`cleanup.py:371-394`), so a move or path replacement in between defeats a
pre-plan comparison. A8 owns the TOCTOU redesign; A3 must not describe this
check as durable containment.

## Implementation plan (TDD; subagent-driven)

Four deployable slices, not seven file-oriented steps. The rejected revision
claimed steps 2–6 were sequential; they are not. Changing `remove_entry` and
`find_owned` breaks twelve call sites at once, so any plan that changes the
signature in one step and its callers in later steps leaves the tree
knowingly broken — and `just all` runs both `ty check` and pytest
(`justfile:22-28`, `justfile:55-56`), so a signature-broken tree is not a
clean intermediate gate. **The API and all of its callers are one slice.**

**RED-first, honestly scoped.** Behavioral tests drive the CLI through a
subprocess, depend on no internal signature, and genuinely land first.
Signature-aware unit tests cannot be type-clean before the types exist, so
they land inside their own slice, still written before the implementation
they cover.

### Slice A — model and serialization contracts

- `RegistryEntry` gains `repository: str | None = None` appended **last**, so
  existing positional construction is not silently rebound.
- `RegistryEntry.create()` (`models.py:64-75`) gains and persists the
  parameter. The rejected revision left this implicit and would have had
  slice C constructing through a factory that rejects the field.
- `to_dict()` unchanged and still public; new `to_registry_dict()` always
  emits `repository`; only `_atomic_write()` switches to it.
- `_decode` accepts raw v1 and v2 structurally, rejects unknown, runs no
  subprocess; null-safe ordering key.
- Tests: raw v1, raw v2, public `list`, and public `cleanup` payloads each
  pinned with **literal dictionaries**, never the serializer under test; a
  null-versus-string ordering tie.

### Slice B — registry API and every caller, atomically

Full inventory, which the rejected revision did not enumerate:

| Symbol | Call sites |
|---|---|
| `remove_entry` | `pipeline.py:182`, `cleanup.py:394` — no direct test callers |
| `find_owned` | `cleanup.py:152`, plus nine test callers: `tests/cli/test_cln.py:108`, `tests/pipeline/test_cln.py:130`, `tests/pipeline/test_inc.py:110`, `tests/pipeline/test_inc.py:142`, `tests/pipeline/test_reg.py:132`, `:135`, `:136`, `:137`, `:143` |

- Replacement identity `(repository, name)` with an explicit **non-null
  guard** on both sides, so two null rows never compare equal.
- Removal takes the complete persisted record and requires exactly one match,
  per the design rule — not the derived `repository` field, and not a
  `(name, worktree)` pair.
- `find_owned` keeps its **existing single-pass, creation-ordered scan and
  its existing selector precedence**; the only change is that a name or
  branch match now additionally requires a non-null invoking identity to
  equal the row's. Path matching is untouched, which keeps explicit paths
  working from a non-repository cwd for free.

  The rejected revision promoted exact-path matches ahead of all symbolic
  matches. That is a new targeting policy `REQ-31` does not define
  (`REQUIREMENTS.md:151-154`), it silently changes behavior for a token that
  is both a valid fork name and a valid relative path, and existing tests
  cover only unambiguous targets so they would have stayed green through the
  change. Not needed for A3, so not done in A3.
- `pipeline.py` builds one named entry from `creation.common_dir`
  (`repository.py:336-343`) and hands that same object to the lineage-failure
  compensation.
- `tests/pipeline/test_reg.py:139-143` is rewritten deliberately: it asserts
  `_decode` raises `ValueError` on a corrupt registry, and a new required
  argument would otherwise make it fail before decoding, silently destroying
  its oracle.

### Slice C — cleanup safety and migration behavior

- `cleanup_registry_mismatch` and `cleanup_registry_ambiguous` enter
  `ERROR_CATALOG` **before** any code raises them (`T-OUT-14`,
  `PreconditionError`).
- Cleanup resolves the invoking common directory for name and branch lookup
  and keeps explicit paths global. While the plan is built — **before any git
  mutation** — it requires the target's live common directory to equal its
  stored identity, and requires the selected record to match exactly one
  persisted row. Removal then deletes that one row. No null-identity
  exception, and `--force` does not override the mismatch refusal. After
  consent and before any git mutation, the lock is re-acquired, identity and
  cardinality are revalidated inside it, and exclusion is held through the
  registry commit; removal is a compare-and-swap on the selected row's token.
- A null-identity row is treated as **unregistered** rather than owned, so
  cleanup falls through to the existing `--force` live-worktree discovery
  (`cleanup.py:158-179`) and the not-owned plan leaves the row in place
  (`cleanup.py:393-394`). No migration probing exists to specify.
- Behavioral tests, written first: the four repros; non-dry-run cleanup from
  repoE cannot touch repoF; **a v1 row migrates to a null identity and is
  never given one**; **a pre-upgrade fork is removable with `--force` via live
  discovery, and its row survives**; a stale null row whose path is reused by
  an unrelated live worktree is refused without `--force` and, with `--force`,
  removes the worktree that live discovery found in the invoking repository —
  never one named only by the stale row;
  successful same-name cleanup in repo A leaves repo B's worktree, branch,
  and row intact; branch-scoped foreign lookup; a token that is both a valid
  fork name and a valid relative path resolves under the **existing**
  creation-ordered precedence, unchanged by this work; exact-path cleanup from
  a non-repository cwd; moved repository, moved-and-repaired linked worktree,
  and deleted parent common directory; raw v1 bytes unchanged after
  `read_registry` and `list`; bare repository identity; linked-worktree
  identity; `find_owned` with a null invoking identity cannot match null rows.
- **Selection ambiguity:** two or more rows claiming one target — sharing a
  resolved worktree path, or sharing name and worktree, or the same worktree
  stored under differing spellings (symlinked, trailing separator) — refuse
  with `cleanup_registry_ambiguous` and destroy nothing. These assert on the
  candidate *count*, not on record equality, which is what round 3 showed
  full-record matching fails to detect.
- **Transaction window:** the planned row is replaced by another writer
  between consent and mutation → refuse, nothing destroyed; the planned row is
  removed by another writer in that window → refuse, nothing destroyed; the
  post-consent lock times out → `registry_busy`, nothing destroyed.
- Moved repository: `cleanup` refuses with `cleanup_registry_mismatch` naming
  both the stored and the live identity, and **`--force` does not override
  it** — the refusal stands and the row is A7's to repair.
- **Every migration and concurrency test asserts the complete expected final
  registry document** — row count and exact identities, not a spot check. This
  applies to the whole inventory above, not only to the concurrency rows; the
  round-2 outcome claimed it while the operative text scoped it to two tests.

### Slice D — documentation, matrix, full gate

`REQUIREMENTS.md` and `README.md`: name and branch cleanup is scoped to the
invoking repository while a registered worktree path stays globally
addressable; conservative migration, the older-binary no-downgrade
consequence, and the `--force` route for pre-upgrade forks; the
moved-repository limitation. New `T-REG` rows in
`docs/testing/TEST-MATRIX.md` under G-REG.

**Routed to A7** per gate-6 routing, in one note naming both cases: stale
rows that A3 leaves inert, and live-but-null rows — a repaired worktree whose
row can no longer gain an identity, which A7's current text ("missing or
moved") does not cover.

**Gate 6 exit criteria.** `just all` green; the four repros pass as tests;
the non-dry-run containment test passes; a pre-upgrade fork is removable via
`--force` live discovery with its row surviving; public `list` and `cleanup`
payloads match their literal fixtures with `repository` absent, and raw v2
rows carry it.

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

Round 4 review: not yet dispatched — pending an owner call on whether to
continue the loop.
