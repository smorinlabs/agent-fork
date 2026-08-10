# Codex renamed-session resolution plan

**Status:** Final proposed plan for owner approval. Design only: no production
implementation, requirements amendment, or matrix mutation has started.

## Evidence and decision

Codex CLI 0.147.0 exposes different positional contracts:

- `codex resume [SESSION_ID]` accepts a UUID or renamed session.
- `codex fork [SESSION_ID]` accepts a UUID.

Agent Fork currently treats every explicit Codex `--parent-session` value as a
UUID and searches for `rollout-*-<value>.jsonl`, so a valid name receives the
false “rollout not flushed” diagnosis.

The installed Codex app-server v2 protocol exposes paginated `thread/list` data
containing `id`, `sessionId`, `name`, `path`, `cwd`, and status. A real VM query
with `useStateDbOnly: true` resolved `hello-codex` to
`019fed92-fa7e-7262-b93e-6bd73a38ac72`. Codex owned all state access; Agent Fork
did not open SQLite or scan rollouts.

**Decision:** use feature-detected `codex app-server thread/list` as the only
renamed-session resolver. Its experimental status is acceptable with bounded
protocol handling, explicit capability failures, real-CLI tests, and a user
switch that forces UUID-only operation. Do not add a direct SQLite fallback.

## Proposed public contract

1. Keep the compatible option name `--parent-session`, but describe its value as
   a session reference: Claude resume reference or Codex UUID/session name.
2. Canonical Codex UUID input remains the fast path. It never starts app-server
   and preserves the existing emitted command byte-for-byte.
3. A non-UUID Codex reference is resolved by exact, case-sensitive match against
   app-server `thread/list` results.
4. Name resolution is enabled by default and can be disabled per invocation:

   ```bash
   agent-fork fork NAME --no-resolve-session-name \
     --agent codex --parent-session '<uuid>'
   ```

5. The corresponding configuration is agent-specific:

   ```toml
   [agents.codex]
   resolve_session_names = true
   ```

   CLI precedence is `--resolve-session-name` / `--no-resolve-session-name`
   over config over the default `true`. No environment variable is proposed.
6. When resolution is disabled, UUID input works normally. A non-UUID value
   refuses before mutation without starting app-server and says to pass the
   full UUID or enable name resolution.
7. Exactly one name match produces a canonical UUID. Preflight, dry-run, JSON,
   and the final `codex fork` command all use it.
8. Zero matches refuse as `session_not_found`, accurately saying the name was
   not found.
9. Multiple matches refuse deterministically as `session_name_ambiguous`; never
   select the newest match silently.
10. App-server absence, unsupported methods/schema, timeout, malformed or
    excessive output, early exit, and pagination exhaustion refuse as
    `session_resolution_unavailable`, always recommending the UUID and the
    disable option. No fallback to direct state access occurs.
11. JSON keeps `parent_session_id` canonical. Successful name resolution adds
    optional `parent_session_name`; human and dry-run output add a short
    resolution notice while preserving the paste command as the last block.
12. Claude behavior, environment-derived `CODEX_THREAD_ID`, and the companion
    skill’s UUID path remain unchanged.
13. Resolution and all refusal paths occur before branch/worktree mutation.
14. No database is opened by Agent Fork, no network call is made, and app-server
    is terminated after the bounded lookup.

## Resolution and identity architecture

The lookup backend and the command-ordering correction are separate concerns.
Introduce immutable values such as:

```text
AgentContext
  agent
  requested_reference

ResolvedAgentContext
  agent
  canonical_session_id
  resolved_session_name | null
  resolution_source = uuid | codex-app-server
```

One operation resolves and preflights identity before any launch command is
built:

```text
requested reference
    -> resolve canonical identity
    -> agent/version/rollout preflight
    -> build launch command from resolved identity
```

This operation must be shared by dry-run and real execution. Today dry-run
builds its launch command before preflight, while the normal pipeline discards
preflight identity and later rebuilds from the original request. Refactor those
paths so resolution occurs once and its immutable result flows through:

- dry-run command construction;
- `ForkRequest`/pipeline preflight;
- `ForkResult`;
- JSON and human output;
- final command construction.

