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

**Null-identity rows must stay cleanable.** A legacy row migrated with
`repository: null` would fail a naive live-versus-stored equality check, which
would make it uncleanable even by explicit path — recreating A7's dead-end
inside A3's own fix. The rule is therefore stated positively: a null-identity
row is unreachable by name or branch (that lookup requires a repository
identity to match, and null matches nothing), so it is reachable **only** by
explicit worktree path. For that path the containment check does not apply —
an explicit registered path is itself sufficient authorization, since a path
is globally unambiguous — and the identity is backfilled from the live probe
on the write that follows. Two null rows can never collide, because null is
never compared for equality.

**Two serialization contracts, deliberately separated.** `to_dict()`
(`models.py:77-85`) currently feeds both the on-disk registry and the public
`list --json` payload. The registry file moves to version 2; the public
output keeps `"version": 1`, which `tests/cli/test_reg.py:43-51` pins. These
are different contracts and a single constant must not drive both.

**Migration — lazy read-through, v2 written on the next mutation.**
`_decode` accepts versions 1 and 2 and keeps rejecting unknown ones. Each v1
row whose worktree still exists and is a valid git worktree is backfilled
with its resolved common directory. A row whose worktree is missing or
broken is preserved with `repository: null`: it stays visible to `list`,
which already reports `worktree_exists: false` deliberately
(`cli.py:1157-1162`), but it can never authorize a name or branch cleanup.
Read-only commands never write. The rewrite happens under the existing lock
on the next `add_entry` or exact removal. Two consequences are documented
rather than engineered around: rows already clobbered under v1 are
unrecoverable, and once a v2 write lands, older binaries reject the file.

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

**New error code.** `cleanup_foreign_repository`, exit 5, "cleanup target
belongs to another repository" — matching the existing `cleanup_*` refusal
family in `errors.py:33-47`, all of which refuse before an unsafe mutation.
The publishable-tier error catalog (REQ-38 / R7.12) is updated with it.

## Implementation plan (TDD; subagent-driven)

Failing tests land before each behavior change. Steps 2–6 are sequential —
each depends on the previous type or signature.

1. **Failing tests first — but only the ones that can exist yet.** Step 1 is
   split, because "all tests first" is not literally achievable here: the
   behavioral tests drive the CLI through a subprocess and depend on no
   internal signature, so they can be written and watched fail before any
   source change; the unit tests import types and signatures that do not
   exist until steps 2 and 3.
   - **1a (before step 2):** new `tests/pipeline/test_reg_scope.py` carrying
     the four live-git repros as two-repository rows under a shared
     `XDG_STATE_HOME`, following the `world.env` fixture shape in
     `tests/pipeline/test_reg.py`; plus the coverage Codex identified as
     missing — a **non-dry-run** assertion that cleanup invoked from repoE
     cannot remove repoF, exact-path cross-repository cleanup still
     permitted, linked-worktree identity (two worktrees of one repository
     share an identity), null-identity rows cleanable by path, and `list`
     showing duplicate names with the public JSON version unchanged.
   - **1b (with the step that introduces each signature):** unit tests for
     v1 rows with a live worktree migrating, v1 rows with a missing worktree
     surviving as `repository: null`, v2 rewrite on the next mutation,
     unknown versions still rejected, and lineage-write failure proving
     repoA's same-named row survives repoB's compensation.
2. **`models.py`** — append `repository: str | None = None` **last**, so
   existing positional construction is not silently rebound. Split
   registry-file serialization from the public result serialization that
   `list --json` consumes.
3. **`registry.py`** — on-disk version to 2; `_decode` accepts v1 and v2 and
   still rejects unknown; replacement identity `(repository, name)`; removal
   takes an exact entry; `find_owned` gains a required invoking-repository
   identity for name and branch matches while exact resolved worktree paths
   stay global; repository and worktree added to the sort key; migration and
   writes stay inside the existing lock and atomic replacement.
4. **`pipeline.py`** — construct one named `RegistryEntry` from
   `creation.common_dir` (already available, `repository.py:336-343`), add
   it, and hand that same object to the lineage-failure compensation at
   `pipeline.py:182` in place of the bare-name removal.
5. **`cleanup.py`** — resolve the invoking repository's common directory for
   name and branch lookup; keep explicit worktree-path targeting global;
   before building a plan, require the selected worktree's **live** common
   directory to equal its stored identity, raising
   `cleanup_foreign_repository` otherwise — except for a null-identity row
   targeted by explicit path, per the design rule above; remove `plan.entry`
   exactly at `cleanup.py:394`.
6. **`cli.py`** — no behavior change. Verify only that the public `list`
   payload still emits `"version": 1` after the registry constant moves to 2.
7. **Docs and matrix** — `errors.py` catalog entry; `REQUIREMENTS.md` and
   `README.md` state that name and branch cleanup is scoped to the invoking
   repository while a registered worktree path stays globally addressable,
   plus the lazy migration and its older-binary no-downgrade consequence;
   new `T-REG` rows in `docs/testing/TEST-MATRIX.md` under G-REG.

**Gate 6 exit criteria.** `just all` green; the four repros pass as tests;
the non-dry-run containment test passes; `tests/cli/test_reg.py:43-51`
unchanged and still green, proving the public output contract held.
