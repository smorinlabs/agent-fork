# Research Index — agent-fork

**Rule:** prefer terminal leaves in `reference/` over new research — check this
file before starting any research thread. Only revisit funnels in `topics/`
when reopening a decision that already has a `DECISION.md`.

## Leaf index (reference/)
- **agent-session-fork-cli-recipes-2026-07-21.md** — claude-code 2.1.216 /
  codex-cli 0.144.6 — the emit-command recipes, self-session-ID discovery, min-version
  matrix, gotchas, and the 4 outstanding live experiments for agent-fork's v1 targets.

## Funnel index (topics/)
- **01-session-fork-resume-cli-mechanics** — status: **decided** (2026-07-21).
  Choice: native fork surfaces for both v1 targets — Claude `--resume $CLAUDE_CODE_SESSION_ID
  --fork-session --session-id <pinned>`, Codex `codex fork $CODEX_THREAD_ID` — no
  session-file copying. Q5 (handoff fallback conventions) and Q6 (Pi/OpenCode/Kilo web
  landscape) produced no verified claims and remain open for a future pass.
  → `topics/01-session-fork-resume-cli-mechanics/DECISION.md`

## Proposal log
_(none — thread 01 was directly commissioned by the requester)_

## Defer log
- **Q5 handoff/fallback-seeding conventions** (2026-07-21) — no claims survived
  verification in thread 01; deferred rather than re-narrowed. Review if Phase 2 needs
  the too-old-CLI fallback specified in detail.
- **Q6 Pi/OpenCode/Kilo session internals** (2026-07-21) — v2 scope; local-binary flag
  surface captured in the leaf; storage/context-carry semantics deferred to a v2 thread.
