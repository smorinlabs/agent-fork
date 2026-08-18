# P02-A9 — Shared agent-signal assessment

This document defines and tracks `P02-T09`, the minimal remediation for fault
A9 in the P02 fault-remediation project. The intended reader is the engineer
implementing or reviewing A9. The required action is to keep every change
inside the approved agent-signal boundary and preserve the existing strict
session preflight before repository mutation.

The CLI interface review in this document uses CLI Design Standard 1.4.14 at
the existing publishable tier. A9 affects scripted machine output, diagnostic
output, and a pre-mutation refusal. It does not add commands, flags,
configuration, network access, streaming, plugins, or interactive behavior.

| P02 gate | State |
|---|---|
| 1. Adversarial verification, including Codex | **CONFIRMED-WITH-CORRECTIONS** on 2026-08-18; exhaustive matrix recorded below |
| 2. Owner scope decision | **approved**; four decisions recorded below |
| 3. Design document | **complete**; this document |
| 4. Implementation plan and adversarial review, including Codex | **APPROVE-WITH-CHANGES** on 2026-08-18; all required changes incorporated |
| 5. Test-driven implementation | **complete** on 2026-08-18; RED and GREEN evidence recorded below |
| 6. Adversarial implementation review, including Codex | **APPROVE** on 2026-08-18; all in-scope findings absorbed, no Gate-6 routing required |

## Outcome required

All ambient-agent consumers must call one pure assessment of the supported
environment values. The assessment reports exactly one state: `absent`,
`incomplete`, `detected`, or `ambiguous`.

Automatic and strict fork modes must refuse an incomplete Claude signal with
the stable error code `agent_signal_incomplete`, process exit code 3, and a
message that names the missing value. Explicit Git-only mode remains
authoritative. A complete explicit `--agent` and `--parent-session` pair also
remains authoritative.

The existing `preflight_agent()` function, which checks native-fork capability
and performs the current Codex-specific rollout availability check, remains
unchanged. It still runs before branch, worktree, registry, or lineage
mutation. It does not prove Claude session liveness. A syntactically complete
environment signal is therefore `detected`, not `validated`.

## Gate-1 verification verdict and evidence

The original `P02-TS09` probe established two different behaviors:

1. A detached process with only a fabricated `CODEX_THREAD_ID` made
   `session --json` report a Codex identity and an available constructed fork
   command. The strict fork path then failed with `session_not_found` before
   mutation because the existing preflight could not read the rollout.
2. `CLAUDECODE=1` without `CLAUDE_CODE_SESSION_ID` was byte-identical to the
   no-signal control. Automatic fork mode silently selected Git-only behavior
   and gave no notice that Claude context was incomplete.

The first behavior does not demonstrate a mutation-safety defect. The second
behavior violates `REQ-45`, the adaptive-agent requirement, because automatic
mode may choose Git-only only when no supported agent signal exists.

The exhaustive follow-up ran all eight supported environment shapes against
automatic and strict fork resolution, `session`, automatic and strict
`doctor`, and `session claude-parent infer --current`. Every fork invocation
used `--dry-run`, an explicit destination under `/private/tmp`, an empty
explicit configuration, isolated XDG state/data/cache roots, an isolated
`CLAUDE_CONFIG_DIR`, and an isolated `CODEX_HOME`. The probe preserved the real
`HOME` so the installed `mise` Codex shim remained executable. The fixed
Claude and Codex identifiers were syntactically valid UUIDs but had no
transcript or rollout in the isolated roots.

This table records the observed current behavior. `eN` is process exit code
`N`. A fork value after the colon is the selected path. A session value is
`agent` / `lineage.status` / `fork_command.status`. A doctor value is
`selected` / overall result.

