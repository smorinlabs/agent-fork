# CLI standards second-level hardening — adversarial review and TDD plan

**Date:** 2026-08-10
**Status:** Complete; S2-G5 green 2026-08-10
**Scope:** Follow-up to P01-T19; no release plumbing or publication
**Authority:** CLI Design Standard v1.4.14 obligations transcribed in
`REQUIREMENTS.md`, plus the built-binary audit in
`docs/testing/CLI-STANDARDS-AUDIT.md`

## 1. Gate and constraints

This document is analysis and planning only. It does not authorize production,
test-matrix, documentation-contract, or completion-script changes. Implementation
starts only after the owner approves the specific proposals below.

Locked constraints:

- preserve the Small-CLI seven-command surface;
- preserve current exit-number families and JSON envelope shape;
- keep runtime dependencies minimal; do not add a completion framework;
- add compatible detail only; do not rename existing flags or commands;
- run TDD with matrix IDs added atomically with their RED tests;
- stop after this hardening increment; do not begin P01-T20 or P01-T21.

## 2. Adversarial review by proposal

### S2-A — authoritative error catalog

**Original proposal:** enumerate every public error code and test the catalog.

**Evidence:** `STABLE_ERROR_CODES` currently contains seven values, while static
inspection finds at least twenty user-facing codes. Missing examples include
`conflict_branch_worktree`, `conflict_worktree_path`, `invalid_branch`,
`invalid_worktree_base`, `invalid_worktree_name`, `not_git_repository`, the
three cleanup guard codes, and `git_version_unsupported`. T-OUT-07 iterates the
same incomplete tuple it purports to verify, so it cannot detect omissions.

**Adversarial challenge:** indiscriminately declaring every internal exception
stable would freeze implementation accidents. A catalog duplicated across code,
tests, and prose would still drift. `ConfigError` currently exits 2 but renders
machine code `runtime_error`; silently renaming that code is compatible under the
open schema but is still an observable contract change requiring approval.

**Recommendation:** approve with a narrower definition: catalog every code that
can intentionally cross the CLI boundary, keep `runtime_error` as the documented
catch-all, and add the more accurate additive `config_error` code for handled
configuration failures.

**Before:**

```text
STABLE_ERROR_CODES = 7 hand-maintained strings
handled ConfigError JSON code = runtime_error, exit = 2
tests prove only that those same 7 strings render
```

**After (proposed):**

```text
ERROR_CATALOG[code] = {exit_code, meaning, remedy/family}
STABLE_ERROR_CODES = tuple(ERROR_CATALOG)
handled ConfigError JSON code = config_error, exit = 2
every intentional boundary code must be cataloged; runtime_error remains fallback
README/CONFORMANCE publish the catalog and compatibility rule
```

**Risks and controls:**

- Risk: missing dynamically supplied `PreconditionError` values. Control: AST
  inventory test plus runtime validation that production literals are cataloged.
- Risk: over-freezing test-only codes. Control: inventory production modules
  only; tests may still construct synthetic `AgentForkError` subclasses.
- Risk: changing existing consumer behavior. Control: retain every existing
  emitted code and exit number; only `ConfigError` becomes more specific.
- Risk: two sources of truth. Control: code catalog generates the documented
  test inventory; prose explains meanings but does not redefine values.

**Decision requested:** approve catalog hardening, and separately approve or
reject the `runtime_error` → `config_error` refinement for handled config errors.

### S2-B — real shell completions

**Original proposal:** replace top-level-only completion stubs with useful Bash,
Zsh, and Fish completions.

**Evidence:** Bash and Fish currently enumerate only seven top-level commands.
Zsh emits `compdef '_arguments *::command:->cmds' agent-fork`, which names no
command candidates and is not a complete command-specific function. No output
completes nested config actions, flags, enum values, or shell names. Existing
T-CLI-05 checks only that output is nonempty and mentions `agent-fork`.

**Adversarial challenge:** fully dynamic parser introspection can create brittle
shell code and import/version coupling. Requiring all three shells in every dev
environment would make tests non-portable. Hand-maintained scripts can drift from
the parser just as the error list did.

