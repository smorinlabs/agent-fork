# P02-A6 — Submodules carried identically

Design doc for P02 gate A6 per the P02 process (step 3). Tracks the item from
verification verdict through implementation sign-off.

| Gate | State |
|---|---|
| 1. Adversarial verification | **CONFIRMED-WITH-CORRECTIONS** (2026-08-17) — matrices below; Codex second lens returned CONFIRM-WITH-CORRECTIONS, findings 5 and 6 narrow the verdict wording |
| 3. Design doc | this document |
| 4. Plan + adversarial plan review (incl. Codex) | **NOT-READY on four passes, closed by owner decision 2026-08-21 rather than pursuing a fifth.** Passes 1–3 summarized below this table's history (see git log on this file for the full text of each). Pass 4, 2026-08-21, scoped to the steps-6/7/8 merge: four findings, all absorbed — see the pass-4 commit (`d8099b9`) for the full list. Across four passes, zero mechanism-level defects survived past pass 2; every pass-3 and pass-4 finding was plan-prose precision, not a design flaw, and two of those findings were introduced by the prior round's own fix rather than pre-existing — the pattern of diminishing severity plus doc-editing risk outweighing review value is why the owner stopped here. Remaining precision risk is deferred to gate 6, which caught real bugs on A6a's own two rounds and reviews actual code rather than prose describing code that does not yet exist. |
| 5. Implementation (TDD, subagent-driven) | **complete**, 2026-08-21 — all 8 steps plus a coverage-gap-closure pass, this branch; `just all`, `just check-matrix`, `just test-git-matrix` all green |
| 6. Adversarial implementation review (incl. Codex) | **round 1: REJECT** (2026-08-21, Codex) — 8 findings, all independently verified real by direct code reading and reproduction before any fix; absorbed. **round 2: REJECT** (2026-08-21, Codex) — 10 findings against the post-merge tree (branch merged with `origin/main`'s A3/A10/A11/A12 between rounds). 9 confirmed real by direct reproduction and absorbed (see commit for the full list); 1 (verify-before-setup-hook ordering, `pipeline.py`) confirmed real but classified as a pre-existing pattern `main`'s own top-level `finish()` already has identically — not an A6b regression, left as a candidate future item rather than fixed here. **Known accepted residual of finding 1's reasoned-skip fix:** a `=`-named submodule with genuine dirt (not just clean and initialized) still rolls back the whole fork — the reasoned skip correctly leaves it cold, but dirt cannot be carried into a checkout that stays cold, so `exact-copy-status` legitimately disagrees; the fork failing is arguably correct, only the surfaced explanation is poor (rung 6 is exempted, but the mismatch is caught by a different rung with no reference back to the `=`-in-name reason). Not fixed here; T-VER-50 only covers the clean case. **round 3: REJECT** (2026-08-21, Codex) — confirmation-scoped, not a full re-review. 9 of round 2's 10 items CONFIRMED-FIXED, finding 6 CONFIRMED as intentionally-not-fixed with its documentation accurate; finding 2's own fix (the `check_git_matrix.sh` trap) was found broken a SECOND time — the double-quoted bake-in avoided the local-scope problem but is itself unsafe if `$tmp` ever contains a single quote (possible via `$TMPDIR`), reproduced by the reviewer in its own environment (this session's sandbox pins `TMPDIR`, so the specific apostrophe scenario could not be reproduced locally and was accepted analytically). Re-fixed by changing idiom rather than patching the quoting: `tmp` is no longer `local`, so the trap goes back to a plain, safe, single-quoted `'rm -rf "$tmp"'` — no interpolation, no scope loss. Verified the trap fires and actually removes the directory on the exact `set -e`-mid-function exit path this whole finding is about (captured the printed path from a subprocess, confirmed it gone after that subprocess exited non-zero). Two low doc-text findings also absorbed: T-VER-44's matrix row described the pin's old, weaker contract rather than the flag's current unconditional one; T-MAT-60's docstring claimed newline coverage the fixture does not exercise (`git submodule add --name` rejects a literal newline outright). Round 4 pending, scoped narrowly to the trap fix (with an explicit ask to reproduce the apostrophe-`TMPDIR` case, since that reviewer's environment can) and confirming the two doc fixes — not a broader re-sweep. |

## Gate 4 — adversarial plan review, first pass

Codex returned **CONFIRM-WITH-CORRECTIONS**: gate 1 confirmed for the matrix-1
states, gate 4 not implementation-ready until findings 1–4 were corrected. Two
high findings were independently re-verified here on git 2.50.1 before being
accepted, because both change the design:

- **Finding 1 — `git submodule sync` in the child mutates the parent.** A linked
  worktree shares `.git/config` with its parent, and top-level `submodule sync`
  writes `submodule.<name>.url` into that shared file. Reproduced: a parent with
  a deliberate local mirror override at `submodule.libfoo.url=/tmp/deliberate-mirror`
  had it silently replaced by the `.gitmodules` URL when sync ran **in the
  child**; the shared config bytes changed. This would break agent-fork's
  parent-read-only invariant, and no existing rung checks configuration
  (`verify.py:106-153`).
- **Finding 2 — `submodule.<name>.update=none` exits 0 while leaving the child
  cold.** Reproduced: `submodule update --init` returned 0, printed nothing, and
  left `child/vendor/module/.git` absent, so a return-code check cannot tell
  success from a no-op. Adding `--checkout` initialized it, return code 0.

Disposition of all nine in-scope findings:

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 1 | high | `submodule sync` mutates the parent's shared config | absorbed — step 3 rewritten, no `sync` |
| 2 | high | init not pinned to checkout mode | absorbed — `--checkout` plus a positive gitdir assertion |
| 3 | high | no frozen recursive snapshot; can verify a mixed-time fork | absorbed — recursive snapshot before worktree creation |
| 4 | high | ambient submodule-ignore config differs parent vs child | absorbed — command-scoped semantic pins |
| 5 | medium | matrix 2 proves a manual prototype, not production | absorbed — verdict wording narrowed here and in the register |
| 6 | medium | captured matrix does not support the cleanup claim | absorbed — provenance corrected; the claim itself stands |
| 7 | medium | `--with-ignored` not threaded into recursion | absorbed — helper signature carries the modes |
| 8 | medium | opt-out `=all` contradicts "carry nothing" | absorbed — opt-out defined precisely |
| 9 | low | flag data-model surfaces omitted from the plan | absorbed — surfaces enumerated |
| 10 | medium | sparse checkout invisible to identity checks | routed to existing issue #31, not A6 |

## Verification verdict and evidence

Two probe matrices were run end to end against the installed console script
(`agent-fork fork probe --no-agent -o json`) in isolated worlds with sealed
environments (`XDG_STATE_HOME` redirected so the real registry is untouched).
Submodule fixtures were built with command-scoped
`-c protocol.file.allow=always`, matching `tests/conftest.py:642`.

### Matrix 1 — is the fault real?

| Cell | Parent state | Parent `git status` | Fork | Failing rungs |
|---|---|---|---|---|
| `e_clean` | clean submodule (control, = T-MAT-14) | *(clean)* | passes | — |
| `a_modified` | tracked file edited inside submodule | ` M vendor/module` | **fails, rolls back** | `exact-copy-status` + `content-match` |
| `b_untracked` | untracked file inside submodule | ` M vendor/module` | **fails, rolls back** | `exact-copy-status` |
| `c_newcommit_unstaged` | submodule advanced, gitlink unstaged | ` M vendor/module` | **fails, rolls back** | `exact-copy-status` + `content-match` |
| `d_newcommit_staged` | submodule advanced, gitlink staged | `M  vendor/module` | **passes** | — |
| `f_modified_plus_plainfile` | submodule dirt + ordinary dirty file | ` M tracked.txt`, ` M vendor/module` | **fails, rolls back** | `exact-copy-status` + `content-match` |

Captured failure (`a_modified`, stderr):

```json
{"error":{"code":"verify_failed","details":{"failed_checks":[{"check":"content-match",
"differences":[{"detail":"no longer carried","kind":"membership","path":"vendor/module"},
{"detail":"staged entry missing","kind":"staged","path":"vendor/module"}],"primary":true,
"total":2}]},"message":"verification failed: exact-copy-status, content-match ..."}}
```

**Corrections to the register entry:**

1. **Two rungs fail, not one.** The entry names only `exact-copy-status`. The
   `content-match` rung added by P02-T01 also fails: `collect_inventory`
   (`content.py:158`) resolves unstaged paths with
   `git diff --name-only --no-renames`, which lists `vendor/module` whenever the
   submodule has modified content or new commits. The path enters the carried
   set, transport cannot carry a gitlink's working tree, and verification reads
   it as "no longer carried". A status-only exemption would not have made the
   fork succeed. The entry predates that rung.
2. **"Unforkable by default" is too broad.** Cell `d` passes today — a submodule
   advance staged in the parent travels in the `diff-index --cached -p` patch and
   the child reproduces `M  vendor/module` exactly. The fault is confined to
   submodule **working-tree** state.
3. **Rollback is clean.** Every failing cell left no branch, no worktree, and an
   untouched parent.
4. **`--no-verify` succeeds and silently drops the state.** The child's submodule
   directory is empty; in cell `f` the ordinary file transports while the
   submodule's changes vanish.
5. **The notice is misleading, as the entry claimed.** Passing runs emit
   `submodules copied opaquely: vendor/module` (`materialize.py:109`) while the
   child's submodule directory is empty. Nothing was copied.

### Matrix 2 — can submodules be carried identically?

Owner decision 2026-08-17: **carry submodules identically by default, with a flag
to opt out.** This matrix tests feasibility. Each cell forks with `--no-verify`,
applies the recipe below by hand, then compares parent-vs-child status at both
levels.

| Cell | Parent state | Top level | Inside the submodule |
|---|---|---|---|
| `a_modified` | file edited in submodule | match — ` M vendor/module` | match — ` M sub-tracked.txt` |
| `b_untracked` | untracked file in submodule | match | match — `?? scratch.txt` |
| `c_newcommit_unstaged` | submodule advanced, gitlink unstaged | match | match |
| `d_newcommit_staged` | submodule advanced, gitlink staged | match — `M  vendor/module` | match |
| `f_modified_plus_plainfile` | both kinds of dirt | match — both lines | match |
| `g_uninit_in_parent` | parent deinitialized the submodule | match — clean both sides | n/a (correctly skipped) |
| `h_nested` | submodule containing a submodule | match | match (inner left cold at depth 1) |
| `i_staged_in_sub_index` | change staged in the submodule's own index | match | match — `M  sub-tracked.txt` |

**Scope of this verdict, narrowed after gate 4 (findings 5 and 6).** What matrix
2 proves is: *eight local, depth-1, status-comparison cells matched under a
manual prototype.* It ran the shipped CLI with `--no-verify` and then applied the
recipe by hand; it never called `verify_fork`, never exercised production
recursion, and its URL override was keyed by path — which every fixture masked
because name equalled path throughout. Copy mode is **feasible**, not yet
**proven in production shape**. Findings 2 and 4 are states outside the eight
cells where the first recipe or unchanged verification would have failed.

**Copy mode is expected to need no verification exemption** — `exact-copy-status`
and `content-match` should pass unmodified because the child reproduces the
parent — but that holds only with the semantic pins added under finding 4 below.
The `--ignore-submodules` work from matrix 1 survives as the semantics of the
opt-out path, not the default.

## Re-validation against main, 2026-08-20

The branch was rebased onto `origin/main` after **51 commits** landed —
including the `refactor/src-duplication` consolidation (PR #53), A9 (PR #43),
A13's targeted remediations (PR #49), A8 closed will-not-fix, P05's session
transcript work, and version consolidation. Build on the rebased branch:
`just all` green, **511 passed, 1 skipped** (was 430). What that changed for A6:

**The fault is unchanged.** Matrix 1 re-run against the rebased build
(`agent-fork 1.2.0`) reproduces byte for byte: the same four cells fail and roll
back, the same two pass, every `stderr` string is identical to the 2026-08-17
capture, and passing runs still emit `submodules copied opaquely: vendor/module`
over an empty directory. Nothing in 51 commits touched the behaviour A6 targets.

**Every cited call site survives; line numbers drifted.** `status_args`
`verify.py:106` → **`verify.py:103`**; the `parent-untouched` capture
`verify.py:150` → **`verify.py:146`**; the cleanup status probe
`cleanup.py:185` → **`cleanup.py:170`**. Unmoved: `pipeline.py:114`,
`content.py:158`, `materialize.py:109` (notice), and the forced worktree
removals at `rollback.py:73` and `cleanup.py:393`. Semantics unchanged in all of
them, so the design's reasoning holds.

**One new hard requirement: A13's pathspec doctrine** (see recipe step 2).
`materialize` now passes `:(literal)` and `:(exclude,literal)` operands, and
`content.py:8-10` documents the rule. A6's recipe hands recorded submodule paths
back to Git and predates it. Reproduced over-match, and the resulting divergence
is invisible to verification.

**Two structural changes to fold into implementation.** `_worktree_pairs`
(`verify.py`) and `_worktrees` (`cleanup.py`) now delegate to the new
`worktree_list.list_worktrees`, and the worktree-list rung compares
`creation.path.resolve()`. Recursive verification should read worktrees through
that helper rather than re-parsing porcelain.

**Ordering and neighbours.** A5 (parent race, skip-with-notice) is still open, so
the `parent-untouched` interactions this design assumes are still against
unmodified code — but A6 now runs ahead of A3, A5, and A7. A8 closed
**will-not-fix**, so no plan-token/immutable-plan remedy is coming from that
item: A6's recursive snapshot has to stand on its own, which is how it is
already specified. `just all` now runs `sync_versions.py --check`, so this PR
must not touch version literals.

**Nothing in the re-validation invalidates the design.** The gate-4 corrections
stand, the flag decision stands, and the recipe changes by one prefix.

## Split into A6a and A6b (owner decision 2026-08-20)

Two gate-4 passes returned NOT-READY. Neither faulted the carry mechanism — that
matched on 8 of 8 cells at first attempt. Both faulted integration: how pins
reach recursive calls, what the snapshot must freeze, what order to build in.
Carry-by-default is a feature-sized change inside a project chartered for
minimal remediation, and it must satisfy five invariants at once, four of them
built by other items for other reasons (A1's frozen inventory domain, A2's
config-injection sanitizer, A13's pathspec doctrine, the parent-read-only rule,
and A8's will-not-fix leaving no shared plan-token mechanism).

The work therefore splits, mirroring the `P02-T13` umbrella convention:

| | A6a — unblock | A6b — carry identically |
|---|---|---|
| Solves | The repository is unforkable | The submodule's work is not carried |
| Change | `--ignore-submodules` filtering at three sites, accurate notice | Full recipe, recursive snapshot, `config_pins`, recursive verification |
| Evidence | Validated 2026-08-17 against real child worktrees | Manual prototype only, 8 local depth-1 cells |
| Gate 4 | Waived — evidence measured, not reasoned (see "Open items" below) | See the gate-4 row in the table at the top of this document for current status |
| Size | Days | The eight-step plan below |

The owner's carry-by-default decision is unchanged: `--with-submodules` remains
the default when A6b ships. Only the sequencing changed, so that users stop
being blocked while A6b gets the review depth two passes say it needs.

**A6a's handling of the unstaged-gitlink-advance case** (matrix 1 cell `c`,
which `--ignore-submodules=dirty` deliberately still reports) was the one open
owner decision at split time. It is resolved in "All three blocking decisions
are resolved" below: a typed `submodule_unrepresentable` refusal, shipped in
A6a and gated on submodules not being carried, so A6b removes the limitation
rather than inheriting it.

## Re-validation against A6a's shipped code, 2026-08-21

A6a merged (`origin/main` at `9956f4a`) since this design was last touched. Its
actual implementation is more specific than what this design's "opt-out" row
assumed, and the difference changes what A6b needs to build.

**What A6a actually shipped, unconditionally, with no flag gating it:**

- `--ignore-submodules=dirty` at three sites — `verify.py:114` (status
  comparison), `content.py:245` (unstaged inventory listing), `cli.py:551`
  (dry-run preview) — plus `repository.py:269` inside the unrepresentable-check.
- `content.py` gained real infrastructure this design doc does not mention:
  `gitlink_paths()` (shared submodule enumeration), `parse_porcelain_status()`
  (rename-safe porcelain parsing — gate-6 pass 2 found the naive slice
  fabricates paths from rename source records), and `suppressed_submodules()`
  (a **per-status-code** comparison between `--ignore-submodules=none` and
  `=dirty`, not the membership-set comparison this design doc never specified
  and would have gotten wrong the same way the first attempt did).
- `materialize.py`'s notice is `submodule_loss_notices()`, built on
  `suppressed_submodules()`.
- `repository.py`'s `validate_fork_guards(..., with_state=True)` raises
  `submodule_unrepresentable` whenever an unstaged, modified (not deleted, not
  conflicted) gitlink exists and `with_state` is true. **No `with_submodules`
  parameter exists yet** — there is nothing else to gate it on.

**Consequence for this design's "Flag" table.** The row
`--no-with-submodules | ... | \`--ignore-submodules=all\` on both status calls
and the unstaged inventory listing` is **superseded**. Building fresh `=all`
filtering for the opt-out would discard the precision A6a already shipped —
the per-status-code comparison that catches a submodule both staged and dirty
at once, and the rename-safe parser. **A6b's opt-out path is not new code**:
it is A6a's already-shipped, already-reviewed behavior, gated behind
`with_submodules=False` instead of being unconditional. Concretely:

- `verify.py:114`, `content.py:245`, `cli.py:551` — the existing
  `--ignore-submodules=dirty` call becomes conditional
  (`if not with_submodules`); when `with_submodules` is true, these sites drop
  the filter entirely (strict comparison, no exemption, per this design's
  existing "Verification: unchanged; strict, no exemption" cell — that cell
  was already correct, just not yet wired to a flag because the flag doesn't
  exist).
- `repository.py`'s guard condition changes from "fires whenever `with_state`"
  to "fires whenever `with_state` and not `with_submodules`" — matching the
  docstring already in the code (`repository.py:254-256`: "A6b removes this
  limitation for the default path... this guard must not fire").
- `materialize.py`'s `submodule_loss_notices()` becomes conditional the same
  way: called under `with_submodules=False`; under `with_submodules=True` a
  successful carry either emits nothing or a distinct "carried" notice, not
  this one.

**This does not change the recipe** (init, name/path resolution, offline URL
override, remote restoration, recursive snapshot, `config_pins`) — that part
of the design was never about A6a's code and is unaffected. It changes
implementation plan **step 6**: "gate the four existing
`--ignore-submodules=dirty` call sites and the existing guard condition on the
new flag" rather than "add new `=all` filtering", which was never built and
should not be. Step 6 below reflects this; the earlier draft did not.

## Design

### Flag

`--with-submodules` / `--no-with-submodules`, default enabled (owner decision
2026-08-17). Chosen over a valued `--submodules {copy,skip}` because its
neighbours are the state-carrying flags `--with-state` and `--with-ignored`, not
the mode-selecting `--agent` / `-o`. It joins `_BOOL_KEYS` (`config.py:30`) as
config key `with_submodules`, and appears in the JSON document beside
`with_state` and `with_ignored` (`output.py:51`).

| Mode | Carry | Verification |
|---|---|---|
| `--with-submodules` (default) | init + recursive transport per the recipe | strict, no exemption — the four sites below drop their filter |
| `--no-with-submodules` | working-tree state stays cold and uncarried; a staged gitlink advance still transports (it always did, via the ordinary staged-patch path) | **A6a's already-shipped behavior, gated rather than rebuilt** (see "Re-validation against A6a's shipped code" above): `--ignore-submodules=dirty` at `verify.py`, `content.py`, `cli.py`, `repository.py`'s guard; `suppressed_submodules()` names what was not carried |

**The opt-out is "do not initialize or carry submodule working trees" — not
"carry nothing"** (finding 8). Blanket `--ignore-submodules=all` would overstate
it: a submodule advance *staged in the parent* still travels in the
`diff-index --cached` patch and still appears in the staged inventory, so it is
carried whether or not porcelain reports it. Hiding it would mean verification
stops checking state the fork actually transported. Precisely:

- top-level **staged gitlink** state stays carried and content-verified;
- submodule **working-tree** state is neither initialized nor carried, and is
  suppressed in the parent-vs-child comparison;
- before filtering, the hidden submodule paths and their state classes are
  inventoried so the notice can name exactly what was dropped, rather than
  falling silent — **this is exactly what `suppressed_submodules()` already
  does**, comparing per status code rather than path membership so a submodule
  both staged and dirty is not missed;
- the `parent-untouched` bracket stays **unfiltered** — it is a different
  comparison (parent before vs parent after), and filtering it would hide a
  clean-to-changed gitlink transition occurring during the fork. This bracket
  (`pipeline.py:119`, `verify.py:158`) is not gated by `with_submodules` either
  way, matching what A6a already does.

Interaction with `--with-state`: `--no-with-state` implies no submodule carry
(there is no state to carry); `--with-submodules` must not silently re-enable
state transport. Mirrors the existing `with_state` / `with_ignored` coupling at
`config.py:90-97`.

### The recipe, per gitlink, depth-first

0. **Resolve name → path.** A submodule's config *name* is not its *path*; they
   coincide only by convention. Probed 2026-08-17:
   `git submodule add --name libfoo <url> vendor/module` yields
   `[submodule "libfoo"] path = vendor/module`, config key `submodule.libfoo.url`,
   and module dir `.git/modules/libfoo`. Read the map with
   `git config -f .gitmodules --get-regexp 'submodule\..*\.path'` and key every
   config override by **name**, while every pathspec uses the **path**. Keying by
   path would silently fail to override a renamed submodule's URL, sending step 2
   to the remote and losing the offline guarantee — and, for cell `c`, sending it
   somewhere the unpushed commit does not exist.
1. **Skip what the parent left cold** — if `<parent>/<path>/.git` is absent, the
   child stays uninitialized. Cell `g`.
2. **Initialize from the parent's own checkout, never the remote:**
   `git -c protocol.file.allow=always -c submodule.<name>.url=<parent>/<path> submodule update --init --checkout -- :(literal)<path>`
   **The `:(literal)` prefix is required** (re-validation 2026-08-20, inherited
   from A13's pathspec doctrine, which landed after this plan was written —
   `content.py:8-10` now states that recorded paths must never be handed back to
   Git as bare pathspec operands). Reproduced on git 2.50.1: a parent holding
   submodules `vendor/x*` and `vendor/xy`, with `vendor/xy` deliberately
   deinitialized, ran `submodule update --init --checkout -- vendor/x*` in the
   child and initialized **both** — the child gained a populated submodule the
   parent keeps cold, and `git status` reported clean on both sides, so no rung
   would catch it. The `:(literal)` form initialized only the target. Every
   pathspec operand in this recipe takes the same treatment.
   Offline, and the only source guaranteed to hold commits the parent made
   locally and never pushed — which is what makes cell `c` carriable.
   `protocol.file.allow` is command-scoped for the path URL agent-fork computes
   itself; never ambient or global. **`--checkout` is required** (finding 2):
   with `submodule.<name>.update=none` the command otherwise exits 0 having done
   nothing, so a return-code check cannot detect the no-op. Assert
   `<child>/<path>/.git` exists before any later step runs.
3. **Point the child's own remote at the real URL — never `git submodule sync`**
   (finding 1). The child is a linked worktree sharing `.git/config` with the
   parent, so top-level `sync` writes `submodule.<name>.url` into the *parent's*
   configuration and destroys any deliberate local override there. Reproduced on
   git 2.50.1. Instead: read the parent submodule's effective
   `remote.origin.url` **before** the fork (it is already resolved, including for
   relative `.gitmodules` URLs), and set only
   `git -C <child>/<path> config remote.origin.url <that value>`, which lives in
   the child's private submodule git dir. Restoring anything beyond the origin
   URL — custom fetch refspecs, `submodule.<name>.active` — is a separate
   configuration-fidelity decision, deliberately out of scope here and stated as
   such in the notice.
4. **Match the checked-out commit:**
   `git -C <child>/<path> checkout --detach <parent submodule HEAD>`. This is what
   makes an unstaged gitlink advance representable.
5. **Reuse the existing transport — through one added seam, not verbatim:**
   `materialize(<parent>/<path>, <child>/<path>, with_state=…, with_ignored=…, inventory=<frozen>)`.
   Unmodified, it carried staged (cell `i`), unstaged (`a`, `f`, `h`), and
   untracked (`b`) state. A submodule is just another repository; this is
   structural reuse, not a second implementation. **"Verbatim" was wrong, and it
   collided with the semantic pins below** (gate-4 re-review 2026-08-20):
   `materialize` builds its own Git argv internally and has no way to receive
   command-scoped `-c` flags, and the environment escape hatch is deliberately
   closed — `run_git` routes every call through `without_config_injection`
   (`git.py:20-47`), which strips `GIT_CONFIG_COUNT`, `GIT_CONFIG_KEY_*`,
   `GIT_CONFIG_VALUE_*`, and `GIT_CONFIG_PARAMETERS` as A2's fix. Hijacking the
   preserved `GIT_CONFIG_GLOBAL` instead is rejected: it would replace the
   user's configuration wholesale, which is the divergence A2 exists to prevent.
   The resolution is an explicit pins parameter at the chokepoint —
   `run_git(..., config_pins=())` prepending `-c k=v`, threaded through
   `materialize`, `collect_inventory`, `capture_state`, and the recursive
   verification calls. One implementation still, one new argument.
   **The modes must be threaded**
   (finding 7): `materialize` defaults `with_ignored=False`
   (`materialize.py:112-120`), so a helper taking only `(parent, child, env)`
   cannot honour a top-level `--with-ignored` — an ignored file inside a
   submodule would be silently dropped, or transported and then false-failed by
   verification, depending on which side forgot the flag.
6. **Recurse** for nested submodules, carrying the frozen plan for that depth.
   Depth 1 leaves the inner one cold.

### The recursive snapshot (finding 3)

The whole pipeline rests on resolving carried state **once, before the worktree
exists**, so transport and verification share one fixed domain
(`content.py:134-144`, `pipeline.py:113-129`). Submodules break that if carry
reads live state afterwards: a gitlink contributes only its index entry to the
top-level inventory, and its working tree is deliberately excluded from the
manifest (`content.py:195-207`), so inner bytes can change from A to B between
`create_worktree_at_anchor` and submodule carry while every top-level bracket —
status, inventory, manifest, `compare_states` — reports no difference. The helper
would then copy the later state and verification would compare against that same
later state: a fork that verifies against a moment that never existed as a whole.

Therefore: **before creating the worktree**, walk the parent recursively and
freeze one plan per submodule — name↔path map, initialized-or-cold, HEAD, the
**resolved `remote.origin.url`** (finding 4: recipe step 3 reads this "before
the fork," and the frozen plan is the only thing that runs at that moment, so
it is where the value must live — a helper that reads it afterward would be
reading mutable parent configuration, the exact hazard step 3 exists to
avoid), the carried inventory, the content state, and the nested plan beneath
it. Carry and verification both consume that frozen plan; the parent is
rechecked recursively after carry, extending the existing `parent-untouched`
bracket one level down.
A deterministic race test belongs in the matrix: mutate inner dirty bytes between
creation and carry while the top-level status record is unchanged, and require
the fork to fail rather than pass.

### Semantic pins on recursive commands (finding 4)

Local configuration inside the parent's submodule is not cloned into the child's
copy, so identical nested working trees can be *reported* differently on the two
sides. Reproduced at depth 2: with `diff.ignoreSubmodules=all` set inside the
parent's outer submodule, the parent read clean while the child read
` M vendor/outer` for byte-identical state. Every recursive status, inventory,
and diff call therefore runs with command-scoped `-c diff.ignoreSubmodules=none`
plus an explicit `--ignore-submodules=none` where the command accepts it. Those
pins reach the recursive calls through the `config_pins` parameter added in
recipe step 5 — there is no environment channel for them, by A2's design. The
matrix gains rows for `diff.ignoreSubmodules`, `submodule.<name>.ignore`,
`submodule.recurse`, and `status.submoduleSummary` set in repository
configuration — none of these may be assumed to hold their defaults or to be
cloned.

**Implementation-time finding (2026-08-21, during the coverage audit
preceding gate 6), corrected by gate 6 itself.** `SEMANTIC_PINS` originally
shipped with only `diff.ignoreSubmodules`, applied to `carry_submodules` and
`verify_submodules` but NOT to `snapshot_submodules`'s own internal
`collect_inventory`/`capture_state` calls. The coverage-audit pass verified
the `-c` pin loses to a command-line `--ignore-submodules` flag and to a
per-submodule `submodule.<name>.ignore` config value (matching this
section's own original warning), but concluded from that alone that the gap
was "real but currently inert" because `snapshot_submodules`,
`carry_submodules`, and `verify_submodules` all independently enumerate
submodules via `.gitmodules`/the index, not via the vulnerable
`collect_inventory` call. **That conclusion was wrong.** Gate 6 (finding 2)
found the actual failure mode: with ambient `diff.ignoreSubmodules=all` set
inside a submodule's own config and its inner submodule genuinely advanced,
the UNPINNED snapshot's `plan.content` never recorded the advance, while
carry (pinned) correctly transported it and verify (pinned) correctly
detected it in the child — producing a false "newly carried" verification
failure for a submodule carry did exactly the right thing on. The domain
mismatch, not enumeration, was the real risk; the audit's own end-to-end
test never actually drove the full snapshot→carry→verify pipeline, only the
`collect_inventory` primitive directly, which is why it missed this. Fixed
by threading `SEMANTIC_PINS` into `_snapshot_one`'s calls too, and — since
the same masking can make the child's freshly-initialized submodule and the
parent's own ambiently-configured one report genuinely different raw
`git status` output even with correctly-carried content — into
`pipeline.py`'s and `verify.py`'s own top-level `collect_inventory`/
`capture_state`/status calls whenever submodules are carried. `T-VER-46` is
the regression, driving the real pipeline. `submodule.recurse` was not
independently probed and remains an open, disclosed risk.
`status.submoduleSummary` only affects git's human-readable long-format
summary text, not `--porcelain` output, so it cannot affect any
machine-parsed call agent-fork makes.

### Recursive verification (finding 2)

"Add recursive rungs" named a requirement without specifying what a rung
checks. That gap is real: two forks can agree on every top-level signal —
status, inventory, `compare_states` — while a submodule inside them is
verifiably wrong. Concretely: the parent's submodule sits at commit `Q`; the
carry step in the child detaches it at the wrong commit, `R`, because the
frozen snapshot or the checkout step has a bug. Top-level `git status` on both
sides still reads ` M vendor/module` (or clean, if the top-level gitlink itself
is unstaged either way) — nothing at the top level distinguishes `R` from `Q`.
Without a rung that inspects the submodule's own HEAD, this ships silently.

A rung is one check, scoped to one carried submodule, each independently
triggerable by an injected defect so a test can prove the rung — not just the
happy path — actually runs:

1. **Initialized/cold parity** — the child is initialized if and only if the
   frozen snapshot recorded the parent as initialized (cell `g`'s guarantee,
   now checked rather than assumed).
2. **HEAD identity** — `git -C <child>/<path> rev-parse HEAD` equals the
   frozen snapshot's recorded parent submodule HEAD, exactly. This is the rung
   that would have caught the `Q` vs `R` example above.
3. **Detached state** — the child's submodule HEAD is detached, not attached
   to a branch that could later diverge from the pinned commit.
4. **Status parity** — `git -C <child>/<path> status --porcelain=v1` (under
   the same semantic pins as capture) matches the frozen snapshot's recorded
   parent-submodule status, the same comparison `verify_fork` already runs at
   the top level, recursed one level.
5. **Content parity** — the frozen inventory and content state for that
   submodule (staged, unstaged, untracked, per recipe step 5's transport)
   verify against the child exactly as `content-match` does at the top level.
6. **Nested-plan completeness** — every submodule the frozen plan recorded at
   this level has a corresponding rung result; a submodule present in the plan
   but silently skipped during carry is a failure, not an omission.
7. **Recursive parent-untouched** — after carry, the *parent's* submodule at
   this path is rechecked against its own pre-fork snapshot, extending the
   top-level `parent-untouched` bracket one level down, so carry cannot be the
   thing that dirties the parent's submodule checkout.

Recursion applies rungs 1–7 at each nested level the frozen plan reaches
(finding `h`'s depth-1 case, generalized). A failure at any rung is a
structured `Difference` scoped to that submodule's path, same shape as the
top-level `content-match` differences, so `error.details.failed_checks` stays
one flat, addressable list regardless of nesting depth.

**Implementation-time note on rungs 4+5 (2026-08-21, before gate-6 round 2).**
Rungs 4 and 5 above are described as two separate comparisons, the first a
raw `git status --porcelain=v1` string match. The shipped implementation
(`verify_submodules`, `src/agent_fork/submodules.py`) does not run that raw
comparison; it reuses the same structural `compare_states(plan.content,
child_content)` the top-level `content-match` rung already runs, one level
down, folding 4 and 5 into a single call. This is a deliberate
implementation choice, not an oversight: `compare_states` compares
`ls-files --stage` index entries (which carry unmerged conflicts as distinct
per-stage entries, not the porcelain `UU` marker) and per-path manifest
digests, and is already exercised and trusted at the top level, so reusing
it here avoids a second parallel parsing path. The accepted residual gap is
whatever a raw porcelain line would show that this structural comparison
would not — chiefly porcelain's own rename markers (`R  old -> new`), which
`compare_states`'s `--no-renames`-derived model reports instead as a
delete-of-old plus add-of-new; the practical difference is presentation, not
missed detection, since both forms flag the same path pair as changed. This
note supersedes the "same comparison ... recursed one level" framing above
and the gate-6 absorption commit's characterization of this area.

Test rows: inject each defect independently — wrong HEAD, cold when it should
be warm, attached instead of detached, dirty content, a plan entry silently
skipped, a parent submodule mutated by carry — and require the fork to fail
with the rung that defect maps to, not just "something failed."

### Constraints established by probe, and their resolution

- **`git worktree remove` refuses on a submodule-bearing worktree** —
  `fatal: working trees containing submodules cannot be moved or removed`, exit
  128. `--force` succeeds. **Already satisfied:** `rollback.py:73` and
  `cleanup.py:387` both pass `--force`. No change needed.
- **Cleanup behaves correctly, but not on the evidence first cited here**
  (finding 6). `agent-fork cleanup probe --yes` on a copy-mode child refuses with
  `cleanup_dirty_worktree` (the child now holds a real uncommitted change), and
  `--allow-dirty --allow-unpushed` removes the worktree, deletes the branch, and
  clears the registry at exit 0. That was observed in a separate hand-run world
  and independently reproduced during gate 4 — **it is not what
  `matrix2-results.json` captured**, because `cleanup_probe` in `a6_probe2.py`
  force-removes the worktree before invoking `agent-fork cleanup`, so the JSON
  records `agent_fork_cleanup_rc: 1` and a missing directory for every cell. The
  probe cells that replace it (plan step 1) must give raw removal, refusal, and
  override-success their own child worlds, and assert registry removal plus no
  residue under `.git/worktrees/<child>/modules`. **Documented behaviour change:** forks whose
  submodules were dirty now require those overrides at cleanup time, where
  previously the state did not exist to object to.
- **Cost.** Each carried submodule is cloned into the child. A local clone from
  the parent's path hardlinks objects, so the cost is a working-tree copy, not a
  full object copy; a large vendored submodule still makes forks slower. The
  child's module git dir lands at
  `<parent>/.git/worktrees/<child>/modules/<path>`.
- **Git-version variance.** Worktree + submodule behaviour has moved across git
  releases; copy-mode rows belong in `scripts/check_git_matrix.sh`.

### Notices

- **Copy mode — still to build.** State what was carried; no such notice exists
  yet, since `submodule_loss_notices()` (`materialize.py:84`) only ever names
  what was *not* carried.
- **Opt-out — already shipped by A6a**, gated behind `with_submodules=False`
  under the "Flag" table above rather than built here:
  `submodule_loss_notices()` names what was not carried.
- Depth: when a nested submodule is left cold, say so rather than implying full
  recursion — still to build, part of the copy-mode notice above.

## Implementation plan (TDD; subagent-driven)

**Ordering rule** (gate-4 re-review 2026-08-20, revised 2026-08-21 after gate-4
pass 3 found the revision itself unsafe). The first draft activated recursive
carrying at step 4, before its flag and verifier existed. The second draft
split the fix across three steps — gate the old protection (6), wire the new
protection (7), fix the notice (8) — which reintroduced the same defect in
miniature: between steps 6 and 7, the default path had *neither* protection.
Splitting a change that must land together is what created both holes, so the
fix is the same both times: **the four pieces that must change together —
gating A6a's existing filters/guard off, wiring carry on, adding recursive
verification, and gating the notice — are now one step**, not three. Every step
before it stays inert exactly as before; that step is the *only* one where the
default (`with_submodules=True`) behaviour changes, and its own tests must all
land green together, in one commit — no intermediate commit within it may leave
the default path less protected than before the step started.

1. **Test rows first.** Extend the `submodule()` state constructor
   (`tests/conftest.py:168`) to express the nine cells (dirty variants,
   uninitialized-in-parent, nested, staged-in-own-index, and
   `j_renamed_submodule` where the config name differs from the path), **plus
   the seven axes finding 3 found scheduled nowhere**: a genuine remote URL
   (not a local path — proves recipe step 3's offline override actually
   engages rather than being masked by every prior fixture using a path
   already), a relative `.gitmodules` URL, a configured
   `submodule.<name>.update` policy (`none`, matching finding 2's original
   repro), depth-2 dirt, ambient ignore configuration (`diff.ignoreSubmodules`,
   `submodule.<name>.ignore`, `submodule.recurse`, `status.submoduleSummary`,
   per "Semantic pins" above), ignored-file state inside a submodule
   (`--with-ignored` interaction), and the deterministic mixed-time race from
   "The recursive snapshot" above (mutate inner dirty bytes between creation
   and carry while the top-level status record is unchanged; the fork must
   fail). Sixteen cells total. Add G-MAT and G-VER rows for each cell × both
   modes to `docs/testing/TEST-MATRIX.md`, failing first. **No later step may
   complete while any of these sixteen lacks a row** — this replaces the
   "Cells the matrix still owes" bullet in Open items below, which is now
   satisfied by this list rather than left unscheduled.
2. **`config_pins` at the chokepoint** — `run_git(..., config_pins=())`
   prepending `-c k=v`, threaded through `materialize`, `collect_inventory`, and
   `capture_state`. Enabling primitive; no caller passes pins yet, so behaviour
   is unchanged. This is what the semantic pins ride on, and it is why transport
   reuse is "one added argument" rather than verbatim.
3. **Flag through the whole data model** (finding 9) — not just `config.py` and
   `cli.py`: `ConfigValues` and `ResolvedConfig` (`models.py:11-33`), or
   `load_config`'s `ConfigValues(**fork)` raises `TypeError` on a config file
   that sets it (`config.py:157-162`) and `_coerce_source` silently drops an
   unknown mapping key (`config.py:41-51`); `ForkRequest` (`pipeline.py:35-46`);
   the dry-run preview; `ForkOutput` and its JSON mode object
   (`output.py:26-57`); config get/set/show; completion and help text. The flag
   is inert until step 6. Add precedence tests for `--no-with-state` against
   every explicit and configured `with_submodules` value.
4. **Recursive snapshot** — resolve the frozen submodule plan in the parent
   before `create_worktree_at_anchor`, alongside the existing inventory and
   status bracket (`pipeline.py:113-129`, the capture itself at `:119`). Read-only:
   computed and returned,
   not yet consumed.
5. **`submodules.py`** — the recipe and its recursion, taking the frozen plan
   plus `with_state` / `with_ignored` / `config_pins` / `env`, and returning
   carried paths, skipped paths, and notices. Unit-tested directly; not yet
   called by the pipeline.
6. **Activation — the one step where default behaviour changes, landed as one
   commit.** Four things happen together; none is meaningful alone. Exact
   predicates (gate-4 pass 4 finding 1 — the merge stated the relationship in
   prose but never pinned the booleans an implementer actually writes):

   | | Condition |
   |---|---|
   | A6a's existing protection (guard + three filters) | `with_state and not with_submodules` |
   | Carry, and recursive verification | `with_state and with_submodules` |
   | `with_state=False` | neither fires, matching A6a's existing carve-on — no state carried, nothing to protect or carry (`repository.py`'s docstring on `with_state`) |

   - **Gate A6a's existing protection off for the carrying path.**
     `--ignore-submodules=dirty` at `verify.py:114`, `content.py`'s unstaged
     listing (~line 245), `cli.py:551`, and the guard condition in
     `repository.py`'s `validate_fork_guards` (currently `if with_state`, per
     `repository.py:346-348`) all ship unconditionally-on-`with_state` today.
     Change each to `with_state and not with_submodules` — **and**, not a bare
     replacement of the existing condition.
   - **Wire carry on**, gated on `with_state and with_submodules`. Consume the
     frozen plan (step 4) through the recipe (step 5), which returns carried
     paths, skipped paths, and notices; carry after `create_worktree_at_anchor`,
     before verification. The sixteen cells from step 1 flip from red to
     green here — not nine; step 1 was expanded by finding 3's absorption.
   - **Add the seven recursive verification rungs** specified under "Recursive
     verification" above, gated on the same `with_state and with_submodules`
     condition. Rung 6, nested-plan completeness, needs **both** inputs from
     the two bullets above — the frozen plan (every submodule that should have
     been carried) and the carry step's own `skipped paths` return value
     (which ones actually were) — a rung that reads only the frozen plan
     cannot detect a submodule the carry step silently skipped, which is
     exactly the failure this rung exists to catch (gate-4 pass 4 finding 2).
   - **Gate the notice, and restore what old step 8 specified before the
     merge compressed it away** (gate-4 pass 4 finding 3): `output.py`'s
     `ForkOutput` JSON document carries the notices produced here, same as any
     other notice; `submodule_loss_notices()` (`materialize.py:84`) stays the
     opt-out message, now conditional on `with_state and not with_submodules`;
     the new "what was carried" notice (the "Copy mode — still to build"
     bullet under "Notices" above) fires on a successful carry and **must
     state the configuration-fidelity limit from recipe step 3** — only
     `remote.origin.url` is restored, not fetch refspecs or
     `submodule.<name>.active`.

   `pipeline.py:119` and `verify.py:158` — the `parent-untouched` rung — stay
   unfiltered on both sides throughout, unconditionally, matching what A6a
   already does; this rung is not part of the four and does not change here.

   Because these four land together, **no reviewed or merged commit boundary**
   has a submodule protection gap (gate-4 pass 4 finding 4 — the earlier
   wording, "no point inside this step," was false: the bullets above are
   listed by concern, not by build order, and gating old protection off before
   carry and verification exist is a real, permitted mid-step WIP state).
   TDD's own discipline gives the safe internal order for free: write the
   red tests for carry, recursive verification, and the new notice first;
   implement and turn them green while the old protection is still active
   (both protections briefly coexist, which is safe — belt and suspenders,
   never a gap); only then flip the guard/filter condition to exclude
   `with_submodules`, confirm every test in the sixteen-cell matrix (step 1)
   is green under both flag values, and make one commit.
7. **`scripts/check_git_matrix.sh`** — copy-mode rows against both system Git
   and Flox Git, covering at minimum the `submodule.<name>.update=none`
   variance from finding 2's original repro; worktree/submodule interaction has
   already shown version-dependent behaviour once (finding 3's `--force`
   requirement). **Clone-cost measurement, bounded**: fork a fixture with one
   large submodule (≥50k objects or equivalent), record wall-clock delta versus
   a no-submodules fork of the same parent size, and record the number as a
   comment in this script — no numeric gate, since one data point is not a
   regression budget, but a silent "acceptable" was finding 3's complaint and
   an unrecorded number is the same failure in a different shape.
8. **Docs** — README, skill text, and the four prose copies of the recipe.

## Open items

**All three blocking decisions are resolved (owner, 2026-08-20).**

1. **Cell `c` — the unstaged gitlink advance — gets a typed refusal.**
   `PreconditionError` raised in `validate_fork_guards` before any filesystem or
   ref mutation, exit 5, naming the remedy. **The refusal is conditional, not
   permanent** (owner question, same date): matrix 2 shows this case forks
   correctly under copy mode — parent and child both read ` M vendor/module` and
   the child's submodule HEAD matches the parent's — because the child has a
   real submodule checkout to represent the advance. So the guard fires only
   when submodule working trees are *not* being carried. In A6a that is always;
   after A6b it is exactly the `--no-with-submodules` path. Two consequences for
   implementation: the guard must be written against a "submodules not carried"
   condition rather than unconditionally, so A6b gates it instead of deleting
   it; and its message must not imply the limitation is permanent. A6b extends
   the remedy list to include "let it be carried, which is the default".
2. **A6b stays in P02** as the second half of the A6 umbrella. A6 closes when
   both halves merge.
3. **A6a's gate-4 adversarial pass is waived.** Its change is three call sites
   plus a notice and a guard, on evidence measured against real child worktrees
   rather than reasoned. Gate 6 — adversarial review of the implementation — is
   unchanged and still applies. A6b's gate-4 review continues until a pass
   returns clean; see the gate table at the top of this document for the
   current pass count and outcome of each.


- **Gate 4 — additional pass required before implementation starts.** Current
  status, live in the gate table above; do not hardcode a pass number here
  (this bullet has drifted stale three times already from doing so). Pass 3
  completed the audit the second pass's lost report could not: all nine
  first-pass findings individually re-verified, eight confirmed genuinely
  absorbed and one (8) reopened and fixed. Each pass since has required its
  report as its final message, never a file — the loss that made pass 3's
  audit necessary in the first place must not recur.
- ~~Cells the matrix still owes~~ — **superseded**: these seven axes are now
  required rows in implementation plan step 1, not a bullet with no owner.
- The gate's probe scripts are session scaffolding, not repository artifacts;
  their permanent encoding is the test rows in plan step 1. Those rows must
  carry finding 6's correction (separate child worlds for raw removal, refusal,
  and override success) and must call the production helper and `verify_fork`
  rather than comparing status strings by hand.
- Clone cost measured on a large submodule, not just reasoned.
- Gate-4 targeted checks that produced no finding, recorded so they are not
  re-probed: name-keyed override initialized offline against an unreachable
  HTTPS `.gitmodules` URL; a relative `../module.git` URL initialized from the
  parent checkout (so the notice should say the *resolved* URL); explicit
  `-- <path>` initialized even with `submodule.<name>.active=false` or an
  excluding `submodule.active` pathspec; a shallow parent submodule produced a
  shallow child; a manual depth-2 carry with differing names at both levels
  matched at all three levels, and forced removal left no orphaned
  `modules/<outer>/modules/<inner>` tree.
- **Routed out of A6:** sparse checkout in a parent submodule makes the child
  hold a tracked file the parent omits, invisible to both status and carried-path
  verification (finding 10). This is the broader content-domain gap already at
  issue #31, not dirty-submodule carry. A6's wording is narrowed to "reproduces
  the selected submodule working-tree changes" accordingly.
- Scope note: A6 closes as a **feature-shaped fix** by owner decision
  2026-08-17. The gate's scope language would otherwise route "carry submodules"
  to P03; the owner directed carry-by-default instead of the register's
  "verification exemption at minimum".
