# Codex renamed-session resolution plan

**Status:** Proposed for owner review; design and test plan only. No production
implementation or matrix mutation has started.

## Problem and evidence

Codex CLI 0.147.0 exposes two different contracts:

- `codex resume [SESSION_ID]` accepts a UUID or session name.
- `codex fork [SESSION_ID]` documents and accepts a UUID.

Codex `/rename hello-codex` stores `hello-codex` separately from the canonical
thread UUID in `$CODEX_HOME/state_5.sqlite`, table `threads`, columns `name`,
`id`, and `rollout_path`. The rollout filename remains UUID-addressed.

Agent Fork currently treats every explicit Codex `--parent-session` value as a
canonical ID and checks `sessions/*/*/*/rollout-*-<value>.jsonl`. A valid renamed
session therefore produces the false diagnosis “rollout <name> is not flushed.”
Passing the UUID works.

## Proposed contract

1. Rename the user-facing concept from “session ID” to “session reference” in
   help and diagnostics without renaming the compatible `--parent-session`
   option.
2. Claude behavior remains unchanged.
3. Codex UUID input remains the fast path and preserves byte-for-byte command
   output.
4. A non-UUID explicit Codex reference is treated as an exact, case-sensitive
   renamed-session lookup.
5. Exactly one compatible record resolves to its canonical UUID and rollout
   path. All preflight and emitted `codex fork` commands use that UUID.
6. Zero matches refuse before mutation as `session_not_found`; the message says
   the name was not found rather than claiming its rollout is unflushed.
7. Multiple matches refuse before mutation with a new stable
   `session_name_ambiguous` error and list the candidate UUIDs deterministically.
8. An unreadable or incompatible Codex state index refuses before mutation with
   a new stable `session_state_unsupported` error and recommends using the UUID.
9. A resolved record whose rollout path is absent refuses as the existing
   `session_not_found`, accurately describing a stale/unflushed canonical UUID.
10. JSON keeps `parent_session_id` canonical. When name resolution occurred, it
    adds the compatible optional field `parent_session_name`; human and dry-run
    output include a short resolution notice.
11. Environment-derived `CODEX_THREAD_ID` and companion-skill inputs remain UUID
    paths. Name lookup is used only when the supplied value is not a UUID.
12. No database is modified, no Codex process is launched for discovery, and no
    network call is introduced.

## Backend decision

### Recommended: guarded read-only Codex state-index lookup

Discover compatible `$CODEX_HOME/state_*.sqlite` files, newest schema generation
first. Open with Python `sqlite3` in read-only URI mode so the active WAL remains
visible. Inspect `sqlite_master`/`PRAGMA table_info(threads)` before querying and
require `id`, `name`, and `rollout_path`; never hard-code only `state_5.sqlite`.
Query with `WHERE name = ?` and parameter binding. Close promptly and set a
small bounded busy timeout.

This is internal integration, but Agent Fork already depends on Codex rollout
layout. Schema detection, refusal, and a real-CLI experiment keep that dependency
honest. Do not copy the database, bypass SQLite locking, search JSONL contents,
or select “most recent” silently.

### Rejected for this version

- `codex resume <name>` launches the TUI and cannot serve as a non-mutating,
  machine-readable resolver.
- `codex fork <name>` does not accept names in 0.147.0.
- The experimental app-server protocol is a larger and less stable runtime
  dependency for one local lookup. Reconsider it if OpenAI publishes a supported
  thread-resolution API.
- Scanning rollout text cannot reliably discover renamed aliases because the
  name is index metadata, not the rollout filename identity.

## Component design

Add a small Codex-specific boundary, preferably `src/agent_fork/codex_state.py`:

- `CodexSession(reference, canonical_id, name, rollout_path)` immutable result.
- `is_canonical_uuid(reference)` accepts canonical UUID text only.
- `discover_state_indexes(codex_home)` returns deterministic candidate paths.
- `inspect_compatible_index(path)` validates required tables/columns.
- `resolve_codex_session(reference, env)` implements UUID fast path and exact
  name lookup.

Refactor `preflight_agent` so resolution occurs after Codex version validation
but before Git mutation. Return the resolved session with preflight notices;
the pipeline and `build_launch_command` receive canonical identity. Avoid
mutating `AgentContext` implicitly: introduce a resolved context/value so tests
can distinguish requested reference from canonical session ID.

## TDD matrix proposal

Reserve these rows only after owner approval:

