---
name: agent-fork
description: Inspect or fork the current Claude Code or Codex agent session. Use for "fork this session", `/agent-fork` or `$agent-fork` with an optional name hint, exact `--session` for inspection plus its native fork command, exact `--session-only` to print only that command, or questions asking for the current agent session ID or repository context. Mixed or other option-like text refuses before any CLI call. Do not use for ordinary Git branch, worktree, directory, or status requests that do not mention the active agent session or Agent Fork.
---

# Agent Fork

Delegate to the installed `agent-fork` CLI. Run every command from the user's
active repository directory. Let the CLI own agent detection, session evidence,
Git operations, automatic naming, verification, rollback, registry state, and
continuation-command construction.

## Apply the argument gate first

Inspect the complete skill argument text before choosing a route or discarding
any token. This gate precedes every CLI call:

- Exact `--session` selects session inspection including the native fork
  command.
- Exact `--session-only` selects command-only output. `--session-only` is one exact token,
  not `--session` followed by text.
- `--session` combined with any other text is invalid. `--session-only` combined with any other text
  is also invalid. Refuse without calling the CLI.
  In particular, `/agent-fork --session review-auth` and
  `/agent-fork --session-only review-auth` are not named forks.
- Every token beginning with `-` other than those two exact forms is
  unsupported. Refuse without calling the CLI.
- Only input containing no option-like token may become an explicit name hint.

Never remove `--session` and then treat the remaining text as a fork name.

## Classify the request

Classify before normalizing. Choose exactly one route.

### Inspect the current agent session and include its fork command

For exact skill argument `--session`, or a natural-language request for the
current Claude Code/Codex session ID or that agent session's repository context,
run exactly:

```bash
agent-fork session --json
```

Validate the session object and its `fork_command` object as specified below.
Summarize the fields the user requested; show raw JSON only when requested. If
the command status is `available`, include `fork_command.command`
character-for-character under a clear fork-command label. Do not rebuild,
reorder, re-quote, execute, or copy it. For `not_detected`, `ambiguous`, or
`unsafe_input`, report the exact status and null command.

### Print only the current session's fork command

For exact skill argument `--session-only`, run exactly:

```bash
agent-fork session --json
```

Validate the same session and `fork_command` object used by `--session`. When
status is `available`, emit only the exact `fork_command.command` string,
character-for-character, with no label, explanation, code fence, reconstruction,
execution, or clipboard action. For `not_detected`, `ambiguous`, or
`unsafe_input`, report the exact unavailable status and stop without inventing a
command.

### Fork with an explicit name hint

Treat all non-option text after the skill name as one name hint. Normalize it as
specified below, then run exactly this command shape:

```bash
agent-fork fork '<normalized-name>' --require-agent --json
```

Pass the normalized value as one shell-quoted argument. Do not add `--agent` or `--parent-session`; strict ambient detection belongs to the CLI.

### Fork with no name hint

For `/agent-fork`, `$agent-fork`, or “Fork this session” without a name:

1. Run `agent-fork session --json` from the active repository directory.
2. If `agent` or `current_session` is null, report `lineage.status` and stop.
   Naming cannot make strict agent detection succeed.
3. If `repository` is null, report the invocation `directory` and stop. Asking
   for a name cannot make the directory forkable.
4. If `repository.detached` is `false`, `repository.branch` is present, and
   `repository.on_default_branch` is `false`, run exactly:

   ```bash
   agent-fork fork --require-agent --json
   ```

   Do not pass a positional name. The CLI owns branch-derived normalization and
   date and collision suffixes.
5. For a default, detached, or unclassified branch, recommend one concise name
   from the active conversation and ask what name to use.
6. If the user already delegated naming, use the recommendation without asking.
7. Normalize the selected name and use the explicit-name route.

Use the same working directory for inspection and fork. Do not run `cd` or
change branches between the two calls.

### Refuse option-like input

The only skill options are the exact single-token forms `--session` and
`--session-only`. Every token beginning with `-` other than those two exact forms
is unsupported and must refuse before normalization and before any CLI call.

- For `--status`, say: Use `--session` to inspect the current agent session.
- Do not turn `--sesion` into a fork name.
- Refuse `--session` mixed with a name or another token.
- Refuse `--session-only` mixed with a name, `--session`, or another token.
- Show the three supported forms:

  ```text
  /agent-fork [name hint]
  /agent-fork --session
  /agent-fork --session-only
  ```

Advanced destination, state-copy, verification, identity, output, clipboard,
dry-run, and force controls are direct-CLI use cases, not skill arguments.

## Normalize an explicit or recommended name

Produce `[a-z0-9]+(?:-[a-z0-9]+)*`:

1. Trim surrounding whitespace.
2. Convert ASCII letters to lowercase.
3. Replace each run outside ASCII letters and digits with one hyphen.
4. Collapse repeated hyphens and remove leading/trailing hyphens.
5. Ask for another name if normalization is empty.

Examples:

```text
"Review Auth" -> "review-auth"
"feature/auth-refresh" -> "feature-auth-refresh"
"Fix OAuth @ Login" -> "fix-oauth-login"
"---" -> empty; ask for another name
```

When the name changes, report
`Fork name normalized: "<input>" -> "<normalized>"` before mutation. Do not ask
for another confirmation solely because of mechanical normalization. Preserve
an explicit-name collision error; do not silently suffix a user-selected name.

## Validate and present CLI results

If `agent-fork` is missing from `PATH`, show
`uv tool install agent-fork` and stop.

Treat exit 0 as success only when stdout is one JSON object with the expected
route fields:

- Session: `agent`, `current_session`, `parent_session`, `lineage`, `notices`,
  `directory`, `repository` (which may be null), and `fork_command`.
  `fork_command` must be an object whose `status` is exactly `available`,
  `not_detected`, `ambiguous`, or `unsafe_input`. `available` requires a
  non-empty string `command`; every other status requires a null `command`.
- Fork: a non-empty string `command` and non-empty strings `fork.name`, `fork.branch`, and `fork.worktree`.

Otherwise report `Invalid agent-fork JSON output` and stop. Do not invent
missing values. An unknown future `fork_command.status` is invalid output; stop
without reconstructing or executing anything.

On fork success, present the effective name, branch, and worktree, followed by
the exact returned `command` string. Do not rebuild, reorder, or re-quote it.

Preserve nonzero CLI output and stop.

- Do not retry with guessed session IDs.
- Do not search transcripts.
- Do not run hand-written Git commands.
- Do not fall back to Git-only mode.
- Do not execute a returned session fork command.
