# P02-A6 — Submodules carried identically

Design doc for P02 gate A6 per the P02 process (step 3). Tracks the item from
verification verdict through implementation sign-off.

| Gate | State |
|---|---|
| 1. Adversarial verification | **CONFIRMED-WITH-CORRECTIONS** (2026-08-17) — matrix below; Codex second lens pending |
| 3. Design doc | this document |
| 4. Plan + adversarial plan review (incl. Codex) | pending |
| 5. Implementation (TDD, subagent-driven) | pending |
| 6. Adversarial implementation review (incl. Codex) | pending |

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

**Copy mode needs no verification exemption.** `exact-copy-status` and
`content-match` pass unmodified because the child genuinely reproduces the
parent. The `--ignore-submodules` work from matrix 1 survives as the semantics of
the opt-out path, not the default.

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

`=all` rather than `=dirty` for the opt-out: the user has explicitly declined to
carry submodules, so suppressing every submodule signal is coherent and the
opt-out never refuses a fork. The objection to `=all` — that it stops checking
the staged-gitlink case that works today — applies only to a default, not to an
explicit opt-out.

Interaction with `--with-state`: `--no-with-state` implies no submodule carry
(there is no state to carry); `--with-submodules` must not silently re-enable
state transport. Mirrors the existing `with_state` / `with_ignored` coupling at
`config.py:90-97`.

### The recipe, per gitlink, depth-first

1. **Skip what the parent left cold** — if `<parent>/<path>/.git` is absent, the
   child stays uninitialized. Cell `g`.
2. **Initialize from the parent's own checkout, never the remote:**
   `git -c protocol.file.allow=always -c submodule.<path>.url=<parent>/<path> submodule update --init -- <path>`
   Offline, and the only source guaranteed to hold commits the parent made
   locally and never pushed — which is what makes cell `c` carriable.
   `protocol.file.allow` is command-scoped for the path URL agent-fork computes
   itself; never ambient or global.
3. **Restore the remote:** `git submodule sync -- <path>` in the child. Without
   it the child's `origin` points at the parent's directory. Verified: origin
   returns to the `.gitmodules` URL.
4. **Match the checked-out commit:**
   `git -C <child>/<path> checkout --detach <parent submodule HEAD>`. This is what
   makes an unstaged gitlink advance representable.
5. **Reuse the existing transport verbatim:**
   `materialize(<parent>/<path>, <child>/<path>)`. Unmodified, it carried staged
   (cell `i`), unstaged (`a`, `f`, `h`), and untracked (`b`) state. A submodule is
   just another repository; this is structural reuse, not a second
   implementation.
6. **Recurse** for nested submodules. Depth 1 leaves the inner one cold.

### Constraints established by probe, and their resolution

- **`git worktree remove` refuses on a submodule-bearing worktree** —
  `fatal: working trees containing submodules cannot be moved or removed`, exit
  128. `--force` succeeds. **Already satisfied:** `rollback.py:73` and
  `cleanup.py:387` both pass `--force`. No change needed.
- **Cleanup verified end to end.** `agent-fork cleanup probe --yes` on a
  copy-mode child correctly refuses with `cleanup_dirty_worktree` (the child now
  holds a real uncommitted change), and
  `--allow-dirty --allow-unpushed` removed the worktree, deleted the branch, and
  cleared the registry at exit 0. **Documented behaviour change:** forks whose
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
   (`tests/conftest.py:168`) to express the eight cells (dirty variants,
   uninitialized-in-parent, nested, staged-in-own-index). Add G-MAT and G-VER
   rows for each cell × both modes to `docs/testing/TEST-MATRIX.md`, failing
   first.
2. **`submodules.py`** — the recipe and its recursion, taking `(parent, child,
   env)` and returning carried paths plus notices.
3. **Pipeline wiring** — run after `create_worktree_at_anchor`, before
   verification; thread the flag through `config.py`, `cli.py`, and the dry-run
   preview.
4. **Verification** — recursive rungs per carried submodule; opt-out exemption on
   `status_args` (`verify.py:106`) and the unstaged inventory listing
   (`content.py:158`). `pipeline.py:114` and `verify.py:150` are a matched pair
   for the `parent-untouched` rung: flag both or neither.
5. **Notices and JSON document** — `materialize.py:109`, `output.py:51`.
6. **`scripts/check_git_matrix.sh`** — copy-mode rows.
7. **Docs** — README, skill text, and the four prose copies of the recipe.

## Open items

- Codex second-lens review of both matrices and this design (process step 1 and
  gate 4).
- Unprobed: a submodule with a genuine **remote** URL (every cell used local
  paths — confirm step 2's URL override keeps it offline); recursion past depth
  1; `--with-ignored` interaction inside submodules; clone cost measured on a
  large submodule.
- Scope note: A6 closes as a **feature-shaped fix** by owner decision
  2026-08-17. The gate's scope language would otherwise route "carry submodules"
  to P03; the owner directed carry-by-default instead of the register's
  "verification exemption at minimum".
