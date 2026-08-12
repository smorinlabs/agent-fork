# Claude parent inference and lineage management plan

**Status:** Proposed for owner review; design and adversarial review complete.
No requirements, design decisions, test-matrix rows, production code, or store
schemas have been changed.

**Date:** 2026-08-11

**Scope:** Add an opt-in, Claude-specific facility that infers likely parent
relationships from local transcript structure, records clearly labeled
inferences separately from Agent Fork's planned lineage claims, and provides
safe listing, inspection, and deletion of Claude-parent metadata.

## Goal

Add a deliberately expensive, explicitly scoped command family:

```text
agent-fork session claude-parent list
agent-fork session claude-parent show --session-id ID
agent-fork session claude-parent infer
    (--current | --session-id ID | --all)
    [--record | --record-all]
agent-fork session claude-parent delete
    --session-id ID [--source SOURCE] [--yes]
```

The feature reconstructs probable Claude relationships when no stronger source
exists. It must preserve the distinction between:

1. two sessions sharing copied message ancestry;
2. the likely chronological direction of that copy; and
3. proof of an immediate parent.

The first two can often be inferred strongly. The third is sometimes
undecidable, especially when siblings fork at the same message boundary.

## Evidence from the real Claude pair

The design is grounded in a known parent/child pair created on this VM.
Transcript contents were not copied into this plan.

```text
known parent: 6e572c9b-73e2-40a9-a6e1-1cb88a57b21c
known child:  2e12da68-6e37-40dd-9ff1-d804ae23f283
```

Observed structural facts:

- The transcripts share an exact ordered chain of five message UUIDs.
- The shared chain contains a user record, not only bootstrap/system records.
- Matching `parentUuid` edges connect the shared UUIDs.
- Claude rewrote every copied record's `sessionId` to the destination session.
- Neither transcript contains `forkedFrom`, `parentSessionId`,
  `forkParentSessionId`, `sourceSessionId`, or another explicit session-parent
  field.
- `parentUuid` is message ancestry, not a parent-session identifier.
- The two bridge-session IDs are distinct and do not cross-reference each
  other. They connect each transcript to its live process, not to its parent.
- Three independent creation proxies agree on direction:

  | Evidence | Known parent | Known child | Child later by |
  |---|---:|---:|---:|
  | live registration `startedAt` | 14:07:36.087 | 14:08:16.029 | 39.942 s |
  | first history event | 14:07:39.512 | 14:08:22.805 | 43.293 s |
  | transcript filesystem birth | 14:07:41.768 | 14:08:22.851 | 41.083 s |

- The parent's transcript was born approximately 31 ms after its oldest
  embedded record. The child's transcript was born approximately 41.1 seconds
  after the same copied record, which is consistent with backfilled history.
- The child and parent can continue independently after the fork, so the first
  or latest unique-message timestamp does not necessarily identify direction.

These findings establish a useful heuristic, not a stable Anthropic API.

## Locked public contract proposed by this plan

### Command namespace

Use `claude-parent` as a namespace and `infer` as one operation beneath it:

```text
agent-fork session claude-parent <list|show|infer|delete>
```

This is preferred over `claude-parent-infer` because listing, showing, and
deleting records are now first-class operations. It is preferred over bare
`session infer` because this algorithm is Claude-specific.

### Explicit inference scope

`infer` requires exactly one target selector:

```text
--current
--session-id ID
--all
```

No selector is an exit-2 usage error. `--current` requires an unambiguous
ambient Claude session and resolves exactly `CLAUDE_CODE_SESSION_ID`.
`--session-id` accepts one canonical Claude session UUID. `--all` analyzes every
discoverable Claude transcript missing stronger parent evidence.

The command never defaults to `--all` and never performs an expensive scan as
a side effect of plain `agent-fork session`.

### Observation and recording

Inference is read-only unless a recording option is present:

| Target | Preview | Recording |
|---|---|---|
| `--current` | allowed | `--record` |
| `--session-id ID` | allowed | `--record` |
| `--all` | allowed | `--record-all` |