| Shape | Fork auto | Fork strict | Session | Doctor auto | Doctor strict | Current inference |
|---|---|---|---|---|---|---|
| none | `e0:git-only` | `e3:agent_not_detected` | `e0:null/not_detected/not_detected` | `e0:git-only/ok` | `e1:git-only/fail` | `e3:claude_parent_unavailable` |
| Claude marker only | `e0:git-only` | `e3:agent_not_detected` | `e0:null/not_detected/not_detected` | `e0:git-only/ok` | `e1:git-only/fail` | `e3:claude_parent_unavailable` |
| Claude ID only | `e0:git-only` | `e3:agent_not_detected` | `e0:null/not_detected/not_detected` | `e0:git-only/ok` | `e1:git-only/fail` | `e3:claude_parent_unavailable` |
| complete Claude | `e0:claude` | `e0:claude` | `e0:claude/not_found/available` | `e0:claude/ok` | `e0:claude/ok` | `e3:claude_parent_unavailable` after attempting the empty isolated corpus |
| Codex only | `e3:session_not_found` | `e3:session_not_found` | `e0:codex/unavailable/available` | `e1:codex/fail` | `e1:codex/fail` | `e3:claude_parent_unavailable` |
| Claude marker plus Codex | `e3:session_not_found` | `e3:session_not_found` | `e0:codex/unavailable/available` | `e1:codex/fail` | `e1:codex/fail` | `e3:claude_parent_unavailable` |
| Claude ID plus Codex | `e3:session_not_found` | `e3:session_not_found` | `e0:codex/unavailable/available` | `e1:codex/fail` | `e1:codex/fail` | `e3:claude_parent_unavailable` |
| complete Claude plus Codex | `e3:agent_not_detected` | `e3:agent_not_detected` | `e0:null/ambiguous/ambiguous` | `e1:ambiguous/fail` | `e1:ambiguous/fail` | `e3:claude_parent_unavailable` after incorrectly entering the Claude corpus path |

The two Codex-bearing partial-Claude rows prove a second consistency defect:
the current predicates discard the partial Claude observation and select
Codex. The complete-dual inference row proves a third: current inference
ignores the simultaneous Codex signal and enters the Claude analysis path.
The Codex-only fork rows reached the existing strict rollout preflight and
refused because the isolated `CODEX_HOME` had no matching rollout. The doctor
Codex rows failed because the installed Codex help probe was unreadable; their
environment-signal checks still selected Codex, which is the A9 fact under
test.

Four compatibility controls also ran: explicit Git-only succeeded for partial
and complete-dual input; a complete explicit Claude identity overrode
complete-dual input; and explicit `--agent claude` retained its environment-ID
fallback when the Claude marker was absent. All exited 0 and selected the
intended path.

These results narrow the old `absent` / `partial` / `candidate` / `validated`
proposal to the four-state assessment in this document. They do not support a
new liveness or validation lifecycle.

Five production sites currently interpret the environment independently:

| Consumer | Current site | Current defect |
|---|---|---|
| Strict detector | `detect_agent()` in `src/agent_fork/agents.py` | Collapses partial Claude context to absence. |
| Adaptive selector | `resolve_agent_mode()` in `src/agent_fork/agents.py` | Repeats the predicate before calling the detector. |
| Session inspection | `inspect_session()` in `src/agent_fork/session.py` | Reports partial Claude context as `not_detected`. |
| Diagnostics | `run_doctor()` in `src/agent_fork/doctor.py` | Treats partial Claude context as automatic Git-only. |
| Current Claude inference | `session claude-parent infer --current` in `src/agent_fork/cli.py` | Reimplements the Claude conjunction and reports only that no current session was detected. |

## Approved owner decisions

1. Partial Claude context must not silently select Git-only behavior in
   automatic fork mode.
2. A9 must not add public Codex `candidate` or `validated` states.
3. A9 must preserve the existing strict session preflight.
4. `session`, `fork`, `doctor`, and current-session Claude inference must use
   the same environment assessment.

The owner also rejected process-tree, parent-process, terminal, `tmux`,
`launchd`, and other liveness corroboration. A9 preserves the existing meaning
of `CODEX_THREAD_ID`.

## Scope boundary

In scope:

- one immutable assessment object and one pure assessment function;
- one typed exit-code-3 refusal for incomplete signals;
- migration of the five current consumers to the shared assessment;
- additive session output that exposes the shared state;
- diagnostic output that names missing supported values;
- focused tests, the public error catalog, requirements, README, and test
  matrix updates required by the new contract.

