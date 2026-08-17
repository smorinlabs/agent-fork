# P02-A3 — Per-repository scoping of the fork registry

**Fault:** A3 — global flat fork registry clobbers across repositories
([P02 register](../../../projects/P02-agent-fork-fault-remediation.md)).

**Status:** gate 1 (adversarial verification) in progress. Gates 3–6 open.

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

**Null-identity rows authorize nothing.** A legacy row that could not be
resolved migrates with `repository: null`. Null never compares equal to
anything, including another null, so such a row is unreachable by name and by
branch. It is **also not** authorized for cleanup by explicit path.

An earlier revision of this design did grant that path exception, reasoning
that refusing it would recreate A7's dead-end. Gate 4 rejected it: a hand-
deleted worktree migrates to null while retaining its *historical* path, and
if an unrelated live worktree later occupies that path, exact-path cleanup
would match the stale row, skip the repository comparison under the
exception, and remove the replacement worktree on a dead row's authority.
Historical path equality is not proof of current ownership.

The row is therefore preserved and visible to `list` — which already reports
`worktree_exists: false` deliberately (`cli.py:1157-1162`) — and inert.
Remediation of stale rows is **A7's** registered scope (`prune` /
`cleanup --missing`); this is noted against A7 per the gate-6 routing rule.
A3 is removing an *unsafe* resolution path, which is not the same as
removing a safe one: the only reason such a row resolved before was the
unscoped bare-name match that is this fault.

**Removal identity must survive migration.** Removal cannot key on the
`repository` field, because that field is *derived*: a live v1 row backfills
to a real identity when the cleanup plan is built, then re-decodes to null
after cleanup deletes the worktree but before the registry write — so the
entry would no longer match itself and the row would survive a successful
cleanup. Removal therefore matches on the persisted, non-derived pair
`(name, worktree)`.

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

**Migration — structural decode and live probing are separate.** These were
conflated in the rejected revision, which put backfill "inside the existing
lock" while `_decode` is also called unlocked by `list`, and which would have
held the exclusive lock across an unbounded `git rev-parse` (`run_git` has no
timeout, `git.py:63-105`) — letting one slow legacy row block every other
writer with `registry_busy`.

- `_decode` is **purely structural**. It accepts versions 1 and 2, keeps
  rejecting unknown ones, and maps a v1 row to `repository: null` meaning
  *unknown*, running no subprocess. Read paths — `read_registry`, `list` —
  stop here and never write.
- **Probing is a separate, explicit step** performed only by mutation paths,
  and performed **before** the lock is taken, never while holding it. Order:
  probe → acquire lock → re-decode → merge → atomic write.
- **Per-row failure classification is explicit.** A worktree that is absent,
  or present but not a valid git worktree, is a *permanent* negative and
  persists as null. A probe that fails transiently — nonzero git exit,
  `OSError` starting git, permission denial, an in-progress repair — leaves
  the row **unmigrated in memory and unchanged on disk**, so a later run can
  still resolve it. One bad row never aborts `list` and never blocks a
  mutation on unrelated rows.
- **v2 null rows are re-probed** on subsequent mutations, so a transient
  failure or a later `git worktree repair` self-heals.
- **Ordering is null-safe.** The sort key wraps `repository` as
  `(item.repository is None, item.repository or "")` rather than placing a
  possibly-`None` value in a tuple, which would raise `TypeError` on a row
  pair that differs only by null-versus-string identity.

Two consequences are documented rather than engineered around: rows already
clobbered under v1 are unrecoverable, and once a v2 write lands, older
binaries reject the file.

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

**New error code.** `cleanup_repository_mismatch`, exit 5, "cleanup target's
repository identity does not match the invoking repository" — matching the
existing `cleanup_*` refusal family in `errors.py:33-47`, all of which refuse
before an unsafe mutation. The publishable-tier error catalog (REQ-38 /
R7.12) is updated with it.

Two constraints on it, both from gate 4:

