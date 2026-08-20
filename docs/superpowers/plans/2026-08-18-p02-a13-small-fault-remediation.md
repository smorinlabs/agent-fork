# P02-A13 — Targeted small-fault remediation

This document defines and tracks the five small A13 remediations that share the
`worktree-p02-a13-small-fixes` branch. The intended reader is the engineer
implementing or reviewing A13. The required outcome is five independently
testable corrections without absorbing the separate D, G, or H1 designs.

The CLI interface review uses CLI Design Standard 1.4.14 at the repository's
existing publishable tier. A13(B) deliberately removes one human output value.
The other four changes preserve the public command grammar and machine schemas.

| P02 gate | State |
|---|---|
| Adversarial validation and sizing | **complete**; each sub-item was executed in an isolated scratch repository |
| Owner scope decision | **approved** on 2026-08-18; solve A, B, C, E, and F together, remove `table`, and route D, G, and H1 separately |
| Design and implementation plan | **approved with changes**; independent adversarial review completed on 2026-08-18 and all six required changes are incorporated below |
| Test-driven implementation | **complete**; per-item and combined evidence recorded below |
| Adversarial implementation review | **APPROVE**; the final re-review confirmed both initial blockers are resolved and found no new correctness blocker |

## Outcome required

The branch must make these five corrections:

| Item | Current problem | Required result | Production boundary |
|---|---|---|---|
| A | A successful human `fork --copy` can print the same clipboard-failure notice on stdout and stderr. | Human stdout contains only the requested result. The notice appears exactly once on stderr. JSON retains `notices[]`. | `src/agent_fork/output.py` |
| B | `table` and `text` are two names for byte-identical human output. | Remove `table` from the CLI, environment setting, help, completions, requirements, and documentation. Make `text` the default. | `src/agent_fork/cli.py`, `src/agent_fork/config.py`, and `src/agent_fork/completion.py` |
| C | A Codex app-server `thread/read` error is converted into successful `not_found` lineage. `session validate --no-parent` can therefore pass when parent evidence is unavailable. | Preserve the existing typed `SessionResolutionUnavailableError`, render lineage as `unavailable` with a notice, and refuse both parent-presence assertions when evidence is unavailable. | `src/agent_fork/codex_app_server.py` and `src/agent_fork/session.py` |
| E | Intent-to-add paths derived from filenames are passed back to Git as pathspec syntax. Overlapping patterns can double-apply a patch, and a filename beginning with pathspec magic can fail. | Mark every intent-to-add filename operand as literal while preserving exact bytes and index state. | `src/agent_fork/materialize.py` |
| F | Cleanup correctly refuses commits that are absent from every remote, but the human guidance says only “push first” when no remote exists. | Keep the refusal and machine fields unchanged. If no remote is configured, explain that the user must configure one before pushing. | `src/agent_fork/cleanup.py` |

These boundaries count production files only. Focused tests and required
documentation are additional files.

## Executed validation evidence

Every retained defect was reproduced through production paths before a
prototype was written.

### A — duplicate clipboard notice

A successful `fork --no-agent --copy -o text` with clipboard helpers absent
exited 0. The identical notice appeared in human stdout and once on stderr.
The prototype removed two renderer lines from `ForkOutput.render()`, the method
that renders a completed fork. It kept the CLI's stderr emission and JSON
`notices[]`. The focused file passed 21 tests after the RED assertion failed.

### B — duplicate human-format names

`-o table` and `-o text` produced byte-identical stdout, stderr, and exit codes
for `fork --dry-run`, `session`, `list`, `cleanup`, `doctor`, and
`config view`. Every executable companion-skill route under
`.agents/skills/agent-fork` invokes only `--json`; the skill has no CLI
`table` dependency. The skill's Markdown presentation tables are unrelated and
remain unchanged.

