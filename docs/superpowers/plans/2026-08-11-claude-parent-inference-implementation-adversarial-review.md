# Adversarial review — Claude parent inference implementation plan

**Status:** Pre-implementation review complete; findings incorporated during
implementation. Post-implementation review completed 2026-08-11 with no
unresolved critical or high correctness finding; stopped at CPI-G8.

**Date:** 2026-08-11

**Reviewed plan:** [Claude parent inference implementation plan](2026-08-11-claude-parent-inference-implementation.md)

## Review method

The review attempted to break the plan at its execution boundaries rather than
repeat the design-level A1–A15 analysis. It checked the installed Python and
filesystem behavior, current argparse layout, matrix enforcement, existing
lineage semantics, and the proposed indexing/graph/storage workflow.

Severity meanings:

- **Critical:** likely false lineage, unusable core behavior, unbounded work, or
  violation of a primary safety invariant.
- **High:** material correctness, compatibility, privacy, race, or destructive
  risk that must be resolved before implementation.
- **Medium:** important ambiguity or testability gap that can be resolved while
  implementing only after its contract is locked.

## Executive verdict

The architecture remains sound: explicit opt-in scope, separate inferred
state, a disposable index, evidence precedence, and ambiguity-first behavior
are the right boundaries. The execution plan is not yet implementation-ready.

Two critical gaps block CPI-G0:

1. the proposed recording threshold depends on creation clocks that are not
   portably available from Python on this Linux VM; and
2. the proposed graph-path wording can lead to exponential path enumeration on
   adversarial transcripts.

Eight high findings also require plan amendments. The most important are
bounded parsing of auxiliary Claude files, stale inference validation
semantics, cache sensitivity, exact `--all` scope, and concurrency around
planned-record deletion/creation.

The owner additionally identified performance as a primary acceptance concern:
large transcript corpora must receive a superficial screening pass and only
possible matches may advance to deep parsing. This is a mandatory execution
contract, not an optional optimization.

## Critical findings

### AR-C1 — Creation-clock threshold is not portable and can make the feature unusable

**Plan assumption:** `strongly_inferred` and recording initially require at
least two agreeing creation proxies. Transcript filesystem birth time is the
first listed durable proxy.

**Observed failure:** On this Linux VM with Python 3.12, `os.stat_result` has
neither `st_birthtime` nor `st_birthtime_ns`. GNU `stat` displays a birth time
because it uses a platform-specific `statx` path, but Python's ordinary API
does not expose it here.

For a completed historical session, the live `~/.claude/sessions/*.json`
registration may no longer exist. That can leave only the first history event
as a usable direction clock. Under the recommended two-clock rule, the primary
historical use case becomes permanently preview-only on common Linux systems.

Using ctime is not an acceptable substitute: it is inode metadata-change time,
not creation time. Spawning `stat` once per transcript would add portability,
PATH, locale, process-count, and performance problems to a large scan.

**Required resolution before CPI-G0:** choose and document one of:

1. implement a small platform birth-time adapter with explicit Linux `statx`,
   macOS `st_birthtime`, feature detection, and bounded fallback tests;
2. allow a unique structurally dominant parent plus one durable clock to be
   recordable as `inferred`, reserving `strongly_inferred` for two clocks; or
3. restrict recording support by platform and document the limitation.

**Recommendation:** combine 1 and 2. Use birth time when natively available,
but let structurally dominant ancestry plus one nonconflicting durable clock
produce a recordable `inferred` result. Never substitute ctime or mtime. Make
the exact rule a table, not a prose score.

Add distinct tests for Linux-without-birth-time, macOS birth time, completed
sessions without live registration, and conflicting single-clock evidence.

### AR-C2 — “Compare all plausible paths” permits exponential graph work

**Plan assumption:** build a message graph and “compare all bounded plausible
paths” rather than selecting raw file order.

**Attack:** A crafted transcript with repeated retry/branch diamonds can have a
linear number of nodes but an exponential number of root-to-terminal paths.
The transcript, record, and candidate limits do not prevent path explosion.

