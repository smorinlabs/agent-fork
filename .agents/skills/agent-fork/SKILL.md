---
name: agent-fork
description: Inspect or fork the current Claude Code or Codex agent session. Use for "fork this session", `/agent-fork` or `$agent-fork` with an optional name hint and an optional exact `--now` to skip the confirmation, exact `--session` for inspection plus its native fork command, exact `--session-only` to print only that command, or questions asking for the current agent session ID or repository context. Other unsupported option-like text refuses before any CLI call. Do not use for ordinary Git branch, worktree, directory, or status requests that do not mention the active agent session or Agent Fork.
argument-hint: "[name-hint] [--now] | --session | --session-only"
allowed-tools: Bash(agent-fork:*), Bash(command -v:*), Bash(pwd -P), Bash(readlink:*), Bash(git ls-remote https://github.com/smorinlabs/agent-fork.git refs/heads/main), Bash(uv run --project:*), Bash(uvx --isolated --from git+https://github.com/smorinlabs/agent-fork@*), Bash(uv tool run --isolated --from git+https://github.com/smorinlabs/agent-fork@*), Bash(uv tool dir --bin), Bash(uv tool install git+https://github.com/smorinlabs/agent-fork@*), Bash(uv tool install --force git+https://github.com/smorinlabs/agent-fork@*), Read, AskUserQuestion
---

# Agent Fork

Delegate to a compatible `agent-fork` CLI. Run every command from the user's
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

A **runner** is the complete executable prefix used to launch Agent Fork.
Every `agent-fork` command below specifies the route arguments; replace its
`agent-fork` prefix with the selected runner for the whole operation, including
inspection, preview, fork, and doctor. Keep that prefix and source revision in
working context rather than relying on shell variables surviving tool calls.

1. Record the invocation directory with `pwd -P` before selecting a runner.
2. Honor an explicit installation or checkout choice through
   [the runner procedure](references/cli-runner.md). Otherwise probe
   `command -v agent-fork` and select that executable when present. If lookup
   fails, read `references/cli-runner.md` and select its temporary runner.
3. Run `agent-fork session --json` through the selected runner and validate it
   below. An absent executable, shell exit `127`, or `command not found` means
   Agent Fork never ran; read `references/cli-runner.md` and recover once.
   Otherwise-valid output missing a required contract field takes that same
   recovery path. Do not ask for confirmation merely because recovery fetches
   code. Malformed output and a CLI refusal do not trigger recovery.
4. Require session `directory` to equal the recorded invocation directory.
   If it differs, report `Agent-fork invocation directory mismatch` with both
   paths terminal-escaped and stop before presentation, preview, or mutation.
5. Reuse the validated inspection when entering the classified route. Do not
   rerun it solely because a route below shows `agent-fork session --json`.
   `--now` skips the fork preview and confirmation, not this read-only check.

Never report tool setup as a completed inspection or fork. A CLI that runs
and reports an environment problem has actually run: preserve its exact output
and suggest `agent-fork doctor` through the selected runner. Doctor checks Git,
the agent CLIs, configuration, XDG paths, and whether a setup hook would run.

## Classify the request

Classify before normalizing. Choose exactly one route.

### Inspect the current agent session and include its transcript, fork, and resume commands

For exact skill argument `--session`, or a natural-language request for the
current Claude Code/Codex session ID or that agent session's repository context,
run exactly:

```bash
agent-fork session --json
```

Validate the session object and its `fork_command` and `resume_command`
objects as specified below. Summarize the fields the user requested; show raw
JSON only when requested. If a command's status is `available`, include its
`command` character-for-character under a clear label — fork command for
`fork_command`, resume command for `resume_command`. `resume_command` is the
"rehydrate" command: it re-enters the exact same session in place (same
session ID, same directory, same branch/worktree) rather than creating a new
one, for picking a set-aside session back up. Do not rebuild, reorder,
re-quote, execute, or copy either command. For `not_detected`, `ambiguous`,
or `unsafe_input`, report the exact status and null command for each.

Also present `transcript`: the absolute path of the file where this session's
conversation is stored on disk — a Claude Code JSONL transcript or a Codex
rollout JSONL. When `transcript.path` is a string, show it under a clear label
with terminal control characters escaped — the path embeds the invocation
directory, so it is a repository-controlled value like any other and is
never printed raw — and state whether `transcript.exists` is `true` or
`false`; a
`false` value means the path is where the transcript belongs but no file is
there yet, which is normal early in a session and also happens when the CLI
was invoked from a directory other than the session's own. When
`transcript.path` is `null`,
report that the transcript could not be located and do not guess a path.
Escaping makes the value safe to display; it never licenses rewriting,
shortening, or re-encoding the path itself. Never read, summarize, copy, or
quote the file's contents — this field is a location only.

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

Advanced destination, state-copy, submodule-copy, verification, identity,
output, clipboard, dry-run, and force controls are direct-CLI use cases, not
skill arguments (this restricts what the user may pass to the skill, not the
confirmation's own dry-run call above). Submodules are carried recursively by
default (`--no-with-submodules` opts out); a dirty submodule counts as at
most one entry in `plan.files_to_carry` above (its own gitlink path) — the
individual files changed inside it are not broken out separately.

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

## Load the agent's output reference

When a successful `agent-fork session --json` or fork run reports `"agent"`,
read the matching example file from this skill's directory before presenting
results:

- `"claude"` -> `references/output-claude.md`
- `"codex"` -> `references/output-codex.md`

The file shows the presentation format for each route: the `--session`
summary, the bare `--session-only` line, the fork confirmation plan, and the
fork result. It changes formatting only; every validation, escaping, and
character-for-character command rule in this file still governs, and its
example values are never material to reconstruct a command from. When
`agent` is null or the CLI is missing, no reference applies.

## Validate and present CLI results

A missing CLI is handled by the preflight above, not here.

Before classifying output as an older contract, require exit 0, one JSON
object, the base session fields listed below, and valid values for every
present command or transcript object. Malformed JSON, invalid present fields,
and unknown status values are `Invalid agent-fork JSON output`; stop without
fetching or retrying.

Otherwise-valid session JSON without `fork_command` predates that contract.
Only the `--session` route also requires `resume_command` and `transcript`;
`--session-only` never requires either. Record the matching diagnostic:

- `Installed agent-fork predates the fork_command contract`
- `Installed agent-fork predates the resume_command contract`
- `Installed agent-fork predates the transcript contract`

Read `references/cli-runner.md`, select a compatible runner, and repeat the
inspection once before any mutation. On success, continue the original route
with that runner; a successful `--session-only` still emits only the returned
command. If recovery fails, report the diagnostic, missing fields, selected
source, and actual failure. Never recover after attempting a real fork.
`agent-fork --version` is not a reliable discriminator: `fork_command`'s
addition did not get one, so check required fields instead of trusting a version.

Treat exit 0 as success only when stdout is one JSON object with the expected
route fields:

- Session: `agent`, `current_session`, `parent_session`, `lineage`, `notices`,
  `directory`, and `repository` (which may be null), plus `fork_command`; the
  `--session` route additionally requires `resume_command` and `transcript`.
  Each of `fork_command` and `resume_command` must be an object whose `status`
  is exactly `available`, `not_detected`, `ambiguous`, or `unsafe_input`.
  `available` requires a non-empty string `command`; every other status
  requires a null `command`. `transcript` must be an object whose
  `transcript.path` is a non-empty string or null and whose
  `transcript.exists` is a boolean; a null `path` with `exists` true is
  invalid output.
- Fork: a non-empty string `command` and non-empty strings `fork.name`, `fork.branch`, and `fork.worktree`.

Otherwise report `Invalid agent-fork JSON output` and stop. Do not invent
missing values. An unknown future `fork_command.status` or
`resume_command.status` is invalid output; stop without reconstructing or
executing anything.

On fork success, present the effective name, branch, and worktree, followed by
the exact returned `command` string. Do not rebuild, reorder, or re-quote it.

Preserve nonzero CLI output and stop.

- Do not retry with guessed session IDs.
- Do not search transcripts.
- Do not run hand-written Git commands except the official-source
  `git ls-remote` lookup in `references/cli-runner.md`.
- Do not fall back to Git-only mode.
- Do not execute a returned session fork or resume command.