**Recommendation:** approve, using one Python completion model derived alongside
the argparse declaration and three deterministic renderers. Test semantic tokens
for all shells; run `bash -n`, `zsh -n`, and `fish -n` when the interpreter exists,
with CI installing all three for the blocking syntax gate.

**Before:**

```text
bash/fish: top-level command words only
zsh: generic placeholder
test: nonempty output containing agent-fork
```

**After (proposed):**

```text
all shells: commands + config actions + command-specific flags
fixed choices: claude/codex, table/text/json, bash/zsh/fish
syntax validation for each shell + cross-shell semantic parity test
```

**Risks and controls:**

- Risk: shell-specific quoting defects. Control: native syntax checks and hostile
  token fixtures.
- Risk: completion/parser drift. Control: compare a normalized completion model
  to argparse actions in a unit test.
- Risk: excessive generated script complexity. Control: complete only static
  grammar; do not complete repository paths, branches, sessions, or registry data.
- Risk: CI dependency expansion. Control: add shells only to development/CI,
  never runtime dependencies.

**Decision requested:** approve completion replacement and the CI-only Zsh/Fish
syntax dependencies.

### S2-C — reserved exit code 4 in help

**Original proposal:** consider adding the reserved authentication code to help.

**Adversarial result:** reject. Code 4 cannot be emitted, authentication is not
applicable, and displaying it suggests a capability the product does not have.
The reservation remains documented in `REQUIREMENTS.md`; user help should focus
on actionable outcomes.

**Before and after:** no change. No approval or implementation item needed.

### S2-D — semantic metavariables

**Original proposal:** replace generic argparse metavariables with the vocabulary
from the interface specification.

**Adversarial challenge:** using argparse `choices` for `--agent` would change an
unknown value from the locked exit 3 diagnostic to parser exit 2. Only display
metadata may change.

**Recommendation:** approve display-only `metavar` values; do not add parser
`choices` for `--agent`.

**Before:**

```text
[name], target, --agent AGENT, --worktree-base-dir WORKTREE_BASE_DIR
```

**After (proposed):**

```text
[NAME], TARGET, --agent {claude,codex}, --worktree-base-dir DIRECTORY
--parent-session ID, --branch BRANCH, --worktree-dir PATH,
--worktree-name COMPONENT
```

**Risk control:** assert unknown `--agent` still exits 3 with its existing error
code and message.

### S2-E — `config view` help consistency

**Original proposal:** describe its `-o/--output` option.

**Adversarial result:** approve. It is a localized omission with no behavior or
compatibility risk.

**Before:** `-o, --output {table,text,json}` with no explanation.
**After (proposed):** append `Select result format`.

### S2-F — config action ordering

**Original proposal:** match the specified `view|get|set|validate` order.

**Adversarial challenge:** help order is observable, but not semantic. Reordering
may churn snapshots and completions; retaining write-first order makes destructive
or mutating actions more prominent than inspection.

**Recommendation:** approve read-first order to match the locked specification.

**Before:** `{set,validate,view,get}`.
**After (proposed):** `{view,get,set,validate}`.

No command invocation changes; only help and completion ordering changes.

### S2-G — examples in help

**Original proposal:** add copyable examples.

**Adversarial result:** defer. README already contains the relevant examples,
while duplicating path/agent examples in argparse epilogs creates another drift
surface and makes top-level help longer. Reconsider only if usability testing
shows README discovery is insufficient.

**Before and after:** no change in this increment.

## 3. Proposed TDD inventory

Add rows only after approval:

| ID | Group | Tier | RED contract |
|---|---|---|---|
| T-OUT-14 | G-OUT | U | production boundary-code inventory equals the authoritative catalog |
| T-OUT-15 | G-OUT | C | every catalog entry renders the correct JSON code and maps to its documented exit family |
| T-OUT-16 | G-OUT | C | handled config failure uses the owner-approved code (`config_error` if approved) and exit 2 |
| T-CLI-16 | G-CLI | C | Bash completion includes nested actions, flags, choices, and passes `bash -n` |
| T-CLI-17 | G-CLI | C | Zsh completion has semantic parity and passes `zsh -n` when installed |
| T-CLI-18 | G-CLI | C | Fish completion has semantic parity and passes `fish -n` when installed |
| T-CLI-19 | G-CLI | C | help metavariables, config output description, and read-first config order match the approved before/after contract |
| T-CLI-20 | G-CLI | C | unknown agent remains exit 3 after display-only enum metadata |

