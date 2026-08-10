# Adaptive agent mode implementation plan

**Status:** Complete on 2026-08-10; all implementation gates green.

## Contract

- `auto` is the default. With exactly one supported session signal it performs a
  managed agent fork; with no signal it performs a Git-only fork.
- `strict` is strict agent mode. It requires an unambiguous agent session and
  full native-agent preflight. `--require-agent` selects it.
- `git-only` explicitly disables agent integration. It ignores ambient session signals and
  `--no-agent` selects it.
- Explicit `--agent` or `--parent-session` inputs imply `strict` and conflict
  with `--no-agent`.
- Ambiguous Claude and Codex signals are always refused unless the caller
  explicitly chooses Git-only mode or supplies an explicit agent/session pair.
- Once auto mode detects an agent, agent detection or preflight failure is a
  refusal; it never silently downgrades to Git-only behavior.
- Git-only mode retains Git preflight, guards, state carry, verification,
  registry, and rollback, but emits a quoted `cd <worktree>` command and does
  not require either agent CLI.

Configuration uses `[fork] agent_mode = "auto" | "strict" | "git-only"`, with
`AGENT_FORK_AGENT_MODE` as its environment counterpart and CLI flags taking
normal highest precedence.

## TDD/SDD sequence and gates

1. **G-AM1 — Contract and RED tests.** Add the identified matrix rows for
   configuration, detection, CLI policy, output, and registry compatibility.
   Gate: each new test fails for the intended missing behavior.
2. **G-AM2 — Configuration and selection.** Implement validated configuration,
   precedence, and one deterministic mode-selection function. Gate: new config
   and detection unit rows pass; legacy explicit detection remains green.
3. **G-AM3 — Fork behavior and schemas.** Make agent context optional through
   the pipeline, add mode-aware output/registry records, and implement the
   Git-only launch command. Gate: unit and functional rows pass, including a
   real disposable Git-only fork with no session environment.
4. **G-AM4 — CLI, doctor, and companion skill.** Add mutually exclusive flags,
   make doctor report mode-appropriate readiness, and force the skill's managed
   invocation through `--require-agent`. Gate: CLI and skill tests pass.
5. **G-AM5 — Specification and product gates.** Record D16 and REQ-45, update
   help/config/output documentation and conformance evidence. Gate: `just all`
   and `just check-matrix` pass, plus a manual no-session Git-only smoke test.

Stop after G-AM5. P01-T20 and P01-T21 remain outside this change.
