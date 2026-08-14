# Fork Confirmation Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `agent-fork` companion skill confirm every fork — showing where you are, where it would land, and what it would be called — before creating anything, with an exact `--now` token to skip that confirmation.

**Architecture:** All changes live in the skill's instruction text and its text-assertion tests; no Python source changes. The confirmation summary is rendered from the CLI's existing `--dry-run --json` output rather than from the skill's own prediction, so the branch name, worktree path, and carried-file counts shown to the user are the CLI's computed values. Naming is resolved before the dry run, from one of three sources depending on branch state.

**Tech Stack:** Markdown (`SKILL.md` is instruction text an agent reads, not executable code), pytest text assertions, `uv`, `just`, `ruff`, `ty`.

**Spec:** `REQUIREMENTS.md` REQ-49 (amended by Task 5 of this plan). The Decisions section below is the authoritative statement of the new behavior and is what REQ-49 will be amended to match.

## Global Constraints

- `SKILL.md` frontmatter must keep starting exactly `---\nname: agent-fork\ndescription:` — new keys go after `description`.
- `SKILL.md` must contain exactly one `\n---\n` (the closing frontmatter fence). **Never add a Markdown horizontal rule to the body** — it breaks `test_skill_is_one_shared_claude_and_codex_artifact`.
- `SKILL.md` must stay under 500 lines (`len(text.splitlines()) < 500`). It is 254 lines at plan time.
- The substring `scripts/` must never appear in `SKILL.md` (`test_wrapper_is_removed_without_a_replacement_executable`).
- **Test assertions are line-wrap sensitive.** Every phrase asserted by a test must sit on a single line in `SKILL.md`. A phrase split across a line break fails with a confusing message. Verified failure mode during PR #22: `assert "still print the install command" in text` failed purely because the paragraph rewrapped.
- `allowed-tools` needs no change: the dry run is covered by the existing `Bash(agent-fork:*)`, and the question is covered by the existing `AskUserQuestion`.
- Every commit is Conventional Commits and ends with the session trailer used by the repo.
- Gate before every commit: `make check`, then `just all`. Expect `369 passed, 1 skipped, 9 deselected` plus the new tests.
- Work happens in a git worktree, never the live checkout or local `main`.

## Decisions (the spec this plan implements)

| Decision | Value |
|---|---|
| Confirmation default | Every fork route confirms before mutating |
| Confirmation shape | One question, three options — create as shown / different name / don't fork |
| Summary source | `agent-fork fork … --dry-run --require-agent --json` |
| Skip token | Exact `--now` |
| `--now` + name hint | Allowed, either order |
| `--now` + `--session`/`--session-only` | Refused |
| Naming under `--now` | Unchanged from the confirmed path — never random |
| `--session` / `--session-only` | Ungated, unchanged, read-only |
| Natural-language naming delegation ("fork this, you pick the name") | **Still confirms.** An exact `--now` is the only skip |

That last row retires the current `SKILL.md` rule "If the user already
delegated naming, use the recommendation without asking." Delegating the
*name* is not the same as waiving the *confirmation*, and keeping the skip
token-exact means the gate cannot be crossed by phrasing. Task 3 deletes that
rule deliberately, not incidentally.

### Why the summary comes from a dry run

A dry run against this repo's own worktree branch produced:

```json
{"dry_run": true, "mutation_performed": false,
 "plan": {"branch": {"name": "fork/worktree-feat+fork-confirmation-gate-0814"},
          "worktree": {"path": "/Users/stevemorin/c/agent-fork/.claude/worktrees/feat+fork-confirmation-gate-fork-worktree-feat+fork-confirmation-gate-0814"},
          "files_to_carry": {"staged": 0, "unstaged": 0, "untracked": 0, "ignored": 0}}}
```

The CLI-derived name inherited the harness's `worktree-` prefix and the `+`, and the destination nested inside the current worktree's parent. Neither is predictable from the skill's side, and both are exactly what a user would want to catch before the directory exists. This is the motivating example for the whole feature.

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `.agents/skills/agent-fork/SKILL.md` | The skill's instruction text — argument gate, naming, confirmation, routes | Modify (all four behavior tasks) |
| `tests/skill/test_companion_skill.py` | Text assertions locking the skill's contract | Modify (all four behavior tasks) |
| `REQUIREMENTS.md` | REQ-49, the normative skill requirement | Modify (Task 5) |
| `projects/P01-agent-fork-v1.md` | Task tracking + the "one word" acceptance criterion | Modify (Task 5) |
| `README.md` | User-facing description of the skill's forms | Modify (Task 5) |

