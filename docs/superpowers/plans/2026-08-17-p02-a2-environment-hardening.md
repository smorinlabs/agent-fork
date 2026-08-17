# P02-A2 — Environment and configuration hardening

Design doc for P02 gate A2. Validation-first per the owner amendment
(2026-08-17): research each input's documented behavior, derive a probe matrix
from that behavior, run it, rewrite the register entry to match, and only then
design a fix.

| Gate | State |
|---|---|
| 0. Research each variable's semantics | **complete** — below |
| 1. Probe matrix derived from research | drafted below; not yet run |
| 2. Run matrix, record each cell with captured output | not started |
| 3. Rewrite register entry to match evidence | not started |
| 4. Design + adversarial plan review (incl. Codex) | not started |
| 5. Implementation (TDD) | not started |
| 6. Adversarial implementation review (incl. Codex) | not started |

## Research — what each variable actually does

Source: `man git` (ENVIRONMENT VARIABLES), `man git-config`, `man
gitnamespaces` on the development machine. Quotations are Git's wording.

### Repository location

| Variable | Documented behavior | Relevance to agent-fork |
|---|---|---|
| `GIT_DIR` | "specifies a path to use instead of the default `.git` for the base of the repository" | Redirects every operation. **Not overridden by `-C`** — `-C` changes the working directory Git starts in; `GIT_DIR` still selects the repository. |
| `GIT_WORK_TREE` | "Set the path to the root of the working tree" | Pairs with `GIT_DIR`; separates the tree from the repository. |
| `GIT_COMMON_DIR` | "non-worktree files that are normally in `$GIT_DIR` will be taken from this path instead. Worktree-specific files such as HEAD or index are taken from `$GIT_DIR`." Explicitly "lower precedence than other path variables such as `GIT_INDEX_FILE`, `GIT_OBJECT_DIRECTORY`" | **Directly implicated.** `verify.py` compares `rev-parse --git-common-dir` against the recorded common directory as a verification rung. This variable is the one thing that can move that answer. |
| `GIT_CEILING_DIRECTORIES` | Directories Git "should not chdir up into while looking for a repository"; "will not exclude … a `GIT_DIR` set on the command line or in the environment" | Can only *prevent* discovery, so the expected outcome is refusal. |
| `GIT_DISCOVERY_ACROSS_FILESYSTEM` | Lets discovery cross filesystem boundaries | Widens discovery; could attach to an unexpected parent repository. |

### Object storage

| Variable | Documented behavior | Relevance to agent-fork |
|---|---|---|
| `GIT_OBJECT_DIRECTORY` | "If the object storage directory is specified via this environment variable then the sha1 directories are created underneath" | **Newly written objects land elsewhere.** agent-fork writes objects during `apply --index`. Objects written outside the repository would leave the fork referencing blobs that vanish when the variable does. |
| `GIT_ALTERNATE_OBJECT_DIRECTORIES` | Colon-separated additional object directories; "New objects will not be written to these directories" | Read-only extra search path — can make objects *appear* resolvable that the repository does not own. |

### Refs

| Variable | Documented behavior | Relevance to agent-fork |
|---|---|---|
| `GIT_NAMESPACE` | "divides the refs of a single repository into multiple namespaces, each of which has its own branches, tags, and HEAD"; refs stored under `refs/namespaces/<ns>/` | **Highest-suspicion variable.** agent-fork guards with `show-ref --verify refs/heads/<branch>`, creates with `worktree add -b`, and deletes with `branch -D`. If those three do not agree about which ref `refs/heads/X` means, the guard can miss an existing branch, or cleanup can delete the wrong ref. |

### Configuration

| Variable | Documented behavior | Relevance to agent-fork |
|---|---|---|
| `GIT_CONFIG_COUNT` + `GIT_CONFIG_KEY_<n>` / `GIT_CONFIG_VALUE_<n>` | Adds pairs to runtime configuration; "will override values in configuration files, **but will be overridden by any explicit options passed via `git -c`**" | Injects arbitrary configuration — the same class as A1's `apply.whitespace`. The `-c` precedence is the single most important fact for the fix design (see below). |
| `GIT_CONFIG_GLOBAL` / `GIT_CONFIG_SYSTEM` | Replace the global/system config files; "Can be set to `/dev/null` to skip" | Substitutes whole config files. |
| `GIT_CONFIG_NOSYSTEM` | Skip `/etc/gitconfig` | Hardening-only; the harness already sets it. |

### Format and creation

`GIT_INDEX_VERSION`, `GIT_DEFAULT_HASH`, `GIT_DEFAULT_REF_FORMAT` affect index
writes and newly created repositories. agent-fork does not create repositories,
so these are lowest priority — but `GIT_INDEX_VERSION` touches index writes,
which `apply --index` performs.

### Diff drivers — transport uses porcelain where plumbing is required