**Impact:** one bounded-size transcript can consume the full timeout, memory,
or CPU. `--all` multiplies the exposure.

**Required resolution:** specify a polynomial algorithm before Task 1B. Use
memoized ancestor sets/chain digests or dynamic programming over a validated
acyclic graph. Cap branch fan-out and graph edges independently. Never
materialize all paths. Cycles and excessive branching must produce a bounded
`unavailable` result for that transcript, not global corruption.

Add a diamond-graph fixture whose path count would be exponential and assert
linear/polynomial node visits with an instrumented counter.

## High findings

### AR-H1 — Auxiliary Claude sources have no bounded parser contract

Direction analysis reads:

```text
~/.claude/history.jsonl
~/.claude/sessions/*.json
```

The plan thoroughly bounds project transcripts but does not define equivalent
limits, containment, symlink, malformed-record, duplicate-session, or changing-
file behavior for these sources. `history.jsonl` also contains prompt-related
fields that must not leak through incidental whole-record parsing.

**Required amendment:** add dedicated structural readers with field
whitelists, byte/record/file caps, root containment, safe degradation, and
content-canary tests. Read history once per invocation into the minimum
`sessionId -> first timestamp` map. Read live registration files once into a
bounded `sessionId -> startedAt` map. Never retain or serialize other fields.

### AR-H2 — The cache is content-free but still sensitive correlation data

Message UUIDs, session IDs, transcript paths, fork boundaries, and timestamps
can reveal activity relationships even without prompt text. Calling the cache
“privacy-safe” or “content-free” is accurate only in a narrow sense.

**Required amendment:** document the cache as sensitive local metadata; create
files/directories with restrictive permissions; never include account,
organization, bridge, prompt, response, or tool fields; provide a documented
cache removal/rebuild command or safe manual path; test modes and umask-hostile
creation. Consider keyed digests for the inverted UUID index, but do not claim
they anonymize low-entropy metadata.

### AR-H3 — Stale inferred evidence and validation semantics are underspecified

The plan recommends that inferred evidence satisfy `session validate
--has-parent`, but does not say whether `stale_sources`, `stale_algorithm`, or
`superseded` records count. Passing validation on a stale or superseded
inference contradicts the meaning of validation.

**Required amendment:** only a current, non-superseded inferred record may
satisfy `--has-parent` or exact `--parent-session-id`. Stale records remain
visible in `list/show` and ordinary inspection but set
`has_parent_evidence=false` for validation, or validation must expose a separate
policy. Recommendation: fail assertions with actual status included. Lock this
at CPI-G0 and add explicit tests.

### AR-H4 — `--all` target set and refresh semantics are ambiguous

The design says `--all` analyzes sessions “missing stronger parent evidence.”
It is unclear whether that includes:

- sessions with current inferred records;
- stale inferred records;
- sessions that are themselves planned parents;
- malformed or duplicate session IDs across project directories;
- root sessions with no candidate ancestry.

This ambiguity affects cost, `--record-all`, summaries, and idempotence.

**Required amendment:** define `--all` as all unique discoverable Claude
session IDs lacking a planned claim as child. Include current and stale inferred
records so bulk analysis can refresh them. Deduplicate identical session IDs
across paths only if structural fingerprints agree; otherwise report conflict.
Roots and insufficient cases appear in preview summaries but produce no write.

### AR-H5 — Planned-claim creation, inference write, and delete can race

The plan requires rechecking a planned claim before inference recording but
does not fully specify lock ownership. A planned claim can appear between the
check and inference write. Likewise, deleting a planned claim can race with
fork pipeline writes or inference refresh.

**Required amendment:** define one global lock order and the exact critical
section. A record operation must hold the relevant planned/inferred locks across
the final stronger-source check and inferred replacement. Planned deletion must
use the planned store's lock and must not hold an inference lock unless both are
needed. Never hold cache locks during expensive analysis. Add concurrent
fork-claim/infer/delete subprocess tests and lock-order assertions.

### AR-H6 — Nested argparse output placement is easy to implement inconsistently