---

### Task 1: Add `--now` to the argument gate

Parsing only. No fork behavior changes yet — this task makes `--now` a recognized token and updates the surfaces that enumerate the supported forms.

**Files:**
- Modify: `.agents/skills/agent-fork/SKILL.md:4` (frontmatter `argument-hint`)
- Modify: `.agents/skills/agent-fork/SKILL.md:15-32` (argument gate section)
- Modify: `.agents/skills/agent-fork/SKILL.md:170-184` (refuse section)
- Test: `tests/skill/test_companion_skill.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: the guarantee that an exact `--now` token is stripped from the argument text before name normalization, and that all remaining text is the name hint. Tasks 3 and 4 rely on this.

- [ ] **Step 1: Write the failing test**

Add to `tests/skill/test_companion_skill.py`:

```python
def test_now_is_a_third_exact_option_token() -> None:
    text = _text()
    assert 'argument-hint: "[name-hint] [--now] | --session | --session-only"' in text
    assert "Exact `--now` skips the fork confirmation." in text
    assert "never accompany `--session` or `--session-only`" in text
    assert "other than those three exact forms" in text
    assert "all remaining text is one name hint" in text
    assert "/agent-fork [name hint] [--now]" in text
```

- [ ] **Step 2: Update the two existing assertions this task invalidates**

Both pin strings that Steps 4-6 replace. Missing either one makes Step 7 fail.

In `test_option_like_input_refuses_without_mutation`, replace this line:

```python
    assert "Every token beginning with `-` other than those two exact forms" in text
```

with:

```python
    assert "Every token beginning with `-` other than those three exact forms" in text
```

In `test_frontmatter_declares_argument_and_tool_hints`, replace this line:

```python
    assert 'argument-hint: "[name-hint|--session|--session-only]"' in text
```

with:

```python
    assert 'argument-hint: "[name-hint] [--now] | --session | --session-only"' in text
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/skill/test_companion_skill.py -q`
Expected: FAIL — `test_now_is_a_third_exact_option_token` and `test_option_like_input_refuses_without_mutation`.

- [ ] **Step 4: Update the frontmatter hint**

In `.agents/skills/agent-fork/SKILL.md`, replace:

```yaml
argument-hint: "[name-hint|--session|--session-only]"
```

with:

```yaml
argument-hint: "[name-hint] [--now] | --session | --session-only"
```

- [ ] **Step 5: Extend the argument gate**

In the `## Apply the argument gate first` list, insert this bullet immediately after the `--session-only` bullet:

```markdown
- Exact `--now` skips the fork confirmation. It may accompany a name hint in
  either order, and may never accompany `--session` or `--session-only`.
```

Then replace this bullet:

```markdown
- Every token beginning with `-` other than those two exact forms is
  unsupported. Refuse without calling the CLI.
- Only input containing no option-like token may become an explicit name hint.
```

with:

```markdown
- Every token beginning with `-` other than those three exact forms is
  unsupported. Refuse without calling the CLI.
- After removing an exact `--now`, all remaining text is one name hint.
```

- [ ] **Step 6: Update the refuse section**

Replace:

```markdown
The only skill options are the exact single-token forms `--session` and
`--session-only`. Every token beginning with `-` other than those two exact forms
is unsupported and must refuse before normalization and before any CLI call.
```

with:

```markdown
The only skill options are the exact single-token forms `--session`,
`--session-only`, and `--now`.
Every token beginning with `-` other than those three exact forms
is unsupported and must refuse before normalization and before any CLI call.
```

Then add this bullet after the `--session-only` refusal bullet:

```markdown
- Refuse `--now` mixed with `--session` or `--session-only`.
```

And replace the supported-forms block:

```text
  /agent-fork [name hint]
  /agent-fork --session
  /agent-fork --session-only
```

with:

```text
  /agent-fork [name hint] [--now]
  /agent-fork --session
  /agent-fork --session-only
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/skill/test_companion_skill.py -q`
Expected: PASS, all tests.

- [ ] **Step 8: Run the full gate**

Run: `make check` then `just all`
Expected: all green.

- [ ] **Step 9: Commit**

```bash
git add .agents/skills/agent-fork/SKILL.md tests/skill/test_companion_skill.py
git commit -m "feat: accept --now as a third exact skill option"
```

---

### Task 2: Resolve one candidate name for every branch state

Introduces the naming rules the confirmation and `--now` both consume. Still no confirmation — this task only states how the name is chosen.

**Files:**
- Modify: `.agents/skills/agent-fork/SKILL.md` (new section before `### Fork with an explicit name hint`)
- Test: `tests/skill/test_companion_skill.py`

