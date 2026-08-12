# Direct companion skill and repository-aware session context — SDD/TDD plan

**Date:** 2026-08-11
**Status:** Owner-approved 2026-08-11; P01 decomposition recorded;
implementation not started
**Scope:** Replace the companion wrapper with direct CLI delegation, add
repository context to the existing session result, and stop before release work
**Project:** P01 — agent-fork v1
**Baseline:** `main` at `49b7caf`, which implements D18/REQ-47 session
inspection and D19/REQ-48 Claude parent inference
**Review:**
[`2026-08-11-direct-companion-skill-session-adversarial-review.md`](2026-08-11-direct-companion-skill-session-adversarial-review.md)

## 1. Outcome

Keep one agentic skill named `agent-fork`. The skill delegates to the installed
`agent-fork` CLI; it does not invoke a skill-side executable.

| User intent | Skill action |
|---|---|
| Inspect this agent session | `agent-fork session --json` |
| Fork with an explicit name hint | Normalize the hint, then run `agent-fork fork '<name>' --require-agent --json` |
| Fork without a name from a non-default branch | Inspect the session, then run `agent-fork fork --require-agent --json` |
| Fork without a name from a default, detached, or unknown branch | Inspect the session, recommend a name, ask for the name, then use the explicit-name route |

Delete `.agents/skills/agent-fork/scripts/fork_session.py`. The CLI already owns
agent detection, session identification, Git mutation, rollback, registry
writes, verification, automatic naming, collision handling, and continuation
command construction.

Extend `agent-fork session --json` additively with the invocation directory and
optional Git repository context. This makes the inspection route useful on its
own and gives the omitted-name route the facts it needs before mutation.

This plan deliberately adds no optional hardening command. It does not add a
`--status` skill alias, a name-validation CLI command, a combined inspect-and-
fork command, or a conditional branch assertion. It does not authorize release
work, configuration expansion, network access, transcript-search expansion, or
another skill-side script.

## 2. Terms and authoritative existing behavior

- A **name hint** is the natural-language text after the skill invocation. It
  is not a raw list of CLI options.
- A **default branch candidate** is the remote branch named by `origin/HEAD`,
  plus any locally present `main` or `master` branch. This preserves the CLI's
  current default-branch classification.
- A **topic branch** is an attached branch for which
  `repository.on_default_branch` is `false`.
- An **automatic name** is a name produced by the CLI when no positional name
  is passed. The current CLI derives `<branch>-<MMDD>` or
  `detached-<sha>-<MMDD>` and suffixes collisions.
- An **explicit name** is a positional name passed to `agent-fork fork`.
  Explicit-name collisions refuse instead of receiving an automatic suffix.

The following behavior on `main` remains authoritative:

- `agent-fork session --json` reports `agent`, `current_session`,
  `parent_session`, `lineage`, and `notices`.
- No detected agent is an observational `not_detected` result with exit 0.
- Simultaneous Claude Code and Codex signals are an observational `ambiguous`
  result with exit 0.
- `session validate` owns assertion failures.
- Session inspection is read-only and does not require a Git repository.
- `agent-fork fork --require-agent --json` detects the active agent and session
  from the environment and refuses missing or ambiguous identity.
- Omitting the CLI name enables automatic date and collision suffixing.

## 3. Locked skill interface

### 3.1 Session route

Run this exact command when the skill argument is exactly `--session`:

```bash
agent-fork session --json
```

Use the same route for a natural-language request that explicitly asks for the
current Claude Code or Codex session identifier or for the current agent
session's directory, repository, branch, worktree type, or Git status.

Do not claim generic requests such as “show Git status” or “what branch am I
on?” when they do not mention the agent session or `agent-fork`.

`--session` is a skill argument, not a `fork` option. A mixed invocation such as
`/agent-fork --session review-auth` refuses without calling the CLI.

The skill summarizes the requested fields from JSON. It emits raw JSON only
when the user asks for raw JSON.

### 3.2 Explicit-name fork route

Classify the input before normalization. If any argument-like token begins with
`-`, apply the refusal behavior in section 3.4. Otherwise, treat all text after
the skill name as one name hint.

These two invocations therefore mean the same thing:

```text
/agent-fork review-auth
/agent-fork Review Auth
```

Both normalize to `review-auth` and run:

```bash
agent-fork fork 'review-auth' --require-agent --json
```

Run from the user's active repository directory. Pass the normalized name as
one shell-quoted argument. Never interpolate unnormalized user text into the
shell command.

### 3.3 Omitted-name fork route

For `/agent-fork`, `$agent-fork`, or “Fork this session” without a name:

