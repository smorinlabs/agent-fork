# DESIGN-DECISIONS.md — `agent-fork` Phase 3

**Date:** 2026-07-21 · **Status:** Phase 3 gate deliverable — all design decisions resolved. Implementation is a separate, later session.
**Method:** async codesign page (`design/phase3-decisions.html`, spec `design/phase3-decisions.spec.json`) — recommendations pre-selected, owner reviewed and exported answers 2026-07-21. Decision IDs D1–D14 from `REQUIREMENTS.md` §10; section/choice IDs (`sec-NN`/`ch-NN-x`) from the page.
**Verdict key:** ★ = followed the recommendation · ⚠ = deliberately went against it.

## Summary

| D# | Decision | Outcome | Verdict |
|---|---|---|---|
| D1 | Bare invocation | Help, exit 0 (R7.9-conforming); skill owns the one-word UX | ★ (decided at Phase 2 gate) |
| D3 | Default posture | **Exact-copy** (staged+unstaged+untracked; gitignored off) | ★ `ch-01-a` |
| D2 | State surface | **agent-deck toggles** `--no-with-state` / `--with-ignored` | ★ `ch-02-a` |
| D5 | Worktree location | **Sibling + mirror-parent**, config override incl. central | ★ `ch-03-a` + note |
| D4 | Fork name | **Optional positional**, auto `<branch-slug>-<mmdd>` fallback | ★ `ch-04-a` |
| D6 | Session name | **= the fork name** (one identity everywhere) | ★ `ch-05-a` |
| D14 | Fallback | **Refuse with diagnosis — no fallback rung in v1** | ⚠ `ch-06-b` |
| D8 | Verification | **On by default**, `--no-verify` | ★ `ch-07-a` |
| D9 | Clipboard | **v1 `--copy` flag**, OSC52-first, config default off | ★ `ch-08-a` |
| D10 | `list` command | **Ships in v1** (registry read) | ★ `ch-09-a` |
| D12 | Cleanup guards | **Registry-scoped; `--force` extends + overrides guards** | ★ `ch-10-a` |
| D13 | Cleanup verb | **`cleanup`** (waiver stands) | ★ `ch-11-a` |
| D7 | Config surface | **Trimmed schema** (see final schema below) | ★ `ch-12-a` |
| D11 | Extra-args passthrough | **Ships in v1**: `[agents.<name>] extra_args` | ⚠ `ch-13-b` |

## Decisions in detail

### D3 — Exact-copy is the default (`ch-01-a` ★)
A bare fork carries staged + unstaged + untracked state; gitignored files are excluded by default. **Owner note applied:** gitignored carryover remains available both as the `--with-ignored` flag and the `with_ignored` config key — config can make it a personal default. *agent-deck reconciliation:* matches the TUI quick-fork posture (#1299) with the #1354 gitignored reversal preserved; rejects the opt-in-everything posture of agent-deck's own CLI as wrong for a one-word gesture.

### D2 — Toggle vocabulary, not modes (`ch-02-a` ★)
Flags `--no-with-state`, `--with-ignored`; config `with_state` / `with_ignored`, tri-state `Optional[bool]` with agent-deck's asymmetric defaults (unset⇒true / unset⇒false) and the implication rule (`with_ignored` ⇒ `with_state`). No `--clean` alias in v1 (can be added compatibly later).

### D5 — Sibling + mirror-parent placement (`ch-03-a` ★, note applied)
Default: sibling `<repo>-<branch-slug>`; when the parent is itself a linked worktree, mirror the parent's observed placement pattern. **Owner note applied:** `worktree_location` config overrides placement with three first-class values plus a template escape hatch — `sibling` (default) · `central` (XDG data: `~/.local/share/agent-fork/worktrees/<repo>/<slug>`) · `subdirectory` (`<repo>/.worktrees/<slug>`) · or a path template with `{repo-name}`/`{repo-root}`/`{branch}` placeholders (agent-deck's template grammar). An explicit config value suppresses the mirror heuristic.

