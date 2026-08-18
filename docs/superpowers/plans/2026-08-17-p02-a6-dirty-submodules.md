# P02-A6 — Submodules carried identically

Design doc for P02 gate A6 per the P02 process (step 3). Tracks the item from
verification verdict through implementation sign-off.

| Gate | State |
|---|---|
| 1. Adversarial verification | **CONFIRMED-WITH-CORRECTIONS** (2026-08-17) — matrices below; Codex second lens returned CONFIRM-WITH-CORRECTIONS, findings 5 and 6 narrow the verdict wording |
| 3. Design doc | this document |
| 4. Plan + adversarial plan review (incl. Codex) | **NOT IMPLEMENTATION-READY** on first pass (2026-08-17) — nine findings, four high; all absorbed below; **re-review required before gate 5** |
| 5. Implementation (TDD, subagent-driven) | blocked on gate 4 re-review |
| 6. Adversarial implementation review (incl. Codex) | pending |

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
| `--with-submodules` (default) | init + recursive transport per the recipe | unchanged; strict, no exemption |
| `--no-with-submodules` | nothing; submodule directories stay cold | `--ignore-submodules=all` on both status calls and the unstaged inventory listing; notice names what was not carried |

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
  falling silent;
- the `parent-untouched` bracket stays **unfiltered** — it is a different
  comparison (parent before vs parent after), and filtering it would hide a
  clean-to-changed gitlink transition occurring during the fork.

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
   `git -c protocol.file.allow=always -c submodule.<name>.url=<parent>/<path> submodule update --init --checkout -- <path>`
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
5. **Reuse the existing transport verbatim:**
   `materialize(<parent>/<path>, <child>/<path>, with_state=…, with_ignored=…, inventory=<frozen>)`.
   Unmodified, it carried staged (cell `i`), unstaged (`a`, `f`, `h`), and
   untracked (`b`) state. A submodule is just another repository; this is
   structural reuse, not a second implementation. **The modes must be threaded**
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
carried inventory, the content state, and the nested plan beneath it. Carry and
verification both consume that frozen plan; the parent is rechecked recursively
after carry, extending the existing `parent-untouched` bracket one level down.
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
plus an explicit `--ignore-submodules=none` where the command accepts it. The
matrix gains rows for `diff.ignoreSubmodules`, `submodule.<name>.ignore`,
`submodule.recurse`, and `status.submoduleSummary` set in repository
configuration — none of these may be assumed to hold their defaults or to be
cloned.

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

- Copy mode: state what was carried, replacing the misleading "copied opaquely"
  (`materialize.py:109`) — the current text fires while the child's directory is
  empty.
- Opt-out: name what was not carried.
- Depth: when a nested submodule is left cold, say so rather than implying full
  recursion.

## Implementation plan (TDD; subagent-driven)

1. **Test rows first.** Extend the `submodule()` state constructor
   (`tests/conftest.py:168`) to express the nine cells (dirty variants,
   uninitialized-in-parent, nested, staged-in-own-index, and
   `j_renamed_submodule` where the config name differs from the path). Add G-MAT
   and G-VER rows for each cell × both modes to `docs/testing/TEST-MATRIX.md`,
   failing first.
2. **Recursive snapshot** — resolve the frozen submodule plan in the parent
   before `create_worktree_at_anchor`, alongside the existing inventory and
   status bracket (`pipeline.py:113-129`).
3. **`submodules.py`** — the recipe and its recursion, taking the frozen plan
   plus `with_state` / `with_ignored` / `env`, and returning carried paths,
   skipped paths, and notices.
4. **Pipeline wiring** — carry after `create_worktree_at_anchor`, before
   verification, consuming the frozen plan.
5. **Flag through the whole data model** (finding 9) — not just `config.py` and
   `cli.py`: `ConfigValues` and `ResolvedConfig` (`models.py:10-44`), or
   `load_config`'s `ConfigValues(**fork)` raises `TypeError` on a config file
   that sets it (`config.py:181-202`) and `_coerce_source` silently drops an
   unknown mapping key (`config.py:40-50`); `ForkRequest` (`pipeline.py:35-46`);
   the dry-run preview; `ForkOutput` and its JSON mode object
   (`output.py:26-57`); config get/set/show; completion and help text. Add
   precedence tests for `--no-with-state` against every explicit and configured
   `with_submodules` value.
6. **Verification** — recursive rungs per carried submodule with the semantic
   pins; opt-out filtering on `status_args` (`verify.py:106`) and the unstaged
   inventory listing (`content.py:158`), leaving the staged path carried.
   `pipeline.py:114` and `verify.py:150` are a matched pair for the
   `parent-untouched` rung: that bracket stays unfiltered on both sides.
7. **Notices and JSON document** — `materialize.py:109`, `output.py:51`;
   including the structured loss notice for the opt-out and the
   configuration-fidelity limit from step 3 of the recipe.
8. **`scripts/check_git_matrix.sh`** — copy-mode rows.
9. **Docs** — README, skill text, and the four prose copies of the recipe.

## Open items

- **Gate 4 re-review required before implementation starts.** The first pass
  found the plan not implementation-ready; findings 1–9 are absorbed above but
  the corrected design has not itself been reviewed.
- Cells the matrix still owes, per finding 5, before "production feasible" may be
  claimed: renamed submodule with a genuine **remote** URL; relative
  `.gitmodules` URL; a configured `submodule.<name>.update` policy; depth-2 dirt;
  ambient ignore configuration; ignored-file state inside a submodule; and the
  deterministic mixed-time race from finding 3.
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
