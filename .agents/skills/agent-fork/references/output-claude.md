# Agent Fork output examples — Claude Code

Load this file only after `agent-fork session --json` (or a fork run) reports
`"agent": "claude"`. These examples fix formatting only: every rule in
SKILL.md still governs, every command string in real output is the CLI's
exact value character-for-character, and all session- and
repository-controlled values are terminal-escaped before display. The IDs,
paths, names, and counts below are illustrative examples, never material to
reconstruct a command from.

## `--session` — inspection summary

| Field | Value |
|---|---|
| Session | `11111111-1111-4111-8111-111111111111` (from `CLAUDE_CODE_SESSION_ID`) |
| Session name | `review-auth` (via Claude transcript) |
| Parent | none recorded (lineage: `not_found`) |
| Repository | `/Users/dev/project` |
| Branch | `main` (default branch) |
| Status | clean |

Fork command — paste in a new terminal to fork this session in place:

```bash
cd /Users/dev/project && claude --session-id 33333333-3333-4333-8333-333333333333 --resume 11111111-1111-4111-8111-111111111111 --fork-session
```

The `--session-id` value is the fork's new session ID, minted fresh on each
inspection.

Resume command — paste in a new terminal to rehydrate this exact session in
place (no new session ID, branch, or worktree):

```bash
cd /Users/dev/project && claude --resume 11111111-1111-4111-8111-111111111111
```

Row variants: an unnamed session shows `—` for Session name; a known parent
shows its ID with the lineage status, for example
`22222222-2222-4222-8222-222222222222 (lineage: claimed)`; qualify an
`inferred` parent with the CLI's exact staleness notice; a dirty repository
shows the counts, for example `staged 2 · unstaged 1 · untracked 3`. Append
any `notices` afterward as a "Notices:" list, verbatim.

## `--session-only`

The entire reply is the exact `fork_command.command` string on one line — no
label, no code fence, no explanation. For example, the reply body is exactly:

cd /Users/dev/project && claude --session-id 33333333-3333-4333-8333-333333333333 --resume 11111111-1111-4111-8111-111111111111 --fork-session

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
cd /Users/dev/project-fork-review-auth && claude --session-id 33333333-3333-4333-8333-333333333333 --resume 11111111-1111-4111-8111-111111111111 --fork-session -n review-auth
```

Claude may show a workspace-trust prompt for the new directory on first
launch. Append any `notices` verbatim.
