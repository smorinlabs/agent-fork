# P08 — Muse as a full agent-fork agent

Detect Muse sessions and support fork, resume, transcript, and messaging.

### Open questions
- Does Muse have a native fork command, or must agent-fork fork the transcript itself? (`muse export --help` says exports include "fork/subagent lineage", so Muse has a fork concept; no `fork` subcommand is listed in `muse --help`.)
- Where is a Muse session's transcript file, and is `muse export` the supported read path?

### Notes
Muse sets MUSE_SESSION_ID and MUSE_THREAD_ID (same value) for commands; no Claude variables (probed 2026-11-12, Muse Code 1.4.18, clean environment).
Sessions: ~/.local/share/muse/session-index.db; resume with `cd <workspace> && muse resume <uuid>` (`muse resume --help`: takes "an exact session UUID or Session Name", scoped to the current workspace; not run interactively). Running sessions via `muse sessions --json`: verified 2026-11-12, a live `muse exec` session listed itself with `sessionId` equal to its MUSE_SESSION_ID and `name` `gold-asteroid`.

<!-- Idea state. Minimal by convention.
     Promote with `project-refine P08` when ready. -->
