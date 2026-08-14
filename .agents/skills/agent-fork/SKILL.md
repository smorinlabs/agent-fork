---
name: agent-fork
description: Inspect or fork the current Claude Code or Codex agent session. Use for "fork this session", `/agent-fork` or `$agent-fork` with an optional name hint and an optional exact `--now` to skip the confirmation, exact `--session` for inspection plus its native fork command, exact `--session-only` to print only that command, or questions asking for the current agent session ID or repository context. Other unsupported option-like text refuses before any CLI call. Do not use for ordinary Git branch, worktree, directory, or status requests that do not mention the active agent session or Agent Fork.
argument-hint: "[name-hint] [--now] | --session | --session-only"
allowed-tools: Bash(agent-fork:*), Bash(command -v:*), Bash(readlink:*), Bash(uv run:*), Read, AskUserQuestion
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
- Exact `--now` skips the fork confirmation. It may appear at most once and
  may accompany a name hint in either order.
  It may never accompany `--session` or `--session-only`.
- `--session` combined with any other text is invalid. `--session-only` combined with any other text
  is also invalid. Refuse without calling the CLI.
  In particular, `/agent-fork --session review-auth` and
  `/agent-fork --session-only review-auth` are not named forks.
- Every token beginning with `-` other than those three exact forms is
  unsupported. Refuse without calling the CLI.
- After removing the single exact `--now`, all remaining text is one name hint.
  That remaining text may contain no option-like token.

Never remove `--session` and then treat the remaining text as a fork name.

## Confirm the CLI before any route

Every route below calls `agent-fork`. An absent CLI is not a CLI refusal:
shell exit `127` or a `command not found` message means Agent Fork never ran.
Never present that as CLI output, and never substitute hand-written Git for it.

When the CLI is missing, always show the durable fix:

```bash
uv tool install git+https://github.com/smorinlabs/agent-fork
```

Install from the source repository. The bare package name is not installable:
the PyPI entry is a placeholder until the first published release.

You may also offer the no-install form as text for the user to run:

```bash
uvx --from git+https://github.com/smorinlabs/agent-fork agent-fork --version
```

Never run a network-fetched command on the user's behalf. Print it and let the
user decide.

### Offer a discovered source checkout before giving up

A missing CLI does not always mean the code is absent. Look for an Agent Fork
checkout in exactly two places, in order:

1. The active repository itself: read `pyproject.toml` at the directory the
   routes already run from, and confirm it declares `name = "agent-fork"`.
   Do not shell out to Git to locate a root.
2. The directory this skill was loaded from: resolve it with `readlink -f`,
   strip the trailing `.agents/skills/agent-fork`, and confirm the same
   `pyproject.toml` at what remains. A development symlink resolves to a
   checkout; a copied installation does not.

Read the candidate `pyproject.toml` and confirm the declared name before
proposing anything. Do not search the filesystem more widely, and do not guess
a path.

With a confirmed checkout, name it, say plainly that the run uses that working
tree rather than a released build, and ask before running the fallback. A dirty
or mid-refactor tree is a different program from a release, so this is the
user's call. On approval, run the classified route unchanged except for the
prefix:

```bash
uv run --directory '<checkout>' agent-fork session --json
```

Shell-quote the checkout path as one argument. Keep every route's arguments,
validation, and presentation rules exactly as specified below.
Then still print the install command so the user can make the fix permanent.

If no checkout is discoverable, or the user declines, stop with the install
command. Never install, fetch, or execute network-fetched code automatically,
and never substitute hand-written Git for the CLI.

A CLI that runs and then reports an environment problem is a different case.
Preserve its exact output and suggest `agent-fork doctor`, which checks Git,
the agent CLIs, configuration validity, and XDG paths.

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

### Choose the candidate name

Fork routes resolve exactly one candidate name before any mutation. Pick the
first case that matches:

1. **An explicit name hint was given.** Normalize it per the rules below.
   The user chose it; do not substitute your own.
2. **No hint, and the branch names the work.** `repository.detached` is `false`,
   `repository.branch` is present, and `repository.on_default_branch` is `false`.
   Pass no positional name and let the CLI derive it, together with its
   date and collision suffixes.
3. **No hint, and the branch names nothing.** A default, detached, or
   unclassified branch carries no topic, so
   derive the candidate from the active conversation: a short name for
   the branch this work would become. Normalize it per the rules below.

