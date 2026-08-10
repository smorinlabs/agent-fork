---
name: agent-fork
description: Fork the current Claude Code or Codex session into a new branch and verified Git worktree. Use when the user says "fork", "agent fork", "fork this session", or asks to continue the current coding-agent session independently in another worktree. Do not use for ordinary Git branch or worktree requests that do not involve forking the active agent session.
---

# Agent Fork

Fork the active session through the `agent-fork` CLI. Let the CLI own all Git,
worktree, verification, rollback, registry, and launch-command mechanics.

1. Run `python3 "${CLAUDE_SKILL_DIR:-$PWD/.agents/skills/agent-fork}/scripts/fork_session.py"` from the user's current repository directory. Append the user's requested fork name or supported `agent-fork fork` options, if any.
2. If that path is unavailable outside Claude Code, resolve this `SKILL.md` directory and run its `scripts/fork_session.py` with `python3`.
3. Preserve the script's error text. Do not retry with guessed session IDs, fallback transcript searches, or hand-written Git commands.
4. On success, present the script output prominently and tell the user to paste the final command into a fresh terminal.

Destination options may be passed through independently, for example
`--branch review/manual --worktree-base-dir /work/forks --worktree-name manual`.
The skill preserves their order and spelling; the CLI validates their semantics.

The script selects the CLI's strict agent mode, then detects Claude Code from `CLAUDECODE=1` plus
`CLAUDE_CODE_SESSION_ID`, or Codex from `CODEX_THREAD_ID`. It passes the detected
agent and session explicitly to `agent-fork fork --json`. If the CLI is absent,
show its installation hint and stop.

Codex session UUIDs supplied by the active environment bypass name resolution.
If a user explicitly supplies a renamed Codex session instead, the CLI resolves
it through the local Codex app-server before emitting the canonical UUID-based
command. Pass `--no-codex-session-name-resolution` only when the user requests
the strict UUID-only behavior; do not attempt a transcript or database lookup.
