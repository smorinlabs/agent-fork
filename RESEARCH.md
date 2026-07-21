# RESEARCH.md — `agent-fork` Phase 1

**Date:** 2026-07-21 · **Status:** Phase 1 gate deliverable (research only — no implementation)
**Prior art:** `asheshgoplani/agent-deck` (Go), local checkout `/Users/stevemorin/c/agent-deck` (branch `main`, contains all fork PRs incl. #1299 and the post-merge #1354 default flip).
**Evidence tiers used below:** `[BIN]` verified against a local binary on 2026-07-21 · `[SRC]` read from agent-deck source (file:line) · `[FS]` verified against local filesystem state · `[WEB]` deep-research finding (see §5 provenance) · `[OPEN]` unresolved, needs live experiment.

---

## 0. Executive summary

- The agent-deck fork core is **cleanly extractable**: the `[fork]` config resolver and the `forkWithStateWorktree` pipeline are pure data + pure git-subprocess logic with a well-documented coupling boundary (tmux/bubbletea/Docker/session-model all sit *outside* the portable core). §1–§3.
- **Every v1 and v2 target has a native session fork today** `[BIN]`: Claude Code `--resume <id> --fork-session`, Codex `codex fork <uuid>` (first-class, documented Stable since ≥0.81.0), Pi `--fork`, OpenCode/Kilo `--fork`. The two former behavioral risks both **resolved favorably** `[WEB]`: Claude resume is officially worktree-scoped (no file copying needed — §5.1 Q1), and Codex injects `CODEX_THREAD_ID` into agent shells since 0.95.0 (§5.1 Q3). One hazard remains open: Codex's TUI cwd-change prompt on cross-directory fork (§5.1 Q4, experiment E2).
- **Host-agent detection and self-session-ID discovery are solved for both v1 targets**: Claude `[BIN]` `CLAUDECODE=1` + `CLAUDE_CODE_SESSION_ID`; Codex `[WEB]` `CODEX_THREAD_ID` (≥0.95.0).
- agent-deck's production fork path **does not verify the fork after creation** — correctness is enforced by its test suite, not runtime checks (§3.6). `agent-fork` can differentiate here: the spec'd contract (“child `git status --porcelain` == parent's”) is directly checkable at runtime for near-zero cost. §4.
- Upstream reversed `with_ignored` from default-ON (#1299) to **default-OFF** (#1354, 2026-06-09) after real-world pain: unbounded gitignored trees (node_modules, venvs), secrets (.env), blocking copy with no progress. This is production evidence for the Phase 3 default decision.

---

## 1. agent-deck `[fork]` config resolver `[SRC]`

Source: `internal/session/userconfig.go:2018–2111`. The resolver is **pure and portable** (no I/O, no agent-deck types).

### 1.1 Schema — exactly six keys, one flat global `[fork]` table

| TOML key | Type | Default when unset | Meaning |
|---|---|---|---|
| `inherit_from_parent` | bool | `false` | Short-circuit: mirror parent (forces worktree+state+ignored ON, sandbox = parent's) and **ignore all structural keys** |
| `worktree` | `*bool` (tri-state) | **ON** | Create new worktree + branch |
| `with_state` | `*bool` (tri-state) | **ON** | Carry parent's tracked uncommitted changes (staged + unstaged + untracked) |
| `with_ignored` | `*bool` (tri-state) | **OFF** (since #1354) | Also copy gitignored files; **implies `with_state`** |
| `docker` | `*string` | `"auto"` | `auto` (match parent) / `on` / `off` — out of scope for agent-fork v1 |
| `branch_prefix` | string | `"fork/"` | Auto branch-name prefix; whitespace-only → default |

Key design points worth porting:

- **`*bool` tri-state pattern is load-bearing**: `worktree`/`with_state` read `nil` as *true* (`== nil || *x`), `with_ignored` reads `nil` as *false* (`!= nil && *x`). "Absent = comprehensive-except-gitignored." Explicit `false` is honored (that's why they're pointers). Python equivalent: `Optional[bool]` with the same asymmetric accessors.
- **No per-project/per-group override tables exist** for `[fork]` — it's a single global block. Precedence is *not* global→project; it is: `inherit_from_parent` gate → per-field accessor default → parent runtime state (docker only) → downstream backend-capability clamp (`gateForkStateForBackend`: git/jj only; anything else silently degrades `with_state`/`with_ignored` to false).
- **No error paths in the resolver**: `docker = "bogus"` → silently `"auto"`; `branch_prefix = "  "` → silently `"fork/"`. Normalization is lazy (at accessor call time), not at load time.
- **Implication rule**: `with_state=false` + `with_ignored=true` resolves to `WithState=true` — you can't copy ignored files without materializing state.
- **`with_ignored` default history** (verified via `git blame`): #1299 shipped it ON; #1354 (commit `162c80b9`, 2026-06-09) flipped it OFF citing unbounded trees, secrets in `.env`, and a blocking copy with no size cap or progress. Phase 3 input.

### 1.2 Scope split that matters for agent-fork's design

`[fork]` config resolution is **TUI-only** in agent-deck. Its own CLI (`agent-deck session fork`) ignores `[fork]` entirely — explicit flags only, all defaulting **off**: `--with-state`, `--with-state-and-gitignored`, `-w/--worktree <branch>` (branch name required, no auto-suggestion). The Web/API fork is plain tool-native with no worktree/state defaults at all. So agent-deck itself contains *two* answers to "config-driven comprehensive default vs explicit-flags-off": TUI = comprehensive-by-default, CLI = opt-in-everything. Phase 3 must pick agent-fork's position on this axis deliberately.

---

## 2. agent-deck `forkWithStateWorktree` — the portable git core `[SRC]`

Source: `internal/ui/home.go:10070–10157` (orchestrator), `internal/git/materialize_wip.go` (state transfer), `internal/git/git.go` + `fork_with_state_destination.go` (detection/validation).

### 2.1 Algorithm (exact order)

1. Normalize: `WithIgnored` implies `WithState`; hard error if called without `WithState`.
2. **Destination collision guard** (before any filesystem mutation): refuse if the branch already exists (`branch %q already exists; choose a new destination branch`) or already has a worktree (`branch %q already has a worktree at %s`).
3. **Worktree-path collision guard**: refuse if the target path exists.
4. **Mid-operation guard**: refuse if parent is mid `rebase`/`merge`/`cherry-pick`/`revert`/`bisect`, with an actionable abort hint: `parent session is mid-<kind>; finish or abort the <kind> before forking with state (cd "<parent>" && git <kind> --abort)`.
5. `mkdir -p` the worktree's parent dir.
6. Submodule check — **warn only**, never block (submodules get copied as opaque files, not recursed).
7. **Parent-HEAD anchoring**: resolve `HEAD^{commit}` *at the parent's own path* (not repo root, not main) — the fork lands on the parent worktree's exact commit even in bare-repo/multi-worktree layouts.
8. Create worktree + branch atomically at that commit (`git worktree add -b <branch> <path> <parent-head>`); track whether the *branch* was newly created (rollback precision).
9. **Materialize state** (§2.2).
10. **On materialize failure — rollback**: always attempt `git worktree remove --force` + (only if branch was created this call) `git branch -D`. If cleanup succeeds: `failed to materialize parent state: <err>; new worktree cleaned up`. If cleanup also fails, emit an exact manual-recovery command: `... manual cleanup required: rm -rf "<worktree>" && git -C "<root>" branch -D "<branch>"`.
11. `.worktreeinclude` processing — non-fatal (separate curated allowlist of gitignored files to always copy, independent of `with_ignored`; gitignore-pattern file at repo root, copies only files that don't already exist in the fork so materialized copies win).
12. Setup hook — non-fatal (`.agent-deck/worktree-setup.sh`, cwd = new worktree, env vars for repo root + worktree path).

### 2.2 State materialization — the exact command sequence (port verbatim)

Contract (doc comment): *parent is read-only — no stash push, no add, no index mutation; child's `git status --porcelain` becomes equal to parent's.* Order is fixed: **staged → unstaged → untracked(+ignored)**.

```
# 1. staged:   parent's index-vs-HEAD diff → child's index AND working tree
git -C <parent> diff --binary --no-color --cached   |  git -C <child> apply --binary --index

# 2. unstaged: parent's worktree-vs-index diff → child's working tree only
git -C <parent> diff --binary --no-color            |  git -C <child> apply --binary

# 3. untracked files
git -C <parent> ls-files --others -z --exclude-standard          → copy each
# 3b. + gitignored (opt-in; --ignored FLIPS the filter, so union of two passes)
git -C <parent> ls-files --others -z --ignored --exclude-standard → copy each
```

Why this preserves the staged/unstaged split: applying the cached diff with `--index` writes both index and working tree (child shows `A  file`); applying the uncached diff *without* `--index` touches only the working tree (child shows ` M file`). Empty diffs are no-ops. File copies: `lstat` (no symlink follow), symlinks recreated verbatim via readlink (relative targets stay relative), directories skipped, regular files copied byte-for-byte **preserving source permission bits**. A redundant mid-operation re-check guards the raw entry point.

### 2.3 Git-state detection matrix (functions to port)

All thin `git` subprocess wrappers — trivially portable via Python `subprocess`:

| Detection | Mechanism |
|---|---|
| Is a git repo | `git -C <dir> rev-parse --git-dir` (exit 0) |
| Bare repo (self, not descendant) | `rev-parse --is-bare-repository` == true AND git-dir resolves to the dir itself |
| Bare-at-root vs `<project>/.bare/` layout | structural: basename == `.bare` distinguishes the nested convention (#715) |
| Inside a linked worktree | `rev-parse --git-common-dir` ≠ `rev-parse --git-dir` |
| Worktree of a bare project | common-dir (absolute) is itself bare — "no main worktree; every linked worktree is equal" |
| Project root from anywhere | `GetWorktreeBaseRoot`: linked worktree → strip main `.git`; bare-at-root → the bare dir; `.bare/` layout → its parent; plain repo → `--show-toplevel`; non-repo dir with nested bare child → resolve through it |
| Current branch / default branch | `rev-parse --abbrev-ref HEAD`; `symbolic-ref refs/remotes/origin/HEAD` → fallback local `main`/`master` |
| Parent HEAD anchor | `rev-parse --verify 'HEAD^{commit}'` at the parent's path |
| Mid-operation | stat git-dir for `rebase-merge`, `rebase-apply`, `MERGE_HEAD`, `CHERRY_PICK_HEAD`, `REVERT_HEAD`, `BISECT_LOG` |

### 2.4 Branch naming & worktree location schemes

- **Branch**: `<branch_prefix><sanitized-lowercased-slug>` (from session title in agent-deck; agent-fork needs its own name source — Phase 3). Sanitizer strips git-illegal chars (`.. ~ ^ : ? * [ \ @{`, spaces → `-`, collapse dashes, strip leading dots / trailing `.lock`). Collision: suffix `-2`, `-3`, … first name that is neither an existing branch nor has a worktree; hard stop at 1000.
- **Location** priority: (1) custom path template with `{repo-name}`/`{repo-root}`/`{branch}`/`{branch-escaped}`/`{session-id}` placeholders; (2) bare-at-root → child of the bare dir; (3) `subdirectory` → `<root>/.worktrees/<branch>`; (4) **default `sibling` → `<root>-<branch>`** (e.g. `myrepo-fork-fix-auth` next to `myrepo`); (5) custom dir prefix → `<prefix>/<repo-name>/<branch>`.

### 2.5 What is coupled to agent-deck (drop in the port)

tmux availability gating · bubbletea `tea.Cmd` async wrapper + spinner state · `session.Instance` persistence model (tool ids, groups, conductor parents, title-lock) · Docker/sandbox axis (whole `docker` key + `Sandbox` plan field) · multi-repo symlink farm · `ClaudeOptions` as options carrier · structured-log event names · jj backend (unless v-next wants it; if git-only, the whole `vcs.Backend` dual-dispatch collapses).

**The portable core** = the detection table (§2.3), destination validation, `CreateWorktreeAtStartPoint`, `MaterializeWipFromParent` + helpers, the orchestrator's guard→anchor→create→materialize→rollback sequence, branch/path naming helpers, and optionally `.worktreeinclude` + setup-hook conventions.

---

## 3. Per-tool session fork construction in agent-deck `[SRC]`

Core file: `internal/session/instance.go` (~8k lines). Every surface (TUI quick-fork, TUI dialog, Web/API) routes through one dispatcher, `CreateForkedInstanceForTool` (`instance.go:6406`), which switches on tool *compatibility* (`IsClaudeCompatible`/`IsCodexCompatible` — so a custom tool wrapping claude/codex inherits native fork treatment) and gates on a per-tool `CanFork*()` check before emitting anything.

### 3.1 Exact fork command templates

| Tool | Template (as built) | Notes |
|---|---|---|
| **Claude** | `cd '<workDir>' && <env>exec claude --session-id "<newUUID>" --resume <parentUUID> --fork-session<extraFlags>` | Fork UUID **pre-generated by the caller**, never left to Claude — proves `--session-id` + `--resume` + `--fork-session` compose in one non-interactive invocation (production-proven ✔). `cd` prefix sets the workdir (this is how agent-deck runs the fork in a *different directory* — a `[WEB]`-relevant datapoint for Q1). |
| **Codex** | `<env>codex [--yolo] [--model m] fork <parentUUID>` | Parent id shell-quoted + regex-validated (`^[0-9A-Fa-f]{8}-…$`). Optional `CODEX_HOME=<dir>` env prefix. |
| **OpenCode** | generated self-deleting bash script: `opencode export <parent>` → mint `ses_<hash>` id → `sed` id-swap in the export → `opencode import` → `opencode -s <newid>` | No native one-shot fork-by-id at the time; export/import round-trip is the mechanism. |
| **Pi** | `source_file=$(find <parent-session-dir> -name '*.jsonl' -exec ls -t {} + \| head -1); pi --fork "$source_file" --session-dir "$session_dir"` | Fork-by-file, newest-jsonl discovery; no id regex — forkability gated on file existence. |
| Gemini | — | `CanFork()` hard-returns false: no fork support. |
| Kilo | — | **Not in agent-deck's tool registry at all** (claude, opencode, gemini, codex, pi, copilot, crush, cursor, hermes, aider, shell). Kilo support in agent-fork v2 is greenfield, informed by its OpenCode lineage `[BIN]`. |

Validation + quoting: `normalizeToolSessionID` enforces per-tool regexes (Codex: strict UUID; OpenCode: `^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$`); Claude ids are Go-generated or extracted only if they match a bare-UUID regex, with refusal of anything containing shell metacharacters (`$VAR`, `$()`, backticks). Everything user-influenced passes `shellescape.Quote` — **except** two inconsistencies worth *not* porting: `workDir` in the Claude fork template is interpolated raw inside `'%s'`, and the Codex *resume* path (unlike fork) interpolates the session id unquoted. agent-fork should quote uniformly.

### 3.2 Codex: rollout-gating, deferred launch, and session-id discovery

- **Rollout-gated** = fork/resume by id is only emitted if the flushed rollout file actually exists: glob `<CODEX_HOME>/sessions/*/*/*/rollout-*-<sid>.jsonl` (`codexRolloutExistsInHome`). Codex writes rollouts asynchronously; a crash in the gap leaves a captured id permanently unresumable (#756), so a stale id is *dropped* (falls back to fresh launch) rather than looped on.
- **CLI-version risk handling**: agent-deck does **not** probe `codex --help` for `fork` support — it emits the command and treats a launch failure as a recoverable error state. (agent-fork emits a command for a *human* to paste, so it should preflight instead — e.g. `codex fork --help` exit status — Phase 2 requirement.)
- **Deferred-launch** = the one-shot `codex fork <sid>` is stored separately from the instance's persistent restart command (`ForkStartCommand` + `IsForkAwaitingStart`, both never persisted), consumed exactly once on first start; later restarts use `codex resume <new-sid>`. For a print-the-command CLI this collapses to: *the pasted command is the one-shot; subsequent resumes are the user's normal workflow.*
- **Session-id discovery ladder** (the part agent-fork must adapt): (1) `CODEX_SESSION_ID` from the tmux pane env — **but agent-deck itself wrote it there** after first discovery; it is not set natively by Codex; (2) probe the *live Codex process's open file descriptors* for the open rollout JSONL — `/proc/<pid>/fd` on Linux, `lsof -p <pid>` on macOS; (3) newest-rollout-for-this-project disk scan with already-claimed ids excluded. **agent-fork adaptation**: it runs as a child of the agent process, so walking *up* its own process ancestry to find a `codex` process, then applying probe (2), yields self-discovery without tmux. Deep-research Q3 confirms whether Codex has since gained a native env var.

### 3.3 Claude specifics

Native mechanism is resume-then-fork (no `claude fork` subcommand): `--resume <parent> --fork-session`, with the new id pre-pinned via `--session-id` and the workdir set by `cd` prefix in the same shell line. Config context is forwarded by exporting `CLAUDE_CONFIG_DIR` when set. A `#745` sentinel prevents the launcher from re-deriving a resume command from a not-yet-existing JSONL — evidence that the fork's own JSONL materializes only once the forked session starts.

### 3.4 Web/API path (scope precedent)

`POST /api/sessions/{id}/fork` calls the same dispatcher with `nil` options: plain tool-native conversation fork, **zero** worktree/state/branch logic — a documented, deliberate scope decision ("Comprehensive Web fork defaults ... needs async worktree creation, state materialization, rollback, branch conflict handling, and degradation notices"). Precedent: the *comprehensive* fork is a distinct product layer above tool-native fork — exactly the layer agent-fork is extracting.

### 3.5 Coupling to drop (per-tool layer)

tmux-pane env round-trip for ids · `AGENTDECK_*` env injection for its hook-watcher · pane-process-tree PID scoping · spawn-lock anti-race machinery · tool re-detection from pane content regexes · `fish`-compat `bash -c` wrapping (why UUIDs are pre-generated host-side — a habit worth keeping anyway) · group/SQLite persistence · title-sync cosmetics.

---

## 4. Git duplication + verification matrix (1c)

Mode axis: **exact-copy** = worktree at parent HEAD + materialize staged/unstaged/untracked (+ignored if opted); **clean-from-HEAD** = worktree at parent HEAD, no materialization. Both anchor to the *parent's* HEAD — never `origin/main` — because the fork must continue the parent's work, not restart from upstream. (A from-`origin/<default>` mode is a possible third mode, deliberately out of scope of the matrix; flag for Phase 3.)

| Detected parent state | Duplication strategy (both modes) | Exact-copy extras | Verification (validated, not assumed) |
|---|---|---|---|
| **Normal repo, on a feature branch** | `git worktree add -b <new-branch> <path> HEAD` from repo root; anchor = parent HEAD | materialize §2.2 | see verification ladder below |
| **Normal repo, on `main`/default branch** | Same mechanics. The fork branch protects `main` by construction (work continues on `fork/*`); parent stays on main untouched | same | same + assert fork branch ≠ default branch |
| **Detached HEAD** | `worktree add -b` from the detached commit works identically (anchor is a commit, not a ref) | same | same; record that parent was detached in fork metadata |
| **Already inside a linked worktree** | Resolve project root via `GetWorktreeBaseRoot`; anchor to *this worktree's* HEAD (not main's); place fork per location scheme — mirroring the parent's observed placement pattern is the Phase 3 lean | same | same + assert `git -C <fork> rev-parse --git-common-dir` == parent's common dir (same repo family) |
| **Bare repo project root (bare-at-root or `.bare/` layout)** | Worktree placed as child of project root (agent-deck's bare-visibility rule); anchor = the *parent worktree's* HEAD if invoked from one, else bare HEAD | same | same |
| **Mid rebase/merge/cherry-pick/revert/bisect** | **Refuse** with abort hint (§2.1 step 4). `git diff` output mid-operation is not a faithful state snapshot | n/a | n/a |
| **Branch/worktree/path collision** | **Refuse** before mutation; suffix `-2…` only in auto-name mode | n/a | n/a |
| **Not a git repo at all** | Refuse (v1 is git-worktree isolation by definition); agent-deck's #1185 degrade-to-no-worktree is a session-manager behavior that doesn't transfer — without a worktree there is nothing for agent-fork to hand off | n/a | n/a |
| **Submodules present** | Proceed + warn (copied as opaque dirs' untracked files, not recursed) — agent-deck's choice; adequate for v1 | same | warn text in output |
| **File state transfer semantics** | staged→`apply --index`, unstaged→`apply`, untracked→byte copy, symlinks verbatim, perms preserved | ignored files = opt-in second `ls-files` pass | — |

**Verification ladder** (agent-fork's improvement over agent-deck, which verifies only in its test suite — production path assumes success from exit codes, §2 extraction finding "no post-creation verification, structurally"):

1. `git -C <fork> rev-parse --verify HEAD` == recorded parent anchor commit.
2. `git -C <fork> rev-parse --abbrev-ref HEAD` == expected new branch.
3. `git worktree list --porcelain` (at root) contains the fork path ↔ branch pair.
4. **Exact-copy mode:** `git -C <fork> status --porcelain=v1 -z` **byte-equal** to `git -C <parent> status --porcelain=v1 -z` (this is agent-deck's *documented but unenforced* contract — cheap to actually enforce; ignored files excluded from comparison unless `with_ignored`, in which case compare `status --porcelain --ignored` sets).
5. **Clean-from-HEAD mode:** fork status output is empty.
6. Parent-untouched assert: parent's `status --porcelain -z` before == after (detects any accidental parent mutation; agent-deck guarantees this by construction — read-only diff/ls-files — but never checks).

---

## 5. Per-agent session-fork mechanics — v1 targets (1b)

### 5.0 Local ground truth `[BIN]`/`[FS]` (verified 2026-07-21 on this machine)

**Claude Code 2.1.216**
- Fork = resume + new identity: `claude --resume <parent-uuid> --fork-session` ("when resuming, create a new session ID instead of reusing the original"; valid with `--resume` or `--continue`).
- `--session-id <uuid>` pins the new session's UUID (must be valid UUID) — enables pre-computing the fork's id; `-n/--name <name>` sets display name (prompt box, `/resume` picker, terminal title).
- Sessions stored per-cwd: `~/.claude/projects/<munged-cwd>/<session-uuid>.jsonl` `[FS]` (munging: `/` and `.` → `-`). This is the root of the cross-directory question (§5.1 Q1).
- **In-session env** `[BIN]`: `CLAUDECODE=1`, `CLAUDE_CODE_SESSION_ID=<running session uuid>`, `AI_AGENT=claude-code_2-1-216_agent` (identity + version in one var), `CLAUDE_CODE_ENTRYPOINT=cli`, `CLAUDE_CODE_EXECPATH=<install path>`. Host-detection *and* self-session-id discovery are solved for Claude Code by env alone.

**Codex CLI 0.144.6**
- `codex fork [SESSION_ID] [PROMPT]` — first-class subcommand; UUID arg forks that session; `--last` = most recent; picker default; `--all` disables **cwd filtering** (⇒ pickers are cwd-scoped by default; an explicit UUID is expected to bypass — confirm §5.1 Q4). Optional `PROMPT` positional seeds the first user message.
- `codex resume [SESSION_ID|name]` — resume accepts session **names**; `archive`/`delete`/`unarchive <id|name>`.
- `-C/--cd <DIR>` global flag sets the agent's working root → candidate one-liner: `codex fork <uuid> -C <worktree>` (validate flag position + behavior, §7).
- Sessions on disk `[FS]`: `~/.codex/sessions/YYYY/MM/DD/rollout-<ISO-timestamp>-<uuid>.jsonl` (nested date-partitioned — confirmed locally), plus `~/.codex/archived_sessions`, `history.jsonl`.
- No obvious `CODEX_*` session env var — self-discovery is the key open question (§5.1 Q3).

**v2 targets (high level)** `[BIN]`: Pi 0.80.6 — `--fork <path|id>`, `--session-id <id>` (create-if-missing), `--session-dir <dir>`, `-n/--name`: fork surface arguably richer than v1 targets. OpenCode 1.18.3 — `--fork` with `-c`/`-s <sessionID>`, `opencode session` subcommand, `export`/`import`. Kilo Code 7.4.11 — OpenCode-lineage twin surface plus `--cloud-fork`.

### 5.1 Deep-research findings (Q1–Q6) `[WEB]`

Provenance: 103-agent deep-research run, 21 sources, 25 claims through 3-vote adversarial verification → **23 CONFIRMED, 2 refuted, 0 left unverified**. Full findings: `research/topics/01-session-fork-resume-cli-mechanics/00-fork-resume-mechanics.md`; distilled recipes: `research/reference/agent-session-fork-cli-recipes-2026-07-21.md`; decision record: `.../DECISION.md`.

**Q1 — Claude cross-directory fork: RESOLVED IN OUR FAVOR.** `--resume <id>` lookup is officially scoped to the current project directory **and its git worktrees** (docs verbatim), live-tested in both directions on 2.1.216. The worktree-fork flow needs **no session-file copying**. Unrelated directories fail ("No conversation found…") — there the only supported path is cd-then-resume (open FRs #58591/#65945 prove no in-place mechanism). Bonus: since 2.1.118, `--resume` also finds sessions that registered the cwd via `/add-dir`. Caveat: worktree scoping was broken on older versions (#48835) — warn below ~2.1.1xx.

**Q2 — Claude fork semantics.** `--fork-session` = **full-history copy** (not summary) under a new ID; parent intact; two independently resumable sessions. `--session-id` pinning of the fork's UUID works non-interactively **since v2.0.73** (live version-boundary-tested; without `--fork-session` it hard-errors). Transcript path + `[^a-zA-Z0-9]→'-'` encoding confirmed via binary strings; format vendor-declared **unstable** → .jsonl-copy is last-resort only. Gotchas: session-scoped permission approvals do **not** carry into a fork; resuming without forking in a second terminal **interleaves** both into one transcript (the exact hazard agent-fork's flow avoids). `-n/--name` combination: untested (experiment E1).

**Q3 — Codex self-discovery: SOLVED.** **`CODEX_THREAD_ID`** is injected into agent-executed shells since **rust-v0.95.0** (2026-02-04, PR #10096, closing #8923) and is present at 0.144.x — refuting the "no env var" lead (true only ≤0.94.x). Pre-0.95.0 fallback: own-process-ancestry → open-fd probe (§3.2) → newest-rollout scan. Session *enumeration* (if ever needed): the App Server JSON API (`thread/list` …), the officially recommended tool-builder surface.

**Q4 — Codex fork.** Timeline: `resume` ≥0.36.0 (2025-09-15) · **`fork` wired ≥0.81.0** (2026-01-14, PR #8994; documented **Stable** today, though never mentioned in the official changelog — GitHub releases are the only provenance) · `fork --last` cwd-filter bug fixed ≥0.129.0. Fork **preserves** the parent transcript. Two scripting hazards: (a) whether an explicit SESSION_ID bypasses the default cwd filtering is **undocumented** (experiment E2); (b) a **TUI cwd-change prompt** fires when the launch dir ≠ the session's recorded cwd (PR #12040; prompt strings present in the 0.144.6 binary) — a pasted cross-directory fork likely stops at "Use session directory / Use current directory". Benign for a human-paste flow but must be documented in agent-fork's emitted output; whether `-C` pre-empts it is untested.

**Q5 — fallback/handoff conventions: UNANSWERED.** No claims survived adversarial verification (deferred — see research/CLAUDE.md defer log). Phase 2 designs the fallback from first principles: fresh named session + handoff file written into the worktree, seeded via Claude `--append-system-prompt-file` / Codex `PROMPT` positional — all to be validated then.

**Q6 — v2 landscape: web pass produced nothing verified**; the local-binary evidence in §5.0 stands as the v2 baseline. agent-deck has no Kilo support at all — Kilo is greenfield for agent-fork v2.

**Refuted (do not re-cite):** "v2.1.94 changed worktree-resume behavior" (0-3); "Codex had no programmatic session id as of 0.79.x" (0-3 — false since 0.95.0).

### 5.2 Resulting v1 launch-command recipes (research conclusion, pre-design)

```bash
# Claude Code (host session discovered via $CLAUDE_CODE_SESSION_ID):
cd '<worktree>' && claude --session-id "<pre-generated-uuid>" --resume <parent-id> --fork-session -n '<derived-name>'   # -n pending E1

# Codex (host session discovered via $CODEX_THREAD_ID, ≥0.95.0):
cd '<worktree>' && codex fork <parent-thread-id>          # -C variant + cwd-prompt behavior pending E2
```

Minimum-version matrix: Claude — pinned-ID fork ≥2.0.73, reliable worktree-scoped resume ≥~2.1.1xx; Codex — fork ≥0.81.0, `CODEX_THREAD_ID` ≥0.95.0, trustworthy `--last` ≥0.129.0. agent-fork should **preflight** installed versions (agent-deck instead emits-and-recovers; wrong trade-off for a print-for-human CLI) and, for Codex, verify the parent rollout file is flushed (`sessions/*/*/*/rollout-*-<id>.jsonl`) before emitting — agent-deck's #756 lesson.

---

## 6. Flox dev environment (#1302) `[SRC]`

`/Users/stevemorin/c/agent-deck/.flox/env/manifest.toml`, schema 1.12.0. Port-relevant patterns:

- **Tiered `[install]`** ordered by need: build/lint/format → hook validators → behavioral-test runtimes → release tooling → agent CLIs.
- **`pkg-group` isolation**: `claude-code`, `codex`, `opencode` live in a dedicated `agents` group — "they track fast-moving nixpkgs revisions and would otherwise over-constrain the stable toolchain." Directly reusable: agent-fork's tests need those same CLIs, same churn problem.
- **Toolchain pinning via `[vars]`** (`GOTOOLCHAIN` redirect because nixpkgs lacked the exact Go patch release) — Python analog: pin `python3.version`, drive the rest with `uv`.
- **`on-activate` appends (not prepends) PATH** so Flox-provided tools win over host installs while `~/.local/bin` etc. remain fallbacks.
- Python-project translation: `python3` (pinned) + `uv` + `just` + `git` in tier 1; `claude-code`/`codex`/`opencode` in an `agents` group for integration tests; `[options].systems` covering both darwin + linux arches.

---

## 7. Live experiments still required `[OPEN]`

(Consolidated with the deep-research run's closing list. Q1's worktree-scoping test was already run live by the research pass — dropped from this list.)

- **E1 — Claude flag combo**: `--resume <id> --fork-session --session-id <pre-pinned> -n <name>` in one non-interactive invocation — does any flag silently no-op?
- **E2 — Codex cross-cwd fork**: `codex fork <explicit-uuid>` from a foreign cwd (does explicit ID bypass cwd filtering? #20165 suggests yes for resume); `-C <worktree>` behavior; does the TUI cwd-change prompt still fire with `-C`? Goal: a fully non-interactive (or documented-one-prompt) paste command.
- **E3 — Claude fork E2E**: full paste command in a real worktree; assert full context recall + fresh UUID + parent transcript untouched.
- **E4 — .jsonl-copy last-resort** (unrelated-directory fallback): copy into a *different encoded project dir* and resume — smoke test per Claude version (agent-deck only validated same-path/different-config-root).
- **E5 — State fidelity**: run the §2.2 sequence on a repo with staged+unstaged+untracked+ignored+symlink+exec-bit files; assert byte-equal porcelain status (the §4 verification ladder).
- **E6 — Codex pre-0.95.0 fallback** (only if we decide to support old Codex): two concurrent sessions in one cwd — is newest-rollout ambiguous, and does the process-fd probe disambiguate?

---

## 8. Inputs to Phase 2/3 (flagged, not decided)

1. **Default posture**: agent-deck TUI = comprehensive-by-default vs agent-deck CLI = everything-opt-in — agent-fork is a CLI *invoked like a TUI gesture* (one word inside a session), which cuts both ways. §1.2.
2. **`with_ignored` default**: upstream's #1354 reversal is strong evidence for OFF + nested-toggle shape.
3. **Separate toggles (`with_state`/`with_ignored`) vs modes (`exact-copy`/`clean-from-HEAD`)**: agent-deck's resolved-plan struct is toggles all the way down; modes would be sugar over it.
4. **Branch/location schemes**: adopt `fork/` prefix + sibling `<repo>-<branch>` default, or mirror-parent-pattern when parent is itself a worktree (needs a mirror-detection heuristic — not in agent-deck).
5. **Name source**: agent-deck slugs the *session title*; agent-fork has no title — candidates: positional arg, task-derived slug, timestamp.
6. **Runtime verification ladder** (§4) — include by default (`--no-verify` escape hatch)?
7. **`.worktreeinclude` + setup-hook conventions**: port, rename (`.agent-fork/…`), or drop for v1?
8. **Session-name derivation**: `<parent-name>-fork-N`? Claude `--name` + Codex named-session support both exist `[BIN]`.
