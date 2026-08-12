# Session inspection and assertion plan

**Status:** implemented through SES-G5; stopped at SES-G6 owner-review gate  
**Date:** 2026-08-11  
**Scope:** add an agent-neutral `session` command for Claude Code and Codex

## Goal

Add one uniform interface that reads the host-agent environment, reports the
current session and any discoverable parent evidence, resolves display names
when a supported local source is available, and optionally asserts caller-
supplied expectations.

```text
agent-fork session [-o table|text|json]
agent-fork session validate
    [--agent {claude,codex}]
    [--session-id ID]
    [--parent-session-id ID]
    [--has-parent | --no-parent]
    [-o table|text|json]
```

`session` is observational. `session validate` is assertion-oriented. It does
not claim that a session or transcript exists merely because an ID was found.

## Locked behavior proposed by this plan

1. `session` uses the existing environment ladder:
   `CLAUDECODE=1` plus `CLAUDE_CODE_SESSION_ID`, or `CODEX_THREAD_ID`.
2. `session` succeeds even when no supported session signal is present and
   reports null identity with detection status `not_detected`. This makes it a
   safe inspection command in ordinary terminals.
3. `session validate` with no constraints asserts only that one unambiguous
   supported current-session signal exists.
4. Validation constraints compose with logical AND:
   - `--agent` requires the detected agent to match.
   - `--session-id` requires the detected current ID to match exactly.
   - `--parent-session-id` requires parent evidence and an exact match.
   - `--has-parent` requires parent evidence.
   - `--no-parent` requires no parent evidence.
5. `--has-parent` and `--no-parent` are parser-mutually-exclusive.
   `--parent-session-id` implies `--has-parent` and conflicts with
   `--no-parent` as an exit-2 usage error.
6. An assertion mismatch is `session_validation_failed`, exit 3. JSON errors
   use the existing stderr error envelope. Successful validation goes to
   stdout and exit 0.
7. `-o table|text|json` is the canonical output control. The existing `--json`
   compatibility alias remains identical to `-o json` if exposed on this
   command.
8. Name and parent fields distinguish evidence from certainty. A missing
   lookup is not an inspection failure. Resolver/protocol corruption is
   reported as lookup status and a notice during inspection; validation fails
   only when the unavailable fact is asserted.
9. No network access, agent resume, session mutation, or transcript mutation is
   allowed. All lookup subprocesses and reads remain bounded.

## Result model

The human and machine renderers consume one immutable result model. JSON is an
open, additive schema:

```json
{
  "agent": "codex",
  "current_session": {
    "id": "019f...",
    "id_source": "CODEX_THREAD_ID",
    "name": "hello-codex",
    "name_status": "resolved",
    "name_source": "codex-app-server"
  },
  "parent_session": {
    "id": "018e...",
    "id_source": "codex-app-server",
    "name": null,
    "name_status": "not_found",
    "name_source": "codex-app-server"
  },
  "lineage": {
    "has_parent_evidence": true,
    "status": "resolved"
  },
  "notices": []
}
```

When nothing is detected, `agent`, `current_session`, and `parent_session` are
null and `lineage.status` is `not_detected`. When a current session is detected
but no parent evidence exists, `parent_session` is null,
`has_parent_evidence` is false, and lineage status is `not_found` rather than a
claim that the session was never forked.

Successful validation adds a stable assertion report:

```json
{
  "valid": true,
  "assertions": [
    {"name": "session_detected", "passed": true},
    {"name": "agent", "expected": "codex", "actual": "codex", "passed": true},
    {"name": "has_parent", "expected": true, "actual": true, "passed": true}
  ],
  "session": {"...": "same inspection object"}
}
```

Do not emit a fabricated `parent_session_id`, infer lineage from timestamps, or
equate message-level `parentUuid` fields with a parent conversation.

## Evidence sources and limitations

### Codex