`--all --record`, `--current --record-all`, `--session-id ID --record-all`, and
`--record --record-all` are exit-2 usage errors. The stronger `--record-all`
spelling makes bulk persistence deliberate.

Recording succeeds only for a unique candidate meeting the accepted evidence
threshold. Ambiguous and conflicting results remain report-only. No force flag
for recording ambiguous results is proposed.

### Output

All subcommands follow existing `-o table|text|json`; `--json` remains the
byte-identical alias for `-o json`.

One-session inference JSON is additive and structurally explicit:

```json
{
  "agent": "claude",
  "session_id": "2e12da68-...",
  "relationship": {
    "kind": "shared-lineage",
    "likely_parent_session_id": "6e572c9b-...",
    "status": "strongly_inferred",
    "immediate_parent_proven": false,
    "fork_boundary_message_id": "902366e5-...",
    "shared_message_count": 5,
    "shared_substantive_message_count": 1
  },
  "direction_evidence": {
    "process_started_at_delta_ms": 39942,
    "first_history_event_delta_ms": 43293,
    "transcript_birth_delta_ms": 41083,
    "clocks_available": 3,
    "clocks_agree": true
  },
  "candidates": [],
  "algorithm": {
    "name": "claude-transcript-lineage",
    "version": 1
  },
  "recorded": false,
  "notices": []
}
```

Do not make a floating-point confidence score the acceptance contract. Stable
statuses drive policy:

```text
strongly_inferred
inferred
ambiguous
conflicting_evidence
insufficient_evidence
unavailable
```

If a score is added for diagnostics, it is additive and must not replace the
documented rule set.

### List and show

```text
agent-fork session claude-parent list [--source planned|inferred|all]
agent-fork session claude-parent show --session-id ID [--source SOURCE]
```

`list` defaults to all Agent Fork-owned Claude-parent records and performs no
transcript scan. It reports child, parent, source, status, record time, and
staleness. `show` reports one full record and its evidence metadata. Multiple
records for one child require `--source` rather than silently choosing for
record-management operations.

### Delete

```text
agent-fork session claude-parent delete \
  --session-id CHILD [--source planned|inferred] [--yes]
```

Deletion targets the child key and removes only Agent Fork metadata. It never
removes Claude transcripts, Claude history, live registration files, branches,
or worktrees. Interactive confirmation is required unless `--yes` is supplied.
If more than one source exists, `--source` is required. Deleting a planned
claim emits a stronger warning because it removes the strongest local evidence
for that child.

A generic `update` command is not proposed. Refresh an inference by rerunning
`infer ... --record`; delete it with `delete`. A future manual `set` operation
must be separately designed and label its source `user-asserted`.

## Evidence precedence and fallback

Normal inspection remains bounded and cheap:

```text
explicit Claude evidence, if a future supported source exists
    > Agent Fork planned claim
    > recorded heuristic inference
    > not_found
```

Codex app-server evidence remains independent and resolved. Claude inference
does not run for Codex.

When `agent-fork session` finds a recorded inference, it may report:

```json
{
  "parent_session": {
    "id": "6e572c9b-...",
    "id_source": "agent-fork-lineage-inference",
    "id_status": "inferred"
  },
  "lineage": {
    "has_parent_evidence": true,
    "status": "strongly_inferred"
  }
}
```

It does not refresh the inference. Missing recorded evidence remains
`not_found`, not proof of no parent.

`session validate --has-parent` needs an owner decision at the first gate:
whether inferred evidence satisfies the existing broad assertion. The
recommendation is **yes**, because the assertion is deliberately phrased as
parent evidence, while `--parent-session-id` remains an exact comparison and
the JSON exposes the evidence status. A future strict assertion can require
`claimed|resolved` if needed; do not silently change current semantics without
tests and documentation.

## Storage architecture

Keep three data classes physically and semantically separate.

### Planned claims

