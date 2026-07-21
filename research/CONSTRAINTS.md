# Research constraints — agent-fork

Harvested from project context on 2026-07-21. Applies to every research
thread under this tree unless a thread's own framing states an override.

## What the project is
`agent-fork`: a Python CLI + agent skill that runs INSIDE a live coding-agent
session, preps a git worktree copy of the current work, and emits the exact
command the human pastes into a new terminal to continue that work in a
forked session of the SAME agent.

## Stack
- Python.

## Target platforms
- macOS and Linux terminals. No Windows.

## Version scope
- **v1 (full research depth):** Claude Code, Codex CLI.
- **v2 (high-level only — one paragraph each, no deep-dive):** Pi, OpenCode,
  Kilo Code.

## License / security posture
- Not declared as binding for this domain. Only raise it if a specific
  thread's question surfaces a concrete concern (e.g., whether copying a
  session transcript file across project directories is safe).

## Skill-default overrides
- None declared. Skill defaults apply: 3-thread budget (+2 lease on a
  cleared re-check), 3-level narrowing ceiling per thread, 25-leaf regroup
  threshold in `reference/`.