No command builder may accept an unresolved Codex name. Existing UUID and
Claude callers remain compatible through explicit constructors/helpers.

## App-server adapter design

Add a narrow boundary such as `src/agent_fork/codex_app_server.py` that:

1. Uses the exact Codex executable already found and version-checked by
   preflight, avoiding a second PATH resolution.
2. Starts `codex app-server --listen stdio://` with the effective environment.
3. Sends JSON-RPC `initialize`, then `initialized`, then paginated `thread/list`.
4. Requests `useStateDbOnly: true`, which avoids JSONL scan-and-repair behavior.
5. Ignores unrelated notifications, correlates numeric request IDs, and validates
   response shapes and required `id`/`name` fields.
6. Paginates until exhaustion so duplicate exact names cannot be missed.
7. Applies explicit bounds: startup/request/overall timeouts, page and record
   caps, maximum line/response/stderr bytes, and maximum diagnostic candidates.
8. Terminates gracefully, escalates to kill after a short bound, and always
   reaps the child process.
9. Never sends `thread/read`, `thread/resume`, `thread/fork`, or any mutation
   method.
10. Treats JSON-RPC method-not-found and schema drift as feature-unavailable,
    not as a generic runtime crash.

The adapter returns only structured thread summaries. Resolution policy—UUID
classification, exact name matching, ambiguity, and error construction—remains
in Agent Fork domain code and is unit-testable without a subprocess.

## UUID and matching rules

- A canonical reference is a hyphenated UUID accepted case-insensitively and
  normalized to lowercase.
- UUID-shaped input is always treated as an ID; an unknown UUID never falls back
  to name lookup.
- Names are compared exactly and case-sensitively to the app-server `name`
  field. Agent Fork does not trim or Unicode-normalize user input.
- Empty names are not references.
- Candidate IDs must themselves be valid canonical UUIDs.
- Duplicate diagnostics sort canonical UUIDs and show a bounded number plus an
  omitted-count suffix.

## TDD matrix proposal

Reserve rows only after owner approval:

| ID | Test-first behavior | Tier |
|---|---|---|
| T-CFG-17 | Codex name resolution defaults true; config and both CLI flags obey precedence | U |
| T-PRE-11 | canonical Codex UUID bypasses app-server entirely | U |
| T-PRE-12 | exact renamed session resolves once to canonical UUID | U |
| T-PRE-13 | disabled resolution + UUID succeeds; disabled + name refuses without spawning | F |
| T-PRE-14 | zero name matches returns accurate `session_not_found` before mutation | F |
| T-PRE-15 | duplicate exact matches return bounded deterministic ambiguity | F |
| T-PRE-16 | unavailable/missing method, timeout, malformed, oversized, early-exit, and pagination-cap failures are typed and leave no mutation | F |
| T-PRE-17 | stale or missing canonical rollout after resolution is accurately diagnosed | F |
| T-PRE-18 | adapter paginates and finds names/duplicates beyond page one | F |
| T-PRE-19 | subprocess lifecycle: graceful exit, forced kill, reap, bounded stderr, notification tolerance | F |
| T-EMT-07 | name input emits canonical `codex fork <uuid> -C <worktree>` | U |
| T-OUT-19 | JSON reports canonical ID plus optional resolved name | C |
| T-OUT-20 | human/dry-run notice is accurate and final-command position is preserved | C |
| T-CLI-24 | help/config/completions document session reference and resolution controls | C |
| T-EXP-07 | real `/rename` resolves through app-server and forks with context intact | R |

Adversarial cells cover JSON-RPC notifications between responses, wrong IDs,
duplicate IDs, missing/null names, invalid returned UUIDs, cursor loops, repeated
cursors, empty pages with cursors, huge pages, huge stderr, hung initialization,
partial JSON lines, clean EOF, signals, quotes, Unicode, case differences,
leading/trailing whitespace, UUID-shaped unknown input, contradictory ambient
UUID, duplicate names, archived sessions, and names beyond the first page.

## SDD/TDD gates

### CRS-G0 — Owner contract gate

