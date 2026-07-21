---
type: framing
topic: 01-session-fork-resume-cli-mechanics
pass: 00
template: "implementation deep-dive (templates.md #4)"
date: 2026-07-21
---

# Framing: per-agent session fork/resume CLI mechanics

## Why this template
Trigger type 3, implementation deep-dive. The tools are already chosen
(Claude Code, Codex CLI are the v1 targets; the rough mechanism —
`--fork-session`/`--resume` on Claude Code, `codex fork` on Codex — is
already identified from local binary testing). What's missing is exact-use-case
mastery: cross-directory fork behavior, whether context-carry is full,
self-discovery of the running session's own ID from inside that session, and
a fallback pattern when a true fork isn't available. This is not a
library-selection question (template #2) or a domain-survey question
(template #1) — the "library" is already picked; we need its API surface for
our specific case.

## Constraints harvested (relevance-filtered per the skill's rule)
- **Stack:** Python CLI + agent skill, runs inside a live agent session,
  drives `git worktree add` and emits a paste-able resume command.
- **Target platform:** macOS + Linux terminals only — stated explicitly by
  the requester, so included.
- **Version scope:** v1 = Claude Code + Codex CLI, full depth; v2 = Pi,
  OpenCode, Kilo Code, one paragraph each, explicitly capped at high-level
  (no deep-dive budget spent there).
- **License / security:** not declared as binding for this domain — omitted
  as a constraint, per "a constraint that doesn't bind is noise."
- The detailed CLI flag ground truth (see the prompt file's "ESTABLISHED
  GROUND TRUTH" block) was independently verified against local binaries on
  2026-07-21 by the requester. Treated as given input to the prompt, not
  re-derived or re-verified by this framing pass.

## Light-search findings (framing only — the deep-research pass owns full verification)
Ran 4 targeted searches to sanity-check the field and surface conflicts the
deep-research prompt should resolve with primary sources rather than
snippets:

1. **agent-deck is real and directly on point.**
   `github.com/asheshgoplani/agent-deck` — a terminal session manager for
   Claude, Gemini, OpenCode, Codex, etc. Its "fork" feature is reported (via
   its README/marketplace listing, not yet source-verified) to inherit the
   parent's full conversation context and create a new git worktree + branch
   while carrying the parent's uncommitted working-tree state. The exact
   mechanism — does it copy the Claude session `.jsonl` into the new
   project's encoded directory, shell out to a documented flag, or something
   else — is unverified from search snippets alone. Flagged as a primary
   target for the deep-research pass: read its actual fork-implementation
   source, not just marketing copy.

2. **Claude Code cross-directory fork: search snippets directly conflict.**
   One source describes `claude --resume <uuid> --fork-session --cwd <dir>`
   as though it works today. Another states `--resume`/`--fork-session` are
   hard-filtered to `~/.claude/projects/<encoded-$PWD>/`, and that
   cross-directory resume requires manually copying the session `.jsonl`
   into the target project's encoded directory before `--resume
   --fork-session` will find it — citing an open feature request
   (`anthropics/claude-code#58591`, "Resume sessions in a different working
   directory: --cwd flag") and a related TUI issue (`#60272`, forking to
   decouple a new session from a prior session's working directory). Neither
   snippet is a changelog or doc page fetched directly. **This is the
   single highest-value conflict for the deep-research pass to resolve** —
   it directly gates whether `agent-fork` can rely on a documented flag or
   must implement (and warn about the safety/support status of) a
   copy-the-session-file workaround itself.

3. **Codex session-ID self-discovery looks unsupported today.** An open
   GitHub issue (`openai/codex#8923`, "expose current Codex session ID
   programmatically") requests a `CODEX_SESSION_ID` env var — implying no
   supported one exists yet, and that Codex only surfaces the session/rollout
   ID via the JSONL file it writes. Rollout file location was reported in
   the *nested*, date-partitioned form
   `~/.codex/sessions/YYYY/MM/DD/rollout-<ISO_TIMESTAMP>-<uuid>.jsonl` (not
   the flat `~/.codex/sessions/rollout-<date>-<uuid>.jsonl` shape assumed as
   a starting guess) — this needs primary-source (docs or source) 
   confirmation plus a version/date pin, since changelog-aggregator
   snippets are not a reliable enough foundation to build a "find the
   currently-running session" heuristic against.

4. **Codex fork/session-management changelog churn is real but shallow from
   search alone.** Multiple changelog aggregator pages (not OpenAI's own
   docs directly fetched yet) mention archive/resume/fork paths improving
   via a "ThreadStore," and `codex archive`/`codex unarchive` protecting
   archived sessions from resume/fork. Exact version each behavior landed
   in, and whether early `codex fork` was ever rollout-gated behind an
   internal flag before general availability, was not resolved by search
   snippets. The deep-research pass should pull OpenAI's own Codex changelog
   pages with dates, not aggregator paraphrases.

## Sources surfaced (for the deep-research pass to verify/deepen — not final citations)
- https://github.com/anthropics/claude-code/issues/58591
- https://github.com/anthropics/claude-code/issues/60272
- https://github.com/asheshgoplani/agent-deck
- https://code.claude.com/docs/en/worktrees
- https://code.claude.com/docs/en/sessions
- https://github.com/openai/codex/issues/8923
- https://github.com/openai/codex/discussions/3827
- https://developers.openai.com/codex/changelog?type=codex-cli

## Handoff to the prompt
All four points above — the Claude Code cross-directory conflict especially —
are folded into the shaped prompt as open questions the engine must resolve
with dated, versioned, sourced claims, never as pre-baked answers. The prompt
does not repeat this framing narrative; it states the ground truth and
questions directly.
