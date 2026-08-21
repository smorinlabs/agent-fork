# CONFIRM-WITH-CORRECTIONS

Gate 1 confirms the shipped A6 fault for the matrix-1 states, but the copy-mode
feasibility and cleanup claims are broader than their captured evidence. Gate 4
is not implementation-ready until findings 1-4 are corrected.

## Findings in scope for A6

### 1. [high] `git submodule sync` mutates the parent repository's shared configuration

**Claim challenged.** “Restore the remote: `git submodule sync -- <path>` in
the child. Without it the child's `origin` points at the parent's directory.
Verified: origin returns to the `.gitmodules` URL.”
(`docs/superpowers/plans/2026-08-17-p02-a6-dirty-submodules.md:135-137`)

**Why it is wrong.** A linked worktree and its parent use the same common
`.git/config`. At the top level, `git submodule sync` writes
`submodule.<name>.url` into that shared file. The command therefore changes the
parent's configuration while appearing to operate in the child. Neither
`exact-copy-status` nor `parent-content` checks configuration
(`src/agent_fork/verify.py:106-153`). `sync` also restores only URL-related
configuration: it did not reproduce a custom parent-submodule fetch refspec in
the child.

**Concrete failing scenario.** On Git 2.50.1, a parent had
`.gitmodules: submodule.libfoo.url=https://127.0.0.1:9/acme/module.git` and an
intentional local mirror override:

```text
$ git -C parent config submodule.libfoo.url /tmp/module-source
$ git -C child submodule sync -- vendor/module
$ git -C parent config --get submodule.libfoo.url
https://127.0.0.1:9/acme/module.git
```

The command replaced the parent's `/tmp/module-source` override. In a second
run, the parent submodule had both the normal heads refspec and
`+refs/changes/*:refs/remotes/origin/changes/*`; the initialized and synced child
retained only the normal heads refspec. The command-scoped initialization URL
itself did not persist, so the residue is caused by `sync`, not by `-c`.

**Smallest fix.** Do not run `git submodule sync` in the linked top-level
worktree. Capture the intended remote URL before creation—preferably the
parent submodule's effective `remote.origin.url`, which is already resolved for
relative `.gitmodules` URLs—and set only the child submodule's own
`remote.origin.url`. Add a before/after byte comparison of the parent's local
`submodule.*` configuration. Narrow “restore the remote” to the exact fields
the implementation restores; copying arbitrary remote refspecs is a separate
configuration-fidelity decision.

### 2. [high] Initialization is not pinned to checkout mode and can succeed while leaving the child cold

**Claim challenged.** “Initialize from the parent's own checkout, never the
remote: `git ... submodule update --init -- <path>`” and then operate on the
initialized repository (`docs/superpowers/plans/2026-08-17-p02-a6-dirty-submodules.md:129-143`).

**Why it is wrong.** `git submodule update` honors
`submodule.<name>.update`. The recipe does not override that policy. With
`update=none`, Git exits 0 after printing “Skipping submodule”, so a return-code
check cannot distinguish success from a still-uninitialized path. Other
non-checkout update policies are likewise outside the recipe's intended
detached-checkout semantics.

**Concrete failing scenario.** On a linked child with an explicit path and the
correct name-keyed local URL override:

```text
$ git -C parent config submodule.libfoo.update none
$ git -C child -c protocol.file.allow=always \
    -c submodule.libfoo.url=/tmp/parent/vendor/module \
    submodule update --init -- vendor/module
Skipping submodule 'vendor/module'
$ echo $?
0
```

`child/vendor/module/.git` was absent. Repeating the command with `--checkout`
returned 0 and initialized the submodule.

**Smallest fix.** Add `--checkout` to the initialization command. Test at least
`update=none` and one non-checkout update policy, and assert the expected child
gitdir exists before sync, checkout, or materialization.

### 3. [high] The plan has no immutable recursive snapshot, so it can verify a mixed-time fork

**Claim challenged.** “Copy mode needs no verification exemption ... the child
genuinely reproduces the parent”
(`docs/superpowers/plans/2026-08-17-p02-a6-dirty-submodules.md:83-86`), with
submodule carry scheduled only after worktree creation
(`docs/superpowers/plans/2026-08-17-p02-a6-dirty-submodules.md:186-194`).

