# Agent Fork output examples — Muse

Load this file only after `agent-fork session --json` (or a fork run) reports
`"agent": "muse"`. These examples fix formatting only: every rule in
SKILL.md still governs, every command string in real output is the CLI's
exact value character-for-character, and all session- and
repository-controlled values are terminal-escaped before display. The IDs,
paths, names, and counts below are illustrative examples, never material to
reconstruct a command from.

## `--session` — inspection summary

| Field | Value |
|---|---|
| Session | `01a1d722-3e08-78b3-8ef6-9624efa87d7e` (from `MUSE_SESSION_ID`) |
| Session name | `gold-asteroid` (via `muse sessions --json`) |
| Message route | `01a1d722-3e08-78b3-8ef6-9624efa87d7e` "gold-asteroid" via Muse's in-session messaging (`muse-session-message`, address only) |
| Parent | `01a1d6db-8e09-7641-99ed-a374a24167d7` (forked from, resolved from the session log) |
| Repository | `/Users/dev/project` |
| Branch | `feature/auth-refresh` |
| Status | staged 0 · unstaged 2 · untracked 0 |
| Transcript | `/Users/dev/.local/share/muse/sessions/2026/11/13/01a1d722-3e08-78b3-8ef6-9624efa87d7e/session.jsonl` (on disk) |

Fork command — paste in a new terminal to fork this session in place:

```bash
cd /Users/dev/project && muse resume "$(/Users/dev/.local/bin/agent-fork muse-fork 01a1d722-3e08-78b3-8ef6-9624efa87d7e)"
```

Muse has no fork command, so the paste command forks when it runs:
`agent-fork muse-fork` asks `muse serve` to fork the session and prints the
new session ID, and `muse resume` opens it. If the fork fails, `muse resume`
refuses the empty ID and no session opens.

Resume command — paste in a new terminal to rehydrate this exact session in
place (no new session, branch, or worktree):

```bash
cd /Users/dev/project && muse resume 01a1d722-3e08-78b3-8ef6-9624efa87d7e
```

The Transcript row is `transcript.path`, terminal-escaped like every other
session- and repository-controlled value in this table, and never otherwise
rewritten. `(on disk)` renders `transcript.exists: true`. Muse session logs
are located by search rather than derived, so a Muse `transcript.path` is
never non-null with `exists: false`; an unlocatable log reads `not located`.

Row variants: an unnamed or not-running session shows `—` for Session name;
a session that is not a fork shows `none recorded (lineage: not_found)`; a
clean repository shows `clean`. Append any `notices` afterward as a
"Notices:" list, verbatim.

## `--session-only`

The entire reply is the exact `fork_command.command` string on one line — no
label, no code fence, no explanation. For example, the reply body is exactly:

cd /Users/dev/project && muse resume "$(/Users/dev/.local/bin/agent-fork muse-fork 01a1d722-3e08-78b3-8ef6-9624efa87d7e)"

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
| After creation | full verification ladder (anchor, branch, worktree registration, copy fidelity, parent untouched) |

The `with_state` and `with_ignored` values are the documented defaults, not
read from the dry run; user-level agent-fork configuration may override them,
and the files-to-carry counts always reflect the effective mode. This plan
text goes immediately before the single three-option question SKILL.md
specifies.

## Fork result (confirmed fork or `--now`)

**Fork created: review-auth**

- Branch: `fork/review-auth`
- Worktree: `/Users/dev/project-fork-review-auth`
- Verification: all checks passed

Continue in the fork — paste in a new terminal:

```bash
cd /Users/dev/project-fork-review-auth && muse resume "$(/Users/dev/.local/bin/agent-fork muse-fork 01a1d722-3e08-78b3-8ef6-9624efa87d7e)"
```

If a fork run fails with `runtime_error` and `Operation not permitted` on a
path under `~/.local/state/agent-fork`, Muse's sandbox blocked agent-fork's
state write; say so and ask the user to approve running the command outside
the sandbox. Do not claim that nothing was created: relay any rollback or
recovery instruction in the error verbatim, and before a retry check
`git worktree list` and the fork branch for leftovers.

The fork name names the branch and worktree only — it is not passed to
`muse`, which gives the forked session its own ID when the command runs. The
Muse session is created only when this command is pasted; it copies the
parent's completed turns. Muse asks whether to trust the new worktree the
first time. Muse sessions cannot be deleted, so pasting the command twice
leaves two forks. Append any `notices` verbatim.