Do not use lifecycle skips for missing shells. Semantic rendering tests always
run; native syntax tests use capability detection locally, while CI supplies all
three interpreters for the blocking gate.

## 4. Implementation sequence

### Gate S2-G0 — owner approval

Record decisions for:

1. S2-A catalog hardening;
2. S2-A `config_error` refinement independently;
3. S2-B completion replacement and CI-only shell packages;
4. S2-D/E/F help polish bundle.

S2-C is rejected and S2-G is deferred unless the owner overrides this review.

### Task S2-T1 — matrix and RED tests

- Set G-OUT and G-CLI to `tdd`.
- Add T-OUT-14..16 and T-CLI-16..20 atomically with collected failing tests.
- Keep `just check-matrix` and `just strict-collect` green while behavioral tests
  are red.

Gate S2-G1: prove each new test fails for the intended missing behavior.

### Task S2-T2 — authoritative error contract

- Introduce the typed catalog in `errors.py` or a dedicated dependency-light
  module.
- Derive `STABLE_ERROR_CODES` from it for compatibility.
- Enforce production code/catalog completeness.
- Apply the separately approved config-code decision.
- Add the user-facing catalog to README/CONFORMANCE and amend the audit evidence.

Gate S2-G2: T-OUT-14..16 green; all prior G-OUT rows green; machine stderr remains
one JSON object without tracebacks.

### Task S2-T3 — completion model and renderers

- Define one static completion model adjacent to parser construction.
- Render deterministic Bash, Zsh, and Fish scripts.
- Cover commands, config actions, command flags, and fixed choices only.
- Add Zsh/Fish to the CI development environment if approved.
- Extend clean-install smoke tests to generate and syntax-check completions.

Gate S2-G3: T-CLI-16..18 green; semantic parity and available native syntax
checks green against the installed wheel.

### Task S2-T4 — help polish bundle

- Apply display-only metavariables.
- Add the missing config-view output description.
- Register config actions in read-first order.
- Preserve runtime unknown-agent validation and exit 3.

Gate S2-G4: T-CLI-19..20 and all prior G-CLI rows green.

### Task S2-T5 — closure and adversarial verification

- Return G-OUT/G-CLI to `done` only after every added row passes.
- Update `CLI-STANDARDS-AUDIT.md`, `CONFORMANCE.md`, and P01 without marking
  P01-T20/P01-T21 complete.
- Run hostile completion tokens, JSON errors under `--debug -vv`, parser errors,
  missing-shell conditions, and catalog mutation tests.
- Run all repository gates against source and a disposable wheel.

Gate S2-G5:

```bash
make check
flox activate -- just all
flox activate -- just check-matrix
flox activate -- just strict-collect
flox activate -- just clean-install
git diff --check
```

Required evidence: all new rows and prior regressions green; only retired
T-EXP-04 skipped; no new waiver; no runtime dependency; no release/publish work.

## 5. Stop boundary

After S2-G5, stop for owner review. Do not create release automation, configure
trusted publishing, modify Homebrew/Nix/Flox distribution, tag v0.1.0, or publish
anything. Those remain P01-T20 and P01-T21.

## 6. Completion evidence

- T-OUT-14..16 and T-CLI-16..20 are live and green; G-OUT/G-CLI are `done`.
- `just all`: 255 passed, with only retired T-EXP-04 skipped.
- Matrix validation, strict collection (256 items), formatting, lint, typing,
  diff hygiene, and disposable wheel installation are green.
- Bash, Zsh, and Fish completion output passes native syntax validation and
  includes global options, commands, nested config actions, command options,
  and fixed choices.
- The production boundary-code inventory equals the authoritative 21-code
  catalog; handled configuration errors emit `config_error` with exit 2.
- Reserved exit 4 was not added to help and CLI examples were not duplicated,
  matching the adversarial recommendations.
- No P01-T20/P01-T21 release or publication work began.