**Why it is wrong.** The current pipeline snapshots only the top-level status,
inventory, and carried state before creation
(`src/agent_fork/pipeline.py:113-129`). A gitlink in that inventory contributes
its index entry, but its working tree is deliberately excluded from the
manifest (`src/agent_fork/content.py:195-207`). The proposed submodule helper
would therefore read each submodule's live HEAD, index, and working tree after
the child exists. If the parent changes in that interval without changing its
top-level porcelain bytes, the helper can copy the later state and recursive
verification can compare against that same later state.

**Concrete failing scenario.** In a parent whose submodule already had a dirty
tracked file, changing the inner bytes from one dirty value to another produced:

```text
top-level status before = b' M vendor/module\0'
top-level status after  = b' M vendor/module\0'
top-level inventory     = unstaged=('vendor/module',)
top-level manifests     = () before and after
compare_states(...)     = ()
```

Thus a change from content A to content B between
`create_worktree_at_anchor` and submodule carry is invisible to every existing
top-level bracket.

**Smallest fix.** Before creating the worktree, recursively capture one frozen
submodule plan: name/path mapping, initialized/cold state, HEAD, index, carried
inventory, content state, and nested plan. Use that same data for carry and
verification, pass each frozen inventory to `materialize`, and recursively
recheck the parent after carry. Add a deterministic race test that changes
dirty inner bytes while preserving the top-level status record.

### 4. [high] Ambient submodule-ignore configuration can make exact copy fail verification

**Claim challenged.** “`exact-copy-status` and `content-match` pass unmodified”
(`docs/superpowers/plans/2026-08-17-p02-a6-dirty-submodules.md:83-85`) and copy
mode uses “unchanged; strict, no exemption” verification
(`docs/superpowers/plans/2026-08-17-p02-a6-dirty-submodules.md:99-102`).

**Why it is wrong.** Local configuration inside a parent submodule is not
cloned as repository configuration. Git status and diff can therefore interpret
identical nested working-tree state differently in parent and child. The
current status command has no semantic config pin
(`src/agent_fork/verify.py:106-113`), and the inventory's unstaged listing is an
ambient `git diff` (`src/agent_fork/content.py:148-160`).

**Concrete failing scenario.** A depth-2 fixture had the same dirty
`inner.txt` bytes in parent and child. Before configuration changes, top,
outer, and inner status all matched. Then:

```text
$ git -C parent/vendor/outer config diff.ignoreSubmodules all
$ git -C parent status --porcelain=v1
<clean>
$ git -C child status --porcelain=v1
 M vendor/outer
```

Inside the outer repositories, the parent was clean and the child reported
` M deps/inner`. Running Git with command-scoped
`-c diff.ignoreSubmodules=none` exposed the nested change consistently.

**Smallest fix.** Pin the copy-mode semantics on every recursive status,
inventory, and diff call—for example, command-scoped
`diff.ignoreSubmodules=none` plus explicit `--ignore-submodules=none` where the
command supports it. Add rows for `diff.ignoreSubmodules`,
`submodule.<name>.ignore`, `submodule.recurse`, and
`status.submoduleSummary`; do not rely on those settings having defaults or
being cloned.

### 5. [medium] Matrix 2 proves a manual local prototype, not production copy mode or its verification

**Claim challenged.** The register says copy mode is “proven feasible and
offline across eight cells, needing no verification exemption”
(`projects/P02-agent-fork-fault-remediation.md:187-191`). The design similarly
concludes that verification passes unmodified
(`docs/superpowers/plans/2026-08-17-p02-a6-dirty-submodules.md:65-86`).

**Why it is unproven.** The probe first runs the shipped CLI with
`--no-verify`, then modifies the child by hand
(`a6-evidence/a6_probe2.py:7-15,120-140`). It compares status strings, but never
calls `verify_fork` or the proposed production recursion. Its URL override is
keyed by `path`, not config name (`a6-evidence/a6_probe2.py:51-80`), and every
matrix fixture happens to use the same name and path
(`a6-evidence/matrix2-results.json:9-20`). The nested cell records an inner
gitlink but deliberately leaves it cold. The document itself admits that remote
URLs, depth greater than 1, and ignored state were unprobed
(`docs/superpowers/plans/2026-08-17-p02-a6-dirty-submodules.md:199-206`).

**Concrete failing scenario.** With config name `libfoo`, path
`vendor/module`, and an unreachable HTTPS `.gitmodules` URL, the probe's
path-keyed override attempted HTTPS and failed. The corrected name-keyed
override initialized offline. Findings 2 and 4 are additional states outside
the eight cells where the claimed recipe or verification fails.