- Current identity: `CODEX_THREAD_ID`.
- Current name and parent: the exact preflighted Codex executable's local
  app-server `thread/read` response. Codex 0.147.0's generated protocol exposes
  `Thread.name` and `Thread.forkedFromId`.
- Parent name: a second bounded `thread/read` by `forkedFromId`, when present.
- Fallback: the rollout `session_meta` record contains `forked_from_id`, but
  direct rollout parsing is not the first path. It should be considered only
  if separately owner-approved; this plan defaults to no fallback.
- Reuse the existing bounded stdio adapter instead of starting a second
  implementation. UUID input remains exact and no database access is added.

### Claude Code

- Current identity: `CLAUDE_CODE_SESSION_ID` only when `CLAUDECODE=1`.
- Current name: bounded parsing of the current transcript's metadata records
  (`custom-title`/`agent-name`) under `CLAUDE_CONFIG_DIR`, when present. Claude
  exposes no machine-readable session-list command in the installed 2.1.220
  help surface.
- Parent identity for future Agent Fork-created sessions: a separate,
  versioned XDG lineage store records the pre-generated Claude child UUID and
  the known source UUID when `agent-fork fork` emits the Claude launch command.
  The record is a provenance claim, not proof that the child was launched or
  that either transcript still exists.
- Existing Claude forks and forks created outside Agent Fork may have no
  discoverable parent. Their output must say `not_found`, not `no_parent`.
- Claude transcript `parentUuid` is message ancestry and must never be used as
  session ancestry.

### Lineage store

Do not expand the stable worktree registry v1 schema. Add an independent,
versioned `$XDG_STATE_HOME/agent-fork/session-lineage.json` with atomic write,
locking, strict decoding, deterministic ordering, and records containing
`agent`, `child_session_id`, `parent_session_id`, `created_at`, and optional
fork/worktree identity. The inspection path is read-only. A planned-but-never-
launched Claude child record is harmless because it is consulted only when the
active environment reports that exact child UUID.

### Claude claim lifecycle

The current pipeline generates Claude's child UUID after the rollback-protected
worktree transaction. Change that ordering deliberately:

1. After agent/Git preflight and destination validation, build the immutable
   launch identity. For Claude this pre-generates the child UUID; for Codex it
   remains null.
2. Create, materialize, and verify the worktree normally.
3. Inside the rollback-protected completion step, write the ordinary worktree
   registry entry and the Claude lineage claim before reporting success.
4. Treat lineage persistence as required for a managed Claude fork. If either
   metadata write fails, compensate the other metadata write and raise so the
   existing worktree/branch rollback runs. Add fault injection at both write
   boundaries and at compensation failure.
5. Return the exact launch command whose child UUID was persisted. Never
   regenerate the child UUID during rendering.

Implement the paired metadata operation behind one pipeline-facing helper with
a documented lock order. Two files cannot be made transactionally atomic with
one rename, so the helper must use deterministic lock acquisition, atomic
per-file replacements, and explicit compensation. A residue after failed
compensation must produce precise manual-recovery diagnostics rather than be
silently ignored.

The initial record state is `planned`: Agent Fork knows the command it emitted,
but not whether the user launched it. When `session` runs under the exact child
UUID, it reports two separate facts without writing anything:

- `current_session.id` is `observed` from `CLAUDE_CODE_SESSION_ID`;
- `parent_session.id` is `claimed` by the Agent Fork lineage record.

Do not silently promote or mutate the record during inspection. Transcript
presence may be returned as additional lookup evidence, but absence can be a
flush race and does not invalidate the claim. Cleanup must retain lineage
records because Claude sessions remain resumable after their Git worktrees are
removed. Retention/pruning is deferred; records contain identifiers and fork
metadata only, never prompts or transcript content.

The lineage record may include the fork identity as a claimed child name. It
must be labeled `claimed`, not `resolved`, until Claude transcript metadata
confirms the current display name.

## TDD matrix

Create a new `G-SES` group before production code. Proposed IDs:

Implementation consolidated overlapping cases into the 22 canonical rows in
`docs/testing/TEST-MATRIX.md`; that matrix is authoritative for collected IDs.

| ID | Tier | Test-first obligation |
|---|---|---|
| T-SES-01 | U | no signals → observational null result, exit 0 |
| T-SES-02 | U | Claude conjunction and Codex signal produce current identity with exact source |
| T-SES-03 | U | simultaneous agent signals remain ambiguous and inspection reports that state |
| T-SES-04 | U | Codex `thread/read` resolves current name, `forkedFromId`, and optional parent name |
| T-SES-05 | U | Codex UUID/name/parent lookup tolerates notifications and enforces time, page/message, schema, and subprocess bounds |
| T-SES-06 | U | Claude transcript metadata resolves the current name with bounded file/record/byte handling |
| T-SES-07 | U | Claude message `parentUuid` is explicitly rejected as session lineage |
| T-SES-08 | F | lineage store atomic round-trip, lock contention, corrupt schema, and deterministic replacement |
| T-SES-09 | F | Claude fork emission records child→parent before mutation handoff without changing the worktree registry schema |
| T-SES-10 | C | `session -o text|json` stream, schema, locale, and no-session contracts |
| T-SES-11 | C | bare `session validate` passes only with an unambiguous current session |
| T-SES-12 | C | `--agent`, `--session-id`, `--parent-session-id`, and `--has-parent` compose with AND semantics |
| T-SES-13 | C | `--no-parent` passes only when parent evidence is absent |
| T-SES-14 | C | `--no-parent --parent-session-id` and `--has-parent --no-parent` are exit-2 usage errors |
| T-SES-15 | C | mismatch/unavailable asserted evidence → `session_validation_failed`, exit 3, stable JSON error |
| T-SES-16 | C | `--json` is byte-identical to `-o json`; completions and help expose every constraint |
| T-SES-17 | C | inspection performs zero network calls and no filesystem writes |
| T-SES-18 | R | Claude `-p` tool execution observes the same session ID as Claude's outer JSON result |
| T-SES-19 | R | Codex `exec --json` tool execution observes the same ID as its `thread.started` event |
| T-SES-20 | R | real Agent Fork-created Claude child reports its recorded parent evidence |
| T-SES-21 | R | real Codex fork reports app-server `forkedFromId` and resolved names when named |
| T-SES-22 | F | paired registry/lineage writes compensate each failure boundary and route unrecoverable residue to manual-recovery diagnostics |
| T-SES-23 | F | cleanup retains lineage after worktree removal and later Claude resume can still inspect the claim |

All parametrized cases must retain one exact matrix marker per collected item.
The four real rows use `requires_real_cli`, the existing identity/auth/state/
network preflight, disposable repositories, bounded timeouts, and precise
diagnostics.

## Can this be tested through `claude -p` and `codex exec`?

Yes, with an important qualification: these are model-mediated acceptance
tests, not the primary correctness tests.

### Claude acceptance

Run a fresh persisted `claude -p --output-format json` session with Bash as the
only allowed tool and a deterministic instruction to execute
`agent-fork session -o json` once and return its stdout unchanged. Parse:

1. the outer Claude result's `session_id`;
2. the Bash tool result containing Agent Fork JSON;
3. assert `current_session.id == outer.session_id` and `agent == "claude"`.

For lineage, first use Agent Fork's normal pinned-child launch template, then
make that child execute the same command and compare its parent with the known
source UUID. Because tool selection is model-mediated, failures must print the
full sanitized event/output diagnostics and may not replace hermetic coverage.

### Codex acceptance

Run a fresh persisted `codex exec --json` session with a read-only sandbox and
an instruction to execute `agent-fork session -o json` once. Parse:

1. the `thread.started` event's thread ID;
2. the command-execution output containing Agent Fork JSON;
3. assert `current_session.id == thread.started.thread_id` and
   `agent == "codex"`.

