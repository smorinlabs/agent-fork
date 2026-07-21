---
type: exploratory
status: chosen
created: 2026-07-21
updated: 2026-07-21
library_version: claude-code 2.1.216 / codex-cli 0.144.6
confidence: high
confidence_basis: deep-research run (103 agents, 21 sources, 25 claims 3-vote adversarially verified, 23 confirmed / 2 refuted / 0 unverified); load-bearing Q1 claims live-tested on local binaries
verified_example: false
assumptions: single-user local terminal workflow, macOS/Linux, default CLAUDE_CONFIG_DIR/CODEX_HOME; headless/CI not tested
sources: [https://code.claude.com/docs/en/sessions, https://code.claude.com/docs/en/cli-reference, https://platform.claude.com/docs/en/agent-sdk/sessions, https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md, https://github.com/anthropics/claude-code/issues/58591, https://github.com/anthropics/claude-code/issues/65945, https://github.com/openai/codex/issues/8923, https://github.com/openai/codex/pull/10096, https://github.com/openai/codex/pull/8994, https://github.com/openai/codex/pull/21089, https://github.com/openai/codex/pull/12040, https://github.com/openai/codex/issues/20165, https://developers.openai.com/codex/changelog, https://developers.openai.com/codex/cli/reference, https://github.com/openai/codex/releases, https://github.com/asheshgoplani/agent-deck]
origin_prompt: prompts/00-fork-resume-mechanics.prompt.md
---

# Research output — per-agent session fork/resume CLI mechanics (Q1–Q6)

Verification stats: 5 angles, 21 sources fetched, 103 claims extracted, 25 verified by
3-vote adversarial panels → 23 confirmed, 2 refuted, 0 left unverified, synthesized to 11 findings.

## Q1 — Claude Code cross-directory fork: RESOLVED IN OUR FAVOR

- **CONFIRMED (docs + live-tested both directions on 2.1.216, 2026-07-21):** `claude
  --resume <session-id>` lookup is scoped to the current project directory **and its git
  worktrees** (docs verbatim: "passing a session ID searches only the current project
  directory and its git worktrees"). A session started in the main checkout is findable
  by ID from a fresh `git worktree add` directory of the same repo — agent-fork's exact
  case — and the reverse direction also works. An unrelated directory fails with
  "No conversation found with session ID". **No session-file copy needed for the
  worktree-fork flow.** (3-0, 3-0)
- **CONFIRMED:** for unrelated projects, the only supported mechanism is
  cd-into-original-dir-then-resume (the picker literally copies a `cd <dir> && claude
  --resume <id>` command to the clipboard). Open feature requests #58591 (`--cwd`) and
  #65945 prove no in-place cross-directory resume exists. `/cd` (v2.1.169+) relocates a
  session's storage but only from inside an already-resumed session. (3-0)
- **CONFIRMED:** since v2.1.118, `--resume`/`--continue` also find sessions that
  registered the current dir via `/add-dir` (discovery only — dirs not auto-restored).
  A second supported cross-directory path. (3-0)
- **Historical caveat:** issue #48835 shows worktree-direction resume failed on older
  versions; do not assume worktree scoping below roughly the 2.1.1xx line without testing.

## Q2 — Claude fork semantics

- **CONFIRMED:** `--fork-session` (with `--resume`/`--continue`; SDK: `fork_session` as a
  modifier on `resume`) creates a **full copy** of the history (not a summary) under a
  new session ID; the original stays intact — two independently resumable sessions.
  Gotchas: session-scoped permission approvals ("allow for this session") do **not**
  carry into the fork; resuming one session in two terminals **without** forking
  interleaves both into one transcript (the motivating hazard agent-fork prevents). (3-0, 3-0, 2-1)
- **CONFIRMED (changelog + live version-boundary test):** pinning the fork's UUID via
  `--session-id <uuid>` with `--resume`+`--fork-session` is supported **since v2.0.73**
  and works non-interactively. `--session-id` + `--resume` **without** `--fork-session`
  errors ("--session-id can only be used with --continue or --resume if --fork-session
  is also specified"). (3-0)
- **CONFIRMED:** transcripts live at `~/.claude/projects/<encoded-cwd>/<id>.jsonl`
  (encoding: `[^a-zA-Z0-9] → "-"`; root overridable via `$CLAUDE_CONFIG_DIR`; verified
  by binary strings extraction). The JSONL format is vendor-declared **internal and
  version-unstable** ("can break on any release") → the copy-the-.jsonl workaround for
  unrelated dirs is last-resort only, with a version guard + post-copy smoke test. (3-0 ×2)
- **OPEN:** whether `-n/--name` combines cleanly with `--resume --fork-session
  --session-id` in one invocation (live experiment).

## Q3 — Codex self-discovery: SOLVED (≥0.95.0)

- **CONFIRMED:** `CODEX_THREAD_ID` is injected into the environment of shells Codex
  executes — PR openai/codex#10096 (merged 2026-02-03, closing #8923), first shipped
  **rust-v0.95.0** (2026-02-04), still present at 0.144.x/main. Refutes the "no env var"
  framing lead (true only through v0.94.x). Read `CODEX_THREAD_ID` first; fall back to
  rollout-file heuristics only pre-0.95.0. (3-0)
- **CONFIRMED:** official surface for *enumerating* sessions is the App Server JSON API
  (`thread/list`, `thread/resume`, …; terminology now "threads"); recommended by
  maintainers for tool-builders. Complements, not replaces, the env var. (3-0)
- **OPEN (residue):** pre-0.95.0 concurrent-session disambiguation in one cwd; the
  definitive "running inside Codex" detection signal set. Rollout layout
  `~/.codex/sessions/YYYY/MM/DD/rollout-<ts>-<uuid>.jsonl` confirmed locally on this
  machine `[FS]` and matches agent-deck's glob.

## Q4 — Codex fork semantics + version history

- **CONFIRMED timeline:** `codex resume` — rust-v0.36.0 (2025-09-15). `codex fork` —
  wired into the CLI in **rust-v0.81.0** (2026-01-14, PR #8994); never mentioned in the
  official changelog (GitHub releases are the only provenance); today documented
  **Stable** in the CLI reference. `fork --last` cwd-filtering bug (#20945: could fork
  another project's session) fixed **rust-v0.129.0** (2026-05-07). Fork-at-a-specific-turn
  (app-server) 0.143.0. **Minimum-version matrix: fork ≥0.81.0, CODEX_THREAD_ID ≥0.95.0,
  trustworthy `--last` ≥0.129.0.** (3-0 ×5)
- **CONFIRMED:** fork "preserves the original transcript" (copy, not move); selection is
  cwd-filtered by default with `--all` the documented override. (3-0)
- **OPEN (the key scripting hazard):** docs are silent on whether an **explicit
  SESSION_ID bypasses cwd filtering** (#20165 suggests yes for resume; unproven for
  fork). And a **TUI cwd-change prompt** fires when the target dir differs from the
  session's recorded cwd (PR #12040; `cwd_prompt.rs` strings — "Use session directory (" /
  "Use current directory (" — present in the 0.144.6 binary). A pasted cross-directory
  `codex fork` will likely hit this interactive prompt; whether `-C/--cd` pre-empts it
  is unverified. (3-0 ×3 on the confirmed parts)

## Q5 — Fallback/handoff conventions: UNANSWERED

No claims survived adversarial verification. Incidental evidence only: agent-deck's
OpenCode fork uses export→import; ykdojo's handoff SKILL.md exists as community
convention. Needs a dedicated pass or design-from-first-principles in Phase 2.

## Q6 — v2 landscape (Pi / OpenCode / Kilo): UNANSWERED by web research

No claims survived. Local binary evidence `[BIN]` stands: Pi `--fork <path|id>`
`--session-id` `--session-dir` `-n`; OpenCode `--fork` + `-c`/`-s` + export/import;
Kilo = OpenCode-lineage + `--cloud-fork`. agent-deck has no Kilo support (greenfield).

## Refuted (do not repeat)

1. "v2.1.94 changed worktree resume from printing a cd command to resuming directly" — 0-3.
2. "As of Codex 0.79.x no programmatic session ID exists" — 0-3 (false since 0.95.0).

## Currency notes

Claude docs annotate through v2.1.211 vs local 2.1.216; agent-deck's Codex verification
pins 0.137.0 vs local 0.144.6; developers.openai.com 308-redirects to learn.chatgpt.com
(cite redirect targets in durable docs).
