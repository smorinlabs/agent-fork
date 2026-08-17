# P02-A1 — Content-level fork verification

Design doc for P02 gate A1 per the P02 process (step 3). Tracks the item
from verification verdict through implementation sign-off.

| Gate | State |
|---|---|
| 1. Adversarial verification | **CONFIRMED-WITH-CORRECTIONS** (2026-08-16) |
| 3. Design doc | this document |
| 4. Plan + adversarial plan review (incl. Codex) | **APPROVE-WITH-CHANGES** (2026-08-16) — all changes incorporated below |
| 5. Implementation (TDD, subagent-driven) | not started |
| 6. Adversarial implementation review (incl. Codex) | not started |

## Verification verdict and evidence

**Claim (as registered):** the verify ladder compares only
`git status --porcelain=v1 -z` bytes (`verify.py:56-60`); content
mutations that preserve porcelain records pass verification.

**Empirical repro (Claude, 2026-08-16):** scratch repo, repo-local
`apply.whitespace = fix`, one unstaged change with trailing whitespace,
`agent-fork fork a1-probe --no-agent` (CLI 1.0.0). Result: parent sha256
`8734d513…`, child sha256 `8aee8d02…` (trailing whitespace stripped by
`git apply` during transport), identical ` M file.txt` porcelain in both
trees, exit 0, `"verification":{"enabled":true,"passed":true}`.

**Codex adversarial pass: CONFIRMED-WITH-CORRECTIONS.** Corrections and
sharpenings adopted into the finding:

- Equality covers complete porcelain records (status columns and paths),
  not merely a "status letter" — wording fixed; conclusion unchanged.
- No hidden content check exists in production; content-level oracles
  exist only in tests (`tests/conftest.py:413-451` raw-byte manifest,
  `tests/conftest.py:197-214` staged index modes/blob IDs) and the
  hostile-filter test covers only a status-*changing* filter
  (`A ` → `AM`, `tests/pipeline/test_ver.py:109-150`) — status-preserving
  divergence is untested.
- Repro is fair: the CLI forwards `os.environ` verbatim (`cli.py:667`)
  and `run_git` adds no config isolation, so user-global
  `apply.whitespace = fix` reaches the same `_apply_patch()` call;
  repo-local config merely made the repro hermetic.
- Sibling vectors capable of status-preserving divergence: idempotent
  clean/smudge filters where `clean(P) == clean(C)` with differing raw
  bytes; `core.autocrlf` round-trips; LFS pointer-vs-hydrated asymmetry
  under ambient `GIT_LFS_SKIP_SMUDGE=1`. Required-filter failures and
  non-idempotent filters that change status are already caught.
- Scope: in scope, not creep — README promises "every uncommitted file
  copied and verified" / "proves the copy is faithful"
  (README.md:3-5, 16-20, 223-232).

## Design

Five coordinated changes. Items 1–4 follow the Codex-recommended
combined design from gate 1; item 0 and the refinements marked *(plan
review)* come from the gate-4 APPROVE-WITH-CHANGES findings.