Out of scope:

- process or session liveness heuristics;
- changes to Codex environment semantics;
- changes to `preflight_agent()` or the repository mutation pipeline;
- a public candidate or validation lifecycle;
- fixes for P02 faults A7, A8, or A10 through A13;
- release, commit, push, pull-request, merge, or unrelated cleanup work.

## Shared assessment design

Place the model with agent identity resolution in
`src/agent_fork/agents.py`. This keeps dependency direction one-way: command
services import the assessment, while the assessment imports no command
service and performs no I/O.

The implementation uses these exact concepts:

```python
AgentSignalStatus = Literal["absent", "incomplete", "detected", "ambiguous"]
AgentSignalName = Literal[
    "CLAUDECODE=1",
    "CLAUDE_CODE_SESSION_ID",
    "CODEX_THREAD_ID",
]

@dataclass(frozen=True)
class AgentSignalAssessment:
    status: AgentSignalStatus
    context: AgentContext | None
    present: tuple[AgentSignalName, ...]
    missing: tuple[AgentSignalName, ...]

def assess_agent_signals(env: Mapping[str, str]) -> AgentSignalAssessment: ...
```

`present` records supported values that are present, in the fixed order shown
above. `missing` records the one absent Claude value when a partial Claude
shape exists. Neither field records an environment value, so diagnostics and
machine output do not disclose session IDs. `context` is non-null only when
`status == "detected"`.

`AgentSignalAssessment` also provides one shared, terminal-safe textual
diagnosis. Consumers may add command-specific guidance, but they must not
recompute which values are present or missing.

Each public operation assesses its ambient environment once:

- `detect_agent()` assesses once when no explicit identity was supplied;
- `resolve_agent_mode()` assesses once and does not call the ambient path in
  `detect_agent()`;
- `inspect_session()`, `run_doctor()`, and current Claude inference each call
  `assess_agent_signals()` once;
- explicit Git-only mode and a complete explicit identity bypass ambient
  assessment because the user supplied the authoritative choice.

Preserve the existing explicit-agent fallback as well: `--agent claude`
without `--parent-session` may still obtain its ID from
`CLAUDE_CODE_SESSION_ID`, and `--agent codex` may still obtain its ID from
`CODEX_THREAD_ID`. The explicit agent supplies the identity choice, so this
path does not require the ambient Claude marker conjunction.

## Truth table

In this table, `present` means a non-empty value. The Claude marker is present
only when `CLAUDECODE` equals the supported value `1` exactly.

| `CLAUDECODE=1` | `CLAUDE_CODE_SESSION_ID` | `CODEX_THREAD_ID` | State | Context | Missing detail |
|---|---|---|---|---|---|
| absent | absent | absent | `absent` | none | none |
| present | absent | absent | `incomplete` | none | `CLAUDE_CODE_SESSION_ID` |
| absent | present | absent | `incomplete` | none | `CLAUDECODE=1` |
| present | present | absent | `detected` | Claude and its session ID | none |
| absent | absent | present | `detected` | Codex and its thread ID | none |
| present | absent | present | `ambiguous` | none | `CLAUDE_CODE_SESSION_ID` |
| absent | present | present | `ambiguous` | none | `CLAUDECODE=1` |
| present | present | present | `ambiguous` | none | none |

The assessment order is deliberate. Any observed Claude value conflicts with
a simultaneous Codex signal, even when the Claude tuple is incomplete.

## Consumer contracts

The following table defines how each command interprets the same assessment.
Only fork resolution continues from `detected` into strict session preflight.

