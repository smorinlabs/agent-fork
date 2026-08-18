# REQUIREMENTS.md — `agent-fork` Phase 2

**Date:** 2026-07-21 · **Status:** Phase 2 gate deliverable (requirements + proposed architecture — no implementation)
**Inputs:** `RESEARCH.md` (Phase 1, reviewed), agent-deck prior art (behavioral reference only — attribution requirement removed by owner amendment 2026-07-22, see REQ-37), **CLI Design Standard v1.4.14** (pinned; conformance tracked in `CONFORMANCE.md`).
**Profile/tier:** Small-CLI **verb-first** (Appendix A — criteria check in §3.1) · **publishable** tier · applicability map in `CONFORMANCE.md`.
**Notation:** `REQ-*` = requirement (MUST unless marked SHOULD/MAY) · `D#` = open decision deferred to Phase 3 (§10) · `R#.#` = standard rule citations.

---

## 1. Product scope

One word forks the work: a new branch + worktree carrying the current file state,
verified, with adaptive integration when invoked inside a supported coding-agent
session and a direct `cd` handoff in an ordinary terminal. v1 agents: **Claude
Code, Codex**. Isolation: **plain git worktree**. The tool cannot open terminals
— the human pastes the final command.

Out of scope for v1: Docker/Flox isolation, Pi/OpenCode/Kilo (v2), Windows, jj backend, launching the forked session itself.

---

## 2. Architecture — skill ↔ CLI split

Two artifacts, one name (locked): an **agent skill** (`agent-fork`) and a **Python CLI** (`agent-fork`).

- **REQ-01** The **CLI owns all mechanics**: git-state detection, worktree+branch creation, state materialization, verification, launch-command construction/emission, cleanup. It is fully usable by a human in a bare terminal with no skill involved (R8.2 non-interactive path).
- **REQ-02** The **skill owns intent routing inside the agent session**: it maps inspection intent and exact `--session`/`--session-only` arguments to `agent-fork session --json`, and fork intent to `agent-fork fork ... --require-agent --json`; it parses machine output and renders the returned result prominently. `--session` includes the exact returned native session-fork command, while `--session-only` prints only that command. It delegates host/session detection, directory inference, command construction, and all Git mechanics to the CLI. No skill-side executable or Git implementation is permitted.
- **REQ-03** The CLI **self-detects as the primary skill path** when `--agent`/`--parent-session` are absent: it runs as a child of the agent process, so the same environment signals are visible (`CLAUDECODE=1` + `CLAUDE_CODE_SESSION_ID`; `CODEX_THREAD_ID`). Detection ladder per agent is in §5. Explicit flags remain available for direct CLI use and always win (R5.1 spirit).
- **REQ-04** The skill↔CLI contract is the CLI's **machine output** (`-o json`, R4.2/R7.2): a stable JSON result object (§3.6). The skill parses JSON, never human tables.
- **REQ-05** Skill distribution: placed for both Claude Code and Codex per the existing skill-placement conventions; the skill's only hard dependency is the CLI being on `PATH` (it reports a clear install hint when missing).

---

## 3. Command surface (interface spec — cli-standards plan-mode deliverable)

### 3.1 Identity & profile

- Binary: `agent-fork` (lowercase, hyphenated — R1.4/R1.5). PyPI name `agent-fork` **available** (checked 2026-07-21, PyPI + TestPyPI; only a real publish is definitive).
- **Small-CLI verb-first profile** (Appendix A) — criteria: (1) fixed set of eight commands ✔ (§3.2); (2) one product domain (*agent forks and their session evidence*) ✔; (3) verbs read naturally without a noun ✔. Migration trigger acknowledged: an unrelated second resource type forces noun-verb in the next major (R9.3).
- Standard pinned: **v1.4.14**.

### 3.2 Command tree