**Interfaces:**
- Consumes: Task 1's guarantee that `--now` is stripped and the remainder is the name hint.
- Produces: the term **candidate name** — exactly one normalized name resolved before any mutation — used verbatim by Tasks 3 and 4.

- [ ] **Step 1: Write the failing test**

```python
def test_candidate_name_resolves_from_hint_branch_or_context() -> None:
    text = _text()
    assert "### Choose the candidate name" in text
    assert "resolve exactly one candidate name before any mutation" in text
    assert "The user chose it; do not substitute your own." in text
    assert "let the CLI derive it" in text
    assert "derive the candidate from the active conversation" in text
    assert "the branch this work would become" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/skill/test_companion_skill.py::test_candidate_name_resolves_from_hint_branch_or_context -v`
Expected: FAIL — `assert '### Choose the candidate name' in text`.

- [ ] **Step 3: Add the section**

Insert immediately before `### Fork with an explicit name hint`:

```markdown
### Choose the candidate name

Fork routes resolve exactly one candidate name before any mutation. Pick the
first case that matches:

1. **An explicit name hint was given.** Normalize it per the rules below.
   The user chose it; do not substitute your own.
2. **No hint, and the branch names the work.** `repository.detached` is
   `false`, `repository.branch` is present, and `repository.on_default_branch`
   is `false`. Pass no positional name and let the CLI derive it, together
   with its date and collision suffixes. The dry run below reports the derived
   branch, so the confirmation still shows a real name.
3. **No hint, and the branch names nothing.** A default, detached, or
   unclassified branch carries no topic, so
   derive the candidate from the active conversation: a short name for
   the branch this work would become. Normalize it per the rules below.

Case 3 is a proposal, not a decision: it reaches the user through the
confirmation below, or through `--now` when they have chosen to skip that.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/skill/test_companion_skill.py::test_candidate_name_resolves_from_hint_branch_or_context -v`
Expected: PASS.

- [ ] **Step 5: Run the full gate**

Run: `make check` then `just all`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add .agents/skills/agent-fork/SKILL.md tests/skill/test_companion_skill.py
git commit -m "feat: resolve one fork candidate name per branch state"
```

---

### Task 3: Confirm every fork from a dry run

The core of the feature.

**Files:**
- Modify: `.agents/skills/agent-fork/SKILL.md` (new section after `### Choose the candidate name`)
- Modify: `.agents/skills/agent-fork/SKILL.md` (the `### Fork with an explicit name hint` and `### Fork with no name hint` routes)
- Test: `tests/skill/test_companion_skill.py`

**Interfaces:**
- Consumes: the **candidate name** from Task 2.
- Produces: the guarantee that no fork mutates without either an approval or an exact `--now`. Task 4 is defined as the exception to this.

- [ ] **Step 1: Write the failing test**

```python
def test_forks_are_confirmed_from_a_dry_run_before_mutation() -> None:
    text = _text()
    assert "## Confirm before creating a fork" in text
    assert "--dry-run --require-agent --json" in text
    assert "`mutation_performed` is `false`" in text
    assert "plan.files_to_carry" in text
    assert "Ask one question with three options" in text
    assert "Do not ask three separate questions." in text
    assert "A dry run is not a fork." in text
    assert text.index("## Confirm before creating a fork") < text.index(
        "### Fork with an explicit name hint"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/skill/test_companion_skill.py::test_forks_are_confirmed_from_a_dry_run_before_mutation -v`
Expected: FAIL — `assert '## Confirm before creating a fork' in text`.

- [ ] **Step 3: Add the confirmation section**

Insert immediately after the `### Choose the candidate name` section. Note the
heading is `###`, a sibling of the routes — an `##` here would nest every
remaining route under it. The test asserts `"## Confirm before creating a fork"`,
which matches `### Confirm…` as a substring, so both assertions hold.

```markdown
### Confirm before creating a fork

Every fork is confirmed before it exists, unless the argument gate found an
exact `--now`.

1. Resolve the candidate name above.
2. Compute the real plan without mutating anything:

   ```bash
   agent-fork fork '<candidate-name>' --dry-run --require-agent --json
   ```

   Omit the positional name only for the branch-derived case, which lets the
   CLI name it. Check that `dry_run` is `true` and
   `mutation_performed` is `false` before showing anything.
3. State the plan in visible text immediately before the question: the
   current branch, the target branch from `plan.branch.name`, the destination
   from `plan.worktree.path`, and the counts under `plan.files_to_carry`.
   Report those values verbatim. Do not predict, reformat, or shorten a path.
4. Ask one question with three options: create the fork as shown, use a
   different name, or do not fork. Do not ask three separate questions.
5. A different name re-enters at step 1 as an explicit hint. Declining stops
   without mutation and without a second question.
6. On approval, run the fork exactly as the route below specifies.

A dry run is not a fork. Never report one as a created fork, and never treat
an approved confirmation as finished until the real run returns.
```