This surfaced during research and is **not in A2's register entry at all**. It
may be the largest real defect in the item.

Agent-fork transports every staged, unstaged, and intent-to-add change by
piping `git diff --binary --no-color …` into `git apply`
(`materialize.py:142`, `:151`, `:163`). It passes neither `--no-ext-diff` nor
`--no-textconv`, and `grep` finds no external-diff guard anywhere in `src/`.

| Mechanism | Documented behavior | Consequence for transport |
|---|---|---|
| `diff.external` (config) and `GIT_EXTERNAL_DIFF` (environment) | "diff generation is not performed using the internal diff machinery, but using the given command" | The patch becomes whatever that program prints. `git apply` receives something that is not a Git patch. |
| textconv diff drivers, set per-path by `.gitattributes` plus a `diff.<driver>.textconv` config entry | "Because textconv filters are typically a one-way conversion, the resulting diff is suitable for human consumption, **but cannot be applied**. For this reason, textconv filters are enabled by default only for **git-diff(1)** and git-log(1), but not for git-format-patch(1) or diff plumbing commands." | Agent-fork uses `git diff` — precisely the command where textconv is on by default. Git states plainly that the result cannot be applied. |

Two properties make this worse than the rest of A2:

1. **It is repository-controlled, not user-controlled.** `.gitattributes` is a
   committed file. Cloning a repository that uses a textconv driver — a
   legitimate, common practice for binary formats such as PDFs or images — is
   enough. No hostile environment is required.
2. **`--no-ext-diff` and `--no-textconv` are the documented remedies**, so the
   fix is small and precise: use plumbing semantics on the transport path
   rather than porcelain defaults.

Whether `--binary` suppresses textconv in practice is **not settled by the
documentation** and must be probed. That probe is priority 1.

## Worktree-specific facts (from `git-worktree(1)`)

- "**all refs starting with `refs/` are shared**" across worktrees; pseudo refs
  such as HEAD are per-worktree. This is the surface `GIT_NAMESPACE` relocates,
  and it confirms why namespace confusion would affect the guard, the create,
  and the delete uniformly.
- "By default, the repository config file is **shared across all worktrees**."
  Per-worktree configuration requires `extensions.worktreeConfig`, after which
  settings live at `git rev-parse --git-path config.worktree`.
- "`core.sparseCheckout` should not be shared, unless you are sure you always
  use sparse checkout for all worktrees" — independent corroboration of the
  sparse-checkout gap tracked in issue #31.
- "Older Git versions will refuse to access repositories with this extension"
  (`extensions.worktreeConfig`) — a compatibility edge worth a probe against
  the declared Git floor.

## What the research changes

**Two conclusions that the earlier "probe everything" plan would have missed.**

**1. `git -c` outranks environment configuration injection.** Git documents
that `-c` beats `GIT_CONFIG_*`. So the configuration half of A2 does **not**
require environment sanitization — a pinning policy applied through `-c` is
sufficient, and is strictly simpler than stripping variables. This narrows the
fix.

**2. The dangerous variables are not the ones already probed.** The two probes
run on 2026-08-17 (`GIT_DIR`+`GIT_WORK_TREE`, and `GIT_INDEX_FILE`) hit the
variables that move the *whole repository* — which is exactly what
agent-fork's config-discovery boundary check already notices. The untested
variables that matter are the ones that move *one component* while leaving the
repository root intact, so that check cannot fire:

- `GIT_NAMESPACE` moves refs only.
- `GIT_OBJECT_DIRECTORY` moves object writes only.
- `GIT_COMMON_DIR` moves shared repository files only — and is the one thing
  that can defeat an existing verification rung.
- `GIT_ALTERNATE_OBJECT_DIRECTORIES` adds object visibility only.

That is the mechanism-level reason to expect trouble there, and it is why this
matrix is prioritized rather than exhaustive-in-arbitrary-order.

## Probe matrix (derived from the research)

**Operations axis** — each probed separately, because agent-fork's guards
protect discovery, not every operation: worktree creation · branch creation ·
materialization · verification · **cleanup** (deletes worktrees and branches;
highest consequence) · registry write.

**Priority 1 — mechanism suggests real damage:**

| Input | Hypothesis to falsify |
|---|---|
| textconv driver via committed `.gitattributes` + `diff.<driver>.textconv` | The transport patch is unappliable or lossy, because `git diff` enables textconv by default and Git documents that its output "cannot be applied". **Repository-controlled — no hostile environment needed.** Run the T1 matrix below; a single binary file is not sufficient coverage. |
| `diff.external` config, and `GIT_EXTERNAL_DIFF` environment | The diff engine is replaced, so `git apply` receives output that is not a Git patch; transport fails or corrupts. |
| `GIT_NAMESPACE` | The existence guard, branch creation, and `branch -D` disagree about `refs/heads/<branch>`; a fork collides with an invisible branch, or cleanup deletes the wrong ref. |
| `GIT_OBJECT_DIRECTORY` | Objects written by `apply --index` land outside the repository; the fork's index references blobs that disappear with the variable, while verification passes because it runs under the same environment. |
| `GIT_COMMON_DIR` | The `common-dir` verification rung is satisfied by a foreign path, or a correct fork is spuriously rolled back. |
| `GIT_ALTERNATE_OBJECT_DIRECTORIES` | Anchor resolution succeeds against an object the repository does not own. |