Case 3 is a proposal, not a decision: it reaches the user through the
confirmation below, or through `--now` when they have chosen to skip that.

### Confirm before creating a fork

Every fork is confirmed before it exists, unless the argument gate found an
exact `--now`.

1. Resolve the candidate name above. If this route has not already run
   `agent-fork session --json`, run it now — the dry run reports the fork it
   would create, not where you are, so the summary takes the current branch
   from `repository.branch`.
2. Compute the real plan without mutating anything:

   ```bash
   agent-fork fork '<candidate-name>' --dry-run --require-agent --json
   ```

   Omit the positional name only for the branch-derived case, which lets the
   CLI name it. Check that `dry_run` is `true` and
   `mutation_performed` is `false` before showing anything, and that
   `plan.branch.name`, `plan.worktree.path`, and `plan.files_to_carry` are all
   present.
   Report `Invalid agent-fork JSON output` and stop if any is missing.
3. State the plan in visible text immediately before the question: the
   current branch from `repository.branch`, or detached HEAD when it is
   null, the target branch from `plan.branch.name`, the destination
   from `plan.worktree.path`, and the counts under `plan.files_to_carry`.
   Report those values verbatim — semantically exact, never shortened or
   normalized — but
   terminal-escape them as repository-controlled values.
   Do not predict, reformat, or shorten a path.
4. Ask one question with three options: create the fork as shown, use a
   different name, or do not fork. Do not ask three separate questions.
5. A different name re-enters at step 1 as an explicit hint. Declining stops
   without mutation and without a second question.
6. On approval, run the fork exactly as the route below specifies.

A dry run is not a fork. Never report one as a created fork, and never treat
an approved confirmation as finished until the real run returns.

### Skip the confirmation with `--now`

An exact `--now` forks immediately: resolve the candidate name, then
skip the dry run and the question, and run the fork exactly as the route
below specifies, treating each route's approval step as already satisfied.

`--now` skips the confirmation, never the naming rules, so it
never invents a random name. A name hint still wins, a topic branch still
yields the CLI's derived name, and a default or detached branch still gets the
name proposed from the conversation. Report the effective name, branch, and
worktree afterward exactly as any other fork.

### Fork with an explicit name hint

Treat all non-option text after the skill name as one name hint. Normalize it
as specified below, confirm it as specified above, then run exactly this
command shape:

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
4. Resolve the candidate name and confirm it as specified above.
5. On approval of a branch-derived name, run exactly:

   ```bash
   agent-fork fork --require-agent --json
   ```

   Do not pass a positional name. The CLI owns branch-derived normalization and
   date and collision suffixes.
6. On approval of any other name, run the explicit-name route's command with
   it. That name is already confirmed; do not confirm it twice.

Use the same working directory for inspection and fork. Do not run `cd` or
change branches between the two calls.

### Refuse option-like input

The only skill options are the exact single-token forms `--session`,
`--session-only`, and `--now`.
Every token beginning with `-` other than those three exact forms
is unsupported and must refuse before normalization and before any CLI call.

- For `--status`, say: Use `--session` to inspect the current agent session.
- Do not turn `--sesion` into a fork name.
- Refuse `--session` mixed with a name or another token.
- Refuse `--session-only` mixed with a name, `--session`, or another token.
- Refuse `--now` mixed with `--session`, `--session-only`, or another `--now`.
- Show the three supported forms:

  ```text
  /agent-fork [name hint] [--now]
  /agent-fork --session
  /agent-fork --session-only
  ```

Advanced destination, state-copy, verification, identity, output, clipboard,
dry-run, and force controls are direct-CLI use cases, not skill arguments
(this restricts what the user may pass to the skill, not the confirmation's
own dry-run call above).

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

A missing CLI is handled by the preflight above, not here.

If session JSON is otherwise valid but contains no `fork_command` key at all,
the installed CLI predates that contract. Report
`Installed agent-fork predates the fork_command contract`, show the upgrade
command, and stop:

```bash
uv tool install --force git+https://github.com/smorinlabs/agent-fork
```

Do not report this as `Invalid agent-fork JSON output` and do not reconstruct
the command. `agent-fork --version` cannot separate these builds because the
contract changed without a version bump.

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