Approve flag/config naming, default-enabled posture, exact/duplicate semantics,
archived-session policy, JSON identity, and stable error codes. Then add
D17/REQ-46, atomic P01 test/implementation tasks, and pending matrix rows.

### CRS-G1 — RED adapter and identity gate

Create a deterministic fake JSON-RPC app-server plus subprocess lifecycle
fixtures. Add failing T-CFG-17 and T-PRE-11..19. Gate: each fails for the
intended missing behavior; existing UUID and Claude tests stay green.

### CRS-G2 — Bounded adapter gate

Implement initialize/list pagination, strict decoding, feature detection,
bounds, and process teardown. Gate: adapter fixtures pass with no unbounded read,
wait, output, pagination, or orphaned process.

### CRS-G2.5 — Resolved identity-flow gate

Implement immutable requested/resolved identity and resolve exactly once before
command construction. Gate: dry-run and real paths produce the same canonical
command; no unresolved Codex name reaches the builder; every resolver failure
proves no branch/worktree mutation.

### CRS-G3 — Policy and preflight gate

Implement UUID bypass, config/flag disable behavior, exact lookup, ambiguity,
and canonical rollout preflight. Gate: T-CFG-17, T-PRE-11..19, T-EMT-07, all
D14 no-mutation tests, and existing byte-exact UUID/Claude templates pass.

### CRS-G4 — CLI/output/error gate

Add help, completions, config view/set/validate, typed catalog entries, optional
JSON name, and notices. Gate: T-OUT-19..20, T-CLI-24, catalog enumeration,
locale independence, stream separation, and installed-wheel tests pass.

### CRS-G5 — Real Codex gate

Through a PTY, create a disposable interactive Codex thread, send `/rename` with
a unique name, wait for explicit confirmation, exit cleanly, and verify the
app-server returns its name/UUID. Invoke Agent Fork by name, verify the dry-run
and real emitted commands contain the UUID, enter the fork, prove inherited
context, and hash the parent rollout before/after. Repeat with resolution
disabled and the UUID to prove the escape hatch. Record CLI/protocol evidence in
`EXPERIMENTS.md`.

### CRS-G6 — Adversarial/release-readiness gate

Review protocol drift, child-process safety, bounds, duplicate names, archived
semantics, error stability, injection, signals, and rollback. Gate: `just all`,
`just check-matrix`, `just clean-install`, T-EXP-01..03 and T-EXP-07 are green;
README, REQUIREMENTS, DESIGN-DECISIONS, CONFORMANCE, and P01 evidence are current.

Stop at CRS-G6 for owner review. Do not begin P01-T20/T21 release work in this
change.

## Risks and mitigations

- **Experimental protocol drift:** feature-detect every exchange and fail with
  UUID guidance; pin fixture schemas and run a real-CLI gate.
- **Resolver blocks normal UUID use:** UUIDs bypass app-server; users can disable
  name resolution globally or per invocation.
- **Hung/noisy subprocess:** strict time, page, line, response, stderr, and
  teardown bounds with adversarial lifecycle tests.
- **Duplicate names:** scan to pagination exhaustion and refuse deterministically.
- **Unexpected Codex repair/write behavior:** always request
  `useStateDbOnly: true`; never issue read/resume/fork or mutation methods.
- **Compatibility:** new configuration and JSON data are additive; canonical
  UUID and Claude paths remain byte-compatible.

## Remaining owner questions

1. Approve `--resolve-session-name` / `--no-resolve-session-name` and
   `[agents.codex] resolve_session_names = true`? These names are recommended.
2. Confirm default enabled? Recommended: yes; UUID paths still bypass it.
3. Should explicit names search active sessions only, or active plus archived?
   Recommended: active only, matching the normal fork picker; UUID remains the
   escape hatch for an archived session.
4. Approve exact case-sensitive matching and duplicate refusal? Recommended:
   yes, matching returned metadata without guessing.
5. Approve canonical `parent_session_id` plus optional
   `parent_session_name`? Recommended: yes.
6. Approve `session_name_ambiguous` and
   `session_resolution_unavailable` as new stable exit-3 codes, while unknown
   name and stale rollout retain `session_not_found`? Recommended: yes.
7. Approve no SQLite fallback under any failure? Recommended: yes.