**Smallest fix.** Rewrite the verdict as: “Eight local, depth-1/status-only
manual prototype cells matched.” Extend the rerunnable probe to call the
production helper and complete verification after implementation. Add a
renamed submodule with a genuine remote URL, relative URL, configured update
policy, depth-2 dirt, ambient ignore config, and ignored-file state before
claiming production feasibility or unchanged verification.

### 6. [medium] The captured probe does not support the claimed end-to-end cleanup result

**Claim challenged.** “Cleanup verified end to end ... `--allow-dirty
--allow-unpushed` removed the worktree, deleted the branch, and cleared the
registry at exit 0”
(`docs/superpowers/plans/2026-08-17-p02-a6-dirty-submodules.md:150-160`).

**Why it is unproven by the supplied evidence.** `cleanup_probe` first runs
plain `git worktree remove`, then force-removes the child, and only then invokes
`agent-fork cleanup` (`a6-evidence/a6_probe2.py:148-185`). It never invokes the
claimed override command. The raw result consequently records force-removal
success, `child_still_exists: false`, and `agent_fork_cleanup_rc: 1` with “No
such file or directory” (`a6-evidence/matrix2-results.json:26-33`).

**Concrete failing scenario.** Re-running `a6_probe2.py` reproduced
`cleanup_rc=1` in all eight cells. A corrected, separate run did verify the
runtime behavior: cleanup without overrides returned
`cleanup_dirty_worktree`; cleanup with both overrides returned 0, removed the
branch/worktree, and left no worktree administrative entries. That later run is
not the captured matrix.

**Smallest fix.** Give raw `git remove`, refusal, and override-success checks
separate child worlds, recapture the JSON, and assert registry removal plus no
residue under `.git/worktrees/<child>/modules`. The source claims about
`--force` are correct (`src/agent_fork/rollback.py:65-82` and
`src/agent_fork/cleanup.py:360-394`); a fully initialized depth-2 scratch case
also left no administrative module dirs after forced removal.

### 7. [medium] The recursive plan drops `--with-ignored` semantics inside submodules

**Claim challenged.** Copy mode promises “recursive transport per the recipe”
(`docs/superpowers/plans/2026-08-17-p02-a6-dirty-submodules.md:99-102`), but the
planned helper accepts only `(parent, child, env)`
(`docs/superpowers/plans/2026-08-17-p02-a6-dirty-submodules.md:186-187`).

**Why it is incomplete.** `materialize` defaults `with_ignored=False`
(`src/agent_fork/materialize.py:112-120`) and copies ignored entries only when
that value is true (`src/agent_fork/materialize.py:186-196`). A recursive helper
without mode inputs cannot honor top-level `--with-ignored`. If recursive
verification also omits the flag, the file is silently lost; if verification
uses it, the fork false-fails after transport.

**Concrete failing scenario.** A tracked submodule `.gitignore` ignores
`local.cache`, and the parent submodule contains that file. Run
`agent-fork fork ... --with-ignored` under the planned helper signature. The
default inner `materialize(parent_sub, child_sub, env=env)` does not enumerate
or copy `local.cache`.

**Smallest fix.** Thread `with_state`, `with_ignored`, and the frozen recursive
inventory through submodule carry and verification. Add depth-1 and depth-2
ignored-file positive tests and opt-out negative tests.

### 8. [medium] The opt-out contract hides commit-level state and contradicts “carry nothing”

**Claim challenged.** Opt-out leaves directories cold and uses
`--ignore-submodules=all`; suppressing “every submodule signal is coherent” so
the fork never refuses
(`docs/superpowers/plans/2026-08-17-p02-a6-dirty-submodules.md:99-108`).

**Why it is incomplete.** `=all` hides both working-tree dirt and commit-level
gitlink changes from porcelain. Yet the plan exempts only the unstaged
inventory listing (`docs/superpowers/plans/2026-08-17-p02-a6-dirty-submodules.md:191-194`): the staged patch and staged inventory still carry and verify a staged
gitlink. Thus “nothing” is not the actual behavior. Applying `=all` to the
parent-untouched bracket would also hide a clean-to-changed gitlink transition
during the fork.

**Concrete failing scenario.** In the supplied matrix worlds:

```text
c_newcommit_unstaged: default=' M vendor/module'; ignore-all='<clean>'
d_newcommit_staged:   default='M  vendor/module'; ignore-all='<clean>'
```

The staged-name listing still contains `vendor/module` for cell `d`, while the
unstaged-name listing contains it for cell `c`.

