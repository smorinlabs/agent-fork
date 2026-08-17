# Agent Fork output examples — Codex

Load this file only after `agent-fork session --json` (or a fork run) reports
`"agent": "codex"`. These examples fix formatting only: every rule in
SKILL.md still governs, every command string in real output is the CLI's
exact value character-for-character, and all session- and
repository-controlled values are terminal-escaped before display. The IDs,
paths, names, and counts below are illustrative examples, never material to
reconstruct a command from.

## `--session` — inspection summary

| Field | Value |
|---|---|
| Session | `11111111-1111-4111-8111-111111111111` (from `CODEX_THREAD_ID`) |
| Session name | `auth-refactor` (via codex app-server) |
| Parent | `22222222-2222-4222-8222-222222222222` "auth-main" (forked from, resolved) |
| Repository | `/Users/dev/project` |
| Branch | `feature/auth-refresh` |
| Status | staged 0 · unstaged 2 · untracked 0 |

Fork command — paste in a new terminal to fork this session in place:

```
codex fork 11111111-1111-4111-8111-111111111111 -C /Users/dev/project
```

Codex assigns the fork its own thread ID at launch and runs in the `-C`
directory.

Row variants: an unnamed session shows `—` for Session name; a session with
no recorded parent shows `none recorded (lineage: not_found)`; a clean
repository shows `clean`. Append any `notices` afterward as a "Notices:"
list, verbatim.

## `--session-only`

The entire reply is the exact `fork_command.command` string on one line — no
label, no code fence, no explanation. For example, the reply body is exactly:

codex fork 11111111-1111-4111-8111-111111111111 -C /Users/dev/project

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

```
codex fork 11111111-1111-4111-8111-111111111111 -C /Users/dev/project-fork-review-auth
```

The fork name names the branch and worktree only — it is not passed to
`codex`, which assigns the new thread its own ID at launch. No directory
prompt is expected (`cwd_prompt_expected` is false). Append any `notices`
verbatim.