**Priority 2 — expect refusal; confirm it is refusal and not something worse:**
`GIT_DIR` alone (no `GIT_WORK_TREE`) · `GIT_CEILING_DIRECTORIES` ·
`GIT_DISCOVERY_ACROSS_FILESYSTEM`.

**Priority 3 — configuration injection, to size the pinning policy:**
`GIT_CONFIG_COUNT`/`KEY`/`VALUE` injecting `apply.whitespace`, `core.autocrlf`,
a clean filter, and `status.showUntrackedFiles` · `GIT_CONFIG_GLOBAL`
substitution. A1 already pins `--whitespace=nowarn` and
`--untracked-files=all`, so these probe whether the remaining surface still
bites.

**Already probed — do not repeat:** `GIT_DIR`+`GIT_WORK_TREE` (refused with
`config_error`) · `GIT_INDEX_FILE` (self-consistent; correct content carried).

**Record per cell:** exact command, captured output, and one verdict —
refused · self-consistent · **wrong-repository or wrong-ref mutation** ·
silent divergence · objects/refs written outside the repository.

## Fix shape (provisional — do not build until the matrix runs)

Sequencing stands: unsealed-configuration test tier first, then whatever
sanitization the matrix justifies, then the pinning policy. The research
already narrows the third piece: pin through `-c`, which outranks environment
injection, rather than enumerating variables to strip.

## T1 matrix — textconv and binary treatment

A single NUL-containing file is **not** sufficient coverage, because Git's
binary decision is not purely content-based. `gitattributes(5)`: Git "usually
guesses correctly … by examining the beginning of the contents," but a file may
be marked binary "because the content, **while technically composed of text
characters**, is opaque to a human reader" — their example is PostScript, which
is pure ASCII. A text file can therefore be binary for diff purposes.

The same page documents a third configuration that `-diff` alone cannot
express: `-diff` and `diff=<driver>` are mutually exclusive, so combining
textconv with binary treatment requires `diff.<driver>.binary = true`. That
combination is the most likely to interact badly with `--binary`.

**Content axis:** C1 NUL bytes (content-detected binary) · C2 high bytes, no
NUL (likely detected as text) · C3 pure ASCII text.

**Attribute axis:** A1 none (control) · A2 `diff=drv` with
`diff.drv.textconv` · A3 `-diff` (marked binary, no driver) · A4 `diff=drv`
with `textconv` plus `diff.drv.binary = true`.

**Procedure.**
1. *Observe (12 cells, cheap).* For each content × attribute pair, modify the
   file unstaged and run `git diff --binary --no-color`. Record only the output
   kind: binary patch · textconv text · `Binary files differ` · ordinary text
   diff.
2. *Fork the suspicious cells.* Any cell whose output is not an applyable patch
   gets a full `agent-fork fork`; record whether transport fails loudly or
   diverges silently.
3. *Isolate `--binary`.* Repeat step 1 without `--binary` for cells that
   differed.

**Decision table.**

| Observation | Conclusion |
|---|---|
| C3 with A3 or A4 yields textconv output | Exposure includes ordinary text files; any repository with a diff driver is affected. Largest scope. |
| Only C1 affected | Exposure limited to genuinely binary content. Narrower, still real. |
| `--binary` suppresses textconv in every cell | Latent only; drops to hardening and the environment variables resume priority. |
| A4 differs from A2 | The fix must handle `diff.<driver>.binary` specifically, not just `--no-textconv`. |

**Deferred:** `core.bigFileThreshold` is a fourth route to binary treatment.
Add it to the matrix only if the attribute axis shows the mechanism bites.

## T1 results — run 2026-08-17

**Phase 1 — `git diff --binary --no-color`, the exact command agent-fork runs.**

| Content | A1 none | A2 `diff=drv` textconv | A3 `-diff` | A4 textconv + `binary=true` |
|---|---|---|---|---|
| C1 NUL bytes | binary-patch | **textconv text** | binary-patch | **textconv text** |
| C2 high bytes, no NUL | text-diff | **textconv text** | binary-patch | **textconv text** |
| C3 pure ASCII | text-diff | **textconv text** | binary-patch | **textconv text** |

Two findings, both contradicting the documentation's framing:

1. **`--binary` does not suppress textconv.** Every cell with a driver
   produced textconv output despite `--binary` being passed.
2. **Textconv is not limited to binary files.** Cell C3/A2 — a pure ASCII text
   file — ran textconv. The documentation describes textconv as being for
   "binary files", but the attribute governs, not the content. Exposure is
   therefore any path with a `diff=<driver>` attribute, of any content type.

**Phase 2 — full fork against a repository shipping a textconv driver.**

Control (no driver) forks cleanly and the child receives the uncommitted work.
The probe fails:

```
{"error":{"code":"runtime_error","message":"error: patch failed: doc.txt:1\nerror: doc.txt: patch does not apply"}}
```

Verdict: **the repository is unforkable.** Not corruption — parent untouched,
worktree rolled back, safety intact. The defects are (a) total loss of
function on affected repositories, and (b) an uncategorized `runtime_error`
carrying raw Git output that never mentions `.gitattributes`, leaving the user
no path to diagnosis.

**T5 — candidate fix validated before design.** Appliability of the produced
patch, tested by applying into a pristine clone:

| Scenario | Today | With `--no-textconv --no-ext-diff` |
|---|---|---|
| textconv on text, textconv+binary, binary content, plain control | **1 of 4 apply** | **4 of 4 apply** |
| same, plus a hostile `diff.external` configured | **0 of 4 apply** | **4 of 4 apply** |

Two flags on the transport diffs resolve both mechanisms across every cell,
and leave the unaffected control unchanged.

**Harness correction.** An earlier run of T5 reported the fix as partial
(2 of 4). That was a defect in the probe, not the fix: capturing a binary
patch through shell command substitution silently strips NUL bytes
(`warning: command substitution: ignored null byte in input`). Routing the
patch through a file corrected it. Recorded because the false result was
plausible and would have mis-scoped the fix.

### What T1 settles

- The transport defect is **real, reproducible, and repository-triggered**.
- Severity is **loss of function**, not data loss — A1's rollback holds.
- The fix is **two flags at three call sites**, validated ahead of design.
- Priority within A2 inverts: this outranks every environment variable,
  because it needs no hostile environment at all.

## T7/T8 — plumbing is immune, and a second failure mode

**T7 — do the plumbing commands support what transport needs?** Yes, verified:
`diff-index` and `diff-files` accept `--ita-invisible-in-index`,
`--ita-visible-in-index`, `--no-renames`, and `--no-color`, and their patches
apply. With a textconv driver active *and* a hostile `diff.external` set
repository-wide, plumbing still produced a valid patch where porcelain produced
garbage.

**T8 — a lossy driver empties the patch.** A converter that renders every
revision identically — realistic, since converters summarize — makes the
porcelain diff **0 bytes** while plumbing produces the real 162-byte patch.
Under porcelain the change is simply dropped. A1's content verification catches
it as `verify_failed` with structured `failed_checks` naming the path, so it is
a refusal rather than silent loss — but the fork still cannot be created.

This is a **second, distinct failure mode**: T1 was *unappliable*, T8 is
*empty*. Both are fixed by the same change, but a fix validated only against T1
would not have been known to cover T8.

## Decision and stage 1 outcome

**Chose plumbing over the two-flag fix**, gated on A1's suite passing
unchanged. Rationale: `--no-textconv --no-ext-diff` disables the two display
features known today, whereas porcelain's contract permits new reader-facing
behavior to be added and enabled by default — each addition a future recurrence.
Plumbing is defined as the layer that does not apply display conversions.

Changed in `materialize.py`, three call sites:

| Was | Now |
|---|---|
| `diff --binary --no-color --cached --ita-invisible-in-index` | `diff-index -p --binary --no-color --cached --ita-invisible-in-index HEAD` |
| `diff --binary --no-color --ita-invisible-in-index -- <path>` | `diff-files -p --binary --no-color --ita-invisible-in-index -- <path>` |
| `diff --binary --no-color --ita-invisible-in-index` | `diff-files -p --binary --no-color --ita-invisible-in-index` |

The `--name-only` enumeration calls were **left alone**: probing showed them
unaffected by both textconv and `diff.external`, so changing them would be
churn without evidence.

**Gates:** T-MAT-21..24 observed RED, then green. A1's 22 verification cells
pass unchanged — the condition for preferring plumbing. Full suite 413 passed,
1 skipped; lint, typecheck, and matrix clean.

## Stage 2 — porcelain audit across the whole codebase

Inventory of every Git subcommand, with a verdict per family.