1. From the user's active repository directory, run
   `agent-fork session --json`.
2. If `agent` is null or `current_session` is null, report the observed
   `lineage.status` and stop. Naming cannot make a strict fork succeed.
3. If `repository` is null, report that the invocation directory is not an
   available Git repository and stop. Asking for a name cannot make a fork
   succeed there.
4. If `repository.detached` is `false`, `repository.branch` is present, and
   `repository.on_default_branch` is `false`, run:

   ```bash
   agent-fork fork --require-agent --json
   ```

   Do not convert the branch into a positional name. The CLI owns branch-based
   normalization, the date suffix, and collision suffixing.
5. If the repository is on a default branch, detached, or has no resolved
   default-branch classification, recommend one concise name from the active
   conversation and ask what name to use.
6. If the user already delegated naming, use the recommendation without asking.
7. Normalize the selected name and use the explicit-name route.

The two CLI calls in this route must use the same working directory. The skill
must not run `cd` or change branches between inspection and fork.

### 3.4 Unsupported option-like input

The skill accepts one reserved argument, `--session`. Every other token that
begins with `-` refuses before normalization and before any CLI call.

The refusal message lists the supported forms:

```text
/agent-fork [name hint]
/agent-fork --session
```

For `/agent-fork --status`, say to use `/agent-fork --session`. For a spelling
error such as `/agent-fork --sesion`, do not silently reinterpret the text as a
fork name.

Advanced destination, state-copy, verification, identity, output, clipboard,
dry-run, and force controls remain direct-CLI use cases. Removing their current
skill pass-through is an intentional simplification, not an accidental
compatibility promise.

## 4. Fork-name normalization

The skill converts an explicit or recommended name hint to this accepted
format:

```text
[a-z0-9]+(?:-[a-z0-9]+)*
```

Apply the following deterministic operations after option classification:

1. Trim surrounding whitespace.
2. Convert ASCII letters to lowercase.
3. Replace each run of characters outside ASCII letters and digits with one
   hyphen.
4. Collapse repeated hyphens.
5. Remove leading and trailing hyphens.
6. Ask for another name if the result is empty.

Examples:

| Name hint | CLI name argument |
|---|---|
| `Review Auth` | `review-auth` |
| `feature/auth-refresh` | `feature-auth-refresh` |
| `Fix OAuth @ Login` | `fix-oauth-login` |
| `---` | no command; ask for a name |

When normalization changes the hint, report the change before mutation:

```text
Fork name normalized: "Review Auth" -> "review-auth"
```

Do not ask for a second confirmation merely because normalization was
mechanical. The restricted result is a valid subset of the CLI's accepted name
space, so the CLI's existing sanitizer is idempotent for the value the skill
passes.

Preserve an explicit-name collision error. Do not retry with a silently changed
name. Automatic topic-branch naming remains collision-safe because it omits the
positional name.

## 5. Additive repository context for `session`

### 5.1 JSON contract

Add `directory` and `repository` without renaming or removing existing fields:

```json
{
  "agent": "codex",
  "current_session": {
    "id": "019fef75-cac2-7ba1-b1ad-d43a4034f4fe",
    "id_source": "CODEX_THREAD_ID",
    "id_status": "observed",
    "name": null,
    "name_status": "unavailable",
    "name_source": null
  },
  "parent_session": null,
  "lineage": {
    "has_parent_evidence": false,
    "status": "unavailable"
  },
  "notices": [],
  "directory": "/Users/stevemorin/c/agent-fork",
  "repository": {
    "root": "/Users/stevemorin/c/agent-fork",
    "branch": "main",
    "detached": false,
    "remote_default_branch": "main",
    "default_branch_candidates": ["main"],
    "on_default_branch": true,
    "linked_worktree": false,
    "bare": false,
    "status": {
      "clean": true,
      "staged": 0,
      "unstaged": 0,
      "untracked": 0,
      "unmerged": 0,
      "operation": null
    }
  }
}
```

Field definitions:

- `directory` is the resolved invocation directory. It can be a subdirectory
  inside the worktree.
- `repository.root` is the current worktree root for a non-bare repository. For
  a bare repository, it is the resolved bare repository path.
- `repository.branch` is the short symbolic `HEAD` branch or null when detached.
- `repository.remote_default_branch` is the branch named by `origin/HEAD`, or
  null when it is unavailable.
- `repository.default_branch_candidates` is deterministic: the remote default
  first, followed by locally present `main` and `master`, with duplicates
  removed. This preserves current fork classification.
- `repository.on_default_branch` is a Boolean when at least one candidate is
  known. It is null when no candidate can be determined.