- **The wording is deliberately neutral.** The rejected revision named it
  `cleanup_foreign_repository`, "belongs to another repository" — which is
  false in the case that will produce it most often in practice: the same
  repository, moved on disk, whose stored common-directory path no longer
  matches the live one.
- **It must be catalogued before any code raises it.** `T-OUT-14`
  (`tests/cli/test_out.py:442-469`) inventories literal production error
  codes and requires exact equality with `ERROR_CATALOG`, and
  `PreconditionError` degrades an uncatalogued code to
  `ValueError("uncataloged precondition error code")` (`errors.py:77-86`).
  The rejected revision raised it in step 5 and catalogued it in step 7,
  which would have left two steps unconditionally red.

**Moved repositories are an accepted, typed limitation.** Identity continuity
across a repository move is explicitly not supported. The refusal above is
the recovery surface, and the documentation states the manual remedy rather
than attempting an automatic rebind — path reuse is indistinguishable from
legitimate movement, which is the same reasoning that rules out the null-row
path exception.

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
- Removal keys on the persisted `(name, worktree)` pair, per the design rule
  — not on the derived `repository` field.
- `find_owned` matches an exact resolved worktree path **first**, before any
  attempt to resolve the invoking repository, so path targeting keeps working
  from a non-repository cwd; name and branch matching then requires a
  non-null invoking identity.
- `pipeline.py` builds one named entry from `creation.common_dir`
  (`repository.py:336-343`) and hands that same object to the lineage-failure
  compensation.
- `tests/pipeline/test_reg.py:139-143` is rewritten deliberately: it asserts
  `_decode` raises `ValueError` on a corrupt registry, and a new required
  argument would otherwise make it fail before decoding, silently destroying
  its oracle.

### Slice C — cleanup safety and migration behavior

- `cleanup_repository_mismatch` enters `ERROR_CATALOG` **before** any code
  raises it (`T-OUT-14`, `PreconditionError`).
- Cleanup resolves the invoking common directory for name and branch lookup,
  keeps explicit paths global, requires the selected worktree's live common
  directory to equal its stored identity before planning, and removes
  `plan.entry` by its persisted pair. No null-identity exception.
- Migration probing runs before the lock, classifies per row (permanent
  negative → null; transient failure → unmigrated, disk unchanged), and
  re-probes v2 nulls.
- Behavioral tests, written first: the four repros; non-dry-run cleanup from
  repoE cannot touch repoF; **live-v1 cleanup by name removes worktree,
  branch, and row** (the migration-derived equality regression); a stale null
  row whose path is reused by an unrelated live worktree is refused;
  successful same-name cleanup in repo A leaves repo B's worktree, branch,
  and row intact; branch-scoped foreign lookup; exact-path priority when one
  entry's name equals another's worktree path; exact-path cleanup from a
  non-repository cwd; moved repository, moved-and-repaired linked worktree,
  and deleted parent common directory; broken row among live rows, git
  nonzero exit, `OSError` on process start, slow probe with another writer
  waiting, reader during v1→v2 replacement; raw v1 bytes unchanged after
  `read_registry` and `list`; bare repository identity; linked-worktree
  identity; `find_owned` with a null invoking identity cannot match null rows.

### Slice D — documentation, matrix, full gate

`REQUIREMENTS.md` and `README.md`: name and branch cleanup is scoped to the
invoking repository while a registered worktree path stays globally
addressable; lazy migration and the older-binary no-downgrade consequence;
the moved-repository limitation and its manual remedy. New `T-REG` rows in
`docs/testing/TEST-MATRIX.md` under G-REG. Note the stale-row gap against A7
per gate-6 routing.

**Gate 6 exit criteria.** `just all` green; the four repros pass as tests;
the non-dry-run containment test passes; the live-v1 cleanup regression test
passes; public `list` and `cleanup` payloads match their literal fixtures
with `repository` absent, and raw v2 rows carry it.

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

Round 2 review: pending.
