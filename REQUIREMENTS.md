# REQUIREMENTS.md — `agent-fork` Phase 2

**Date:** 2026-07-21 · **Status:** Phase 2 gate deliverable (requirements + proposed architecture — no implementation)
**Inputs:** `RESEARCH.md` (Phase 1, reviewed), agent-deck prior art (behavioral reference only — attribution requirement removed by owner amendment 2026-07-22, see REQ-37), **CLI Design Standard v1.4.14** (pinned; conformance tracked in `CONFORMANCE.md`).
**Profile/tier:** Small-CLI **verb-first** (Appendix A — criteria check in §3.1) · **publishable** tier · applicability map in `CONFORMANCE.md`.
**Notation:** `REQ-*` = requirement (MUST unless marked SHOULD/MAY) · `D#` = open decision deferred to Phase 3 (§10) · `R#.#` = standard rule citations.

---

## 1. Product scope

One word inside a running coding-agent session forks the work: new branch + new worktree carrying the current file state, verified, and the **exact paste command** to continue in a forked session of the same agent in a new terminal. v1 agents: **Claude Code, Codex**. Isolation: **plain git worktree**. The tool cannot open terminals — the human pastes the final command (clipboard assist is the stretch).

Out of scope for v1: Docker/Flox isolation, Pi/OpenCode/Kilo (v2), Windows, jj backend, launching the forked session itself.

---

## 2. Architecture — skill ↔ CLI split

Two artifacts, one name (locked): an **agent skill** (`agent-fork`) and a **Python CLI** (`agent-fork`).

- **REQ-01** The **CLI owns all mechanics**: git-state detection, worktree+branch creation, state materialization, verification, launch-command construction/emission, cleanup. It is fully usable by a human in a bare terminal with no skill involved (R8.2 non-interactive path).
- **REQ-02** The **skill owns orchestration inside the agent session**: detect the host agent from environment signals, capture the parent session ID, invoke the CLI with explicit `--agent`/`--parent-session` values, and render the returned paste command prominently to the user. The skill never re-implements git logic.
- **REQ-03** The CLI **self-detects as fallback** when `--agent`/`--parent-session` are absent: it runs as a child of the agent process, so the same env signals are visible to it (`CLAUDECODE=1` + `CLAUDE_CODE_SESSION_ID`; `CODEX_THREAD_ID`). Detection ladder per agent in §5. Explicit flags always win (R5.1 spirit).
- **REQ-04** The skill↔CLI contract is the CLI's **machine output** (`-o json`, R4.2/R7.2): a stable JSON result object (§3.6). The skill parses JSON, never human tables.
- **REQ-05** Skill distribution: placed for both Claude Code and Codex per the existing skill-placement conventions; the skill's only hard dependency is the CLI being on `PATH` (it reports a clear install hint when missing).

---

## 3. Command surface (interface spec — cli-standards plan-mode deliverable)

### 3.1 Identity & profile

- Binary: `agent-fork` (lowercase, hyphenated — R1.4/R1.5). PyPI name `agent-fork` **available** (checked 2026-07-21, PyPI + TestPyPI; only a real publish is definitive).
- **Small-CLI verb-first profile** (Appendix A) — criteria: (1) fixed set ≤ ~7 commands ✔ (§3.2 tree = 7); (2) single implicit resource (*the fork*) ✔; (3) verbs read naturally without a noun ✔. Migration trigger acknowledged: a second resource type forces noun-verb in the next major (R9.3).
- Standard pinned: **v1.4.14**.

### 3.2 Command tree

```
agent-fork
├── fork [NAME]            # THE action: prep fork + emit paste command   (D1: bare-invocation behavior)
├── cleanup <TARGET>       # remove a fork's worktree (+branch unless kept)  — destructive (§6)
├── list                   # enumerate forks this tool created           (D10: in v1?)
├── doctor                 # env/agent-CLI/version/rollout diagnostics (R9.10)
├── config view|get|set|validate   # effective config + introspection (R5.7/R5.8)
├── completion <shell>     # bash/zsh/fish (R9.1)
└── help [command]
```