| ID | Test-first behavior | Tier |
|---|---|---|
| T-PRE-11 | canonical Codex UUID uses fast path without opening state DB | U |
| T-PRE-12 | exact renamed session resolves to canonical UUID and rollout | U |
| T-PRE-13 | unknown name returns accurate `session_not_found` before mutation | F |
| T-PRE-14 | duplicate exact names return deterministic `session_name_ambiguous` | F |
| T-PRE-15 | missing DB, unreadable DB, busy DB, corrupt DB, missing table, and missing columns each refuse safely | F |
| T-PRE-16 | stale resolved rollout returns accurate canonical-ID diagnosis | F |
| T-PRE-17 | active WAL rename is visible through the read-only lookup | F |
| T-EMT-07 | name input emits `codex fork <canonical-uuid> -C <worktree>` | U |
| T-OUT-19 | JSON reports canonical `parent_session_id` plus optional `parent_session_name` | C |
| T-OUT-20 | human/dry-run output reports name-to-UUID resolution without changing final-command position | C |
| T-CLI-24 | help calls `--parent-session` a session reference and documents Codex names | C |
| T-EXP-07 | real 0.147+ `/rename` name resolves, forks, recalls context, and leaves parent untouched | R |

Adversarial parameter cells must include quotes, SQL metacharacters, glob
characters, Unicode, leading/trailing whitespace, UUID-shaped unknown values,
case differences, symlinked `CODEX_HOME`, duplicate names, archived rows, stale
rows, and a rollout path outside `CODEX_HOME`. Queries must remain parameterized;
candidate lists and errors must be locale-independent and bounded.

## SDD/TDD execution gates

### CRS-G0 — Owner contract gate

Approve the exact-match semantics, duplicate refusal, read-only SQLite backend,
new error codes, and optional JSON field. Then add D17/REQ-46, P01 task IDs, and
the proposed matrix rows with pending lifecycle.

### CRS-G1 — RED resolver gate

Build disposable SQLite/WAL fixtures and land failing T-PRE-11..17 tests.
Gate: each row fails for the intended absent resolver; the existing UUID tests
remain green.

### CRS-G2 — Pure resolution gate

Implement discovery, schema inspection, parameterized lookup, uniqueness, path
validation, bounded errors, and canonical UUID results. Gate: resolver unit and
functional tests pass with zero writes verified by database hashes/query-only
mode.

### CRS-G3 — Preflight and command gate

Thread resolved identity through Codex preflight and command construction before
any repository mutation. Gate: T-EMT-07 and all D14 no-mutation assertions pass;
Claude and canonical Codex output remain byte-compatible.

### CRS-G4 — CLI/output/error gate

Add accurate diagnostics, catalog entries, help, optional JSON name, and notices.
Gate: T-OUT-19..20, T-CLI-24, complete error-catalog enumeration, locale tests,
and clean-install checks pass.

### CRS-G5 — Real Codex gate

Create a disposable real Codex thread, rename it, resolve/fork by name into a
disposable worktree, prove inherited context, verify the emitted command uses
the canonical UUID, and prove the parent rollout is unchanged. Record the exact
CLI version and results in `EXPERIMENTS.md`.

### CRS-G6 — Adversarial and release gate

Run a second-pass review of schema drift, WAL concurrency, path trust, duplicate
names, injection, error stability, and rollback boundaries. Gate: `just all`,
`just check-matrix`, `just clean-install`, T-EXP-01..03 and T-EXP-07 are green.
Update README, REQUIREMENTS, DESIGN-DECISIONS, CONFORMANCE, and P01 evidence.

Stop at CRS-G6 for owner review. Do not begin P01-T20/T21 release work as part
of this change.

## Risks and mitigations

- **Internal schema drift:** discover and inspect rather than assume a filename;
  fail with UUID guidance instead of guessing.
- **Concurrent Codex writes:** use SQLite read-only/WAL semantics and a bounded
  timeout; never copy or mutate the live DB.
- **Name uniqueness is not schema-enforced:** refuse duplicates deterministically.
- **Path trust:** validate resolved rollout paths are regular files within the
  resolved Codex home before use.
- **Semantic drift in future Codex:** keep T-EXP-07 gated by the real installed
  CLI and prefer a published resolver API when one appears.
- **Compatibility:** canonical UUIDs and Claude take unchanged paths; new JSON
  data is additive; error codes are cataloged before release.

## Owner decisions required

1. Approve direct, guarded read-only Codex SQLite integration (recommended), or
   defer name support until Codex exposes a supported resolver API.
2. Approve exact case-sensitive matching and refusal on duplicates
   (recommended).
3. Approve `parent_session_id` as canonical plus optional
   `parent_session_name` (recommended).
4. Approve the two new stable exit-3 codes or collapse all failures into the
   existing `session_not_found` code (new precise codes recommended).