Existing store:

```text
$XDG_STATE_HOME/agent-fork/session-lineage.json
```

Meaning: Agent Fork generated a child UUID and emitted a Claude command naming
that child and parent. It is a planned provenance claim, not proof of launch.
Do not change its v1 semantics as part of inference.

### Recorded inferences

New store:

```text
$XDG_STATE_HOME/agent-fork/session-lineage-inferences.json
```

Proposed record:

```json
{
  "version": 1,
  "inferences": [
    {
      "agent": "claude",
      "child_session_id": "2e12da68-...",
      "likely_parent_session_id": "6e572c9b-...",
      "relationship": "shared-lineage",
      "status": "strongly_inferred",
      "immediate_parent_proven": false,
      "fork_boundary_message_id": "902366e5-...",
      "shared_message_count": 5,
      "shared_substantive_message_count": 1,
      "direction_evidence": {
        "transcript_birth": "agrees",
        "history_first_event": "agrees",
        "live_process_start": "agrees"
      },
      "algorithm_version": 1,
      "analyzed_at": "2026-08-11T...Z",
      "source_fingerprints": []
    }
  ]
}
```

Use the repository's established locked, bounded, atomic-write pattern.
Replacement is keyed by `(agent, child_session_id)` and may replace only an
existing inferred record. It cannot mutate or remove a planned claim.

Store identifiers and structural evidence only—never prompts, responses, tool
content, account UUIDs, organization UUIDs, bridge IDs, or credentials.

### Disposable index

New cache namespace:

```text
$XDG_CACHE_HOME/agent-fork/claude-lineage-index-v2/
```

The index accelerates analysis but is never evidence. It can be deleted and
rebuilt. Store only transcript identity, safe file fingerprints, ordered
structural UUID/edge information or compact equivalents, type classifications,
and creation proxies. Do not store message content.

Index records must be versioned and keyed by canonical path plus file identity
such as size, `mtime_ns`, and platform-available birth time. Reparse changed
files; discard entries for missing or unsafe paths. Fingerprints are
optimizations and staleness inputs, not security boundaries.

Use a small manifest plus bounded per-transcript screening/structural shards,
not one corpus-sized JSON document. Publish shards atomically before the
manifest; orphan shards are harmless and removed by a later bounded cleanup.
Although message content is excluded, UUIDs, session IDs, paths, and timestamps
remain sensitive local correlation metadata and require restrictive file modes.

## Inference algorithm

### 1. Discover transcripts safely

Resolve the Claude root from `CLAUDE_CONFIG_DIR`, falling back to
`$HOME/.claude`. Search only bounded `projects/*/*.jsonl` candidates beneath
that resolved root. Refuse symlink escapes, non-regular files, invalid session
filenames, excessive directory counts, excessive total bytes, and files that
change incompatibly while read.

Expose documented limits for records, bytes, transcripts, candidate fan-out,
and overall duration. Initial limits are implementation decisions to lock at
the design gate; tests must cover every boundary.

### 2. Extract structural graphs

For each valid JSONL record retain only:

```text
sessionId
uuid
parentUuid
type/subtype classification
timestamp
isSidechain
```

Exclude message bodies and metadata values unrelated to structure. Treat
`parentUuid` only as an edge between messages. Validate that session IDs and
UUIDs are bounded strings with the expected UUID shape before indexing.

Claude transcripts may contain branches, retries, attachments, snapshots, and
sidechains, so raw file order is not sufficient. Build a bounded message graph
and identify comparable main-chain paths. The exact main-chain selection rule
must be locked with fixtures before implementation. The recommendation is to
start from terminal non-sidechain user/assistant records, follow `parentUuid`
to roots, and compare all bounded plausible paths rather than selecting the
last line blindly.

### 3. Generate candidates with an inverted index

Build:

```text
message UUID -> session IDs containing that UUID
```

Candidate sessions are only those sharing at least one validated substantive
UUID with the target. This avoids pairwise full-transcript comparison.