- `repository.linked_worktree` distinguishes a linked worktree from the main
  checkout using the existing Git/common-directory comparison.
- `repository.status` is null for a bare repository. A bare repository has no
  working tree whose state can be counted.
- `status.staged`, `status.unstaged`, `status.untracked`, and
  `status.unmerged` count unique Git-visible paths in each independent state.
  One path may appear in more than one count.
- `status.operation` is one of the existing recognized operations—`rebase`,
  `merge`, `cherry-pick`, `revert`, or `bisect`—or null.
- `status.clean` is true only when all four counts are zero and `operation` is
  null. Ignored paths do not affect this value and are not counted.

Outside a Git repository, preserve the existing session evidence and add:

```json
{
  "directory": "/private/tmp",
  "repository": null
}
```

These two fields are shown in isolation. They are additive members of the
existing document. An ordinary outside-Git result needs no notice. A missing
Git executable, unsafe-repository refusal, permission failure, or malformed Git
response also produces `repository: null`, adds a bounded notice, and leaves
session inspection successful.

The same additive fields appear inside the `session` member returned by
`session validate --json` because validation embeds the inspection document.

### 5.2 Human output

Human `agent-fork session` output appends concise directory and repository lines
after the existing identity result. It does so even when session identity is
`not_detected` or `ambiguous`.

Escape directory paths, branch names, operation names, and notices with the
existing `terminal_text()` boundary. Never print repository-controlled bytes
directly to a terminal.

### 5.3 Implementation boundary

Extend the existing `session` command. Do not add another session module or CLI
subcommand.

- Keep repository topology, default-branch classification, working-state
  counting, and operation detection in `src/agent_fork/repository.py`.
- Keep agent/session aggregation and additive serialization in
  `src/agent_fork/session.py`.
- Keep human rendering in `src/agent_fork/cli.py`.
- Reuse the PATH-resolved `run_git()` primitive and NUL-delimited Git output.
- Extract the default-candidate helper without changing the existing rule that
  locally present `main` and `master` remain candidates even when
  `origin/HEAD` names another branch.
- Let dry-run reuse the working-state helper only at the common counting seam.
  Dry-run's `with_state` suppression and ignored count remain caller-specific.
- Compute repository context once and attach it to every `inspect_session()`
  return path, including missing and ambiguous agent signals.
- Convert `SessionInspection` construction to keyword arguments before adding
  fields so existing positional `notices` values cannot bind silently to a new
  field.
- Preserve fork-path error semantics. Session inspection catches repository
  context failures and represents them as `repository: null` plus a notice;
  strict fork operations continue to refuse through their existing errors.

## 6. Confirmation, output, and failure behavior

Do not ask for confirmation when:

- the user supplies a non-empty name hint;
- the CLI can automatically name a fork from a known topic branch;
- the user explicitly delegates naming;
- the request is session inspection only.

Ask only for the missing name when an unnamed fork starts on a default,
detached, or unclassified branch. Include one recommended name based on the
active conversation.

On a successful fork, parse the JSON object and present the effective name,
branch, worktree path, and exact `command` string. Do not rebuild, reorder, or
re-quote the continuation command.

The skill must retain the two wrapper safeguards that do not belong to Git or
agent detection:

- If `agent-fork` is not on `PATH`, show `uv tool install agent-fork` and stop.
- If exit 0 does not return a JSON object with the expected route fields, report
  `Invalid agent-fork JSON output` and stop. A fork success requires a string
  `command` plus `fork.name`, `fork.branch`, and `fork.worktree`. A session
  success requires the existing identity fields plus `directory` and
  `repository`.

On nonzero CLI exit, preserve the JSON error or stderr and stop. Do not retry
with a guessed session identifier, search transcripts, issue hand-written Git
commands, or fall back to Git-only mode.

## 7. Corpus and project tracking

Use the next unallocated identifiers on baseline `49b7caf`:

- `D20` — the companion skill delegates directly to the existing CLI commands
  and uses repository-aware session context for omitted-name decisions.
- `REQ-49` — the two skill routes, direct command shapes, name normalization,
  confirmation rules, option refusal, output handling, and additive repository
  context.

Repair the related existing corpus while adding those entries:

- `DESIGN-DECISIONS.md`: put the D18 and D19 bodies under their correct
  headings, add `session` to the consolidated command surface, then add D20.
- `REQUIREMENTS.md`: replace wrapper-owned REQ-02 behavior; amend REQ-03 and
  REQ-26 so ambient CLI detection is the primary skill path; add the existing
  `session` tree; then add REQ-49.