### D4 — Optional positional name (`ch-04-a` ★)
`agent-fork fork fix-auth` names the fork; bare `fork` derives `<parent-branch-slug>-<mmdd>`, collisions suffixed `-2`, `-3` (agent-deck's `uniqueForkBranch` scheme, 1000-cap guard included). The name feeds branch (`<branch_prefix><name>`), worktree suffix, and session name. **Amended 2026-08-08 (owner, test-architecture spec A5):** Detached HEAD auto-name: `detached-<short-sha>-<mmdd>`, collision-suffixed normally.

### D6 — Session name = fork name (`ch-05-a` ★)
One identity across branch, worktree, and session. Claude: `-n '<fork-name>'` in the emitted command. Codex: names are a resume-time concept; the identity lives in the branch/worktree, and emitted output may note how to name the session. No `session_name_template` config key exists.

### D14 — v1 refuses when native fork is impossible (`ch-06-b` ⚠ went against)
When preflight fails (agent CLI below the version matrix, Codex rollout not flushed, unknown/undetectable agent), v1 **refuses with a diagnosis**: what was detected, which requirement failed, the minimum version or missing artifact, and a pointer to `agent-fork doctor`. No handoff-file rung, no session-file copying. The worktree is **not** created on a preflight refusal (fail before mutation). *Consequence:* the fresh-session + `HANDOFF.md` degradation ladder moves to the v1.1+ roadmap; RESEARCH Q5 stays deferred until then. *Rationale (owner):* keep v1 honest and small — a fork that silently loses conversation context is a different product promise.

### D8 — Verification on by default (`ch-07-a` ★)
The REQUIREMENTS §4 ladder runs after every fork; `--no-verify` skips. Failure ⇒ rollback + exit 1. This is agent-fork's deliberate improvement over agent-deck's runtime-unverified pipeline.

### D9 — Clipboard ships in v1 (`ch-08-a` ★)
`--copy` flag; `copy` config key (default off) for always-on. Implementation order: OSC52 escape (SSH/tmux-safe) → `pbcopy`/`xclip`/`wl-copy` shell-outs. Copy failure is a stderr notice, never a failed exit.

### D10 — `list` ships in v1 (`ch-09-a` ★)
Reads the fork registry (XDG state, locked writes); columns: name, branch, worktree path, agent, worktree-still-exists. Deterministic order (by creation time), `-o json` supported.

### D12 — Cleanup is registry-scoped; force escalates (`ch-10-a` ★)
Default targets: only registry-recorded forks. Guards (exit 5): uncommitted changes · commits reachable from no remote ref (no upstream ⇒ unpushed) · target is the invoking cwd. `--force` both extends targeting to any worktree **and** overrides the dirty/unpushed guards; `--yes` remains the separate consent bypass (R8.1 semantics preserved).

### D13 — `cleanup` keeps its name (`ch-11-a` ★)
The R2.1 waiver in `CONFORMANCE.md` stands, now marked confirmed. `prune`-style sweeping, if ever wanted, becomes `cleanup --all`, not a new verb.

### D7 — Final v1 config schema (`ch-12-a` ★, amended by D5 note + D11)

```toml
# .agent-fork/agent-fork_config.toml (project) · $XDG_CONFIG_HOME/agent-fork/… (user)
[fork]
with_state        = true        # tri-state; unset = true
with_ignored      = false       # tri-state; unset = false; implies with_state
branch_prefix     = "fork/"
worktree_location = "sibling"   # sibling | central | subdirectory | <path template>
verify            = true
copy              = false

[agents.claude]
extra_args = []                 # e.g. ["--model", "opus"] — appended to the emitted command
[agents.codex]
extra_args = []
```

Dropped from agent-deck's `[fork]`: `docker`, the `worktree` toggle, `inherit_from_parent` (no meaning in a standalone CLI). Every `[fork]` key mirrors a flag (R3.8 parity); `[agents.*]` is config-only by design (no flag equivalent in v1).

### D11 — Extra-args passthrough ships in v1 (`ch-13-b` ⚠ went against)
`[agents.<name>] extra_args` (array of strings) is appended to that agent's emitted launch command. Constraints: each element individually shell-quoted at emission (no string-splitting, no interpolation); values appear in `--dry-run` and `-o json` output (`command` field reflects them); tests cover the quoting boundary (spaces, quotes, `$`, `;`). *Consequence for testing:* launch-template tests assert the fixed prefix byte-for-byte plus a quoted-suffix property, rather than the whole line as a constant.

## Resulting v1 surface (consolidated)

- **Commands:** `fork [NAME]` · `cleanup <TARGET>` · `list` · `doctor` · `config view|get|set|validate` · `completion <shell>` · `help` — bare `agent-fork` prints help (D1).
- **Emitted commands** (quoted uniformly; `<extra>` = D11 args):
  - Claude: `cd '<worktree>' && claude --session-id "<uuid>" --resume <parent-id> --fork-session -n '<fork-name>'<extra>` (`-n` pending experiment E1)
  - Codex: `cd '<worktree>' && codex fork <parent-thread-id><extra>` (`-C` variant + cwd-prompt handling pending E2)
- **Pipeline:** guards → parent-HEAD anchor → `worktree add -b` → materialize (staged→unstaged→untracked[+ignored]) → verify ladder → registry write → emit (+ optional copy). Any failure after creation ⇒ rollback; preflight failure ⇒ refuse with diagnosis, nothing created (D14).

## Deferred (v1.1+ roadmap)

1. Handoff-file degradation ladder (D14 runner-up; needs the deferred Q5 research pass).
2. `--clean` alias sugar (D2 runner-up).
3. jj backend, Pi/OpenCode/Kilo agents (v2 per kickoff).

## Next session (implementation kickoff) — queued, not started

PROJECTS.md project creation per house process · git init + worktree-discipline setup for this repo · live experiments E1–E3 (E4 retired per spec A8; RESEARCH §7) as the first test-writing step · conformance fixture scaffold (R9.14) · TDD per REQUIREMENTS §9.
