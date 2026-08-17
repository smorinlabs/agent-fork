# Session handoff — P02-A2 validation-first probe matrix — 2026-08-17

## 🎯 Outcome

**Goal:** Run an exhaustive probe matrix for fault A2 — every Git environment
variable and correctness-relevant configuration key, crossed with every
operation agent-fork performs — and record what each cell *actually does* with
captured output. Then rewrite A2's register entry to match the evidence and
decide whether a fix is still warranted, and of what size.

**Out of scope:** implementing any A2 fix before the matrix is complete;
the other fault items (A3–A13); enhancements B1–B4 (project P03); issues
#28–#32, which are already routed and tracked.

**Self-contained:** ✓ stands alone. The probe evidence, the matrix design, and
the reasoning are inlined below; the referenced files are depth, not payload.

## ⚠ Portability & dependency preflight — read first

- **Uncommitted:** none. Working tree clean.
- **Unpushed:** none. Branch is level with its remote.
- **Stashes:** none.
- ⚠ **The rewritten A2 entry may not be on `main` yet.** It lives on branch
  `worktree-p02-a2-register-rewrite`, open as **PR #34**. Until that merges, a
  session reading `projects/P02-agent-fork-fault-remediation.md` on `main` sees
  the **old, overstated** A2 entry. Check `gh pr view 34`; if it is still open,
  read the file from the branch or merge it first.
- **Referenced docs:** `projects/P02-agent-fork-fault-remediation.md` (305
  lines) ✓ committed · substantive · no placeholders.
  `docs/superpowers/plans/2026-08-16-p02-a1-content-verification.md` (288
  lines) ✓ committed · substantive — A1's worked example of the same gate.

## 🧭 Where you are

- **Repo:** `agent-fork` · origin `https://github.com/smorinlabs/agent-fork.git`
  · default branch `main`