| Subcommand | Calls | Verdict |
|---|---|---|
| `status --porcelain=v1 -z` | 15 | **Keep.** `--porcelain` *is* Git's documented stable machine format; it is the plumbing contract for status, not a human format. |
| `worktree … --porcelain` | 11 | **Keep.** Same reasoning; the porcelain flag selects the machine format. |
| `ls-files` | 10 | **Keep.** Already plumbing. |
| `diff --name-only` | 10 | **Keep as porcelain** — see below. |
| `rev-parse`, `show-ref`, `symbolic-ref`, `rev-list`, `check-ref-format` | 17 | **Keep.** Already plumbing. |
| `branch` | 8 | **Keep for now.** Porcelain, with plumbing equivalents (`for-each-ref`, `update-ref -d`). No evidence of a defect; revisit only if the `GIT_NAMESPACE` probe implicates ref handling. |
| `apply`, `add` | 3 | **Keep.** No display-driver surface. |

### Why the `--name-only` enumeration calls stay porcelain

Swapping them was the obvious next step and the evidence argued against it:

1. **They are provably unaffected** by both mechanisms. Probed directly: with a
   textconv driver active and with `diff.external` set repository-wide, the
   `--name-only` output listed paths correctly and exited 0 in both cases.
   These calls never render content, so no driver touches them.
2. **Swapping would introduce a new failure.** `diff-index` requires a tree
   argument, and `git diff-index --cached HEAD` fails on a repository with no
   commits — `fatal: ambiguous argument 'HEAD'` — where porcelain succeeds.
   `inspect_working_tree_status` runs outside the fork guards, serving
   `agent-fork session` on any repository, so the swap would break session
   inspection on a fresh repository. Trading a proven-absent problem for a real
   one is a bad trade.

The transport calls do not share this hazard: `validate_fork_guards`
(`pipeline.py:95`) refuses `repo_no_commits` before `materialize`
(`pipeline.py:132`) ever runs, and T-GRD-10/11 cover it.

### The audit's own finding — rename counts disagreed

`content.py` passes `--no-renames` when building the inventory; `cli.py` and
`repository.py` did not when counting for display. Porcelain enables rename
detection by default, so one staged rename produced:

| Caller | Paths |
|---|---|
| reported count (dry run, session status) | **1** — `new_name.txt` |
| carried inventory | **2** — both endpoints |

The user confirmed a fork carrying "1 staged file" while transport carried two
paths. Cosmetic rather than data-affecting — the patch reproduces the rename
correctly either way — but it contradicts the principle A1 established, that
reported numbers match reality.

Fixed by adding `--no-renames` at the two reporting sites rather than swapping
commands: minimal, and it introduces no empty-repository hazard. `T-MAT-25`
pins it, observed RED (`reported staged=1 but the inventory carries 2`).

**Gates:** 414 passed, 1 skipped; lint, typecheck, matrix clean.

## Canonical input inventory (authoritative)

Earlier drafts listed different sets in three places and disagreed on the
count, which undermines the exhaustiveness the matrix depends on. **This list
is authoritative; the register entry and any handoff cite it rather than
restating it.**

**Resolved — do not re-probe:**

| Input | Verdict | Where |
|---|---|---|
| `GIT_DIR` + `GIT_WORK_TREE` | refused (`config_error`, discovery boundary) | 2026-08-17 probe |
| `GIT_INDEX_FILE` | self-consistent; correct content carried | 2026-08-17 probe |
| textconv attribute (`.gitattributes` + `diff.<drv>.textconv`) | **defect, fixed** by plumbing transport | T1/T8, T-MAT-21/22 |
| `diff.external` (config form) | **defect, fixed** by plumbing transport | T5, T-MAT-23 |

**Untested — 13 inputs, grouped by mechanism:**

| # | Input | Priority |
|---|---|---|
| 1 | `GIT_NAMESPACE` | 1 — refs relocate; cleanup deletes |
| 2 | `GIT_OBJECT_DIRECTORY` | 1 — new objects land elsewhere |
| 3 | `GIT_ALTERNATE_OBJECT_DIRECTORIES` | 1 — phantom object visibility |
| 4 | `GIT_COMMON_DIR` | 1 — moves the `common-dir` verification rung |
| 5 | `GIT_DIR` alone (no `GIT_WORK_TREE`) | 2 — expect refusal |
| 6 | `GIT_CEILING_DIRECTORIES` | 2 — expect refusal |
| 7 | `GIT_DISCOVERY_ACROSS_FILESYSTEM` | 2 — expect refusal |
| 8 | `GIT_CONFIG_COUNT` / `KEY_<n>` / `VALUE_<n>` | 3 — sizes the pinning policy |
| 9 | `GIT_CONFIG_GLOBAL` | 3 — whole-file substitution |
| 10 | `GIT_CONFIG_SYSTEM` | 3 — whole-file substitution, system level |
| 11 | `GIT_ATTR_NOSYSTEM` | 3 — suppresses system attributes |
| 12 | `GIT_EXTERNAL_DIFF` | 3 — environment twin of `diff.external`; the plumbing fix should neutralize it, which is now an untested claim |
| 13 | `GIT_INDEX_VERSION` | 4 — touches index writes performed by `apply --index` |