| Consumer | `absent` | `incomplete` | `detected` | `ambiguous` |
|---|---|---|---|---|
| `fork`, automatic mode | Git-only | raise `agent_signal_incomplete` | use detected context | retain `agent_not_detected` refusal |
| `fork`, strict mode | retain `agent_not_detected` refusal | raise `agent_signal_incomplete` | use detected context | retain `agent_not_detected` refusal |
| `fork`, explicit Git-only | Git-only | Git-only | Git-only | Git-only |
| `fork`, complete explicit identity | explicit context | explicit context | explicit context | explicit context |
| `session` | observational success | observational success with explicit incomplete state and notice | current behavior | observational ambiguous result with shared diagnosis |
| `doctor`, automatic mode | pass signal check; agent CLIs optional | fail signal check and diagnose missing Claude value | pass signal check | fail signal check |
| `doctor`, strict mode | fail signal check | fail signal check | pass signal check | fail signal check |
| `doctor`, explicit Git-only | pass signal check while reporting observations | same | same | same |
| `session claude-parent infer --current` | retain `claude_parent_unavailable` | raise `agent_signal_incomplete` | continue only for Claude | reject the conflicting context as `claude_parent_unavailable` |

For `doctor` in automatic or strict mode, an incomplete state selects the
Claude CLI only for diagnostic version and recipe checks. It does not select
Claude fork mode. Explicit Git-only mode keeps both agent CLIs optional and
all recipe drift informational, regardless of the observed assessment.
Ambiguous input outside Git-only mode selects no agent: both version checks
remain non-optional, while recipe drift remains informational because no agent
was selected. These rules preserve the current Git-only and complete-dual
diagnostic behavior.

## Session output compatibility

The handoff proposed adding `incomplete` to both `lineage.status` and
`fork_command.status`. The implementation must not do that because those fields
already describe different dimensions:

- `lineage.status` describes evidence about a parent session and may be
  `claimed`, `resolved`, `not_found`, or another lineage result after an agent
  has been detected.
- `fork_command.status` describes whether a safe native command can be
  constructed and currently has a documented finite value set.

Changing either field's meaning or expanding a documented value set in v1
would violate CLI Design Standard 1.4.14 rules R7.2 and R9.3. The README also
defines v1 machine schemas as open only for compatible additions.

`session` therefore adds this optional top-level object to human-independent
machine output:

```json
{
  "agent_signal": {
    "status": "incomplete",
    "present": ["CLAUDECODE=1"],
    "missing": ["CLAUDE_CODE_SESSION_ID"]
  }
}
```

The object is present for all four states and never includes environment
values. `session validate --json` embeds the complete session document, so the
same additive object also appears inside its successful `session` value. For
incomplete context, existing fields remain compatible:

- `agent` is null;
- `current_session` and `parent_session` are null;
- `lineage.status` remains `not_detected` because no lineage lookup ran;
- `fork_command.status` remains `not_detected` and `command` remains null;
- `notices` gains the shared diagnosis naming the missing value.

Human output adds `agent signal: incomplete`, retains
`session: not_detected`, and prints the shared notice. This keeps `session:` a
direct rendering of `lineage.status` while exposing the new dimension
explicitly. The result is not byte-equivalent to absent context and never
advertises an available fork command, while existing v1 field semantics remain
unchanged.

## Typed refusal and stable error contract

Add `AgentSignalIncompleteError`, a typed `AgentForkError` subclass, with:

- stable code `agent_signal_incomplete`;
- process exit code 3, the existing agent and session precondition family;
- a message that names every missing supported value; fork resolution also
  offers `--no-agent` as an intentional Git-only recovery, while consumers
  without that flag use neutral restore-and-retry guidance;
- additive machine `details` containing `status`, `present`, and `missing`
  without environment values.

Under `--json`, the CLI continues to emit one JSON error object on stderr and
nothing on stdout. This satisfies CLI Standard rules R7.6, R7.8, and R7.12.
Add the code to `ERROR_CATALOG`, the README exit-code-3 row, and the
authoritative-catalog wording in `REQUIREMENTS.md`.

## Pre-mutation invariant

The fork CLI resolves agent mode before repository inspection, naming,
destination planning, dry-run rendering, or `pipeline.fork()`. The incomplete
refusal therefore occurs before every repository or Agent Fork write.

The existing detected path remains:

```text
supported environment values
            |
            v
  assess_agent_signals()
            |
            v
   resolve_agent_mode()
            |
            v
  existing preflight_agent()
            |
            v
 branch/worktree/registry/lineage mutation
```