Current `session` and `session validate` each define their own `-o/--output` and
`--json` options so options work after the selected action. A new nested
`claude-parent` namespace adds another parser depth. Defining output only on an
ancestor will make common forms fail depending on option placement.

**Required amendment:** lock supported spelling and test it. Recommendation:
each terminal action (`list`, `show`, `infer`, `delete`) owns output options,
using one helper to prevent drift. Require at least the documented form with
output options after the action; optionally accept ancestor placement only if
byte-identical and unambiguous. Add bare `session claude-parent` help/error
tests.

### AR-H7 — Index and state decoding can violate the memory bounds

The plan allows a 2 GiB corpus and proposes JSON cache/state documents. A
single `json.loads(path.read_text())` of a large generated cache can allocate
far beyond the nominal corpus limit. Atomic rewrite can duplicate memory and
disk usage. A corrupt cache can claim enormous arrays.

**Required amendment:** set a much smaller explicit cache-file cap, use a
streamable or sharded format, and bound decoding before allocation. Prefer one
small manifest plus per-transcript structural shards, or JSONL records with an
incrementally rebuilt inverted structure. The 2 GiB scan cap must not imply a
2 GiB monolithic cache. Test oversized length, deep nesting, duplicate keys,
disk-full, and partial shard replacement.

### AR-H8 — A nominal index can still deep-parse every file

**Attack:** Build the inverted index by fully decoding every JSONL transcript.
The work is technically linear in corpus bytes, but it allocates and decodes
every record even when nearly every file is unrelated. A coarse cache can
repeat that work on warm runs.

**Required amendment:** enforce separate manifest, superficial screen, exact
deep parse, and graph-analysis stages. Screening must be streaming,
content-free, and no-false-negative; false positives may only add bounded deep
work. Persist per-file shards so warm lookup does not read unchanged unrelated
transcript bytes. Instrument deep parses, bytes, records, comparisons, graph
visits, cache hits, and bounded-buffer size.

Add cold/warm/incremental sparse-corpus tests, chunk/whitespace screening tests,
an injected false-positive test, a huge matching-file bounded-memory test, a
nonquadratic `--all` test, and a sanitized real-corpus benchmark. Assert logical
work counts primarily; use wall time only as a generous catastrophic-regression
guard.

## Medium findings

### AR-M1 — Recommended limits are arbitrary and may not be test-practical

The proposed 256 MiB per transcript, 2 GiB total, and 120-second timeout are
large enough to make boundary tests slow or disk-heavy. Conversely, 250,000
records can create substantial Python-object overhead.

**Resolution:** centralize injectable `InferenceLimits`; unit tests use tiny
limits and production defaults are justified with measured real-corpus data.
Use logical byte counters rather than allocating boundary-sized fixtures.

### AR-M2 — Fingerprints need device/inode identity and read-time checks

Path, size, and mtime can be reused after replacement. Birth time is optional.

**Resolution:** include device/inode where available; compare `fstat` before and
after bounded read; re-resolve containment; revalidate immediately before
record. Fingerprints detect staleness but are not authenticity proofs.

### AR-M3 — Matrix implementation wording can conflict with one-row/one-item rules

The repository checker requires exact matrix marker discipline. Broad test
functions covering several provisional IDs or parameter IDs that do not match
markers will fail collection/matrix checks.

**Resolution:** Task 0 must reserve exact rows; each collected item gets exactly
one matching marker, with parametrized IDs following existing rules. Run
`check-matrix` and `strict-collect` at every RED batch, not only late gates.

### AR-M4 — `--record` error output needs a stable analysis location

The plan says an unrecordable result exits 3 while “the analysis result” remains
available, but does not define whether JSON places it in stdout or the stderr
error envelope. Splitting a machine result across streams is hazardous.

**Resolution:** choose one contract at CPI-G0. Recommendation: JSON error on
stderr includes bounded `details.analysis`; stdout remains empty on exit 3,
matching existing error conventions. Preview ambiguity remains exit 0/stdout.

### AR-M5 — Real tests can create persistent Claude state and cost