**Excluded, with reason:** `GIT_DEFAULT_HASH` and `GIT_DEFAULT_REF_FORMAT`
apply to repository creation, which agent-fork never performs.
`GIT_CONFIG_NOSYSTEM` is hardening-only and already set by the test harness.

## Group 2–4 results — run 2026-08-17

Four priority-1 inputs probed against a full fork. **No defect found. The
mechanism-based prioritization that put these first was wrong.**

| Input | Verdict | Evidence |
|---|---|---|
| `GIT_NAMESPACE` | **unaffected** | Has no effect on the local ref operations agent-fork performs |
| `GIT_OBJECT_DIRECTORY` | **refused** | `fatal: Needed a single revision`; zero objects written to the foreign directory, no partial fork |
| `GIT_ALTERNATE_OBJECT_DIRECTORIES` | **unaffected** | Fork succeeded and content verified correct on both layers |
| `GIT_COMMON_DIR` (foreign repository) | **refused** | Same refusal as `GIT_OBJECT_DIRECTORY` |

### `GIT_NAMESPACE` — hypothesis refuted

It was the highest-suspicion input in the matrix, on the reasoning that
relocating refs would make the existence guard, `worktree add -b`, and
`branch -D` disagree. Probed directly:

- `GIT_NAMESPACE=ns git branch alpha` creates `refs/heads/alpha`. **No
  `refs/namespaces/` directory is created at all.**
- `rev-parse alpha` resolves identically with and without the namespace.
- `GIT_NAMESPACE=ns git branch -D target` deletes the **real** `refs/heads/target`
  — the intended ref, not a namespaced one.

The namespace does apply, but at the **transport layer**: `ls-remote` shows 0
refs under the namespace against 3 without it. That matches
`gitnamespaces(7)`'s framing — namespaces exist to "expose each namespace as an
independent repository to pull from and push to". The local ref commands
agent-fork uses do not honor it, so the predicted disagreement cannot occur.

**Correction to record:** the design reasoning treated "refs are relocated" as
applying to all ref access. It applies to the remote protocol. Reading
`gitnamespaces(7)` more carefully would have caught this before the probe —
though the probe is what settled it, which is the point of the gate.

### Content verification mattered

`GIT_ALTERNATE_OBJECT_DIRECTORIES` initially looked like "fork succeeded", which
is not a verdict. Re-probed asserting both layers of the three-way split: parent
and child both `WORKING alt` in the working tree and `STAGED alt` in the index.
Only then is "unaffected" supportable.

Likewise `GIT_COMMON_DIR` was first probed pointed at the repository's own
`.git`, which is benign by construction and proves nothing. Re-probed against a
*different* repository, it refuses.

### The one real observation

Both refusals surface as **`runtime_error: fatal: Needed a single revision`** —
uncategorized, with raw Git text that names neither the variable nor the cause.
Safety holds (nothing is created, nothing is written outside the repository),
but a user hitting this has no path to diagnosis. This is the same error-typing
weakness seen in the T1 transport failure, now observed from a second
independent direction, which strengthens the case that issue #28's typed-error
work has a live trigger.

### Running tally

| Status | Inputs |
|---|---|
| Resolved, defect fixed | textconv attribute · `diff.external` |
| Resolved, no defect | `GIT_DIR`+`GIT_WORK_TREE` · `GIT_INDEX_FILE` · `GIT_NAMESPACE` · `GIT_OBJECT_DIRECTORY` · `GIT_ALTERNATE_OBJECT_DIRECTORIES` · `GIT_COMMON_DIR` |
| Remaining untested | 9 of the canonical 13 — priorities 2 and 3: `GIT_DIR` alone, `GIT_CEILING_DIRECTORIES`, `GIT_DISCOVERY_ACROSS_FILESYSTEM`, `GIT_CONFIG_COUNT`/`KEY`/`VALUE`, `GIT_CONFIG_GLOBAL`, `GIT_CONFIG_SYSTEM`, `GIT_ATTR_NOSYSTEM`, `GIT_EXTERNAL_DIFF`, `GIT_INDEX_VERSION` |

**Interim read:** every environment variable probed so far is either refused or
harmless. The only confirmed A2-adjacent defects came from *configuration and
attributes* (textconv, `diff.external`), not from the environment. If the
remaining configuration-injection cells behave the same way, A2's severity
should drop again and its fix should be scoped to the pinning policy alone.

## Group 6 results — configuration injection (2026-08-17)

### C1 — the fix design's load-bearing assumption, verified

`git-config(1)` states that `GIT_CONFIG_*` pairs "will be overridden by any
explicit options passed via `git -c`". The whole pinning-policy approach rests
on it, so it was measured rather than trusted:

| Check | Result |
|---|---|
| `apply.whitespace` injected only | `fix` |
| injected, plus `-c apply.whitespace=nowarn` | **`nowarn` — `-c` wins** |
| hostile `GIT_CONFIG_GLOBAL` file only | `fix` |
| same, plus `-c` | **`nowarn` — `-c` wins** |
| `apply` **without** a pin, injection active | whitespace **stripped** — the threat is real |
| `apply` **with** A1's `--whitespace=nowarn`, injection active | whitespace **preserved — A1's pin holds** |

Two conclusions: a pinning policy applied through `-c` is effective against both
the environment-injection and file-substitution forms, and A1's existing pins
already defend the keys they cover.

### C2 — which keys still bite

Ten keys injected via `GIT_CONFIG_*` against a full fork:

| Key | Verdict |
|---|---|
| `core.autocrlf=true` / `=input` | **refused** — A1's `content-match` rung fires (`f.txt: content differs`) |
| `core.symlinks=false` | **silent divergence** — see below |
| `core.fileMode`, `core.ignorecase`, `core.quotePath`, `status.showUntrackedFiles`, `apply.whitespace`, `diff.noprefix`, `core.bigFileThreshold` | ok — parent and child agree |

**Harness correction.** The first run reported all ten as refused, which was a
probe defect, not a finding: each child worktree was created *inside* its parent
repository, which agent-fork correctly refuses. Ten identical refusals across
keys that could not plausibly matter was the signal to re-check rather than
report. Children are now siblings.

### C3 — the one real gap, and it is not about the environment

`core.symlinks=false` produced a child whose **committed** symlink became a
regular file, with the fork reporting success:

| Path | Carried? | Parent | Child |
|---|---|---|---|
| `untracked_link` | yes | symlink | symlink — correct |
| `committed_link` | **no** | symlink | **regular file** containing `f.txt` |

Inventory at the time: `staged: () unstaged: ('f.txt',) untracked:
('untracked_link',)`. `committed_link` is absent, so no rung examined it.

The mechanism: **verification is scoped to carried paths**, but the child's copy
of committed content comes from `worktree add`'s checkout, which configuration
can alter. `core.autocrlf` was caught in the same run *only because* its file
was carried — same class of key, opposite outcome, decided by inventory
membership alone.

Routed to **issue #35** (pre-existing scope gap, surfaced by A2 rather than
caused by it). Recommended remedy there is option 1: pin the checkout-affecting
keys on `worktree add`, which C1 proves is effective and which costs nothing at
fork time.

### Updated tally