The diagram answers where A9 stops. A9 changes only the first two stages; the
strict preflight and mutation pipeline remain intact.

## Test-driven implementation plan

Every production change follows a demonstrated failing test. Test IDs are
added to `docs/testing/TEST-MATRIX.md` with their tier and requirement source.

### Step 1 — RED: pure truth table and resolution

Add these unit rows to `tests/unit/test_det.py`:

| Test ID | Required proof |
|---|---|
| `T-DET-13` through `T-DET-20` | One row for each of the eight truth-table inputs, including fixed `present` and `missing` detail. |
| `T-DET-21` | Automatic and strict modes raise typed `agent_signal_incomplete` for both partial Claude shapes. |
| `T-DET-22` | A complete explicit identity overrides incomplete or ambiguous ambient values. |
| `T-DET-23` | Explicit Git-only mode ignores incomplete or ambiguous ambient values. |
| `T-DET-24` | Complete Claude and Codex shapes retain automatic and strict resolution behavior. |
| `T-DET-25` | An explicit agent without `--parent-session` retains the existing matching environment-ID fallback and does not require the ambient Claude marker. |
| `T-DET-26` | Automatic and strict modes classify both partial-Claude-plus-Codex shapes as ambiguous rather than incomplete or detected. |

Run the focused file and capture the RED failures before changing production
code. Existing `T-DET-01` through `T-DET-12` remain regression guards.

### Step 2 — GREEN: shared assessment and resolver

In `src/agent_fork/agents.py`:

1. add the immutable types and `assess_agent_signals()`;
2. centralize assessment diagnosis;
3. make the ambient path in `detect_agent()` consume one assessment;
4. make `resolve_agent_mode()` consume one assessment directly;
5. keep explicit identity and Git-only handling ahead of assessment.

In `src/agent_fork/errors.py`, add the typed error and catalog entry. Run
`tests/unit/test_det.py` and `tests/cli/test_out.py` until GREEN. The existing
catalog exactness and JSON round-trip rows must remain green.

### Step 3 — RED and GREEN: session inspection

Add:

| Test ID | File | Required proof |
|---|---|---|
| `T-SES-33` | `tests/unit/test_session.py` | Both partial Claude shapes use the shared incomplete assessment; both partial-Claude-plus-Codex shapes use the shared ambiguous assessment; none creates a current session or exposes a fork command. |
| `T-SES-34` | `tests/cli/test_session.py` | A parameterized machine-output row asserts the exact additive `agent_signal` object for `absent`, `incomplete`, `detected`, and `ambiguous`. The incomplete human and JSON cases retain unchanged `lineage.status` and `fork_command.status`, add a missing-value notice and null command, and perform no agent, clipboard, Git, lineage, inference, freshness, or cache write. |
| `T-SES-35` | `tests/unit/test_session.py` | Successful validation embeds the same additive detected `agent_signal` document without changing existing assertion results. |

Then update `SessionInspection` to carry the shared assessment, add the
top-level `agent_signal` document, and replace the local environment predicate
in `inspect_session()`. Do not call agent preflight or write state.

### Step 4 — RED and GREEN: doctor and current Claude inference

Add:

| Test ID | File | Required proof |
|---|---|---|
| `T-CLI-27` | `tests/cli/test_cli.py` | In automatic and strict modes, `doctor` fails its environment-signal check for both incomplete Claude shapes and classifies both partial-Claude-plus-Codex shapes as ambiguous. Human and JSON output assert exact signal detail, both native CLI checks are nonoptional for ambiguity, and recipe drift remains informational because no agent is selected. |
| `T-CLI-28` | `tests/cli/test_cli.py` | Explicit Git-only doctor mode remains successful while reporting incomplete or ambiguous observations. |
| `T-CPI-36` | `tests/cli/test_claude_parent.py` | `session claude-parent infer --current` raises `agent_signal_incomplete` for partial Claude context, rejects partial or complete Claude plus Codex as ambiguous, still uses the detected Claude ID for complete Claude-only context, and preserves the existing unavailable result for absent and Codex-only context. |