- [ ] **Step 4: Point the explicit-name route at the confirmation**

Replace the body of `### Fork with an explicit name hint`:

```markdown
Treat all non-option text after the skill name as one name hint. Normalize it as
specified below, then run exactly this command shape:
```

with:

```markdown
Treat all non-option text after the skill name as one name hint. Normalize it
as specified below, confirm it as specified above, then run exactly this
command shape:
```

- [ ] **Step 5: Point the no-name route at the confirmation**

In `### Fork with no name hint`, replace steps 4 through 7:

```markdown
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
```

with:

```markdown
4. Resolve the candidate name and confirm it as specified above.
5. On approval of a branch-derived name, run exactly:

   ```bash
   agent-fork fork --require-agent --json
   ```

   Do not pass a positional name. The CLI owns branch-derived normalization and
   date and collision suffixes.
6. On approval of any other name, use the explicit-name route with it.
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/skill/test_companion_skill.py -q`
Expected: PASS, all tests.

- [ ] **Step 7: Run the full gate**

Run: `make check` then `just all`
Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add .agents/skills/agent-fork/SKILL.md tests/skill/test_companion_skill.py
git commit -m "feat: confirm every fork from a dry run before mutating"
```

---

### Task 4: `--now` fast path

**Files:**
- Modify: `.agents/skills/agent-fork/SKILL.md` (new subsection at the end of the confirmation section)
- Test: `tests/skill/test_companion_skill.py`

**Interfaces:**
- Consumes: Task 1's `--now` token and Task 2's candidate name.
- Produces: nothing later tasks depend on.

- [ ] **Step 1: Write the failing test**

```python
def test_now_skips_the_confirmation_but_never_the_naming_rules() -> None:
    text = _text()
    assert "### Skip the confirmation with `--now`" in text
    assert "skips the confirmation, never the naming rules" in text
    assert "never invents a random name" in text
    assert "skip the dry run and the question" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/skill/test_companion_skill.py::test_now_skips_the_confirmation_but_never_the_naming_rules -v`
Expected: FAIL — `assert '### Skip the confirmation with `--now`' in text`.

- [ ] **Step 3: Add the subsection**

Insert immediately before `### Fork with an explicit name hint`, so it sits
between the confirmation section and the routes:

```markdown
### Skip the confirmation with `--now`

An exact `--now` forks immediately: resolve the candidate name, then
skip the dry run and the question, and run the fork.

`--now` skips the confirmation, never the naming rules, so it
never invents a random name. A name hint still wins, a topic branch still
yields the CLI's derived name, and a default or detached branch still gets the
name proposed from the conversation. Report the effective name, branch, and
worktree afterward exactly as any other fork.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/skill/test_companion_skill.py -q`
Expected: PASS, all tests.

- [ ] **Step 5: Run the full gate**