| Status | Count |
|---|---|
| Resolved — defect found and fixed | 2 (textconv, `diff.external`) |
| Resolved — no defect | 8 environment variables |
| Resolved — defect routed to an issue | 1 (`core.symlinks` → #35) |
| Remaining untested | 4: `GIT_ATTR_NOSYSTEM`, `GIT_EXTERNAL_DIFF`, `GIT_INDEX_VERSION`, and the priority-2 discovery trio treated as one group |

**Read so far:** no environment variable has produced a defect. Every confirmed
problem has come from *configuration or attributes*. A2's fix is therefore
converging on a pinning policy — now with C1's evidence that the mechanism
works and C3's evidence that it must cover `worktree add`, not only transport.

## Fix for issue #35 — and one half of it dropped after probing

**Recommended:** (1) strip inline configuration injection at the `run_git`
chokepoint; (2) pass the parent's effective checkout-affecting values to
`worktree add`.

**Shipped: part 1 only.** Part 2 was dropped, and part 1's scope was corrected,
both because probing contradicted the proposal.

### Correction to part 1 — what may be stripped

The proposal named `GIT_CONFIG_GLOBAL` and `GIT_CONFIG_SYSTEM` among the
variables to remove. **That would have broken the test suite**:
`tests/conftest.py:854` sets `GIT_CONFIG_GLOBAL` to seal every test's
configuration, so stripping it would make each sealed test fall back to the
real `~/.gitconfig`.

The distinction that matters is not "environment versus file" but *what the
variable does*:

| Variable | Nature | Decision |
|---|---|---|
| `GIT_CONFIG_COUNT`, `GIT_CONFIG_KEY_<n>`, `GIT_CONFIG_VALUE_<n>` | inline values that outrank every configuration file | **strip** — no legitimate use in this tool's subprocesses |
| `GIT_CONFIG_GLOBAL`, `GIT_CONFIG_SYSTEM` | pointers to configuration *files* | **keep** — this is how tooling deliberately controls Git; removing them ignores user configuration rather than protecting it |

### Part 2 dropped — agent-fork already matches plain Git

Part 2 addressed file-based configuration drift: a parent checked out under one
setting, then the setting changed, then a fork. Probed against plain Git as the
control:

| Under repository-local `core.symlinks=false` | Committed symlink in the new worktree |
|---|---|
| `git worktree add` | regular file |
| `agent-fork fork` | regular file |

They agree. Agent-fork is honouring the user's own explicit configuration, and
a fresh checkout legitimately differs from a stale parent. Implementing part 2
would have meant overriding a deliberate user setting *and* diverging from the
behavior of the command agent-fork wraps — worse than the problem.

**This is the second time in A2 that a proposed fix half was removed by
probing** (the first was `--no-textconv --no-ext-diff`, superseded by plumbing).
The pattern argues for keeping the validation gate ahead of design, not just
ahead of implementation.

### Result

One change, in `git.py`: `_without_config_injection` filters the injection
triple out of the environment handed to every Git subprocess. When `env` is
`None` the filter is applied to `os.environ`, so inheriting callers are covered
too.

`T-GRD-17` reproduces issue #35 and was observed RED. `T-GRD-18` asserts
transport is defended independently of A1's per-call pin. `T-GRD-19` and
`T-GRD-20` are regression guards against over-stripping — file pointers still
honoured, repository-local configuration still applied.

**Gates:** 418 passed, 1 skipped; lint, typecheck, matrix clean.

## Final results — all 13 canonical inputs resolved (2026-08-17)

| # | Input | Verdict |
|---|---|---|
| 1 | `GIT_NAMESPACE` | unaffected — no effect on local ref operations |
| 2 | `GIT_OBJECT_DIRECTORY` | refused; nothing written outside the repository |
| 3 | `GIT_ALTERNATE_OBJECT_DIRECTORIES` | unaffected; content verified on both layers |
| 4 | `GIT_COMMON_DIR` (foreign repository) | refused |
| 5 | `GIT_DIR` alone (foreign repository) | **refused** — `verify_failed: branch`; bystander repository untouched in branches, worktrees, status, and content; rolled back |
| 6 | `GIT_CEILING_DIRECTORIES` | unaffected |
| 7 | `GIT_DISCOVERY_ACROSS_FILESYSTEM` | unaffected |
| 8 | `GIT_CONFIG_COUNT`/`KEY`/`VALUE` | **defect found (#35), fixed** by sanitization |
| 9 | `GIT_CONFIG_GLOBAL` | overridden by `-c`; preserved deliberately |
| 10 | `GIT_CONFIG_SYSTEM` | flattens a committed symlink — **but plain `git worktree add` does the same**, so agent-fork matches the command it wraps |
| 11 | `GIT_ATTR_NOSYSTEM` | **not meaningfully testable here** — no system attributes file exists on this machine to suppress |
| 12 | `GIT_EXTERNAL_DIFF` | unaffected — confirms the plumbing transport neutralizes it, previously an untested claim |
| 13 | `GIT_INDEX_VERSION=4` | takes effect (child index v4 against parent v2) and is harmless: staged and working content both intact |

### Three probes were redone because the first attempt proved nothing

- `GIT_CONFIG_SYSTEM` was run with `GIT_CONFIG_NOSYSTEM=1` exported, which
  suppresses system configuration outright. The original "ok" was vacuous.
- `GIT_ATTR_NOSYSTEM` had no system attributes file to suppress. Its honest
  verdict is *not applicable on this machine*, not *harmless*.
- `GIT_INDEX_VERSION` was not checked for having taken effect. It had — the
  child's index really is version 4 — which is what makes "harmless" meaningful.

`GIT_DIR` was also re-run specifically to answer A2's founding claim, checking
the bystander repository's branches, worktrees, status, and content before and
after.

## Conclusion — A2 is resolved

**The environment-passthrough claim is refuted.** Thirteen inputs, zero
wrong-repository mutations, zero silent divergences attributable to agent-fork.
Every refusal left both repositories untouched.

**The real defect class was configuration reaching Git**, and all three
demonstrated instances are fixed:

| Defect | Route | Fix |
|---|---|---|
| Unappliable / empty transport patches | `.gitattributes` textconv | plumbing transport |
| Transport replaced wholesale | `diff.external` config | plumbing transport |
| Committed symlink flattened | `GIT_CONFIG_*` injection | environment sanitization |

**The "untestable under the sealed harness" claim is refuted by
demonstration.** `T-GRD-17` through `T-GRD-20` test configuration injection
inside the existing harness. No new test tier was required — which was the
premise of the original "test tier first" sequencing.

**No pinning policy is needed.** It was scoped at roughly a week. The evidence
retired it: A1's existing pins hold under injection, injection is now stripped,
and for file-based configuration agent-fork behaves exactly as plain Git does,
so overriding it would substitute the tool's judgement for the user's.

**Remaining, and deliberately not fixed:** `GIT_ATTR_NOSYSTEM` is unprobed
because this machine has no system attributes file. That is a coverage gap, not
a known defect, and it belongs with the other coverage items in issue #31.