- **Branch:** `worktree-p02-a2-register-rewrite` (PR #34)
- **Repo root (this machine):** `/Users/stevemorin/c/agent-fork` ← will differ on yours
- **Build/verify:** `make check` first, then `just all` (format, lint,
  typecheck, test). Test suite is at 414 passed / 1 skipped / 9 deselected.
- **House rule:** never work in the live checkout — create a worktree from
  `origin/main` before writing anything.

## 📎 Artifacts & sources of truth

| What | Repo-relative path (canonical) | Abs (this machine) | Status |
|------|-------------------------------|--------------------|--------|
| A2 register entry (rewritten) | `projects/P02-agent-fork-fault-remediation.md` | `/Users/stevemorin/c/agent-fork/projects/P02-agent-fork-fault-remediation.md` | ✓ committed & substantive — **on branch only, not `main`** |
| A1 design doc (gate worked example) | `docs/superpowers/plans/2026-08-16-p02-a1-content-verification.md` | same root | ✓ committed & substantive |
| Git subprocess chokepoint | `src/agent_fork/git.py` (`run_git`) | same root | ✓ on `main` |
| Environment passthrough | `src/agent_fork/cli.py:667` | same root | ✓ on `main` |
| Sealed test harness | `tests/conftest.py:809-863` | same root | ✓ on `main` |

## 📋 Plan · inlined skeleton

### What A2 is (carry this; do not re-derive)

Agent-fork runs `git` **50 times across 10 modules**. Every call inherits the
user's environment unchanged (`cli.py:667`), and **no call pins configuration**
— there is no `git -c` anywhere in `src/`. Git takes instructions from
arguments, configuration files, *and* environment variables, and the
environment overrides the directory Git is pointed at.

Meanwhile `tests/conftest.py:809-863` builds the test environment as a
whitelist from empty, pinning `GIT_CONFIG_NOSYSTEM=1`, a controlled
`GIT_CONFIG_GLOBAL`, and `defaultBranch`/`quotePath`/`autocrlf`/`symlinks`.
**Every test therefore runs where this class cannot occur** — which is why
A1's fault survived 400 passing tests.

### Evidence already gathered (2026-08-17) — do not repeat these two

| Probe | Result |
|---|---|
| `GIT_DIR` + `GIT_WORK_TREE` aimed at a second repository, run from the first | Git *was* redirected (`rev-parse --show-toplevel` reported the other repo), but agent-fork **refused**: `{"error":{"code":"config_error","message":"cannot discover project config outside worktree root .../bystander"}}`. A config-discovery boundary check caught the mismatch. **No mutation.** |
| `GIT_INDEX_FILE` aimed at a genuinely divergent index (verified: different blob for the same path) — chosen because it does not move the repo root, so the check above cannot fire | Fork **succeeded**, verification passed, child received the **correct** content. One environment reaches every Git call, so reads, transport, and verification agree with each other. Self-consistent, not corrupt. |

Probe scripts are in this session's scratchpad (machine-local, will not travel);
rewrite them from the descriptions above rather than hunting for them.

### The matrix to build

**Axis 1 — inputs:** use the **canonical inventory** in the A2 design doc
(`docs/superpowers/plans/2026-08-17-p02-a2-environment-hardening.md`,
"Canonical input inventory") — 13 untested inputs with priorities, plus the
resolved ones and the exclusions with reasons. It is authoritative precisely
because earlier drafts restated divergent lists here and disagreed on the
count. Add the correctness-relevant config keys listed alongside it:
`core.autocrlf`, `core.symlinks`, `core.quotePath`, `core.fileMode`,
`core.ignorecase`, clean/smudge filters, `status.showUntrackedFiles`.

**Axis 2 — operations (each must be probed separately):** worktree creation ·
branch creation · materialization (staged, unstaged, intent-to-add, untracked,
ignored) · verification · **cleanup** · registry writes.

**Why per-operation matters:** the boundary check that caught `GIT_DIR` guards
*discovery*. It does not necessarily guard cleanup, which deletes worktrees and
branches — that is the highest-consequence cell in the matrix and is untested.

**Record per cell:** the exact command, the captured output, and a verdict of
refused / self-consistent / **wrong-repository mutation** / silent divergence.

### Then

1. Rewrite the A2 entry again to match the full matrix.
2. **If any cell produces a wrong-repository mutation, restore the high
   rating** — the current medium rating is conditional on that not happening.
3. Only then design. Sequencing already decided: unsealed-configuration test
   tier **first** (it is what makes the class visible), then environment
   sanitization at the single `run_git` chokepoint, then the per-subcommand
   pinning policy.

## 🔧 State to resume

- **Done:** A1 merged (`68ce894`) — content-level fork verification. Issue #32
  merged (`aefcda0`) — repository-controlled text escaped in guard errors and
  hook notices. `main` is at `aefcda0`, clean.
- **In flight:** branch `worktree-p02-a2-register-rewrite`, open as **PR #34**,
  carrying the A2 register rewrite, the validation-first amendment, the research,
  the transport fix (plumbing diff), and the porcelain audit. Until it merges,
  `main` still shows the old A2 entry.
- **Open issues:** #28 root-confined hashing and I/O error classification ·
  #29 intent-to-add raw pathspecs (registered as A13(e)) · #30 latency gate and
  progress output · #31 coverage gaps including dirty submodules (A6) ·
  #32 guard-error and hook-output sinks rendering repository text raw.
- **CI note:** a GitHub incident on 2026-08-17 made `casey/just` release
  listing return `[]`, which broke `extractions/setup-just@v4` with "no release
  matching version specifier" repo-wide, alongside 429/503 responses. It
  cleared on its own; a rerun went green. **Do not "fix" the workflow** unless
  it recurs after the platform is healthy.

## 🧠 Critical context that won't survive a fresh window

**Decisions and why:**
- **Validation-first is now the standing gate for every A item** (owner
  decision, 2026-08-17). Reading the code is not verification. Build and run
  the probe matrix, rewrite the register entry to match the evidence, *then*
  design. A2 is the worked example of why.
- **One PR per item**, carrying design doc + status flips + implementation,
  merged only when the item is fully done. Do not merge doc-only PRs early.
- **Gate-6 routing:** an item absorbs only what its own approved design
  promised plus defects that work introduced. Everything else becomes a GitHub
  issue. That rule produced #28–#32.
- **Severity is evidence-based.** A2 went high → medium because the headline
  claim did not reproduce.

**Rejected approaches — do not redo:**
- **Do not implement A2 as originally written.** The "wrong-repository
  mutation, high impact" framing did not reproduce. Building defenses around it
  would aim at a threat that does not exist while missing the one that does.
- **Do not add a general unsealed-environment test tier as a standalone
  effort** — that was explicitly dropped (it was part of B5–B9). The tier
  belongs *inside* A2's fix, scoped to what the matrix confirms.
- **Do not pin every Git setting reflexively.** Pinning too little admits the
  next `apply.whitespace`; pinning too much overrides settings a repository
  legitimately needs, such as `core.autocrlf` on a Windows-oriented repo or a
  required content filter. This is the design-heavy part, roughly a week's work
  dominated by deciding rather than coding.

**Conventions agreed:**
- Adversarial review of every plan and implementation includes a Codex pass as
  the independent second-model lens.
- Conventional Commits; merge commits (not squash); fast-forward-only syncs.
- Verify gate results by **exit code**, never through a pipe — `just lint | tail`
  reports the exit status of `tail`, which masked a real lint failure twice
  this session.

## 👉 First action

Land **PR #34** if it is still open, so the corrected A2 entry reaches `main`
before anyone reads the old one:

```
gh pr merge 34 --merge --repo smorinlabs/agent-fork
```

Then build the probe matrix above in a fresh worktree off `origin/main`,
starting with the highest-consequence untested cell: **cleanup under `GIT_DIR`
alone** — cleanup deletes worktrees and branches, and the boundary check that
refused the `GIT_DIR` fork guards discovery, not deletion.

## ℹ How this was made

digest: composed from live session context · gathered 2026-08-17 ·
self-contained: ✓