Owner decision: remove `table` rather than document it as an alias. This is an
intentional compatibility break before the deferred v1 release. It also creates
a release-blocking nonconformance with CLI Design Standard 1.4.14 rule R4.1,
which requires `table` as the default human format. A local waiver cannot make
this conforming because R4.1 is a `MUST`, not a `SHOULD`. The implementation
must record the nonconformance in `CONFORMANCE.md` and must not claim the
publishable CLI is conforming. Phase F release remains blocked until the
standard is amended or a real `table` default is restored. Rule R4.2 remains
satisfied because `-o`/`--output` stays the canonical format selector and
`--json` remains identical to `-o json`.

The removal is also a release blocker under R9.3, the SemVer interface-stability
rule. The repository has no Git tags and Phase F publication is deferred, but
`pyproject.toml` already declares version 1.0.0 and a Production/Stable
classifier, and the companion skill documents installation from Git. The
implementation therefore must not assume that “not published” removes all
compatibility obligations. Phase F must resolve both R4.1 and R9.3 before a
conforming release.

The exact B contract is:

- the accepted values are `text` and `json`;
- every human-result command defaults to `text`;
- `-o table` is an argparse usage error with exit code 2;
- `AGENT_FORK_OUTPUT=table` is a typed `config_error` with exit code 2 when
  `fork` or a `config` action resolves it as the effective value. `doctor`
  converts that configuration error into its existing failed diagnostic check
  and exits 1;
- an explicit `fork -o text`, `fork -o json`, or `fork --json` overrides an
  invalid lower-precedence `AGENT_FORK_OUTPUT` value under R5.1;
- `session`, `list`, and `cleanup` continue to ignore `AGENT_FORK_OUTPUT`
  because changing that broader configuration inconsistency belongs to A11;
- shell completions suggest only `text` and `json`;
- the companion skill remains unchanged because it uses JSON;
- support for `[fork].output` and `config set output` remains outside A13 and
  belongs to A11. B must not silently add that separate configuration feature.

### C — Codex app-server error conflation

A deterministic app-server returned three responses: successful
initialization, a list containing the requested thread, and a JSON-RPC error for
`thread/read`. The production CLI exited 0 with `lineage.status=not_found` and
no notice. A valid `thread/read` response with no parent produced the same
result, which proved the failure was indistinguishable from valid absence.

The prototype changes the error branch in `_query_threads()`, the bounded
Codex app-server query, from `return ()` to the existing typed `_failure()`
path. `validate_session()`, the session assertion service, also refuses a
`has_parent` assertion when lineage is `unavailable`; the same assertion field
represents both `--has-parent` and `--no-parent`. A valid no-parent response
remains successful. Two compatibility controls are required: a parent-name-read
failure must preserve the resolved parent ID while marking only its display
name unavailable, and lineage unavailability must not fail validation that
asserts only the agent or current session ID.

### E — intent-to-add pathspec interpretation

A single `src/[id].tsx` intent-to-add filename already copied correctly, so
that original example was refuted. Two surviving production failures were
confirmed:

1. Two overlapping intent-to-add patterns caused an ordinary `src/a.txt` patch
   to apply twice. The fork exited 1 and rolled back its worktree and branch.
2. A literal filename beginning `:(glob)` was interpreted as pathspec magic.
   The fork exited 1 and rolled back.

The prototype uses `:(literal)<path>` for the per-file diff and child
`git add --intent-to-add` operands. It uses `:(exclude,literal)<path>` for
ordinary-diff exclusions. All scenarios passed on Apple Git 2.50.1 and Flox
Git 2.54.0, and 52 relevant tests passed.

### F — cleanup guidance without a remote

With no remote configured, cleanup correctly found both local commits absent
from all remotes and exited 5. Its only safe guidance was the incomplete phrase
`or push first`. A configured repository whose commits were reachable exited
0. A configured repository with one local-only commit retained the appropriate
`push first` guidance.

The prototype adds one local `git remote` call only after cleanup has already
found unpushed commits and is about to refuse. It changes only the human
message. The error code, exit code, reachability rule, JSON object, `--force`,
and `--allow-unpushed` behavior remain unchanged.