Implement candidate generation as a staged performance pipeline rather than
deeply parsing every transcript to build the index:

```text
Stage 0: bounded filesystem manifest
    -> Stage 1: superficial streaming UUID screen
        -> Stage 2: exact candidate JSON/graph parse
            -> Stage 3: relationship and direction analysis
```

Stage 0 records canonical path, filename session ID, device/inode where
available, size, `mtime_ns`, optional birth time, and cache version. Unchanged
files require no content scan during a warm lookup.

Stage 1 scans only changed/new files as bounded byte streams and builds a
compact per-file screen, such as a Bloom filter or sorted keyed UUID digests.
It recognizes top-level `uuid` candidates without decoding message bodies or
constructing full JSON records. It must tolerate legal whitespace and
chunk-boundary splits. False positives are allowed; false negatives for any
UUID accepted by the deep parser are forbidden.

The target is deeply parsed once to obtain validated substantive UUIDs. A
screen-negative file is eliminated. Only screen-positive files advance to
Stage 2, where exact UUIDs, edges, types, and graph paths are verified. Clock
sources are loaded once into minimal bounded maps and consulted only after an
exact structural relationship exists.

Complexity target:

```text
index refresh: O(total changed transcript bytes)
target lookup: O(target structural records + related candidate comparisons)
```

Do not implement an O(session_count squared) all-pairs scan.

Expose internal work counters for deterministic performance tests:

```text
files enumerated; superficial bytes scanned; files/bytes deeply parsed;
records decoded; candidate pairs compared; graph nodes/edges visited;
cache hits/misses; peak bounded-buffer size
```

On a cold cache, each changed file may receive one superficial linear scan, but
only the target and screen-positive candidates incur deep parsing. On a warm
cache, unchanged unrelated transcript bytes are not read. Changing one
unrelated file refreshes only its shard. A false-positive screen adds bounded
deep work but cannot create a relationship. One huge matching file must remain
streamed and memory-bounded. `--all` refreshes screening once and compares only
exact-overlap components.

Tests assert logical work counts rather than relying primarily on wall time. A
generous wall-clock smoke threshold may catch catastrophic regression, but
normal CI must not be host-speed-sensitive.

### 4. Establish shared lineage

A related-session result requires all of:

- different session IDs;
- exact shared UUIDs;
- matching `parentUuid` edges along an ordered path;
- at least one shared substantive user or assistant record;
- divergence or a distinct materialization identity;
- no graph contradiction proving the candidate relationship impossible.

System/bootstrap UUIDs alone are insufficient. The minimum total shared count
is a design-gate parameter, recommended initially as three with at least one
substantive record.

The last message in the strongest shared ordered path becomes the inferred
fork boundary. Report the boundary; do not call it proof of an exact fork
operation.

### 5. Infer direction

Evaluate independent clocks in descending durability:

1. transcript filesystem birth time, when supported;
2. first session-specific `~/.claude/history.jsonl` event;
3. live `~/.claude/sessions/*.json` `startedAt`, when safely matched;
4. materialization gap between transcript birth and oldest embedded record;
5. earliest clearly non-copied structural record, only as supporting evidence.

Never use transcript modification time as creation time. Never decode creation
time from bridge-session IDs unless Anthropic documents that contract. Treat
live `startedAt` as process start, not immutable session creation; a resumed
old parent can start after its child.

Direction is `strongly_inferred` only when ancestry is strong, at least two
independent creation proxies agree, and none conflict. One usable proxy may
produce `inferred`; disagreement produces `conflicting_evidence`.

### 6. Select or refuse a likely parent

Rank candidates primarily by inherited substantive ancestry and latest shared
boundary, then by consistent older creation evidence. Timestamps may rank
direction only after structural relationship is established.

Never choose merely because one related session is older.

For multi-generation history:

```text
A -> B -> C
```

prefer B only if C contains B-specific ancestry beyond the A/B shared root. If
C contains no B-specific record, immediate parentage remains ambiguous.