Replace both remaining predicates with `assess_agent_signals()`. No lineage
inference algorithm or cache behavior changes. For `--current`, assess before
constructing `ClaudeLineageCorpus`, the bounded transcript corpus, so an
incomplete signal refuses without an unnecessary transcript discovery pass.

### Step 5 — RED and GREEN: public fork refusal and no-mutation proof

Add CLI rows covering automatic, strict, and automatic dry-run invocations:

| Test ID | File | Required proof |
|---|---|---|
| `T-CLI-29` | `tests/cli/test_cli.py` | Automatic real fork with incomplete Claude context exits 3 as `agent_signal_incomplete` and returns exact `status`, `present`, and `missing` machine details. |
| `T-CLI-30` | `tests/cli/test_cli.py` | Strict real fork has the same typed refusal and exact machine details. |
| `T-CLI-31` | `tests/cli/test_cli.py` | Automatic `fork --dry-run --json` emits one JSON error on stderr, emits nothing on stdout, and does not create a branch, worktree, registry, lineage, inference, freshness, or cache artifact. |

The no-mutation row snapshots Git branches and worktrees and checks the
fixture's XDG state and cache roots. It uses an explicit destination so absence
is unambiguous. No production mutation code should change to make this pass;
the shared resolver must refuse before that code is reached.

### Step 6 — Compatibility documentation and conformance

Update:

- `README.md`, adding `agent_signal_incomplete` to exit code 3 and explaining
  `agent_signal` in the session-inspection output section;
- `docs/session-inspection.md`, documenting the additive object and all four
  values without redefining `lineage.status` or `fork_command.status`;
- `REQUIREMENTS.md`, amending `REQ-17`, `REQ-26`, `REQ-38`, `REQ-45`,
  `REQ-47`, `REQ-48`, and `REQ-50` only as needed to describe the shared
  assessment, final doctor rules, and additive session object;
- `CONFORMANCE.md`, adding one CLI Standard 1.4.14 review-history row and
  refreshing the affected requirement evidence; no new waiver is expected;
- `docs/testing/TEST-MATRIX.md`, adding every new test ID, adding the new
  signal-state and consumer-mode axes, preserving one implementation per live
  row, and updating the matrix's asserted total row count after the rows exist.

CLI Standard 1.4.14 review scope:

| Rule | A9 requirement |
|---|---|
| R6.1 | Keep the new agent/session precondition in exit code 3. |
| R7.1 and R7.6 | Keep failures on stderr and observational session results on stdout. |
| R7.2 and R9.3 | Add `agent_signal`; do not change existing field semantics. |
| R7.8 | Preserve one JSON error object for machine failures. |
| R7.12 | Publish the stable new error code. |
| R8.6 | Prove incomplete dry-run refusal has no mutation. |
| R9.10 | Make `doctor` diagnose the exact missing supported value. |
| R9.14 | Add permanent conformance rows to the existing matrix. |

Groups not affected by the A9 interface delta are N/A for this scoped review:
command structure and vocabulary, flags, configuration precedence,
destructive confirmation, networked behavior, streaming, plugins, and
interactive setup.

### Step 7 — Repository gates and review

Run focused tests after each GREEN step. Then run:

```bash
just all
just check-matrix
just strict-collect
just clean-install
```

Obtain an adversarial implementation review and an independent Codex second
lens against the complete A9 diff. Absorb only findings promised by this
design or introduced by A9. Route unrelated findings under P02 Gate 6.

## Implementation evidence

Six test files were changed before production code. The combined RED run
produced 20 failures, all in new A9 assertions: the missing assessment and
typed error, absent session object, old doctor interpretation, silent
automatic Git-only fallback, and duplicated current-inference predicate.
Existing selected rows remained green.

The smallest GREEN change added the shared assessment and typed error, migrated
the five consumers, and updated compatible output and documentation. Focused
runs then passed all 115 selected detection, output, session, CLI, doctor, and
Claude-parent items.

Repository gates after documentation and matrix updates:

| Gate | Result |
|---|---|
| `just all` | **pass** — Ruff format, Ruff lint, ty, 454 tests passed, 1 skipped, 9 deselected |
| `just check-matrix` | **pass** — 398 rows across 20 groups, with one collected item per live row |
| `just strict-collect` | **pass** |
| `just clean-install` | **pass** — sdist and wheel built; disposable wheel install and smoke checks completed |

The first clean-install attempt built both artifacts but could not resolve
PyPI under the default network-restricted sandbox. The authorized network
rerun passed. This was an environment block, not a product or packaging
failure.

## Plan-review outcome

Three read-only lenses reviewed the complete plan before implementation:

1. The source-precedent review approved the shared dependency direction and
   corrected one claim: the current Claude preflight checks native CLI
   capability, not session readability. This document now states that exact
   boundary.
2. The consumer-contract review approved the additive top-level
   `agent_signal` object and required exact behavior for human session output,
   explicit Git-only doctor mode, complete-dual inference, machine error
   details, and `session validate`. Those requirements now appear above.
3. The independent Codex second lens returned **APPROVE-WITH-CHANGES**. It
   required the executed eight-shape Gate-1 matrix; partial-Claude-plus-Codex
   rows for resolution, session, and doctor; exact session schema assertions
   for all four states; absent and Codex-only current-inference regressions;
   complete documentation coverage including `docs/session-inspection.md`,
   `REQ-38`, and `REQ-48`; explicit test file ownership; and a refreshed
   matrix row-count assertion. Every required change is incorporated in this
   plan and the Gate-1 register entry was rewritten before RED tests.

No review requested a scope expansion, a new user decision, or a change to the
existing preflight and mutation pipeline. Gate 4 is therefore complete and
implementation may proceed test-first.

## Rejected alternatives

- **Process ancestry or liveness checks:** rejected by the owner and
  outside A9. Existing strict preflight verifies the selected CLI's native-fork
  capability and verifies Codex rollout availability; it does not prove that a
  detected Claude session is live.
- **Public Codex candidate and validated states:** rejected by the owner; no
  A9 user flow requires them.
- **Command-specific partial-signal fixes:** rejected because they preserve the
  semantic drift A9 must remove.
- **A notice while still selecting Git-only automatically:** rejected because
  scripts could still execute a different mode than intended.
- **Adding `incomplete` to lineage or fork-command status:** rejected because
  it mixes state dimensions and changes existing v1 machine-field semantics;
  the additive `agent_signal` object supplies the new dimension directly.
- **Changing strict preflight:** rejected because A9 concerns environment-shape
  assessment. The existing preflight already checks native-fork capability and
  Codex rollout availability before mutation; adding Claude liveness proof is
  a separate design.

## Implementation outcome

**Complete.** Twenty new assertions failed in the combined RED run, all for
the missing A9 behavior. The GREEN implementation added one pure four-state
assessment, one typed incomplete-signal error, and one additive session object;
it migrated all five consumers without changing strict preflight or the
mutation pipeline. All 115 focused items then passed. The final reviewed tree
passed Ruff, ty, `454` repository tests with `1` expected skip and `9`
deselections, the `398`-row matrix check, strict collection, diff validation,
and a disposable wheel install. There was no scope deviation. The initial
network-restricted clean-install attempt and its authorized successful rerun
are recorded in the implementation evidence above.

## Adversarial implementation review outcome

**APPROVE — no remaining in-scope findings.** The source review found no code
defect and prompted two accuracy cleanups in this design record. The contract
review found four defects: a false matrix declaration, invalid universal
`--no-agent` guidance, incomplete real-fork mutation proofs, and a
current-inference test that did not prove assessment preceded discovery. All
four were corrected and re-reviewed. The independent Codex review found one
remaining consumer inconsistency: ambiguous current inference discarded the
shared diagnosis. The implementation now emits the exact diagnosis in both
human and JSON output, with both partial-plus-Codex shapes protected by
T-CPI-36. All three lenses approved the final diff. No unrelated finding was
routed through P02 Gate 6.