- `IMPLEMENTATION-PROMPT.md`: bring its decision/requirement range current and
  replace the obsolete explicit-identity wrapper requirement.
- `CONFORMANCE.md`: correct cache applicability; backfill REQ-45..48 and
  D16..19; then add pending and final D20/REQ-49 evidence.

After the owner approves this plan and before implementation begins, run the
`project-refine` decomposition route for P01. It must:

- link this plan from `projects/P01-agent-fork-v1.md`;
- repair the stale P01 reference range and completed Claude-parent-plan note;
- allocate the next test-spec and implementation task identifiers by max+1;
- decompose the approved plan without changing `PROJECTS.md` project status.

The refinement pass recalculated the live maxima and allocated `P01-TS26` plus
`P01-T39..41`.

## 8. Test-matrix changes

Add the following rows to `G-SES`, whose current last row is `T-SES-22`:

| ID | Contract | Tier |
|---|---|---|
| `T-SES-23` | every identity outcome preserves existing fields and adds the exact resolved directory | U |
| `T-SES-24` | default, topic, detached, linked, and bare repository context uses deterministic classification | U |
| `T-SES-25` | clean, staged, unstaged, untracked, unmerged, and operation status is exact | U |
| `T-SES-26` | repository-context failures preserve session evidence, return `repository: null`, and add a bounded notice | U |
| `T-SES-27` | human output labels and escapes directory and repository-controlled values in every identity state | C |

Extend existing `T-SES-22` to assert the additive `directory` and
`repository: null` contract outside Git instead of adding a duplicate row.

Change `G-SES` from `done` to `tdd` while these rows are live. Add each matrix
row and its marked failing test in the same change so `just check-matrix`
continues to pass. Restore `G-SES` to `done` only after every row has one passing
test and full closure evidence.

Do not invent untracked `T-SKL-*` identifiers. The focused skill tests are
unnumbered because `tests/skill/` is not currently a matrix tier. Expanding the
matrix checker with a `G-SKL` group is outside this minimal change.

## 9. File-level implementation

### 9.1 Repository-aware session result

Modify:

- `src/agent_fork/session.py` — context aggregation, additive models, and
  serialization;
- `src/agent_fork/repository.py` — shared default-branch, status, and operation
  helpers;
- `src/agent_fork/cli.py` — human rendering for additive fields;
- `tests/unit/test_session.py` and `tests/cli/test_session.py` — T-SES-22..27;
- test fixtures only where a named topology or Git-failure seam is required.

Do not change existing identity, lineage, assertion, or Claude-parent evidence
semantics.

### 9.2 Direct companion skill

Modify:

- `.agents/skills/agent-fork/SKILL.md` — direct routing and low-freedom decision
  rules;
- `.agents/skills/agent-fork/agents/openai.yaml` — generated metadata that
  mentions both inspection and fork without biasing every invocation to fork;
- `tests/skill/test_companion_skill.py` — static contract, placement, and
  wrapper-absence checks;
- `README.md` — skill invocations, naming behavior, and session context.

Delete:

- `.agents/skills/agent-fork/scripts/fork_session.py`;
- the empty skill `scripts/` directory if no resource remains.

Do not replace the wrapper with another executable helper.

### 9.3 Corpus files

Modify:

- `DESIGN-DECISIONS.md`;
- `REQUIREMENTS.md`;
- `IMPLEMENTATION-PROMPT.md`;
- `CONFORMANCE.md`;
- `docs/testing/TEST-MATRIX.md`;
- `projects/P01-agent-fork-v1.md` through the approved `project-refine` pass.

## 10. TDD execution order

### Gate 0 — Owner approval and project decomposition — complete 2026-08-11

1. The owner approved both intentional behavior changes: unnamed topic-branch
   forks omit the positional name, and advanced CLI flags no longer pass
   through the skill.
2. `project-refine` allocated P01-TS26 and P01-T39..41.
3. Execution must stop if a newer `main` conflicts with this approved plan.

### Task 1 — Lock and repair the contract

1. Repair the D18/D19 ordering and stale command surfaces.
2. Add D20 and REQ-49; amend REQ-02, REQ-03, REQ-26, the implementation prompt,
   and conformance scope.
3. Change `G-SES` to `tdd`.
4. Add each T-SES-23..27 row atomically with its marked RED test; amend
   T-SES-22 with its new assertions.
5. Prove RED for behavior, not import or fixture failure, while keeping matrix
   and collection validation green.

### Task 2 — Extend session context test-first

