# P09 — OpenCode as a full agent-fork agent

Detect OpenCode sessions and support fork, resume, transcript, and messaging.

### Open questions
- The database has a `session_inbox` table. Is there a supported way to deliver a message into a running OpenCode session (API endpoint via `opencode api`)?
- Does `opencode run --session <id>` reach an already-open TUI session through the background service, or a separate copy?

### Notes
OpenCode sets OPENCODE=1 and OPENCODE_SESSION_ID (ses_ + letters/digits) for commands (probed 2026-11-12, OpenCode 2.2.7, clean environment). IDs contain "_", which agent-fork's SAFE_SESSION_ID rejects; needs its own pattern.
Sessions: ~/.local/share/opencode/opencode.db (tables session_v2, session, session_message). Resume: `opencode --session <id>` (creates the session if the ID is unknown). Fork: `opencode run --session <id> --fork`. Transcript: `opencode session export <id>` (JSON). All verified from `--help` and a live session list 2026-11-12.

<!-- Idea state. Minimal by convention.
     Promote with `project-refine P09` when ready. -->
