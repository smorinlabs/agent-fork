---
decided: 2026-07-21
status: decided
---

# Decision: how does agent-fork invoke fork/resume and discover the running session's ID, per v1 target?

## Choice

**Claude Code:** emit `cd '<worktree>' && claude --session-id "<pre-generated-uuid>"
--resume $CLAUDE_CODE_SESSION_ID --fork-session -n '<derived-name>'`. Self-ID via the
`CLAUDE_CODE_SESSION_ID` env var; no session-file copying (worktree-scoped resume is
officially supported). Conditional: on CLI < ~2.1.1xx warn (worktree scoping unreliable,
#48835); on < 2.0.73 drop `--session-id` pinning; `-n` inclusion pending experiment 1.

**Codex:** emit `cd '<worktree>' && codex fork <thread-id>` (possibly with `-C`, pending
experiment 2). Self-ID via `CODEX_THREAD_ID` (≥0.95.0); pre-0.95.0 fallback = own-process-
ancestry → open-fd probe → newest-rollout scan. Preflight: installed codex ≥0.81.0 and
rollout file exists on disk before emitting. Document the possible TUI cwd-change prompt
in the emitted output.

## Why

Both tools now have native, Stable, full-copy fork surfaces, and the load-bearing unknown
(Claude cross-directory) resolved favorably from primary docs + live tests. The command
shapes are production-proven in agent-deck. Self-ID needs zero filesystem heuristics on
current versions of both tools (env vars exist in both).

## Runner-up (ranked)

**Copy-the-.jsonl into the target's encoded project dir, then plain `--resume`** (Claude,
unrelated-directory case only): viable but manipulates a vendor-declared-unstable format —
switch to it only if a same-repo worktree turns out not to satisfy the resume scoping in
practice (experiment 4 fails), and then only with a version guard + post-copy smoke test.
For Codex: `codex fork --all` + picker as the interactive fallback if explicit-UUID
cross-cwd fork fails (experiment 2 fails).

## Why not the others

- Fresh-session + handoff-file seeding as *primary*: strictly lossy vs native full-copy
  fork; remains the designed fallback for too-old CLIs (Q5 — still unresearched).
- App Server API for Codex self-ID: enumeration surface, heavier than reading an env var;
  right tool for listing, wrong tool for "who am I".
- tmux-env round-trip (agent-deck's id side-channel): requires a persistent pane manager
  agent-fork doesn't have.

## Chain

- Prompt: prompts/00-fork-resume-mechanics.prompt.md
- Framing: prompts/00-fork-resume-mechanics.framing.md
- Output: 00-fork-resume-mechanics.md
- Leaf(s): ../../reference/agent-session-fork-cli-recipes-2026-07-21.md