1. Convert `SessionInspection` construction to keyword arguments.
2. Add repository-context models and attach them to every identity path.
3. Extract compatible default-branch, status-count, and operation helpers.
4. Cover default, topic, detached, linked, bare, subdirectory, outside-Git,
   unavailable-Git, dirty, conflicted, and mid-operation cases.
5. Add JSON and human black-box behavior without changing existing evidence.

### Task 3 — Replace the companion wrapper test-first

1. Rewrite focused tests around required literal routes, normalization examples,
   route classification before normalization, refusal text, missing-CLI advice,
   malformed-JSON handling, and exact handoff fields.
2. Rewrite `SKILL.md` to call the installed CLI directly from the active
   repository.
3. Regenerate `agents/openai.yaml` with the `skill-creator` tooling.
4. Delete `scripts/fork_session.py` and prove no repository reference remains.
5. Run the skill validator and focused skill tests.

Static tests prove the artifact's literal contract and placement. They do not
prove model interpretation, exact shell construction, or route choice. Those
behaviors require the real-agent forward tests in Task 4.

### Task 4 — Integrate, forward-test, and close

1. Update README, corpus evidence, project tracking, and conformance evidence.
2. Restore `G-SES` to `done` only when every row passes.
3. Install the editable CLI and the development skill placements.
4. Forward-test fresh, minimal prompts in real Claude Code and Codex sessions.
   Do not leak expected commands into the prompts.
5. Include negative forward cases for `--sesion`, `--status`, mixed
   `--session` input, hostile name text, empty normalization, missing CLI,
   malformed success JSON, ambiguous host signals, absent Git context, and an
   explicit-name collision. Prove no mutation for each refusing case.
6. Run all focused and full gates, record exact evidence, and stop before
   release work.

## 11. Verification gates

Focused gates:

```bash
uv run pytest tests/unit/test_session.py tests/cli/test_session.py -q
uv run pytest tests/skill/test_companion_skill.py -q
uv run python scripts/check_matrix.py
uv run pytest --collect-only -q
```

Full local gates:

```bash
just all
just check-matrix
just strict-collect
just clean-install
just test-git-matrix
just test-signals
```

Host-managed acceptance gate:

```bash
just test-live
```

Run the repository's `skill-creator` validation and metadata-generation commands
discovered from the installed skill instructions at execution time. Do not
hard-code a possibly stale generator path in this plan.

Real Claude Code and Codex acceptance must prove:

1. `/agent-fork --session` or `$agent-fork --session` reports the exact active
   session ID, invocation directory, repository root, branch, worktree type,
   and Git status without mutation.
2. An unnamed fork from a topic branch uses the CLI's date-bearing automatic
   name and suffixes an automatic collision.
3. An unnamed fork from a default branch asks with one recommended name before
   mutation.
4. Detached, unclassified, missing-agent, ambiguous-agent, and absent-repository
   contexts stop or ask for exactly the reason defined in section 3.3.
5. An explicit or recommended name is normalized before execution and its
   effective CLI result is reported.
6. The created worktree carries the expected staged, unstaged, and untracked
   state.
7. The exact returned continuation command resumes or forks the intended
   conversation in the reported worktree.
8. The parent session and parent worktree remain unchanged.

## 12. Done means

The work is complete only when:

- existing D18/REQ-47 and D19/REQ-48 evidence remains compatible;
- `session --json` adds directory and repository context in every identity
  outcome;
- human session output is present and terminal-safe in every identity outcome;
- the canonical skill implements inspection, explicit-name fork, and omitted-
  name fork behavior without a wrapper script;
- topic-branch auto-naming remains owned by the CLI;
- default, detached, unclassified, missing-agent, ambiguous-agent, absent-Git,
  empty-normalization, mixed-route, and unknown-option cases stop or ask for the
  defined reason;
- direct fork calls add `--require-agent --json` and never add explicit
  `--agent` or `--parent-session` values;
- missing-CLI, malformed-JSON, nonzero-error, and exact-command handoff behavior
  remains explicit in the skill contract and passes real-agent forward tests;
- matrix, focused, full, clean-install, Git-matrix, signal, skill-validation,
  and real-agent gates pass;
- corpus, P01 tracking, README, and conformance evidence are current;
- no release, publish, or unrelated cleanup work has started.

## 13. Accepted residual risk

The two-process omitted-name route has a small time-of-check/time-of-use window:
an external actor could change the checked-out branch after `session --json`
and before `fork`. Omitting the positional name prevents a stale inferred name,
but a topic-to-default branch change could bypass the intended name prompt.

Closing that race requires a new conditional CLI contract or a combined command.
Both are optional hardening and are excluded from this minimal replacement.