0. **Carried-state inventory** *(plan review)*. One immutable inventory
   captured in the parent **before worktree creation**, consumed by both
   materialization and verification as the single comparison domain. It
   contains: staged paths (both endpoints of renames; deletions as
   explicit tombstones), unstaged paths, paths with both staged and
   unstaged facets, intent-to-add paths, untracked files, and — only
   under `--with-ignored` — ignored files. Empty directories stay
   excluded (existing Git-visible contract); gitlinks are index-only and
   pruned from working-tree traversal (the `tests/conftest.py:413-435`
   oracle's rule). All membership filtering happens in Python on literal
   paths — never via raw pathspec operands, which would reproduce the
   registered A13-e pathspec fault. Inventory membership itself is
   compared parent-before vs parent-after and against the child, so a
   file appearing mid-fork (including an ignored one that today evades
   the non-ignored `parent-untouched` snapshot) is caught.
1. **Pin whitespace handling at the transport site.** `_apply_patch()`
   (`materialize.py`) gains `--whitespace=nowarn` so ambient
   `apply.whitespace` config can never rewrite transported hunks. One
   central site covers staged, intent-to-add, and unstaged paths.
2. **Staged-index rung.** Verify compares `git ls-files --stage -z`
   restricted to inventory paths — mode, blob OID, and stage — parent vs
   child, **and** parent-after vs the parent-before snapshot *(plan
   review: the parent index must be bracketed too — an `MM` path's index
   blob can move from A to B mid-fork while working bytes and porcelain
   hold still, which would evade child-vs-live-parent comparison)*.
3. **Working-tree manifest rung.** For inventory paths: existence and
   file type, mode, symlink target, and a streamed raw-byte SHA-256,
   parent vs child. Mode semantics are category-specific *(plan
   review)*: tracked paths compare Git's executable-bit semantics;
   copied untracked/ignored files compare full `stat.S_IMODE`, matching
   `_copy_entry()` (`materialize.py:43-57`, REQUIREMENTS.md:131).
4. **Parent bracketing.** The parent-before snapshot (inventory
   membership + staged index + working-tree manifest) is compared
   against parent-after. Status-preserving parent-side changes fail
   deterministically instead of silently verifying a moving target.
   *(Rollback-on-race ergonomics remain A5's concern; A1 only makes the
   comparison honest.)*

**Failure reporting** *(plan review)*: the stable top-level error code
`verify_failed` and exit 1 are preserved — rung labels are not new
`error.code` values. `content-match` appears once in the failure list
with component detail (index vs manifest, and the divergent paths
bounded), `parent-content` likewise; both ride in the message text plus
an additive, documented `error.details.failed_checks` field.
`parent-content` does not replace `parent-untouched`: the former covers
inventory-path content, the latter whole non-ignored porcelain and still
matters in `--no-with-state` (clean) mode. When one mutation trips
several rungs, all are reported (existing accumulate-and-report
behavior), with parent drift named as the primary cause when the
bracketing rung fires.

**Rejected alternatives** (gate 1 and gate 4): comparing `git diff`
output parent-vs-child (applies clean/EOL conversions, omits untracked
files); `git hash-object` without `--no-filters` (reintroduces the
filter blind spot); whole-worktree hashing (breaks the ~2 s budget —
inventory-only keeps cost proportional to what materialize touched);
size-bounded or skip-large hashing (silently weakens the promise);
a new `--no-verify-content` flag (the whole-ladder `--no-verify` escape
already exists, README.md:349-365).

Symmetric conversions — parent and child producing identical raw bytes
under identically-configured filters — verify as matching. That is
correct behavior, not a gap; raw-different-but-clean-equivalent files
are deliberate failures under this design.

## Implementation plan (TDD; subagent-driven)

Each step lands RED before its implementation lands GREEN. Fixture
discipline *(plan review)*: every negative fixture asserts the
same-porcelain precondition FIRST (proving the divergence is invisible
to the existing rung), then the intended index/manifest divergence, then
the exact new rung label and rollback — otherwise a fixture can go green
through `exact-copy-status` without proving the new rungs. Hostile
config is expressed as A1-local fixture helpers / tightly parameterized
variants of the sealed environment — not a general hostile-environment
tier (P02 out-of-scope boundary; the A1/A2 overlap stays as narrow as
the register allows).

1. **RED negative fixtures** (exact config + input bytes specified per
   fixture): (a) the `apply.whitespace=fix` repro as a pipeline test;
   (b) idempotent status-preserving clean-filter divergence;
   (c) `core.autocrlf=true` round-trip divergence; (d) staged blob/mode
   divergence; (e) parent working-tree edit mid-transport
   (status-preserving); (f) parent **index** swap mid-transport (`MM`
   path, blob A→B, porcelain unchanged); (g) one case per manifest
   dimension — existence/type, mode, symlink target, raw bytes.
2. **RED positive guards** (false-rollback protection — these must PASS
   verification): symmetric conversions; staged+unstaged same path;
   intent-to-add; rename; deletion; untracked; ignored under
   `--with-ignored`; exec-bit; gitlink (index-only). REQUIREMENTS.md:186-188.
3. **Whitespace pin.** `--whitespace=nowarn` in `_apply_patch()`;
   fixture (a) flips to faithful-transport GREEN.
4. **Inventory + rungs.** Implement the carried-state inventory in the
   pipeline (captured pre-create, threaded to materialize and verify);
   implement `content-match` and `parent-content` in `verify.py`;
   failure reporting per the design above. Fixtures (b)–(g) and the
   positive guards go GREEN.
5. **Performance gate** *(plan review)*: latency regression test on a
   representative repository asserting the fork budget (REQ-40,
   REQUIREMENTS.md:170-172) and slow-path progress coverage for large
   inventories. No size skips.
6. **Docs + conformance.** README "Safety and guarantees" / "How it
   works" state content verification; `error.details.failed_checks`
   documented as additive; TEST-MATRIX rows added.
7. **Gates.** `just all` green; adversarial implementation review
   (incl. Codex); real-agent smoke fork.

## Adversarial plan review (gate 4) — outcome

Codex verdict: **APPROVE-WITH-CHANGES** (2026-08-16). Blocking findings,
all incorporated above: (1) parent bracketing must include the staged
index, not the manifest alone; (2) "carried paths" must be one
immutable, literal-path-safe inventory with precise rename / deletion /
ITA / ignored / empty-dir / permission / gitlink rules, consumed by both
materialize and verify, with membership itself bracketed; (4) the ~2 s
budget claim needs a latency regression gate and slow-path progress, and
neither size-skips nor a content-only opt-out are acceptable; (5) keep
top-level `verify_failed` — rung labels go in message text plus an
additive `error.details.failed_checks`; (6) RED fixtures need
same-porcelain preconditions, exact bytes/config, the parent-index race
case, full manifest-field coverage, and positive false-rollback guards.
Non-blocking, also adopted: (3) failure-aggregation attribution defined;
(7) hostile config stays A1-local, not a general tier. No scope-creep
flag was raised; the four production changes were judged within A1.
