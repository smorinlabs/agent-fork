## Scope

Resolve the exact CLI mechanics needed to build `agent-fork`: a Python CLI +
agent skill that runs INSIDE a live coding-agent session, preps a git
worktree copy of the current work, and emits the exact command the human
pastes into a new terminal to continue that work in a **forked session of
the same agent**. Do not re-derive the ground truth stated below — build on
it. Do not evaluate whether to build this tool; that decision is made. The
job is use-case mastery of the underlying CLIs' fork/resume surfaces,
current as of today.

## Project constraints

- Stack: Python.
- Target platforms: macOS and Linux terminals only. No Windows.
- v1 targets (research these in full depth): **Claude Code** and **Codex
  CLI**.
- v2 targets (cover at high level only — one paragraph each, no deep-dive
  budget): **Pi**, **OpenCode**, **Kilo Code**.

## Established ground truth — verified against local binaries on 2026-07-21

Do not re-verify these flags exist; they are confirmed. Build the deep-dive
on top of them — the open questions below are about *behavior*, not
existence.

**Claude Code 2.1.216**
- `--resume [id]` — resume a session, optionally by ID.
- `--fork-session` — "when resuming, create a new session ID." Documented as
  usable together with `--resume` or `--continue`.
- `--session-id <uuid>` — pin the new session's UUID explicitly.
- `-n/--name <name>` — display name shown in the prompt box, resume picker,
  and terminal title.
- `-c/--continue` — resume the most recent conversation in the current
  directory.
- `--add-dir`, `--from-pr` — also present, lower priority for this research.
- Env vars visible inside a running session: `CLAUDECODE=1`,
  `CLAUDE_CODE_SESSION_ID=<uuid of the running session>`,
  `AI_AGENT=claude-code_<version>_agent`, `CLAUDE_CODE_ENTRYPOINT=cli`.

**Codex CLI 0.144.6**
- `codex fork [SESSION_ID] [PROMPT]` — SESSION_ID is a UUID; `--last` selects
  the most recent; `--all` "disables cwd filtering"; a picker is shown by
  default when no ID is given.
- `codex resume [SESSION_ID|session-name]`.
- `-C/--cd <DIR>` — sets the working root.
- `codex archive/delete/unarchive <id|name>`.

**Pi 0.80.6**
- `--fork <path|id>`, `--session <path|id>`, `--session-id <id>`,
  `--session-dir <dir>`, `-n/--name`.

**OpenCode 1.18.3**
- `--fork` (used with `-c/--continue` or `-s/--session <id>`), `opencode
  session` subcommand, `opencode export/import [sessionID]`.

**Kilo Code 7.4.11**
- OpenCode-lineage; same `--fork`/`--session`/`--continue` surface plus
  `--cloud-fork`.

## What light framing search already turned up (resolve, don't repeat)

A quick pre-check (not the deep-research pass) surfaced a direct conflict and
two open upstream feature requests that bear directly on this design. Treat
these as leads to run down with primary sources, not as answers:

- `agent-deck` (github.com/asheshgoplani/agent-deck) is a real, existing
  terminal session manager across Claude/Gemini/OpenCode/Codex whose "fork"
  feature reportedly inherits full parent context and creates a new git
  worktree + branch. Read its actual implementation (not just its README) to
  see how it solves the same cross-directory-fork problem this project
  faces.