Controlled sibling and multi-generation tests create real sessions that may
persist after Git fixtures are cleaned. Repeated runs can grow the very corpus
being benchmarked and incur model usage.

**Resolution:** make real cases explicitly opt-in, version/cost bounded, use
unique disposable roots through `CLAUDE_CONFIG_DIR` where supported, record
cleanup limits, and never delete user-owned sessions. A fixture must distinguish
test-owned state from pre-existing state.

### AR-M6 — Planned deletion weakens a transactional provenance invariant

Although user-authorized deletion is valid, exposing planned deletion means a
managed child can lose its only strong local parent evidence. The warning alone
does not make later behavior obvious.

**Resolution:** after deletion, return the exact consequence and recovery
options. `show/list` should not retain ghost indexes. Do not automatically infer
a replacement during delete. Consider requiring explicit `--source planned`
even when it is the only record.

### AR-M7 — A current inference should not be trusted forever merely because two files are unchanged

A previously absent candidate can appear without changing the target or chosen
parent fingerprints. Cheap staleness checks cannot detect that.

**Resolution:** record an index generation/corpus fingerprint. Plain inspection
may label the record `current_at_analysis` rather than globally current.
Appearance of a new transcript makes the inference potentially stale when the
index is next refreshed; only explicit inference can re-establish uniqueness.
Documentation must avoid claiming cheap checks prove global freshness.

## Required plan amendments before implementation

1. Replace the two-clock recording rule with an explicit portable evidence
   table and decide birth-time acquisition.
2. Specify a polynomial graph algorithm and edge/fan-out limits.
3. Lock the manifest/screen/deep/graph performance architecture and its
   cold/warm/incremental work-count tests.
4. Add bounded, privacy-whitelisted history and live-registration readers.
5. Treat cache data as sensitive metadata and bound/shard its decoding.
6. Define stale/superseded inference behavior under validation.
7. Define the exact `--all` target set and refresh behavior.
8. Define lock order and concurrent planned/inferred/delete critical sections.
9. Lock nested output-option placement and error-stream schema.
10. Add injectable limits, stronger fingerprints, and per-gate matrix checks.
11. Define real-test ownership, cost, persistence, and cleanup boundaries.

## Gate recommendation

CPI-G0 should remain closed. After the eleven amendments are folded into the
implementation plan, rerun this review against the revised text. If no critical
or high finding remains, the plan can proceed to Task 0 corpus/matrix changes
and then CPI-G1 RED fixtures.

## Post-implementation disposition

- AR-C1: resolved by allowing structurally dominant ancestry plus one durable
  nonconflicting history clock to record `inferred`; birth time is optional and
  ctime/mtime are not substituted.
- AR-C2: resolved with memoized longest-compatible-chain analysis; paths are
  not enumerated.
- AR-H1/H2/H7/H8: bounded transcript/history reads, sharded `0600` screening
  cache, content-canary tests, cold/warm counters, and target-plus-candidate
  deep parsing are implemented. The known corpus warm run reread zero
  superficial bytes.
- AR-H3: recorded source fingerprints are cheaply revalidated; stale inference
  is noticed and excluded from ordinary parent evidence/validation.
- AR-H4: `--all` is explicit and bounded; planned-child claims are excluded.
- AR-H5: stores use the established lock/atomic-replace pattern; planned and
  inferred schemas remain physically separate and precedence is rechecked by
  ordinary inspection. Cross-store transactions remain deliberately avoided.
- AR-H6: every terminal `claude-parent` action owns its output options and help
  is black-box exercised.
- Destructive review: delete resolves decoded child/source records and only
  invokes the matching metadata-store removal. Claude and Git paths are never
  deletion targets.
- Correctness review found and fixed a boundary bug: latest-timestamp selection
  was replaced by longest validated shared ancestry chain selection before the
  final gates.

Final evidence: `just all` reports 327 passed, one intentional retired skip,
and nine explicit live/signal deselections; matrix, strict collection,
clean-install, Git matrix, and signal gates pass. The known real Claude pair
returns the expected parent and boundary with 138 files enumerated, two deep
parses, and zero warm superficial bytes.
