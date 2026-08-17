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