The current product floor is Git 2.19. The prototype execution on Git 2.50.1
and 2.54.0 is not enough by itself. The implementation must update
`docs/testing/PRODUCT-GIT-MIN-AUDIT.md` with versioned documentation or
execution evidence for E's `:(literal)` and `:(exclude,literal)` pathspec forms
and F's read-only `git remote` call.

## Separate and refuted sub-items

The combined branch must not implement these items:

| Item | Disposition | Durable record |
|---|---|---|
| D | Separate: newline-safe worktree parsing needs four production files and a Git 2.19 versus Git 2.36 compatibility decision. | [GitHub issue #46](https://github.com/smorinlabs/agent-fork/issues/46) |
| G | Separate: protecting changed ignored files needs a persisted baseline and cleanup-lifecycle design across four production files. | [GitHub issue #44](https://github.com/smorinlabs/agent-fork/issues/44) |
| H1 | Separate: bounding staged-binary memory changes the central Git runner and adds temporary-file and disk lifecycle. | [GitHub issue #45](https://github.com/smorinlabs/agent-fork/issues/45) |
| H2 | No fix: `materialize()` already converts untracked paths to a set. Executed 500,000-by-500,000-path probes were linear, not quadratic. | Validation report retained outside the product tree; no production, test, or documentation change required. |

## Test-driven implementation plan

Each implementation group must prove RED before changing production code.

### Group 1 — A and C: output and unavailable evidence

1. Strengthen T-OUT-09 so clipboard failure must be absent from human stdout
   and present exactly once on stderr. Confirm RED, then remove only the human
   renderer's duplicate notice insertion. Add a JSON counter-case proving
   `notices[]` remains populated while stderr still contains one notice.
2. Add focused Codex-resolution tests for valid no-parent, JSON-RPC error, and
   malformed response. Add CLI/session assertion tests proving unavailable
   evidence cannot satisfy either parent-presence assertion. Confirm RED, then
   route the JSON-RPC error through the existing typed failure and add the
   assertion guard.
3. Update `docs/session-inspection.md` and the affected test-matrix rows.

### Group 2 — B: remove `table`

1. Add RED tests proving the default is `text`, `table` is rejected at the CLI
   and applicable `AGENT_FORK_OUTPUT` boundaries, `doctor` reports an invalid
   effective value through its diagnostic contract, and completions omit
   `table`. Add a valid explicit fork-output counter-case proving R5.1
   precedence over an invalid environment value.
2. Change every output choice and parser default together. Change the resolved
   configuration default to `text` and validate the final environment-derived
   value against `text|json`.
3. Update README, requirements, help assertions, completion assertions,
   `CONFORMANCE.md`, and the test matrix. `CONFORMANCE.md` must label R4.1 as a
   release-blocking `MUST` nonconformance, not as a waiver. Do not edit the
   companion skill.
4. Exercise default versus explicit `text` on all six top-level result
   surfaces: `fork --dry-run`, `session`, `list`, `cleanup`, `doctor`, and
   `config view`. Exercise `-o table` rejection on all eleven parser routes:
   those six routes, `session validate`, and the four `session claude-parent`
   actions `list`, `show`, `infer`, and `delete`. Inspect the parser objects so
   every independently declared output control has exactly the `text|json`
   choices and the correct `text` or configuration-derived default; use
   representative black-box invocations to lock exit behavior.

### Group 3 — E and F: Git operand safety and cleanup guidance

1. Extend T-MAT-12 with the overlapping and leading-magic intent-to-add cases.
   Confirm both fail and roll back at baseline. Add literal pathspec magic at
   the three filename-derived operand sites, then prove exact bytes, status,
   and rollback behavior.
2. Add T-CLN-24 for the no-remote refusal while retaining a configured-remote
   control. Confirm the guidance failure, then add the conditional local remote
   probe without changing machine fields or safety overrides. A JSON
   no-remote counter-case must preserve the existing error code and `details`;
   a configured-remote counter-case must retain `push first`.
3. Update `docs/testing/PRODUCT-GIT-MIN-AUDIT.md` for the Git syntax and command
   added by E and F, then retain the existing cross-Git execution gate.

The groups may run in parallel because their production files do not overlap.
Shared documentation is reconciled after their focused GREEN runs.

## Implementation evidence

The five fixes stayed inside the approved eight-production-file boundary. Tests
and documentation are counted separately.

| Item | RED evidence | Focused GREEN | Production result |
|---|---|---|---|
| A | Clipboard notice remained in human stdout. | The A/C focused group passed 6 tests; all 51 assigned A/C tests passed. | Removed two lines from `ForkOutput.render()`; JSON and stderr behavior remain explicit. |
| B | Two focused tests proved the default and nested parser values were still `table`. The first adversarial review then found a separate before-subcommand JSON overwrite; its new assertion failed before the correction. | T-CFG-18 and T-CLI-32 pass. The complete 35-test CLI file and 14-test configuration file pass after the review fix. | `text` is the default; only `text` and `json` are accepted. Child session parsers suppress absent defaults so parent-level `-o json` and `--json` survive all five nested actions. |
| C | Four target assertions failed while two valid-absence controls passed. | The A/C focused group passed 6 tests; all 51 assigned A/C tests passed. | JSON-RPC failure is typed unavailable evidence; valid no-parent, parent-name failure, and unrelated assertions remain distinct. |
| E | The overlapping-pattern and leading-magic public scenarios failed and rolled back. | T-MAT-12 passes; the full 20-test materialization file passes; Apple Git 2.50.1 and Flox Git 2.54.0 each pass both cross-Git rows. | All three ITA-derived operands use literal pathspec magic. |
| F | A no-remote refusal still provided only `push first` guidance. | Five focused E/F tests pass; the full 14-test cleanup file passes. | No-remote guidance explains remote setup; configured-remote text and JSON error fields remain stable. |

Repository-wide integration evidence:

- post-rebase `just all`: formatting, linting, type checking, version
  synchronization, and the hermetic suite passed; the suite reported 482
  passed, 1 expected skip, and 9 live/signal tests deselected;
- `just check-matrix`: 413 rows with one collected owner per live row after
  rebasing onto current `main`;
- `just strict-collect`: passed;
- `just fmt-check`, `just lint`, and `just typecheck`: passed;
- `just clean-install`: sdist, wheel, disposable installation, and packaged CLI
  smoke checks passed;
- `git diff --check`: passed.

The first adversarial implementation review returned `REJECT` for two
blockers. The code blocker was real: child `session` parsers overwrote
parent-level JSON options. T-CLI-32 now covers `-o json` and `--json` both
before and after `validate` plus all four `claude-parent` actions. The project
record blocker was resolved by updating only the A13 task block in
`projects/P02-agent-fork-fault-remediation.md`; the user-owned main-checkout
file and its unrelated A7 through A12 edits remain untouched.

The final adversarial re-review returned `APPROVE`. It independently verified
all 20 nested session route, option, and placement combinations; confirmed the
P02 task record and this design record match the completed and separated work;
and found no new correctness blocker in the resulting diff.

## Acceptance gates

The branch is complete only when all of these checks pass:

1. Focused RED evidence is recorded for A, B, C, E, and F.
2. Every focused test becomes GREEN with the stated production boundary.
3. The test-matrix checker reports no missing, duplicate, or unreferenced row.
4. The complete non-live test suite passes.
5. Ruff formatting and linting pass.
6. ty type checking passes.
7. A clean-install CLI check passes so parser defaults and completions are
   tested from a built artifact rather than only the source checkout.
8. `docs/testing/PRODUCT-GIT-MIN-AUDIT.md` supports E and F at the declared Git
   2.19 product floor.
9. An independent adversarial diff review finds no cross-fix regression,
   undocumented public change, weakened machine schema, or scope leak into D,
   G, H1, H2, or A11.

Commit, push, pull-request creation, merge, release, and cleanup of other
worktrees remain outside this implementation run unless the owner requests
them separately.