- **REQ-06** Bare `agent-fork` → help on stdout, exit 0 (R7.9 MUST). **D1 DECIDED 2026-07-21**: no bare-invocation fork — the *skill* delivers the one-word UX by running `agent-fork fork …`; the CLI stays fully conforming.
- **REQ-07** `cleanup` is a domain verb (R2.1 allows established domain verbs; nearest core verb `delete` covers less — cleanup removes worktree, optionally branch, and prunes). Name locked by kickoff; recorded in `CONFORMANCE.md`. (D13 if Phase 3 wants `delete`/`prune` instead.)

### 3.3 `fork` — arguments & flags

Positional `[NAME]` = the fork's identity (R2.3): seeds branch slug, worktree dir, and derived session name. Optional; when absent the name is auto-derived (D4).

| Flag | Short | Type | Default | Purpose |
|---|---|---|---|---|
| `--agent <claude\|codex>` | — | enum | self-detect | Host agent (skill passes explicitly; REQ-03) |
| `--parent-session <id>` | — | str | from env | Parent session/thread ID |
| `--branch <name>` | — | str | `<branch_prefix><slug>` | Explicit fork branch |
| `--worktree-dir <path>` | — | path | location scheme (D5) | Explicit worktree destination |
| *state model:* `--no-with-state` | — | bool | exact-copy default (D2/D3) | Clean-from-HEAD vs carry state (`--clean` alias deferred to v1.1+, D2) |
| `--with-ignored` | — | bool | **off** (#1354 evidence) | Also copy gitignored files (implies state carry) |
| `--dry-run` | — | bool | off | Print full plan incl. the would-be paste command; no mutation (R4.3/R8.6) |
| `--no-verify` | — | bool | verify **on** (D8) | Skip the §4 verification ladder |
| `--copy` / `--no-copy` | — | bool | D9 | Clipboard assist (stretch) |
| **`--force`** | — | bool | off | **Amended 2026-08-08 (owner, test-architecture spec A14):** override the `PRODUCT_GIT_MIN` refusal only (stderr warning; verify still on); never overrides correctness refusals |
| `--output` / `--json` | `-o` | enum | `table` | R4.1 result-output tier |

- **REQ-08** All boolean-true defaults get documented `--no-<foo>` negations (R3.6). No prefix abbreviation (R3.10). Long flags kebab-case (R3.3); no short flags beyond the reserved set (R3.4).
- **REQ-09** `fork` is **not** destructive (creates only) — no confirmation prompt. Collisions and unsafe parent states are **refusals**, not prompts (§4, exit 5).

### 3.4 Standard options & exit codes

- **REQ-10** Required global core implemented verbatim (R4.1): `-h/--help`, `-V/--version`, `-v/--verbose` (repeatable), `-q/--quiet`, `--config`, `--debug`. Result-output (`-o/--output`, `--json`) on every command that emits result data (`fork`, `cleanup`, `list`, `doctor`, `config view`). Verbosity ladder per R4.4. `--version` prints `agent-fork <semver>` (R4.6).
- **REQ-11** Exit codes (R6.1/R6.2), documented in help + error catalog (R7.12):

| Code | agent-fork meaning |
|---|---|
| 0 | Fork prepped + verified (or cleanup done, or dry-run printed) |
| 1 | Runtime failure (materialize failed → **after** rollback per §4; unreadable repo; parent-untouched assert tripped) |
| 2 | Usage error; also: prompt required but `--no-input` (R8.2) |
| 3 | Not found: parent session/rollout not on disk; cleanup TARGET unknown; unknown `--agent` |
| 4 | *(reserved — no auth concept; N/A)* |
| 5 | Conflict/precondition: branch or worktree-path collision (incl. the atomic worktree/branch collision loss in a guard race — caught and mapped to 5 with `conflict_branch_exists` per spec A1; nothing left behind; rollback runs); parent mid-rebase/merge/etc.; cleanup guard refused (dirty/unpushed without `--force`) |
| 130/143 | SIGINT/SIGTERM, clean rollback of partial work first (R9.6) |

### 3.5 Configuration & environment

- **REQ-12** TOML config named per R5.2: project `.agent-fork/agent-fork_config.toml` (walk-up, stop at repo boundary), user `$XDG_CONFIG_HOME/agent-fork/agent-fork_config.toml`, system `$XDG_CONFIG_DIRS/...`. Precedence chain documented verbatim (R5.1); `--config` replaces discovery. XDG throughout (R5.3); state (fork registry for `list`/`cleanup`) in `$XDG_STATE_HOME/agent-fork/` with locking (R5.8). **Amended 2026-08-08 (owner, test-architecture spec A6):** In a linked worktree the walk-up boundary is the worktree's own root.
- **REQ-13** Final `[fork]` schema (**D7 DECIDED 2026-07-21** — see DESIGN-DECISIONS.md):

| Key | Default | Notes |
|---|---|---|
| `with_state` | `true` (tri-state) | agent-deck semantics incl. explicit-false honored |
| `with_ignored` | `false` (tri-state) | implies `with_state`; #1354 default; flag `--with-ignored` |
| `branch_prefix` | `"fork/"` | whitespace → default |
| `worktree_location` | `"sibling"` | `sibling` \| `central` (XDG data) \| `subdirectory` \| path template; explicit value suppresses the mirror-parent heuristic (D5 note) |
| `verify` | `true` | §4 ladder (D8: on by default) |
| `copy` | `false` | clipboard (D9: ships in v1) |

  Plus per-agent tables (**D11 DECIDED — ships in v1**): `[agents.<name>] extra_args = []` — array of strings appended to that agent's emitted command, each element individually shell-quoted; config-only (no flag equivalent); visible in `--dry-run` and `-o json` output. No `session_name_template` key exists (D6: session name = fork name).
  **Dropped from agent-deck:** `docker` (out of scope), `worktree` toggle (v1 fork *is* a worktree — locked), `inherit_from_parent` (no parent-session runtime to mirror in a standalone CLI).
  **Amended 2026-08-08 (owner, test-architecture spec A12):** Cross-source conflicts: an explicit flag beats config **and suppresses dependent config settings** (config `with_ignored=true` + `--no-with-state` → no state carried). The RESEARCH §1.1 implication rule applies only within a single source.
- **REQ-14** Env vars: curated `AGENT_FORK_*` subset only (R5.4) — `AGENT_FORK_CONFIG`, `AGENT_FORK_OUTPUT`; flag/env/config name parity via deterministic transform (R3.8). Host-agent env (`CLAUDE_CODE_SESSION_ID`, `CODEX_THREAD_ID`, …) is **read**, never required when flags are given.
- **REQ-15** No secrets accepted anywhere on argv (R5.5). Note: `--with-ignored` may *copy* secret-bearing files (`.env`) between working trees — a documented behavior note + the off-default, not a secrets-handling feature.

### 3.6 Output contract

- **REQ-16** stdout = requested result only; all progress/diagnostics/prompts → stderr (R7.1/R7.4). Human default: compact summary + the **paste command as the final stdout block**. TTY never changes format (R7.3).
- **REQ-17** `-o json` result object (stable within major, open schema per R7.2) — minimum fields: `agent`, `parent_session_id`, `fork.branch`, `fork.worktree`, `fork.anchor_commit`, `fork.mode` (state-carry booleans), `verification` (per-check results), `command` (the paste command string), `notices[]`, and for Codex the `cwd_prompt_expected` boolean (RESEARCH §5.1 Q4). Errors: single JSON object `{"error":{"code","message"}}` on stderr under any machine format (R7.8); stable codes cataloged: `conflict_branch_exists`, `parent_mid_operation`, `session_not_found`, `verify_failed`, **`repo_no_commits` (spec A2)**, **`unmerged_index` (spec A4)**, **`registry_busy` (spec A13)**, … (R7.12).
- **REQ-18** `--dry-run` output identifies every planned mutation (branch, worktree path, files-to-carry counts, the paste command) and states validation was local (R8.6).

---

## 4. Duplication + verification pipeline

Port of RESEARCH §2 (agent-deck `forkWithStateWorktree` + `MaterializeWipFromParent`), with runtime verification added (agent-deck's documented-but-unenforced contract):

- **REQ-19 Guards (refuse before any mutation, exit 5):** branch exists · branch already has a worktree · worktree path exists · parent mid `rebase`/`merge`/`cherry-pick`/`revert`/`bisect` (error includes the exact abort hint) · **Amended 2026-08-08 (owner, test-architecture spec A2):** unborn HEAD (zero-commit repo) → refuse, code `repo_no_commits`, message contains remedy (make an initial commit and re-run) · **Amended 2026-08-08 (owner, test-architecture spec A4):** unmerged index entries (`git ls-files -u` non-empty, markers present or not) → refuse, code `unmerged_index`, message lists conflicted paths + remedy. Git-only guard: not-a-repo → error (agent-deck's degrade-to-no-worktree does not transfer; a fork without a worktree has nothing to hand off).
- **REQ-20 Anchor:** resolve `HEAD^{commit}` at the **parent's own path**; create worktree+branch atomically at that commit; track whether the branch was newly created (rollback precision). Repo-root resolution must handle: plain repo, linked worktree, bare-at-root, `.bare/` layout (RESEARCH §2.3 matrix).
- **REQ-21 Materialize (exact-copy mode):** the verbatim sequence — staged diff `--binary --cached` → `apply --index`; unstaged diff → `apply`; untracked via NUL-delimited `ls-files --others`; ignored via the second `--ignored` pass only when enabled. Symlinks verbatim, permission bits preserved, parent strictly read-only. **Amended 2026-08-08 (owner, test-architecture spec A3):** Intent-to-add entries are supported: cached diff uses `--ita-invisible-in-index`; ITA paths transported via `git apply --intent-to-add`; verification is ITA-aware.
- **REQ-22 Rollback:** on materialize failure, remove worktree (+ branch only if created), report `cleaned up` or emit the exact manual-recovery command when cleanup itself fails. Signals mid-pipeline trigger the same rollback (exit 130/143).
- **REQ-23 Verify (default on, `--no-verify` opt-out — D8):** ladder from RESEARCH §4 — anchor commit matches · branch matches · `git worktree list` registers the pair · exact-copy: child `status --porcelain -z` byte-equal to parent's (ignored-aware when `--with-ignored`) · clean mode: empty status · parent status before == after. Any failure → exit 1 with rollback (never hand the user an unverified fork).
- **REQ-24 (SHOULD)** `.worktreeinclude` and a post-create setup hook (`.agent-fork/worktree-setup.sh`) as non-fatal steps, agent-deck-compatible in spirit (D7 scope call).
- **REQ-25 (SHOULD)** Submodules: warn-only, copied opaquely, documented.

---

## 5. Per-agent launch commands (v1)

- **REQ-26 Detection ladder** — Claude: `CLAUDECODE=1` ∧ `CLAUDE_CODE_SESSION_ID` (version from `AI_AGENT`). Codex: `CODEX_THREAD_ID` (≥0.95.0). **Amended 2026-08-08 (owner, test-architecture spec A7):** Pre-0.95.0 Codex fallback ladder removed: detection is `CODEX_THREAD_ID`-only; below-matrix versions refuse per D14/REQ-29. Ambiguity (both/none, no flags) → exit 3 with a clear message; skill always passes explicit flags anyway (REQ-02).
- **REQ-27 Preflight (emit-for-human ⇒ check first, not emit-and-fail):** installed agent CLI present + version ≥ matrix (Claude: pinned-ID fork ≥2.0.73, warn <~2.1.1xx re #48835; Codex: fork ≥0.81.0, env ≥0.95.0) · Codex: parent rollout file flushed on disk (glob `sessions/*/*/*/rollout-*-<id>.jsonl`) before emitting (#756 lesson).
- **REQ-28 Templates** (single-line, fully shell-quoted — uniformly, unlike agent-deck's two unquoted warts):
  - Claude: `cd '<worktree>' && claude --session-id "<pre-generated-uuid>" --resume <parent-id> --fork-session -n '<derived-name>'` (`-n` inclusion pending experiment E1).
  - Codex: `cd '<worktree>' && codex fork <parent-thread-id>` (`-C` variant + cwd-prompt handling pending E2; until then the emitted output documents the possible one-time prompt and the right answer: *current directory*).
- **REQ-29 Preflight failure = refusal (D14 DECIDED 2026-07-21 — owner overrode the fallback-ladder recommendation):** when native fork is impossible (CLI below the version matrix, Codex rollout not flushed, agent undetectable), v1 **refuses with a diagnosis** — what was detected, which requirement failed, the minimum version/missing artifact, and a `doctor` pointer — and creates **nothing** (fail before mutation). Never emit a command known to fail. The fresh-session + HANDOFF.md degradation ladder is deferred to v1.1+ (with the Q5 research pass).
- **REQ-30** Session naming (**D6 DECIDED**): the session display name **is the fork name**; Claude gets `-n '<fork-name>'`; Codex names are a resume-time concept — the identity lives in the branch/worktree, with optional rename guidance in the emitted output. `[agents.<name>] extra_args` (REQ-13) are appended to the templates in REQ-28, individually quoted.

---

## 6. `cleanup` semantics & safety

- **REQ-31** `agent-fork cleanup <TARGET>` (fork name, branch, or worktree path): removes the worktree (`git worktree remove` + prune), deletes the fork branch **unless** `--keep-branch`, updates the fork registry. Never touches the parent checkout; refuses targets it didn't create unless `--force` (registry-based ownership check — D12).
- **REQ-32 Guards (exit 5 unless `--force`):** uncommitted changes in the fork worktree · commits not on any upstream (unpushed) · target is the current working directory. **Amended 2026-08-09 (owner, pre-merge review):** `--force` overrides the dirty/unpushed guards only (D12; the invoking-cwd refusal is not overridable). It does **not** replace consent (R8.1).
- **REQ-33 Consent:** TTY prompt (stderr) naming exactly what will be removed; `--yes` for non-interactive consent; `--no-input` → fail exit 2 when consent/guard flags are missing (R8.2). `--dry-run` prints the removal plan (R8.6).
- **REQ-34** Session files are **never** deleted (Claude/Codex own them); cleanup output notes the fork session remains resumable and how to archive it (e.g. `codex archive`).

---

## 7. Distribution & release (publishable tier)

- **REQ-35** Python ≥3.11 (stdlib `tomllib`), minimal runtime deps (`platformdirs`; clipboard via `pbcopy`/`xclip`/OSC52 shell-outs, not a dependency — D9). Single package, console-script `agent-fork`.
- **REQ-36** Channels, difftree-style: **PyPI** `agent-fork` (**reserved 2026-07-21** on PyPI + TestPyPI as `0.0.0.dev0` placeholders — verified via registry check), installable via `uv tool install`/`pipx`; **Homebrew tap** (smorinlabs); **Nix/Flox**. Release automation per the org's release-please pattern; merge-commit strategy per global git policy.
- **REQ-37** License: MIT (© 2026 Steve Morin). **Amended 2026-07-22 (owner):** the agent-deck attribution requirement is removed — no `NOTICE` file, no upstream headers, no derivation statement in `LICENSE`. Consequence for the build: agent-deck serves as a **behavioral reference only** (via RESEARCH.md's documented semantics, command sequences, and detection matrix); implementation is written fresh from that documentation, never translated from agent-deck source, keeping the codebase outside MIT's notice-preservation obligation.
- **REQ-38** Publishable-tier obligations: SemVer interface contract (R9.3) · deprecation policy (R9.2) · UTF-8 + locale-independent machine output (R9.4) · clean SIGINT/SIGPIPE/SIGTERM (R9.6) · `doctor` (R9.10 — checks: **Amended 2026-08-08 (owner, test-architecture spec A9):** git version vs `PRODUCT_GIT_MIN` (named constant; value fixed by the implementation-phase git-feature audit), **Amended 2026-08-08 (owner, test-architecture spec A14):** failing checks → non-zero exit; agent CLIs found + versions vs matrix, env signals visible, config valid, XDG paths writable) · error catalog (R7.12) · **conformance fixtures in CI** (R9.14; scaffold at implementation start, not this run) · telemetry: **none** (R9.7 posture: no data collection, stated in README) · self-update: none (package managers own it; R9.9 N/A).
- **REQ-39** Dev environment: Flox manifest following the RESEARCH §6 pattern (pinned python + uv + just tier-1; `agents` pkg-group with claude-code/codex for integration tests). Repo bootstrap: uv + ruff + ty + just per the global Python-project conventions.

---

## 8. Non-functional

- **REQ-40** Zero network calls at runtime (fully local tool). Typical fork ≤ ~2s on a normal repo; `--with-ignored` may be slow — progress on stderr (R7.4) and the #1354 rationale documented.
- **REQ-41** Concurrency safety: registry/state writes atomic + locked (R5.8); two simultaneous forks of one repo must not corrupt each other (the mid-mutation collision loss is classified as exit 5 per spec A1; nothing left behind; rollback runs). **Amended 2026-08-08 (owner, test-architecture spec A13):** Registry locking: OS advisory lock (self-clearing on process death); contending process waits ≤ ~5s then fails with `registry_busy`.
- **REQ-42** Every emitted shell command is quoted defensively (shlex.quote equivalents) — REQ-28 note.
- **REQ-43** Testability: **Amended 2026-08-08 (owner, test-architecture spec A10):** the CLI resolves `git` via PATH at each invocation — never a cached absolute path (canaried in the test suite).

---

## 9. Test-first plan (implementation-session input)

TDD per house process: the §4 pipeline is specified by an integration harness on disposable fixture repos (staged+unstaged+untracked+ignored+symlink+exec-bit files; each RESEARCH §4 matrix row = a test case; verification-ladder assertions are the test oracle). **Amended 2026-08-08 (owner, test-architecture spec A8):** Experiments E1–E3 run as gated integration tests against real CLIs (E4 retired until v1.1 per spec A8; E5 absorbed into the §4 pipeline TDD; E6 tombstoned with A7) (skipped when binaries absent — Flox `agents` group provides them in dev/CI). Conformance fixtures (R9.14) assert help/streams/exit-code contracts. **Amended 2026-08-08 (owner, test-architecture spec A11):** Implementation-phase TDD and suite runs are dispatched to subagents per the house SDD model matrix; the driving session orchestrates.

---

## 10. Design decisions — ALL DECIDED 2026-07-21 (Phase 3 closed)

Full record with rationale, notes, and agent-deck reconciliation: **`DESIGN-DECISIONS.md`**. Summary (⚠ = owner went against the recommendation):

| D# | Outcome |
|---|---|
| D1 | Bare invocation → help, exit 0; skill owns the one-word UX (REQ-06) |
| D2 | agent-deck toggles `--no-with-state` / `--with-ignored` |
| D3 | Exact-copy default; gitignored addable via flag or config |
| D4 | Optional positional NAME; auto `<branch-slug>-<mmdd>` fallback |
| D5 | Sibling + mirror-parent; config override `sibling`/`central`/`subdirectory`/template |
| D6 | Session name = fork name |
| D7 | Trimmed config schema (REQ-13 final) |
| D8 | Verification on by default + `--no-verify` |
| D9 | Clipboard `--copy` in v1, OSC52-first |
| D10 | `list` ships in v1 |
| D11 | ⚠ `[agents.<name>] extra_args` ships in v1 (REQ-13/REQ-30) |
| D12 | Cleanup registry-scoped; `--force` extends targets + overrides guards |
| D13 | Verb stays `cleanup` (waiver confirmed) |
| D14 | ⚠ Preflight failure → refuse with diagnosis; handoff ladder deferred to v1.1+ (REQ-29) |

Queued for the implementation session: PROJECTS.md project creation (house process), git init + worktree discipline for this repo, live experiments E1–E3 (E4 retired per spec A8), conformance fixture scaffold (R9.14).