Run: `make check` then `just all`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add .agents/skills/agent-fork/SKILL.md tests/skill/test_companion_skill.py
git commit -m "feat: add --now to fork without confirmation"
```

---

### Task 5: Reconcile spec, tracking, and README

The behavior is done; this task makes the normative documents agree with it. REQ-49 currently specifies the old unconfirmed behavior, so leaving it would put the spec in conflict with the skill.

**Files:**
- Modify: `REQUIREMENTS.md` (REQ-49)
- Modify: `projects/P01-agent-fork-v1.md` (task rows and the Manual Verification line)
- Modify: `README.md` (the supported-forms block and the paragraph describing them)

**Interfaces:**
- Consumes: the final behavior from Tasks 1-4.
- Produces: nothing.

- [ ] **Step 1: Amend REQ-49**

In `REQUIREMENTS.md`, find REQ-49 and append this sentence to the end of the requirement:

```markdown
Amended 2026-08-14 (owner, fork confirmation): every fork route resolves exactly one candidate name — an explicit hint, the CLI's branch-derived name on a topic branch, or a conversation-derived proposal on a default, detached, or unclassified branch — then confirms before mutating by computing `agent-fork fork … --dry-run --require-agent --json`, stating the current branch, `plan.branch.name`, `plan.worktree.path`, and `plan.files_to_carry` verbatim, and asking one question offering create-as-shown, a different name, or no fork. An exact `--now` skips that confirmation and its dry run without changing the naming rules; `--now` may accompany a name hint in either order, never `--session` or `--session-only`, and every other option-like token still refuses before any CLI call. Inspection through `--session` and `--session-only` remains ungated.
```

- [ ] **Step 2: Add the tracking rows**

In `projects/P01-agent-fork-v1.md`, insert immediately before the `- [x] Regression Test Status` line:

```markdown
Fork confirmation follow-up (gate: owner-approved design, TDD, local gates)
- [ ] [P01-TS29] Add RED coverage for the `--now` token, candidate-name resolution, the dry-run confirmation, and the `--now` fast path
- [ ] [P01-T48] Accept `--now` in the argument gate and resolve one candidate name per branch state
- [ ] [P01-T49] Confirm every fork from a dry run, and skip that confirmation under `--now`
- [ ] [P01-T50] Reconcile REQ-49, the P01 acceptance criterion, and README with the confirmed-fork behavior
```

- [ ] **Step 3: Amend the acceptance criterion**

In the same file's Manual Verification block, replace:

```markdown
- From a real Claude Code session: one word produces a verified fork and a paste command that works in a fresh terminal
```

with:

```markdown
- From a real Claude Code session: one word plus a confirmation produces a verified fork and a paste command that works in a fresh terminal; `--now` produces the same result in one step
```

- [ ] **Step 4: Update the README forms block**

In `README.md`, in the `## From inside your agent session` block, add these two lines after the `$agent-fork --session-only` line:

```text
/agent-fork try-redis --now  # Claude: fork immediately, no confirmation
$agent-fork try-redis --now  # Codex: fork immediately, no confirmation
```

- [ ] **Step 5: Update the README paragraph**

In the paragraph beginning `The skill calls the installed CLI directly.`, replace:

```markdown
An explicit name hint is
normalized to lowercase kebab case. With no
name, a topic branch uses the CLI's date-bearing automatic name and collision
suffixes. A default, detached, or unclassified branch gets one recommended name
and asks before mutation.
```

with:

```markdown
An explicit name hint is
normalized to lowercase kebab case. With no
name, a topic branch uses the CLI's date-bearing automatic name and collision
suffixes, and a default, detached, or unclassified branch gets a name proposed
from the conversation. Every fork is then confirmed against a dry run — showing
the target branch, the destination worktree, and the files it would carry —
before anything is created. `--now` skips that confirmation without changing
how the name is chosen.
```

- [ ] **Step 6: Run the full gate**

Run: `make check` then `just all`
Expected: all green. No test reads `REQUIREMENTS.md`, `README.md`, or the project file, so this task cannot break the suite; run it anyway to confirm nothing else drifted.

- [ ] **Step 7: Flip the tracking rows to done**

In `projects/P01-agent-fork-v1.md`, change `- [ ] [P01-TS29]`, `- [ ] [P01-T48]`, `- [ ] [P01-T49]`, and `- [ ] [P01-T50]` to `- [x]`, appending to each the observed result (for example `— 6 intended RED failures observed; 373 passed/1 skipped`).

- [ ] **Step 8: Commit**

```bash
git add REQUIREMENTS.md projects/P01-agent-fork-v1.md README.md
git commit -m "docs: reconcile REQ-49, P01, and README with confirmed forks"
```

---

## Verification

**Automated:** `make check` clean; `just all` green with four new tests (expect `373 passed, 1 skipped, 9 deselected`).

**Manual — these need a real agent session and cannot be automated:**

1. On a topic branch, run `/agent-fork` with no arguments. Expect a summary naming the target branch and worktree path, then one question. Decline it, and confirm with `agent-fork list` that no fork was created.
2. Repeat, and approve. Confirm the created branch and worktree match the values shown in the summary exactly.
3. On `main`, run `/agent-fork` with no arguments. Expect a conversation-derived name proposal rather than a branch-derived one.
4. Run `/agent-fork try-redis --now`. Expect no question and a fork named from the hint.
5. Run `/agent-fork --now --session`. Expect a refusal before any CLI call.
6. Run `/agent-fork --session`. Expect unchanged inspection output with no confirmation.

## Out of scope

- Any change to the `agent-fork` CLI itself. The CLI stays non-interactive by design; all confirmation lives in the skill.
- Changing the CLI's naming derivation, including the `worktree-` prefix and `+` seen in the motivating example. The confirmation surfaces the bad name so the user can override it; fixing the derivation is separate work.
- Persisting a "don't ask again" preference. `--now` is per-invocation.