For siblings:

```text
A
|- B
`- C
```

if B and C share only A's boundary, B being seconds older cannot make it C's
parent. Report the shared root or candidate set and leave
`likely_parent_session_id` null when immediate direction cannot be supported.

### 7. Revalidate before recording

Before `--record` or each `--record-all` write:

- verify the target and selected candidate files retain their analyzed
  fingerprints;
- verify no stronger planned claim appeared concurrently;
- verify the result remains uniquely recordable;
- acquire locks in a documented global order;
- atomically replace only the inferred record for the target.

If inputs changed, report `stale_during_analysis` and do not record.

## Staleness and lifecycle

An inference can become stale when a transcript grows, a deleted transcript is
restored, a new candidate appears, the algorithm changes, or stronger evidence
is created. Persist source fingerprints and algorithm version.

Plain `session`, `list`, and `show` may perform only cheap staleness checks. A
record is:

```text
current
stale_sources
stale_algorithm
superseded
```

They never trigger inference. Refresh explicitly with:

```text
agent-fork session claude-parent infer --session-id ID --record
```

Cleanup of a Git worktree must not remove planned or inferred Claude lineage.
Claude sessions remain independently resumable. Retention/pruning is deferred.

## Failure and exit behavior

- Parser conflicts and missing required scope: exit 2.
- Target session/transcript not found: existing `session_not_found`, exit 3.
- Bounded lookup unavailable/corrupt/unsafe: a dedicated stable inference error,
  exit 3, with JSON error envelope on stderr.
- Successful analysis with no relationship: exit 0 with
  `insufficient_evidence`; absence is an analysis result.
- Successful ambiguous analysis: exit 0 with candidates and no parent.
- `--record` requested but result not recordable: exit 3 with a stable
  `claude_parent_not_recordable` error and the analysis result available in the
  documented output/error shape.
- Partial `--record-all`: default recommendation is exit 3 with per-target
  results and counts; successfully written records remain committed. Atomic
  all-or-nothing bulk recording is not justified across many independent
  targets. This policy requires owner approval at G0.
- Delete missing record: exit 3 without touching transcripts or other stores.

All human diagnostics are bounded and control-character safe. JSON preserves
raw valid identifiers but never transcript content.

## Code isolation

Suggested modules:

```text
src/agent_fork/session.py
    fast ordinary inspection; reads recorded inference only

src/agent_fork/lineage.py
    existing planned claims; semantics unchanged

src/agent_fork/claude_lineage_inference.py
    structural extraction, graph comparison, candidate ranking

src/agent_fork/claude_lineage_index.py
    disposable incremental index and safe discovery

src/agent_fork/lineage_inference_store.py
    recorded inference schema and atomic CRUD

src/agent_fork/cli.py
    claude-parent command family and target/record constraints