- Two different secondary sources disagree on whether Claude Code's
  `--resume --fork-session` can target a different working directory today:
  one implies a working `--cwd`-style flow exists; another states
  `--resume`/`--fork-session` are hard-filtered to
  `~/.claude/projects/<encoded-$PWD>/` and that cross-directory fork requires
  manually copying the session's `.jsonl` into the target directory's encoded
  project folder first — citing open GitHub issues
  `anthropics/claude-code#58591` ("Resume sessions in a different working
  directory: --cwd flag") and `#60272` (forking to decouple from a prior
  session's working directory). Resolve this conflict from primary sources
  (official docs, the actual issue threads, changelog entries) — this is the
  single most consequential unknown in this research.
- Open issue `openai/codex#8923` ("expose current Codex session ID
  programmatically") suggests no supported `CODEX_SESSION_ID`-style env var
  exists yet. A secondary source described the rollout file path as the
  nested, date-partitioned
  `~/.codex/sessions/YYYY/MM/DD/rollout-<ISO_TIMESTAMP>-<uuid>.jsonl` —
  confirm this against Codex's own docs or source, since it changes the
  "find the currently-running session" heuristic from a flat-directory scan
  to a partitioned one.

## The research questions

**1. Claude Code cross-directory fork.** Sessions are stored per project
directory (`~/.claude/projects/<munged-cwd>/`). If the parent session lives
in directory A and we run `claude --resume <parent-id> --fork-session` from
a NEW worktree directory B, does it find the session? Is there a supported
cross-directory resume path (a `--cwd`-style flag, or something else), or
must the session file be copied/linked into directory B's project folder
first — and if so, is that copy operation safe and supported, or an
undocumented workaround liable to break? What does `agent-deck` (or
similar tooling) actually do to solve this, mechanically?

**2. Claude Code fork semantics.** Does `--fork-session` carry the FULL
conversation context (not a summary/truncation)? Can `--session-id` pre-pin
the fork's UUID non-interactively (no picker, fully scriptable)? Does
`--name` work combined with `--resume --fork-session` in one invocation? Any
flag-interaction gotchas documented in the 2.x changelogs (e.g., ordering
requirements, flags that silently no-op in combination)?

**3. Codex self-discovery.** From INSIDE a running Codex session (i.e., a
shell command Codex itself executes), how do we discover the current
session's UUID? Is there any supported `CODEX_*` env var (confirm the
`#8923` request's implication that there is not, and note if that's changed
since)? What is the actual current rollout/session file layout under
`~/.codex/sessions/` (confirm or correct the nested
`YYYY/MM/DD/rollout-<timestamp>-<uuid>.jsonl` shape above), and how do we
reliably map "newest rollout file for this cwd" to the actually-running
session (race conditions? multiple concurrent sessions in the same cwd?).
Separately: how do we detect that we are running inside Codex at all —
what env vars or other signals distinguish a Codex-spawned shell from a bare
terminal or from Claude Code?

**4. Codex fork semantics.** Does `codex fork <uuid>` work with an explicit
UUID from ANY cwd (bypassing the cwd-filtered picker), consistent with `-C`
setting the fork's working root cleanly? Does the fork carry full context?
Version history: when did `codex fork` land, and was it ever rollout-gated
or experimental (it's understood to have been rollout-gated circa early
2026) — when did it stabilize into general availability, with dates and
version numbers?

**5. Fallback pattern.** Where a true fork is impossible (CLI too old,
headless/CI constraints, unsupported cross-directory case from Q1), what is
the current state of the art for "start a fresh named session seeded with a
handoff/context file written into the worktree"? Cover known conventions:
a `HANDOFF.md`-style file, Claude Code's `--append-system-prompt-file` (or
equivalent), Codex's initial `PROMPT` positional argument, and
`AGENTS.md`/`CLAUDE.md` seeding conventions. Which of these are documented
features vs. community convention?

**6. v2 targets — one paragraph each, high-level only.** For **Pi**,
**OpenCode**, and **Kilo Code**: where are sessions stored on disk, does
`--fork` carry full context, and what is the cross-directory behavior (does
it share Claude Code's cwd-scoping problem, Codex's cwd-filtering-with-
override model, or something else)? No deep API dive — this is a landscape
note for a future v2 pass, not a terminal leaf.

## Answer requirements

- **Version-stamped claims.** Every behavioral claim must cite the CLI
  version and/or documentation date it was verified against. A claim with no
  version/date attached is not usable.
- **Source URLs for every claim.** Official docs and changelogs preferred;
  GitHub issues/discussions acceptable when they are the primary evidence
  (e.g., an open feature request proving a gap exists); blog posts/
  aggregators only as corroboration, never as sole source for a load-bearing
  claim.
- **Explicit CONFIRMED vs UNVERIFIED labeling** on every claim — CONFIRMED
  means cross-checked against an official/primary source (docs, changelog,
  or source code); UNVERIFIED means secondary-source-only or inferred.
- **Surface conflicts explicitly**, especially the Claude Code
  cross-directory conflict in the framing section above — state what each
  source claims and which (if either) is authoritative, rather than picking
  one silently.
- **State confidence and its basis** per claim/section (e.g., "cross-checked
  against source" vs. "single blog post, unverified").
- **State assumptions** — note what the research assumed about the use case
  (e.g., single-user local terminal workflow, no CI/headless constraint)
  so a future reader knows whether it transfers.
- **Currency check** — flag anything that changed recently (last 1-2 minor
  versions) that could make an otherwise-correct answer stale by the time
  this is implemented.
- **Recommend, don't just list.** Close with a concrete recommended
  implementation approach per v1 target (Claude Code, Codex CLI) for how
  `agent-fork` should invoke fork/resume and discover the running session's
  ID — conditional recommendations are fine and preferred over false
  certainty (e.g., "if cross-directory `--fork-session` is unsupported as of
  version X, use the copy-then-resume workaround, with caveat Y").

## Final required section: what could only be verified by live experiment

Close with an explicit list of every claim or behavior that documentation,
changelogs, and issue trackers could not settle with confidence, and that
therefore requires running the actual CLI locally to confirm (e.g., "whether
copying a `.jsonl` session file into a different project's encoded directory
and then running `--resume --fork-session` actually works" or "whether two
concurrent Codex sessions in the same cwd produce an ambiguous 'newest
rollout' read"). This list drives the local experiments to run next — be
specific enough that each item is directly actionable as a test.