```
agent-fork
├── fork [NAME]            # THE action: prep fork + emit paste command   (D1: bare-invocation behavior)
├── session [validate|claude-parent ...]  # inspect/assert session and manage Claude parent evidence
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

Positional `[NAME]` = the fork's identity (R2.3): seeds the default branch, derived worktree leaf, and session name. Optional; when absent the name is auto-derived (D4). D15's explicit branch or worktree overrides replace only their named resource and do not alter the fork/session identity.

| Flag | Short | Type | Default | Purpose |
|---|---|---|---|---|
| `--agent <claude\|codex>` | — | enum | self-detect | Host agent (skill passes explicitly; REQ-03) |
| `--parent-session <id>` | — | str | from env | Parent session/thread ID |
| `--branch <name>` | — | str | `<branch_prefix><slug>` | Explicit fork branch |
| `--worktree-dir <path>` | — | path | location scheme (D5) | Explicit worktree destination |
| `--worktree-base-dir <directory>` | — | path | derived parent (D5) | Replace only the worktree parent; must already be a directory |
| `--worktree-name <component>` | — | str | derived leaf (D5) | Replace only the worktree leaf, preserving exact spelling |
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
- **REQ-17** `-o json` completed-fork result object (stable within major, open schema per R7.2) — minimum fields: `agent`, `parent_session_id`, `fork.branch`, `fork.worktree`, `fork.anchor_commit`, `fork.mode` (state-carry booleans), `verification` (per-check results), `command` (the paste command string), `notices[]`, and for Codex `cwd_prompt_expected: false` (E2: the locked `-C` template suppresses the prompt). `--json` is identical to `-o json` on completed and dry-run paths (R4.2). Errors: single JSON object `{"error":{"code","message"}}` on stderr under any machine format (R7.8); the authoritative catalog and exit families are published in README and implemented by `ERROR_CATALOG`, including `config_error` for handled configuration failures, **`repo_no_commits` (spec A2)**, **`unmerged_index` (spec A4)**, **`registry_busy` (spec A13)**, and **`agent_signal_incomplete` (P02 A9, exit 3 with non-secret `status`/`present`/`missing` details)** (R7.12).
- **REQ-18** `--dry-run` output identifies every planned mutation (branch, worktree path, files-to-carry counts, the paste command) and states validation was local (R8.6). **Amended 2026-08-10 for issue #14:** under `-o json` or `--json`, dry-run emits a distinct stable, open preview object with `dry_run: true`, `plan.branch`, `plan.worktree`, `plan.files_to_carry`, `command`, `notices`, `validation`, and `mutation_performed: false`; it does not fabricate completed-fork verification fields.

---

## 4. Duplication + verification pipeline

Port of RESEARCH §2 (agent-deck `forkWithStateWorktree` + `MaterializeWipFromParent`), with runtime verification added (agent-deck's documented-but-unenforced contract):

- **REQ-19 Guards (refuse before any mutation, exit 5):** branch exists · branch already has a worktree · worktree path exists · parent mid `rebase`/`merge`/`cherry-pick`/`revert`/`bisect` (error includes the exact abort hint) · **Amended 2026-08-08 (owner, test-architecture spec A2):** unborn HEAD (zero-commit repo) → refuse, code `repo_no_commits`, message contains remedy (make an initial commit and re-run) · **Amended 2026-08-08 (owner, test-architecture spec A4):** unmerged index entries (`git ls-files -u` non-empty, markers present or not) → refuse, code `unmerged_index`, message lists conflicted paths + remedy. Git-only guard: not-a-repo → error (agent-deck's degrade-to-no-worktree does not transfer; a fork without a worktree has nothing to hand off).
- **REQ-20 Anchor:** resolve `HEAD^{commit}` at the **parent's own path**; create worktree+branch atomically at that commit; track whether the branch was newly created (rollback precision). Repo-root resolution must handle: plain repo, linked worktree, bare-at-root, `.bare/` layout (RESEARCH §2.3 matrix).
- **REQ-21 Materialize (exact-copy mode):** the verbatim sequence — staged diff `--binary --cached` → `apply --index`; unstaged diff → `apply`; untracked via NUL-delimited `ls-files --others`; ignored via the second `--ignored` pass only when enabled. Symlinks verbatim, permission bits preserved, parent strictly read-only. **Amended 2026-08-10 (owner, Apple Git portability correction to test-architecture spec A3):** Intent-to-add entries are supported: cached diff uses `--ita-invisible-in-index`; each ITA working-tree patch is transported via plain `git apply`, then its child path is marked with `git add --intent-to-add -- <path>`; verification is ITA-aware. Production must not use `git apply --intent-to-add`, which can replace unrelated index entries under Apple Git 2.50.1.
- **REQ-22 Rollback:** on materialize failure, remove worktree (+ branch only if created), report `cleaned up` or emit the exact manual-recovery command when cleanup itself fails. Signals mid-pipeline trigger the same rollback (exit 130/143).
- **REQ-23 Verify (default on, `--no-verify` opt-out — D8):** ladder from RESEARCH §4 — anchor commit matches · branch matches · `git worktree list` registers the pair · exact-copy: child `status --porcelain -z` byte-equal to parent's (ignored-aware when `--with-ignored`) · clean mode: empty status · parent status before == after. Any failure → exit 1 with rollback (never hand the user an unverified fork).
- **REQ-24 (SHOULD)** `.worktreeinclude` and a post-create setup hook (`.agent-fork/worktree-setup.sh`) as non-fatal steps, agent-deck-compatible in spirit (D7 scope call).
- **REQ-25 (SHOULD)** Submodules: warn-only, copied opaquely, documented.

---

## 5. Per-agent launch commands (v1)

- **REQ-26 Detection ladder** — Claude: `CLAUDECODE=1` ∧ `CLAUDE_CODE_SESSION_ID` (version from `AI_AGENT`). Codex: `CODEX_THREAD_ID` (≥0.95.0). **Amended 2026-08-08 (owner, test-architecture spec A7):** Pre-0.95.0 Codex fallback ladder removed: detection is `CODEX_THREAD_ID`-only; below-matrix versions refuse per D14/REQ-29. The strict detector refuses both/neither; D16/REQ-45 adds the outer adaptive selector that maps neither to Git-only in auto mode. **Amended 2026-08-11 (D20):** the skill selects strict mode with `--require-agent` and relies on this ambient detector; explicit identity remains a direct-CLI capability. **Amended 2026-08-18 (P02 A9):** one pure assessment classifies the three supported values as `absent`, `incomplete`, `detected`, or `ambiguous`. Either half of the Claude tuple alone is incomplete; any observed Claude value plus Codex is ambiguous. `detected` describes a complete environment shape, not session liveness. Explicit Git-only and complete explicit identity remain authoritative, and explicit-agent matching-ID fallback remains supported.
- **REQ-27 Preflight (emit-for-human ⇒ check first, not emit-and-fail):** installed agent CLI present + version ≥ matrix (Claude: pinned-ID fork ≥2.0.73, warn <~2.1.1xx re #48835; Codex: fork ≥0.81.0, env ≥0.95.0) · Codex: parent rollout file flushed on disk (glob `sessions/*/*/*/rollout-*-<id>.jsonl`) before emitting (#756 lesson).
- **REQ-28 Templates** (single-line, fully shell-quoted — uniformly, unlike agent-deck's two unquoted warts):
  - Claude: `cd '<worktree>' && claude --session-id '<pre-generated-uuid>' --resume '<parent-id>' --fork-session -n '<derived-name>'` (E1/E3 verified: pinned UUID, name, full context, and parent preservation all compose).
  - Codex: `codex fork '<parent-thread-id>' -C '<worktree>'` (E2 verified: explicit UUID bypasses cwd filtering; `-C` selects the worktree and suppresses the cwd-change prompt).
- **REQ-29 Preflight failure = refusal (D14 DECIDED 2026-07-21 — owner overrode the fallback-ladder recommendation):** in the mutating `fork` pipeline, when native fork is impossible (CLI below the version matrix, Codex rollout not flushed, agent undetectable), v1 **refuses with a diagnosis** — what was detected, which requirement failed, the minimum version/missing artifact, and a `doctor` pointer — and creates **nothing** (fail before mutation). The mutating pipeline never emits a command known to fail. D21/REQ-50 ordinary inspection is explicitly construction-only and does not claim preflight success. The fresh-session + HANDOFF.md degradation ladder is deferred to v1.1+ (with the Q5 research pass).
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
- **REQ-38** Publishable-tier obligations: SemVer interface contract (R9.3) · deprecation policy (R9.2) · UTF-8 + locale-independent machine output (R9.4) · clean SIGINT/SIGPIPE/SIGTERM (R9.6) · `doctor` (R9.10 — checks: **Amended 2026-08-10 (implementation-phase A9 audit and Apple Git portability correction):** git version vs named constant `PRODUCT_GIT_MIN = 2.19.0`; 2.19 remains the conservative supported floor after REQ-21/A3 stopped relying on vendor-divergent `git apply --intent-to-add`; evidence in `docs/testing/PRODUCT-GIT-MIN-AUDIT.md`, **Amended 2026-08-08 (owner, test-architecture spec A14):** failing checks → non-zero exit; agent CLIs found + versions vs matrix, env signals visible, config valid, XDG paths writable; **Amended 2026-08-18 (P02 A9):** doctor reports the shared signal status and non-secret present/missing names; incomplete and ambiguous fail automatic/strict signal checks, incomplete diagnoses Claude with Codex optional, ambiguity keeps both CLIs nonoptional with recipe drift informational, and explicit Git-only keeps both CLIs and recipe drift informational) · error catalog (R7.12) · **conformance fixtures in CI** (R9.14; scaffold at implementation start, not this run) · telemetry: **none** (R9.7 posture: no data collection, stated in README) · self-update: none (package managers own it; R9.9 N/A).
- **REQ-39** Dev environment: Flox owns the four-system Python, uv, just, Git, shell, and make toolchain. Claude Code and Codex are host-managed prerequisites rather than Flox packages because their release cadence and available systems differ from the declared `aarch64-darwin`, `x86_64-darwin`, `aarch64-linux`, and `x86_64-linux` matrix. Repo bootstrap follows the global Python-project conventions with uv + ruff + ty + just. **Amended 2026-08-10:** `just all` is hermetic and excludes real-agent and unrestricted process-group tests; `just test-live` reports each selected host executable and version, owns authentication/state/network preflights, and runs real Claude/Codex calls with captured failure output; `just test-git-matrix` owns system-Git/Flox-Git ITA compatibility; `just test-signals` is a separate Linux CI gate.

---

## 8. Non-functional

- **REQ-40** Zero network calls at runtime (fully local tool). Typical fork ≤ ~2s on a normal repo; `--with-ignored` may be slow — progress on stderr (R7.4) and the #1354 rationale documented.
- **REQ-41** Concurrency safety: registry/state writes atomic + locked (R5.8); two simultaneous forks of one repo must not corrupt each other (the mid-mutation collision loss is classified as exit 5 per spec A1; nothing left behind; rollback runs). **Amended 2026-08-08 (owner, test-architecture spec A13):** Registry locking: OS advisory lock (self-clearing on process death); contending process waits ≤ ~5s then fails with `registry_busy`.
- **REQ-42** Every emitted shell command is quoted defensively (shlex.quote equivalents) — REQ-28 note.
- **REQ-43** Testability: **Amended 2026-08-08 (owner, test-architecture spec A10):** the CLI resolves `git` via PATH at each invocation — never a cached absolute path (canaried in the test suite).
- **REQ-44** Partial worktree destination overrides (D15): derive the normal D5 path, then replace its parent with `--worktree-base-dir` and/or its leaf with `--worktree-name`. The partial flags compose; `--worktree-dir` is parser-incompatible with either. A relative base resolves from invocation cwd and must exist as a directory. A leaf is preserved exactly but must be one non-empty component (not `.`, `..`, absolute, slash/backslash/NUL-containing, or whitespace-only). Resolve the base once and do not follow an existing leaf symlink. Explicit resource collisions refuse without suffixing; auto-suffixing proceeds only when the next candidate changes each colliding resource. Existing invocations, exact-path behavior, configuration, registry, and JSON schemas remain compatible.
- **REQ-45** Adaptive agent integration (D16): `[fork] agent_mode` is `auto` (default), `strict`, or `git-only`, with `AGENT_FORK_AGENT_MODE` and CLI precedence. `--require-agent` selects strict and `--no-agent` selects Git-only. A complete explicit agent/session pair works without environment signals and implies strict intent. Auto chooses Git-only only when the shared assessment is `absent`; `detected` selects that agent; `incomplete` refuses as `agent_signal_incomplete`, exit 3; and `ambiguous` retains the identity-conflict refusal. Strict likewise refuses absent, incomplete, or ambiguous input. A detected agent that fails preflight never silently degrades. Git-only remains authoritative for every ambient state, retains the complete Git/state/verify/include/hook/registry/rollback pipeline, and emits `cd <worktree>`. Success JSON adds top-level `mode`; Git-only omits nullable agent/session identity and registry records `mode` with nullable `agent` while legacy records default to agent mode. Doctor makes unused agent CLIs informational in auto Git-only and explicit Git-only modes.
- **REQ-46** Codex renamed-session resolution (D17): canonical UUID inputs preserve the current fast path and never start app-server. Non-UUID explicit Codex session references resolve through the exact preflighted executable's local `app-server` `thread/list` protocol using `searchTerm`, `useStateDbOnly=true`, bounded pagination, exact case-sensitive local matching, and nonblocking bounded stdout/stderr handling. Resolution defaults on and is controlled by `--codex-session-name-resolution` / `--no-codex-session-name-resolution` over `[agents.codex] session_name_resolution=true`. Disabled name input refuses with UUID guidance; UUID input still succeeds. Zero, duplicate, unavailable, malformed, timed-out, or stale results are typed exit-3 refusals before mutation. The emitted command and `parent_session_id` always contain the canonical UUID; successful lookup adds optional `parent_session_name`. No SQLite or network fallback is permitted. The Codex-specific flags remain compatible if a future generic control is added.
- **REQ-47** Session inspection and validation (D18): `session -o text|json` consumes the shared Claude/Codex environment assessment and reports current identity plus bounded, sourced name and parent evidence. JSON additively includes `agent_signal` for all four states with ordered non-secret `status`, `present`, and `missing` fields. It succeeds with an absent `not_detected` result outside agents and with an explicit incomplete result that retains `lineage.status` and `fork_command.status` as `not_detected`, exposes no current identity or command, and names the missing value. Ambiguous input exposes no current identity. `session validate` requires a detectable current session, embeds the same session document, and composes optional agent/current-ID/parent-ID/parent-presence assertions; mismatches are `session_validation_failed`, exit 3, while contradictory flags are exit 2. Codex uses local app-server state. Future Agent Fork-created Claude children persist a prompt-free XDG child→parent claim; message `parentUuid` is never session ancestry. Inspection performs no network access or writes and does not claim transcript existence.
- **REQ-48** Claude parent inference (D19): `session claude-parent list|show|infer|delete` manages Agent Fork-owned Claude parent metadata. Inference is opt-in and requires exactly one of `--current`, `--session-id`, or `--all`; preview never writes, single-target persistence requires `--record`, and bulk persistence requires `--record-all`. `infer --current` assesses ambient agent signals before corpus discovery: incomplete Claude input is `agent_signal_incomplete`; any Claude value plus Codex is `claude_parent_unavailable` ambiguity; absent and Codex-only input retain `claude_parent_unavailable`; complete Claude-only supplies the target ID. Relatedness requires exact shared UUID/`parentUuid` structural ancestry including a substantive record. Direction uses separately sourced creation evidence and never resolves same-boundary siblings by age. Planned lineage outranks separately versioned inferred state. Discovery is bounded and staged: manifest, superficial no-false-negative UUID screening, exact candidate parsing, then polynomial graph analysis. A warm lookup does not reread unchanged unrelated transcript bytes; `--all` never compares all pairs. Cache/state exclude message content and use restrictive, atomic, sharded storage. Ordinary `session` never scans; only current non-superseded inferred evidence may satisfy parent validation. Delete removes only the exact selected Agent Fork metadata record and never Claude/Git resources.
- **REQ-49** Direct companion skill and repository-aware session context (D20): exact skill argument `--session` and natural-language current-agent-session inspection call `agent-fork session --json`; explicit name text is classified before normalization, converted to `[a-z0-9]+(?:-[a-z0-9]+)*`, shell-quoted as one argument, and passed to `agent-fork fork <name> --require-agent --json`. An unnamed fork first inspects the session: missing/ambiguous identity or absent repository context stops; a known topic branch calls `agent-fork fork --require-agent --json` without a positional name; default, detached, or unclassified branches require a recommended or user-selected name. Unsupported option-like text refuses, including `--status` with guidance to use `--session`. Advanced CLI flags are not skill arguments. The skill reports normalization, validates success JSON, preserves nonzero errors and the exact returned continuation command, detects an absent CLI before any route from shell exit 127 or `command not found` and prints `uv tool install git+https://github.com/smorinlabs/agent-fork`, because the bare package name resolves to a PyPI placeholder until first publication; it may offer `uvx --from git+https://github.com/smorinlabs/agent-fork agent-fork --version` as text it never executes, suggests `agent-fork doctor` when the CLI runs but reports an environment problem, and reports otherwise-valid session JSON carrying no `fork_command` key as a superseded-contract upgrade (`uv tool install --force git+https://github.com/smorinlabs/agent-fork`) rather than invalid output, because that contract changed without a version bump. Skill frontmatter declares `argument-hint` covering the three exact forms and least-privilege `allowed-tools`. The skill never retries with guessed identity and never substitutes hand-written Git or a Git-only path for the CLI. Amended 2026-08-14 (owner, Option B): a missing CLI may additionally be resolved from a confirmed local Agent Fork checkout, discovered only from the active repository root or the skill's own resolved load directory and verified by a `pyproject.toml` declaring `name = "agent-fork"`. That fallback requires explicit user consent because a working tree is not a released build, runs the classified route unchanged under `uv run --directory` with the path shell-quoted, prints the install command regardless, never installs or executes network-fetched code automatically, and degrades to install-and-stop when no checkout is confirmed or consent is withheld. Session JSON additively reports resolved `directory` and nullable `repository` context: root, branch/detached state, remote default, deterministic default candidates, default membership, linked/bare topology, and nullable working-tree status with clean/staged/unstaged/untracked/unmerged/operation fields. Repository-context failure preserves session evidence; human output labels and terminal-escapes repository-controlled values. Amended 2026-08-14 (owner, fork confirmation): every fork route resolves exactly one candidate name — an explicit hint, the CLI's branch-derived name on a topic branch, or a conversation-derived proposal on a default, detached, or unclassified branch — then confirms before mutating by computing `agent-fork fork … --dry-run --require-agent --json`, refusing as invalid output any dry run whose `plan.branch.name`, `plan.worktree.path`, or `plan.files_to_carry` is absent, stating the current branch and those three values verbatim — semantically exact yet terminal-escaped like every other repository-controlled value — and asking one question offering create-as-shown, a different name, or no fork. A no-name request whose approved name is not branch-derived hands off to the explicit-name command without confirming a second time. An exact `--now` skips that confirmation and its dry run without changing the naming rules; `--now` may appear at most once and may accompany a name hint in either order, never `--session` or `--session-only`; a repeated `--now`, like every other option-like token, refuses before any CLI call, and the text remaining after the single `--now` is removed may itself contain no option-like token. Inspection through `--session` and `--session-only` remains ungated.
- **REQ-50** Read-only native session-fork command (D21): ordinary `session` JSON additively includes `fork_command` with `status` and nullable `command`. Exactly one safe ambient identity yields `available` and the exact shell-quoted command: Claude `cd '<resolved-directory>' && claude --session-id '<fresh-child-uuid>' --resume '<current-session-id>' --fork-session`; Codex `codex fork '<current-thread-id>' -C '<resolved-directory>'`. `shlex.quote` output is normative, so safe values may be visibly unquoted. Absent or incomplete identity yields `not_detected`; ambiguous Claude/Codex identity yields `ambiguous`; C0/C1, DEL, or Unicode bidirectional controls in the identity or resolved directory yield `unsafe_input`; every non-available status has `command: null`. The separate `agent_signal` object distinguishes absent from incomplete without expanding this closed command-status set. Status depends only on ambient identity and terminal safety, not lineage, native-binary presence, app-server results, names, parent evidence, or preflight. A Claude child UUID is generated once per inspection, remains stable across repeated serialization and embedded validation, differs across inspections, and is single-use. Human output prints a safe command byte-exact or an explicit unavailable status. Exact skill forms `--session` and `--session-only` share validation of this object; the former includes the command with inspection, while the latter emits only it. Missing, malformed, non-available, or unknown status stops without reconstruction or execution. Mixed, misspelled, or other option-like skill input refuses before any CLI call. Construction performs no configuration resolution, preflight, Git mutation, filesystem write, registry/lineage mutation, clipboard access, network access, or command execution.

