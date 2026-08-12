# Goal: complete the companion agent skill

**Created:** 2026-08-10
**Status:** complete; orchestration mechanism superseded by D20 on 2026-08-11
**Branch:** `feat/phase-e-companion-skill`
**Worktree:** `/work/agent-fork-phase-e`

**Superseded mechanism:** The direct companion-skill plan replaces this goal's
skill-side explicit-identity orchestration with `agent-fork session --json` and
`agent-fork fork ... --require-agent --json`. The real-host evidence below
remains historical acceptance evidence.

## Objective

Complete the reordered Phase E companion skill for Claude Code and Codex. The
skill must inspect the active host session through `agent-fork session --json`,
invoke `agent-fork fork ... --require-agent --json`, and prominently return the
paste command without reimplementing Git mechanics.

## Gate

- One canonical Agent Skills artifact is discoverable by both hosts.
- Missing, ambiguous, and malformed inputs fail diagnostically without mutation.
- Automated structure, invocation, and JSON-contract tests pass with `just all`.
- A real Claude Code invocation produces a verified fork and usable paste command.
- A real Codex invocation produces a verified fork and usable paste command.
- Phase F release, publishing, registry, Homebrew, and release automation work
  has not begun.

Stop for owner review after the two real demos. Phase E does not authorize any
package publication or release-channel mutation.

## Evidence

- Skill structural validation passed with the skill-creator validator.
- Focused orchestration tests cover both hosts, shared placement, ambiguous and
  absent host signals, managed-option protection, missing CLI, and malformed JSON.
- Full repository gate: 225 passed, 1 retired skip.
- Real Codex `$agent-fork phase-e-codex-demo` created a verified fork; its paste
  command resumed in the generated worktree and returned
  `PHASE_E_CODEX_PASTE_OK`.
- Real Claude `/agent-fork phase-e-claude-demo` created a verified fork; its
  paste command resumed in the generated worktree and returned
  `PHASE_E_CLAUDE_PASTE_OK`.
- Both disposable forks were removed through `agent-fork cleanup --yes --force`;
  the registry is empty and session files remain resumable.
