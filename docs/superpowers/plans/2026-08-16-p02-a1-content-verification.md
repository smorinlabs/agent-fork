# P02-A1 — Content-level fork verification

Design doc for P02 gate A1 per the P02 process (step 3). Tracks the item
from verification verdict through implementation sign-off.

| Gate | State |
|---|---|
| 1. Adversarial verification | **CONFIRMED-WITH-CORRECTIONS** (2026-08-16) |
| 3. Design doc | this document |
| 4. Plan + adversarial plan review (incl. Codex) | plan below; review pending |
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

Four coordinated changes (Codex-recommended combined design, adopted):

1. **Pin whitespace handling at the transport site.** `_apply_patch()`
   (`materialize.py`) gains `--whitespace=nowarn` so ambient
   `apply.whitespace` config can never rewrite transported hunks. One
   central site covers staged, intent-to-add, and unstaged paths.
2. **Staged-index rung.** New verify comparison: `git ls-files --stage -z`
   restricted to carried paths, parent vs child — mode, blob OID, and
   stage must match. Catches staged-content divergence without touching
   filters (blob OIDs compare the clean form on both sides).
3. **Working-tree manifest rung.** For carried paths only (staged,
   unstaged, untracked; ignored when `--with-ignored`): existence and
   file type, executable bit, symlink target, and a streamed raw-byte
   SHA-256, parent vs child. The test oracle at
   `tests/conftest.py:413-451` is the precedent; this puts the same idea
   in production `verify.py` as a `content-match` failure id.
4. **Parent manifest bracketing.** Capture the parent manifest once
   before worktree creation and compare parent-after against it, so a
   status-preserving parent-side change during transport fails as
   `parent-content` instead of silently verifying a moving target.
   (The *rollback-on-race* ergonomics remain A5's concern; A1 only makes
   the comparison honest.)

Rejected alternatives (from the adversarial pass): comparing
`git diff` output parent-vs-child (applies clean/EOL conversions, omits
untracked files); `git hash-object` without `--no-filters` (reintroduces
the filter blind spot); whole-worktree hashing (breaks the ~2 s fork
budget, REQUIREMENTS.md:170-173 — carried-paths-only keeps cost
proportional to what materialize already touched).

## Implementation plan (TDD; subagent-driven)

Each step lands RED before its implementation lands GREEN.

1. **RED fixtures.** Add a hostile-config fixture tier that deliberately
   unseals specific keys (`apply.whitespace=fix`; an idempotent
   status-preserving clean filter; `core.autocrlf=true`) — explicitly the
   A1/A2 overlap the P02 register allows; A1 takes only the fixture
   variants it needs. Tests: (a) the repro as a pipeline test asserting
   fork FAILS verification (or transports faithfully) rather than
   diverging silently; (b) status-preserving clean-filter divergence;
   (c) CRLF round-trip divergence; (d) staged blob/mode divergence;
   (e) parent-side status-preserving edit during transport.
2. **Whitespace pin.** `--whitespace=nowarn` in `_apply_patch()`; test
   (a) flips to faithful-transport GREEN.
3. **Verify rungs.** Implement `content-match` (index + manifest rungs
   over carried paths) and `parent-content` (bracketing) in `verify.py`;
   thread the carried-path set and the pre-create parent manifest through
   `pipeline.py`. Tests (b)–(e) go GREEN; failure ids surface in the
   documented verification-failure format with rollback + manual
   recovery guidance unchanged.
4. **Docs + conformance.** README "Safety and guarantees" and
   "How it works" updated to state content verification; error catalog
   gains the new failure ids if they are user-visible identifiers;
   TEST-MATRIX rows added for the new cases.
5. **Gates.** `just all` green; adversarial implementation review
   (incl. Codex); real-agent smoke fork.

## Risks and bounds

- Perf: hashing is carried-paths-only and streamed; large staged
  binaries were already fully buffered by materialize (A13-h tracks the
  memory issue; A1 must not make it worse — hash by streaming, never by
  reading whole files into memory).
- Symmetric conversions (parent and child both smudge to identical
  bytes) verify as matching — that is correct behavior, not a gap.
- The manifest rung must use `surrogateescape`/`os.fsdecode` path
  handling to match materialize on non-UTF-8 names.

## Adversarial plan review (gate 4)

Pending — Codex pass dispatched after this doc's first commit; outcome
recorded here.