---

## 9. Test-first plan (implementation-session input)

TDD per house process: the §4 pipeline is specified by an integration harness on disposable fixture repos (staged+unstaged+untracked+ignored+symlink+exec-bit files; each RESEARCH §4 matrix row = a test case; verification-ladder assertions are the test oracle). **Amended 2026-08-10 (owner, explicit external-capability gates):** Experiments E1–E3 run only through `just test-live`, after selected host executable/version, authentication, writable-state, and network-reachability preflights (E4 retired until v1.1 per spec A8; E5 absorbed into the §4 pipeline TDD; E6 tombstoned with A7). Ordinary `just all` excludes tier-R tests. SIGINT/SIGTERM rollback rows run through `just test-signals` on unrestricted Linux CI. Conformance fixtures (R9.14) assert help/streams/exit-code contracts. **Amended 2026-08-08 (owner, test-architecture spec A11):** Implementation-phase TDD and suite runs are dispatched to subagents per the house SDD model matrix; the driving session orchestrates.

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
| D15 | Independent worktree base/leaf overrides; exact destination remains exclusive (REQ-44) |
| D16 | Adaptive agent integration with `auto`, `strict`, and `git-only` (REQ-45) |
| D17 | Codex renamed-session resolution through app-server with UUID-only escape hatch (REQ-46) |
| D18 | Agent-neutral session evidence and assertion command (REQ-47) |
| D19 | Opt-in Claude parent inference and lineage management (REQ-48) |

Queued for the implementation session: PROJECTS.md project creation (house process), git init + worktree discipline for this repo, live experiments E1–E3 (E4 retired per spec A8), conformance fixture scaffold (R9.14).