**Smallest fix.** Define opt-out precisely as “do not initialize or carry
submodule working trees”; keep top-level staged gitlink state carried and
content-verified. Before filtering, inventory the hidden submodule paths and
state classes for a structured loss notice. Keep the parent-untouched bracket
unfiltered and distinct from parent-versus-child opt-out comparison.

### 9. [low] The implementation plan omits required flag data-model surfaces

**Claim challenged.** The flag “joins `_BOOL_KEYS` ... and appears in the JSON
document” (`docs/superpowers/plans/2026-08-17-p02-a6-dirty-submodules.md:90-97`),
while the plan says to thread it through `config.py`, `cli.py`, and the pipeline
(`docs/superpowers/plans/2026-08-17-p02-a6-dirty-submodules.md:186-195`).

**Why it is incomplete.** `ConfigValues` and `ResolvedConfig` define every
resolved flag (`src/agent_fork/models.py:10-44`), `_coerce_source` discards
mapping keys absent from `ConfigValues` (`src/agent_fork/config.py:40-50`),
`ForkRequest` carries the runtime modes (`src/agent_fork/pipeline.py:35-46`),
and `ForkOutput` owns the JSON mode object (`src/agent_fork/output.py:26-57`).
Editing only the named modules can produce a config-file load failure, a flag
that is silently dropped during source coercion, or a value that never reaches
carry/verification.

**Concrete failing scenario.** Add `with_submodules` only to `_FORK_KEYS` and
`_BOOL_KEYS`, then load `[fork] with_submodules=false`. `load_config` constructs
`ConfigValues(**fork)` (`src/agent_fork/config.py:181-202`), so the missing
dataclass field raises `TypeError`. A mapping-based flag source instead reaches
`_coerce_source`, which silently omits the unknown field and leaves runtime
behavior at the default.

**Smallest fix.** Enumerate `models.py`, `ForkRequest`, dry-run output,
`ForkOutput`, config get/set/show, completion/help, and their tests as explicit
plan surfaces. Add precedence tests for `--no-with-state` with every explicit
or configured `with_submodules` value.

## Findings that belong to a different item or existing issue

### 10. [medium, existing issue #31] Sparse checkout remains invisible to the claimed identity checks

**Claim challenged.** “The child genuinely reproduces the parent”
(`docs/superpowers/plans/2026-08-17-p02-a6-dirty-submodules.md:83-85`).

**Why this is not an A6 implementation finding.** A parent submodule using
sparse checkout omitted a tracked `excluded/file.txt`; the locally initialized
child had the file. Both internal porcelain statuses were clean and both dirty
name inventories were empty. This is the broader sparse-checkout/content-domain
gap already routed to issue #31 (`projects/P02-agent-fork-fault-remediation.md:57-66`),
not a failure unique to dirty-submodule carry.

**Concrete failing scenario.** Configure sparse checkout in the parent
submodule to omit a tracked directory, then initialize the child from that
parent checkout. The parent lacks the file, the child contains it, and status
plus current carried-path verification report no difference.

**Smallest fix.** Narrow the A6 wording to “reproduces the selected submodule
working-tree changes” and cross-link issue #31. Resolve clean tracked checkout
shape, including sparse patterns, in that issue rather than expanding A6.

## Targeted checks that did not produce another finding

- The correct name-keyed command-scoped URL override initialized offline when
  `.gitmodules` held an unreachable HTTPS URL. A path-keyed override failed, so
  the design's name/path correction at
  `docs/superpowers/plans/2026-08-17-p02-a6-dirty-submodules.md:115-126` is
  necessary and correct.
- A relative `../module.git` URL initialized from the parent checkout; sync
  changed the child submodule origin to its resolved absolute remote path. The
  offline step works, but “returns to the `.gitmodules` URL” should say
  “returns to the resolved `.gitmodules` URL.”
- Explicit `submodule update ... -- <path>` still initialized when either
  `submodule.<name>.active=false` or an excluding `submodule.active` pathspec was
  configured.
- A genuinely shallow parent submodule initialized from its local checkout and
  produced a shallow child. A `.gitmodules` `shallow=true` hint against a
  non-shallow local source initialized successfully but Git ignored depth for
  the local clone.
- A manual fully initialized depth-2 carry, including config names different
  from paths at both levels, matched top, outer, and inner status. Plain removal
  failed as documented; forced removal deleted the nested
  `modules/<outer-name>/modules/<inner-name>` administrative tree with no
  orphan. Recursion still needs the snapshot and configuration fixes above.