For lineage, create a disposable parent and native Codex fork using the existing
PTY helper, execute the inspection command in the child, and compare
`parent_session.id` with the known parent. Again, app-server unit/functional
tests are authoritative; the model-mediated run is an integration proof.

Neither acceptance test should use `--ephemeral` or Claude's
`--no-session-persistence`, because name and lineage lookup intentionally tests
persisted local state.

## Implementation sequence

1. **Corpus gate:** approve D18 and REQ-47; add `G-SES` rows as `tdd`; add the
   command to conformance and help contracts.
2. **Pure model/detection:** add immutable inspection/evidence/assertion models
   and reuse the existing environment detector without making Git a
   prerequisite.
3. **Codex resolver:** generalize the bounded app-server transport, add exact
   `thread/read`, and return name plus `forkedFromId` without SQLite/network.
4. **Claude resolver:** implement bounded transcript metadata lookup and tests
   that distinguish message ancestry from session ancestry.
5. **Lineage persistence:** implement the independent XDG store, then record
   the known Claude child→parent claim during fork planning/emission.
6. **Inspection service:** merge current identity, optional names, and optional
   parent evidence with explicit status/source values. Lookup degradation is
   data plus notices, not silent fabrication.
7. **CLI/output:** add `session` and nested `validate`, `-o`, `--json`, assertion
   constraints, stable exit behavior, completions, README examples, and error
   catalog entries.
8. **Hermetic gates:** make G-SES green, flip it to `done`, then run
   `just all`, `just check-matrix`, `just strict-collect`,
   `just clean-install`, `just test-git-matrix`, and `just test-signals`.
9. **Real gates:** run T-SES-18..21 via `just test-live`; record versions,
   commands, IDs, and outcomes in `EXPERIMENTS.md` without transcript content.
10. **Review gate:** correctness review, adversarial review of local-state
    parsing/protocol bounds/assertion semantics, then owner review before PR.

## Adversarial checklist

- Both/no environment signals; empty, malformed, uppercase, or non-UUID IDs.
- Conflicting assertion flags and parent-ID implication.
- Environment ID differs from looked-up record ID.
- Renamed, duplicate-named, deleted, unflushed, and planned-but-unlaunched
  sessions.
- Corrupt/truncated/huge Claude transcript and lineage files; symlink/path
  escape; excessive records; concurrent lineage writers.
- Codex notifications, unknown response IDs, cursor loops, duplicate responses,
  stderr floods, timeout, early exit, and unsupported schemas.
- Terminal control characters in names and errors; safe human rendering and
  unchanged raw JSON strings.
- Closed stdout/stderr, SIGPIPE, SIGINT/SIGTERM, locale variance, and no writes
  during inspection.
- Ensure `session` works outside a Git repository and never starts a network
  request or mutates an agent session.

## Gates

- **SES-G0 Design:** owner approves interface, evidence vocabulary, D18/REQ-47,
  and the separate lineage store.
- **SES-G1 Red:** every G-SES row exists and fails for the intended reason.
- **SES-G2 Sources:** Codex and Claude resolvers pass bounded adversarial tests.
- **SES-G3 CLI:** inspection and every validation combination pass black-box
  installed-CLI tests.
- **SES-G4 Hermetic:** all canonical non-live gates are green.
- **SES-G5 Real:** Claude and Codex current-ID comparisons pass; lineage tests
  either pass or produce an owner-reviewed, version-specific limitation record.
- **SES-G6 Review:** code/adversarial reviews have no unresolved high or medium
  findings. Stop for owner approval before PR/merge.

## Explicit non-goals

- Proving that a parent transcript still exists unless explicitly added as a
  future assertion.
- Reconstructing arbitrary historical Claude lineage.
- Traversing an entire ancestor chain in v1 of this command.
- Reading Codex SQLite directly, using network APIs, or launching/resuming an
  agent as part of ordinary inspection.
- Treating missing parent evidence as proof that no parent ever existed.