```

The fast inspection path may import the inference-store reader but must never
import or invoke the scanner/index builder. This architectural boundary gets a
test.

## Documentation deliverables

Update README and command help with:

- exact command names and explicit-scope requirement;
- preview versus `--record`/`--record-all` behavior;
- locations and meanings of planned, inferred, and cache files;
- relationship versus direction versus immediate-parent distinction;
- the observed shared-UUID and creation-clock experiment;
- `parentUuid` and bridge-session non-lineage findings;
- sibling, multi-generation, resume, copy, restore, and retention limitations;
- algorithm version and staleness behavior;
- performance bounds and cache controls;
- privacy guarantee that message content is not indexed or stored;
- deletion scope and confirmation behavior;
- statement that Anthropic does not document this heuristic as a stable API.

Record a sanitized real-agent experiment in `EXPERIMENTS.md`, containing only
versions, commands, session IDs, structural counts, clock deltas, classifications,
and results—never prompts or responses.

## Proposed TDD matrix

Reserve final IDs only after owner approval. Candidate rows:

| ID | Tier | Test-first obligation |
|---|---|---|
| T-CPI-01 | U | structural extractor retains only approved fields and rejects content leakage |
| T-CPI-02 | U | exact UUID/edge chain with substantive record establishes shared lineage |
| T-CPI-03 | U | system-only overlap, UUID collision with conflicting edge, and raw-order coincidence do not establish lineage |
| T-CPI-04 | U | graph path selection handles metadata, attachments, retries, sidechains, and malformed/cyclic edges within bounds |
| T-CPI-05 | U | fork boundary is the last exact shared ordered structural record |
| T-CPI-06 | U | two agreeing creation proxies infer direction; conflict refuses strong direction |
| T-CPI-07 | U | mtime and bridge IDs are never treated as creation or parent evidence |
| T-CPI-08 | U | multi-generation candidate prefers inherited parent-specific history |
| T-CPI-09 | U | siblings at one boundary remain ambiguous regardless of timestamp ordering |
| T-CPI-10 | U | planned claim always supersedes inferred record and prevents overwrite |
| T-CPI-11 | F | inference store atomic round-trip, replacement, ordering, locking, corrupt schema, and source isolation |
| T-CPI-12 | F | index incremental refresh parses changed files once and deletes stale entries safely |
| T-CPI-13 | F | discovery rejects symlinks, escapes, non-files, races, excess files/bytes/records/fan-out/time |
| T-CPI-14 | F | input fingerprint change before record produces no write |
| T-CPI-15 | C | command hierarchy/help/completions expose list/show/infer/delete and output options |
| T-CPI-16 | C | infer requires exactly one of current/session-id/all |
| T-CPI-17 | C | record works only with current/session-id; record-all only with all |
| T-CPI-18 | C | preview is read-only and plain session never starts inference/index work |
| T-CPI-19 | C | list/show are store-only, bounded, source-aware, and stable in JSON |
| T-CPI-20 | C | delete requires exact child/source/consent and never removes Claude or Git resources |
| T-CPI-21 | C | recorded inference appears in ordinary session with inferred source/status and staleness |
| T-CPI-22 | C | no-result, ambiguity, unavailable, unrecordable, and partial-bulk exits/streams are stable |
| T-CPI-23 | C | terminal controls, locale, closed streams, SIGPIPE, SIGINT, and SIGTERM remain conformant |
| T-CPI-24 | R | known real parent/child pair yields shared boundary and correct direction without content capture |
| T-CPI-25 | R | real siblings or controlled equivalent remain ambiguous at the shared boundary |
| T-CPI-26 | R | real multi-generation chain selects parent only when parent-specific ancestry is inherited |
| T-CPI-27 | U | cold screening scans changed bytes once and deeply parses only target and screen-positive files |
| T-CPI-28 | U | warm screening skips unchanged unrelated bytes and refreshes only changed shards |
| T-CPI-29 | U | whitespace/chunk variants have no screen false negatives; false positives only add bounded deep work |
| T-CPI-30 | F | large sparse corpus and huge matching transcript obey deep-parse, comparison, memory, and cancellation budgets |
| T-CPI-31 | F | `--all` refreshes once and compares exact-overlap components without quadratic growth |
| T-CPI-32 | R | real corpus records cold, warm, and incremental work counters plus elapsed diagnostics |

Every implementation task must have its corresponding failing test first. Add
the group to `docs/testing/TEST-MATRIX.md` as `tdd`; flip it to `live` only
after hermetic implementation is green, and to `done` only after real gates and
documentation pass.

## SDD/TDD implementation sequence and gates

### CPI-G0 — Owner contract gate

Approve:

- `session claude-parent <operation>` naming;
- required `--current|--session-id|--all` targeting;
- `--record` versus `--record-all` safety;
- evidence vocabulary and precedence;
- separate inference store and disposable cache;
- `session validate --has-parent` treatment of inferred evidence;
- partial bulk-recording exit policy;
- initial hard bounds and recording threshold.

Then amend requirements/design decisions, add atomic P01 TS/T tasks, reserve
matrix IDs, and link canonical documents. No production code before this gate.

### CPI-G1 — RED fixtures and structural model

Create synthetic transcript-family fixtures for parent/child, siblings,
multi-generation chains, resume, copied files, retries, sidechains, cycles,
truncation, and hostile paths. Add T-CPI-01..10 and prove each fails for the
intended missing behavior while existing G-SES remains green.

### CPI-G2 — Bounded index and extractor

Implement safe discovery, structural extraction, graph normalization, inverted
indexing, incremental refresh, limits, and cancellation. Gate: T-CPI-01..07 and
12..13 pass; scans are linear in changed bytes; no message content reaches
cache snapshots.

### CPI-G3 — Candidate and ambiguity engine

Implement boundary detection, creation evidence, ranking, multi-generation
selection, and sibling refusal. Gate: T-CPI-02..09 pass, including deterministic
candidate ordering and no timestamp-only parent choice.

### CPI-G4 — Inference persistence

Add the separate versioned store, locking, atomic replacement, staleness, and
stronger-source checks. Gate: T-CPI-10..14 pass under concurrency and injected
failures; planned claims remain byte/semantically compatible.

### CPI-G5 — CLI and deletion safety

Wire `list`, `show`, `infer`, and `delete`; output renderers; errors; help; and
completions. Gate: T-CPI-15..23 pass through the installed console script;
plain session proves it never invokes the scanner.

### CPI-G6 — Hermetic repository gate

Run:

```text
just all
just check-matrix
just strict-collect
just clean-install
just test-git-matrix
just test-signals
```

Gate: all green, no unexpected skips, no cache/state residue in fixtures, and
no regression to current session inspection or fork transactionality.

### CPI-G7 — Real Claude gate

Run known pair, controlled siblings, and controlled multi-generation cases on
the supported Claude CLI. Validate preview, record, ordinary inspection,
refresh, list/show, and metadata-only delete. Record sanitized results in
`EXPERIMENTS.md`.

### CPI-G8 — Review gate

Perform correctness review and a second adversarial review of graph semantics,
privacy, bounds, state precedence, races, bulk behavior, and destructive
targets. No unresolved high or medium findings. Stop for owner approval before
PR or merge.

## Adversarial review

### Finding A1 — Critical: older sibling can be misidentified as parent

**Attack:** A forks B and C at the same boundary. B starts seconds before C.
Timestamp ranking selects B as C's parent.

**Resolution:** timestamps never establish relationship and cannot break an
ancestry-boundary tie. Without B-specific history in C, return ambiguity. Add
T-CPI-09 and real/controlled T-CPI-25.

### Finding A2 — Critical: inferred records can contaminate planned claims

**Attack:** an inferred parent overwrites the v1 planned claim for the same
child, causing lower-confidence evidence to appear transactionally known.

**Resolution:** separate stores and source types; strict precedence; inference
cannot replace planned data. Add T-CPI-10/11.

### Finding A3 — Critical: transcript content leaks into cache or state

**Attack:** a convenient parsed-record cache persists prompts, tool output,
account identifiers, or credentials.

**Resolution:** whitelist structural fields, test serialized cache/state for
content canaries, and keep account/bridge data out. Add T-CPI-01.

### Finding A4 — High: naive all-pairs comparison is quadratic

**Attack:** thousands of sessions make `--all` consume unbounded CPU and time.

**Resolution:** one-pass incremental inverted index, related-candidate-only
comparison, explicit caps, cancellation, and complexity tests. Add
T-CPI-12/13.

### Finding A5 — High: file order is not conversation order

**Attack:** retries, attachments, sidechains, resumes, and metadata interleave;
longest raw prefix yields a false boundary.

**Resolution:** compare validated `uuid`/`parentUuid` graph paths, not JSONL line
prefixes. Lock main-chain rules with adversarial fixtures before implementation.
Add T-CPI-04/05.

### Finding A6 — High: creation clocks reverse on resume or restore

**Attack:** an old parent is resumed after its child, or restored with a new
filesystem birth time, making it appear younger.

**Resolution:** clocks are individually sourced and weighted; process start is
ephemeral; conflicts downgrade/refuse direction; no single clock is decisive.
Add T-CPI-06/07.

### Finding A7 — High: TOCTOU records stale analysis

**Attack:** target or candidate transcript changes after analysis but before
the inference write.

**Resolution:** fingerprint inputs, revalidate under documented lock ordering,
and refuse changed inputs. Add T-CPI-14.

### Finding A8 — High: bulk recording hides partial failure

**Attack:** `--record-all` writes some relationships, fails later, and implies
all-or-nothing success.

**Resolution:** return per-target results and explicit written/skipped/failed
counts; use deliberate partial-commit semantics and nonzero exit on any hard
failure. This remains an owner decision at G0.

### Finding A9 — High: delete removes agent-owned data

**Attack:** path confusion or source ambiguity deletes transcripts or the wrong
lineage record.

**Resolution:** delete only by decoded store key, never by arbitrary path;
require source when ambiguous and consent always; prove Claude/Git files remain
unchanged. Add T-CPI-20.

### Finding A10 — Medium: shared bootstrap UUIDs produce false relationships

**Attack:** copied fixtures or initialization records overlap without shared
conversation history.

**Resolution:** require substantive user/assistant ancestry and matching graph
edges; system-only overlap is insufficient. Add T-CPI-02/03.

### Finding A11 — Medium: manual transcript copy resembles a fork

**Attack:** a user duplicates a transcript file, producing perfect UUID
ancestry and later creation time.

**Resolution:** classify the result as inferred shared lineage, never proof of
a Claude fork. Distinct session IDs and divergence improve evidence; exact
duplicates remain ambiguous/insufficient for immediate parentage.

### Finding A12 — Medium: recorded inference silently becomes stale

**Attack:** a restored transcript supplies a better candidate, but plain
inspection continues presenting the old result as current.

**Resolution:** persist fingerprints and algorithm version, expose staleness,
and require explicit refresh. Never run hidden background inference.

### Finding A13 — Medium: validation treats inference as certainty

**Attack:** `session validate --has-parent` passes and callers mistake inferred
evidence for resolved truth.

**Resolution:** preserve `id_status=inferred` in output and document that
`--has-parent` means evidence. Owner must approve this compatibility decision
at G0; a stricter future assertion should name the required evidence class.

### Finding A14 — Medium: index trusts mutable filenames and metadata

**Attack:** symlinks, path replacement, malformed IDs, oversized records, or
mtime reuse poison candidate lookup.

**Resolution:** resolved-root containment, regular-file enforcement, bounded
decoding, identity checks during read/record, versioned cache, and cache-as-
optimization semantics. Add T-CPI-12..14.

### Finding A15 — Medium: algorithm changes alter historical conclusions

**Attack:** a newer algorithm would choose a different parent while old records
look current.

**Resolution:** version every recorded result; mark prior versions stale rather
than silently reinterpret or migrate them.

### Review conclusion

The proposal is viable if the sibling ambiguity rule, evidence-store
separation, structural-only privacy boundary, bounded inverted index, and
pre-write revalidation remain mandatory. No unresolved critical finding remains
in the design. The bulk partial-failure contract, initial bounds/thresholds,
and validation treatment of inferred evidence require explicit owner approval
at CPI-G0.

## Explicit non-goals

- Claiming Anthropic supplies an authoritative Claude parent ID.
- Treating an inferred likely parent as proof of immediate parentage.
- Running historical inference during ordinary `session` inspection.
- Parsing message content semantically.
- Using bridge-session IDs as lineage or timestamps.
- Deleting or editing Claude-owned files.
- Direct network calls or Claude session mutation.
- Cross-host matching in the first implementation.
- Codex inference; Codex keeps its app-server evidence path.
- Family-tree visualization, pruning, or a generic manual `update` command.
