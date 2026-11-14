# Agent Fork output examples — OpenCode

Load this file only after `agent-fork session --json` (or a fork run) reports
`"agent": "opencode"`. These examples fix formatting only: every rule in
SKILL.md still governs, every command string in real output is the CLI's
exact value character-for-character, and all session- and
repository-controlled values are terminal-escaped before display. The IDs,
paths, names, and counts below are illustrative examples, never material to
reconstruct a command from.

## `--session` — inspection summary

| Field | Value |
|---|---|
| Session | `ses_e2c7c88bcffeV0uSO2gZ67RGwa` (from `OPENCODE_SESSION_ID`) |
| Session name | `Auth refactor` (via opencode api) |
| Message route | `ses_e2c7c88bcffeV0uSO2gZ67RGwa` (address only) |
| Parent | `ses_e2c91a7afffe4l8DL2eUsdCt1n` "Auth main" (forked from, resolved) |
| Repository | `/Users/dev/project` |
| Branch | `feature/auth-refresh` |
| Status | staged 0 · unstaged 2 · untracked 0 |
| Transcript | none on disk (OpenCode keeps history in its database) |

Fork command — paste in a new terminal to fork this session in place:

```bash
cd /Users/dev/project && child=$(opencode api session.fork --param sessionID=ses_e2c7c88bcffeV0uSO2gZ67RGwa -d '{}' | sed -n 's/^{"data":{"id":"\(ses_[A-Za-z0-9]*\)".*/\1/p') && [ -n "$child" ] && opencode --session "$child"
```

It is one line of two commands: OpenCode forks the session through its
background service, then opens the child, which gets its own `ses_…` ID.
OpenCode has no single command that forks and opens without first running a
model turn.

Resume command — paste in a new terminal to rehydrate this exact session in
place (no new session, branch, or worktree):

```bash
cd /Users/dev/project && opencode --session ses_e2c7c88bcffeV0uSO2gZ67RGwa
```

The Transcript row renders `transcript.path: null`: OpenCode stores every
session in one shared database rather than a per-session file, so an
OpenCode session never reports a path. `opencode session export <id>` prints
one session's history as JSON; mention it only if the user asks how to read
the history.

Row variants: an unnamed session shows `—` for Session name; a session with
no recorded parent shows `none recorded (lineage: not_found)`; a name or
lineage the CLI could not look up shows `unavailable` (for example when the
OpenCode background service is stopped); a clean repository shows `clean`.
Append any `notices` afterward as a "Notices:" list, verbatim.

## `--session-only`

The entire reply is the exact `fork_command.command` string on one line — no
label, no code fence, no explanation. For example, the reply body is exactly:

cd /Users/dev/project && child=$(opencode api session.fork --param sessionID=ses_e2c7c88bcffeV0uSO2gZ67RGwa -d '{}' | sed -n 's/^{"data":{"id":"\(ses_[A-Za-z0-9]*\)".*/\1/p') && [ -n "$child" ] && opencode --session "$child"

## Fork confirmation (dry run)

**Fork plan** (dry run — nothing has been created)

| | |
|---|---|
| Current branch | `main` |
| New branch | `fork/review-auth` |
| Worktree | `/Users/dev/project-fork-review-auth` |

Files to carry:

| Staged | Unstaged | Untracked | Ignored |
|---|---|---|---|
| 2 | 1 | 3 | 0 |

Copy mode and rules:

| Rule | Value |
|---|---|
| Carry working-tree state (`with_state`) | default: true |
| Carry ignored files (`with_ignored`) | default: false |
| Your current checkout is modified | never |
| Anything created before you confirm | nothing |
| After creation | full verification ladder, then the OpenCode session is forked into the worktree |

The `with_state` and `with_ignored` values are the documented defaults, not
read from the dry run; user-level agent-fork configuration may override them,
and the files-to-carry counts always reflect the effective mode. The dry
run's command shows `<forked session ID>` because the child session does not
exist until the confirmed fork creates it; do not present that placeholder
as a command to paste. This plan text goes immediately before the single
three-option question SKILL.md specifies.

## Fork result (confirmed fork or `--now`)

**Fork created: review-auth**

- Branch: `fork/review-auth`
- Worktree: `/Users/dev/project-fork-review-auth`
- Verification: all checks passed

Continue in the fork — paste in a new terminal:

```bash
cd /Users/dev/project-fork-review-auth && opencode --session ses_e28dc03bdffey68mUW28f9PNEU
```

Unlike Claude Code and Codex, the OpenCode session is already forked: as the
fork's last step agent-fork created the child session and moved it into the
worktree, and this command opens it. The fork name names the branch and
worktree only — it is not passed to `opencode`. `agent-fork cleanup` later
removes the worktree but leaves the forked session in OpenCode's session
list. Append any `notices` verbatim.
