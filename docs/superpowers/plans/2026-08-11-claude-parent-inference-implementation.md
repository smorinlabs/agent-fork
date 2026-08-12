# Claude parent inference implementation plan

**Status:** Implemented through CPI-G8 on 2026-08-11; stopped for owner review
before PR. The 32 provisional obligations were consolidated into nine canonical
G-CPI matrix rows without dropping the locked relationship, performance,
privacy, persistence, or CLI contracts.

**Date:** 2026-08-11

**Design:** [Claude parent inference and lineage management](2026-08-11-claude-parent-inference.md)

**Objective:** Implement bounded, opt-in Claude transcript lineage inference,
separate persistence for inferred relationships, and safe record management
without slowing ordinary session inspection or weakening planned lineage
claims.

## Delivery contract

The completed command tree is:

```text
agent-fork session claude-parent list
agent-fork session claude-parent show --session-id ID
agent-fork session claude-parent infer
    (--current | --session-id ID | --all)
    [--record | --record-all]
agent-fork session claude-parent delete
    --session-id ID [--source planned|inferred] [--yes]
```

Inference without a recording option is read-only. Plain `agent-fork session`
may read an already-recorded inference but must never discover transcripts,
build an index, or infer a relationship.

## Working rules

1. Execute tasks in order. Every `TS` task must be red for the intended reason
   before its paired implementation task begins.
2. Reserve final project and matrix IDs atomically at Task 0. The provisional
   `T-CPI-01..32` names below become canonical only then.
3. Do not expose transcript content in fixtures, caches, state, snapshots,
   diagnostics, experiment logs, or test failure output.
4. Do not alter `session-lineage.json` v1 semantics. Planned claims and
   inferred records remain separate.
5. Never resolve a sibling-boundary tie by timestamps.
6. No production step may begin before CPI-G0; no PR may be opened before
   CPI-G8 owner approval.

## Task 0 — Lock contract and tracking

**Files:**

- Modify `REQUIREMENTS.md`
- Modify `DESIGN-DECISIONS.md`
- Modify `docs/testing/TEST-MATRIX.md`
- Modify `projects/P01-agent-fork-v1.md`
- Modify this plan only if owner decisions differ from recommendations

### Owner decisions

Approve or amend:

1. Command names and required target selectors.
2. `--record` versus `--record-all` constraints.
3. Recorded inferred evidence satisfies `session validate --has-parent` while
   retaining `id_status=inferred` — **recommended: yes**.
4. Bulk recording commits independently per child and exits 3 if any hard
   failure occurs — **recommended: yes**.
5. Initial recording threshold — **recommended:** at least three exact shared
   graph records, at least one shared user/assistant UUID, at least two agreeing
   creation proxies, no conflicting proxy, and one unique best candidate.
6. Initial safety bounds — **recommended starting values:** 10,000 transcripts,
   256 MiB per transcript, 2 GiB total bytes per invocation, 250,000 records per
   transcript, 1,000 candidates per target, and 120 seconds overall. Bounds are
   implementation constants in v1, documented and testable; avoid premature
   config surface.

### Changes

1. Add the next requirement and design-decision IDs for Claude parent
   inference, evidence separation, performance bounds, and destructive scope.
2. Add `G-CPI` as `tdd` with canonical rows corresponding to T-CPI-01..32.
3. Add atomic `[P01-TSxx]` and `[P01-Txx]` pairs for Tasks 1–9.
4. Record approved deviations in both the design and this plan.

### Gate: CPI-G0

```bash
just check-matrix
```

Pass conditions: corpus links are bidirectional, every new implementation task
has a preceding TS task, G-CPI is `tdd`, and owner decisions are no longer open.

## Task 1 — Build privacy-safe transcript-family fixtures

### Task 1A — RED fixtures and extractor tests

**Tests:**

- Add `tests/unit/test_claude_parent_inference.py`
- Add fixture builders to `tests/conftest.py` or a focused helper under
  `tests/fixtures/`
- Implement T-CPI-01..05 as failing tests

Create synthetic structural families:

```text
single unrelated sessions
A -> B
A -> B -> C
A -> B and A -> C siblings
same boundary with different creation order
fork after parent-specific history
system-only overlap
conflicting UUID edge
retry/alternate branch
sidechain
attachment and metadata interleaving
cycle, orphan edge, duplicate UUID
truncated and malformed JSONL
exact manual copy without divergence
```

Use content canaries in message bodies and assert they never appear in returned
models, serialized cache data, notices, or failure representations.

RED proof:

```bash
pytest -q tests/unit/test_claude_parent_inference.py
```

Expected: collection succeeds; tests fail because no extractor/graph engine
exists, not because fixtures are malformed.

### Task 1B — Implement structural extraction and graph normalization

**Production:**

- Add `src/agent_fork/claude_lineage_inference.py`

Implement frozen models for safe transcript metadata, structural records,
graph paths, shared boundaries, direction evidence, candidate results, and the
final inference result. Parse only whitelisted keys:

```text
sessionId, uuid, parentUuid, type, subtype, timestamp, isSidechain
```

Validate bounded UUID-like identifiers. Build graph edges independently of
JSONL order. Detect cycles, duplicate/conflicting nodes, missing edges, and
multiple plausible terminal paths deterministically. Compare bounded plausible
non-sidechain paths ending in user/assistant lineage; never choose the last
JSONL line as a proxy for the main chain.

GREEN proof:

```bash
pytest -q tests/unit/test_claude_parent_inference.py \
  -k 'extract or graph or boundary or privacy'
```

Pass conditions: T-CPI-01..05 green; canary scan proves content exclusion.

### Gate: CPI-G1

The structural fixture corpus is deterministic, every extractor/graph test was
observed red before implementation, T-CPI-01..05 are green, and no content
canary crosses the structural-model boundary.

## Task 2 — Implement bounded discovery and incremental index

### Task 2A — RED index, path, and bound tests

**Tests:**

- Add `tests/unit/test_claude_lineage_index.py`
- Add T-CPI-12..13 and T-CPI-27..31

Cover:

- `CLAUDE_CONFIG_DIR` and default root;
- only resolved `projects/*/*.jsonl` regular files;
- symlink files/directories and root escape;
- invalid filenames and internal session mismatch;
- file replacement/truncation during read;
- file, byte, record, candidate, and duration caps;
- deterministic ordering;
- first scan, unchanged reuse, changed-file refresh, deletion, corrupt cache,
  stale algorithm version, and interrupted cache write;
- UUID-to-session inverted lookup;
- content canaries absent from cache bytes.
- cold sparse corpus scans changed files superficially but deeply parses only
  the target and screen-positive candidates;
- warm sparse corpus does not read unchanged unrelated transcript bytes;
- one changed unrelated file refreshes only its screening shard;
- legal whitespace/key formatting and chunk splits cannot cause a screening
  false negative;
- injected screening false positives add deep work but never a relationship;
- huge unrelated and huge matching files keep buffers and memory bounded;
- `--all` refreshes once and compares overlap components without quadratic
  candidate-pair growth.

### Task 2B — Implement index

**Production:**

- Add `src/agent_fork/claude_lineage_index.py`

Implement this staged pipeline:

```text
manifest/stat
  -> superficial streaming UUID screen
      -> exact candidate JSON/graph parse
          -> relationship analysis
```

Implement:

```text
$XDG_CACHE_HOME/agent-fork/claude-lineage-index-v2/
```

Use a small manifest plus per-transcript atomic shards rather than a monolithic
corpus JSON file. Use canonical containment checks, no-follow/identity revalidation where
available, bounded streaming reads, deterministic cache documents, atomic
replacement, and the existing lock style. Fingerprint with canonical path,
size, `mtime_ns`, optional birth time, and algorithm version. Treat every cache
hit as an optimization; unsafe or contradictory metadata forces a safe reparse
or refusal.

The superficial scanner extracts top-level UUID candidates into a compact Bloom
filter or sorted keyed-digest shard without full JSON decoding. False positives
are acceptable; false negatives relative to the deep parser are forbidden.
Build candidate postings once per refreshed corpus:

```text
substantive message UUID -> sorted session IDs
```

Do not perform all-pairs transcript comparison. Parse the target deeply once;
deeply parse other files only after a positive screen. Load bounded history and
live-registration timestamp maps once and only after structural candidates
exist.

Instrument logical work counters for tests:

```text
enumerated files, superficial bytes, deep files/bytes, decoded records,
candidate comparisons, graph visits, cache hits/misses, peak buffer
```

Verification:

```bash
pytest -q tests/unit/test_claude_lineage_index.py
```

Pass conditions: T-CPI-12..13 and T-CPI-27..31 green, bounded failure leaves no
temporary files, cache snapshots contain no content canaries, and a sparse
N-file fixture proves deep parse count is O(matches), not O(N).

### Gate: CPI-G2

Safe discovery and incremental screening/indexing pass all path, race,
corruption, and resource-bound fixtures. Cold work is linear in changed bytes;
warm unrelated bytes are not rescanned; deep work is proportional to
screen-positive candidates; no all-pairs comparison or content persistence
exists.

## Task 3 — Implement inference, direction, and ambiguity policy

### Task 3A — RED policy tests

**Tests:** extend `tests/unit/test_claude_parent_inference.py`

Add T-CPI-06..10 covering:

- two agreeing clocks and no conflict -> `strongly_inferred`;
- one clock -> `inferred` but not recordable under the initial threshold;
- conflicting clocks -> `conflicting_evidence`;
- mtime and bridge IDs ignored;
- process `startedAt` treated as ephemeral;
- parent-specific inherited history selects the closer generation;
- same-boundary siblings remain ambiguous despite age ordering;
- exact duplicate without divergence does not prove immediate parent;
- deterministic candidate ordering;
- stronger planned claim supersedes inference.

### Task 3B — Implement candidate engine

**Production:** extend `src/agent_fork/claude_lineage_inference.py`

Implement this policy in order:

1. Use the inverted index to obtain related candidates.
2. Establish shared structural ancestry before reading clocks.
3. Find the strongest shared graph path and boundary.
4. Prefer candidates whose target contains candidate-specific ancestry beyond
   older common roots.
5. Evaluate transcript birth, first history event, live process start,
   materialization gap, and non-copied record time as separately sourced facts.
6. Require the approved recording threshold.
7. Return ambiguity for equal-boundary sibling/ancestor candidates.

Create explicit result constructors for `strongly_inferred`, `inferred`,
`ambiguous`, `conflicting_evidence`, `insufficient_evidence`, and `unavailable`.
Do not scatter status strings through CLI code.

Verification:

```bash
pytest -q tests/unit/test_claude_parent_inference.py
```

Pass conditions: T-CPI-01..10 green and no timestamp-only selection path exists.

### Gate: CPI-G3

Parent/child, sibling, multi-generation, resume, restore, and exact-copy
fixtures produce the locked statuses deterministically. Same-boundary siblings
remain ambiguous under every creation-time ordering.

## Task 4 — Implement separate inference persistence

### Task 4A — RED store and race tests

**Tests:**

- Add `tests/unit/test_lineage_inference_store.py`
- Add functional race cases under `tests/pipeline/` if subprocess concurrency is
  required
- Implement T-CPI-11 and T-CPI-14

Test version validation, deterministic ordering, exact child replacement,
atomicity, lock contention/death, corrupt/truncated/oversized state, symlink
escape, temporary cleanup, concurrent planned-claim appearance, analyzed-file
change, and injected replacement/fsync failures.

### Task 4B — Implement store

**Production:**

- Add `src/agent_fork/lineage_inference_store.py`
- Reuse narrowly factored atomic-store helpers only if doing so leaves existing
  registry and lineage behavior unchanged

Implement:

```text
$XDG_STATE_HOME/agent-fork/session-lineage-inferences.json
```

Persist structural evidence, fingerprints, algorithm version, and analyzed
time—never content. Key replacement by `(agent, child_session_id)`. Before
write, revalidate source fingerprints and recheck the planned lineage store.
Acquire multiple locks in one documented global order to avoid deadlock.

Provide pure operations:

```text
read_inferences
find_inference
add_or_replace_inference
remove_inference
classify_staleness
```

Verification:

```bash
pytest -q tests/unit/test_lineage_inference_store.py tests/pipeline/test_reg.py
```

Pass conditions: T-CPI-11/14 green; existing T-SES-05/06/15/16 remain green;
planned store bytes and schema are unchanged.

### Gate: CPI-G4

Inference persistence is atomic, source-separated, race-safe, and content-free;
source changes or a concurrent stronger claim prevent recording without
damaging either store.

## Task 5 — Integrate recorded evidence into ordinary inspection

### Task 5A — RED fast-path and validation tests

**Tests:** extend `tests/unit/test_session.py` and `tests/cli/test_session.py`

Add T-CPI-18 and T-CPI-21:

- planned claim wins over inferred record;
- current inferred record appears with
  `id_source=agent-fork-lineage-inference`, `id_status=inferred`;
- stale inference is visibly stale and never refreshed;
- no claim/inference remains `not_found`;
- plain inspection works when inference/index modules are instrumented to fail
  if imported or called;
- approved `validate --has-parent` semantics;
- exact `--parent-session-id` comparison preserves evidence status.

### Task 5B — Implement fast integration

**Production:** modify `src/agent_fork/session.py`

Read only the small inference store after planned-claim lookup misses. Do not
import the discovery/index engine. Extend immutable evidence models additively
for staleness/source status without changing existing Codex and planned-Claude
documents.

Verification:

```bash
pytest -q tests/unit/test_session.py tests/cli/test_session.py
```

Pass conditions: T-CPI-18/21 and all G-SES rows green.

## Task 6 — Add CLI grammar, service orchestration, and output

### Task 6A — RED black-box command tests

**Tests:**

- Add `tests/cli/test_claude_parent.py`
- Extend `tests/cli/test_out.py`
- Implement T-CPI-15..19 and T-CPI-22

Test installed-console behavior for:

- full nested help and bare namespace behavior;
- exactly-one target selector;
- record/record-all conflicts;
- `--current` Claude-only detection;
- exact historical target;
- `--all` deterministic result arrays and summary counts;
- preview leaves stores byte-identical;
- recordability refusal;
- JSON/text/table schemas and streams;
- `--json` byte identity;
- list source filters;
- show zero/one/multiple-source behavior;
- partial bulk success and approved exit policy;
- no Git requirement and no agent/network mutation.

### Task 6B — Implement orchestration and renderers

**Production:**

- Modify `src/agent_fork/cli.py`
- Modify `src/agent_fork/output.py` or add a focused renderer module
- Modify `src/agent_fork/errors.py`

Keep parser validation separate from service policy. Add a service boundary
that resolves targets, refreshes the index once per invocation, evaluates each
target deterministically, and records only approved results. Reuse one immutable
result document for human and JSON output.

Add stable catalog errors for inference unavailable, not recordable, ambiguous
record source, and missing record only where existing codes are not accurate.
Keep diagnostics bounded.

Verification:

```bash
pytest -q tests/cli/test_claude_parent.py tests/cli/test_out.py
```

Pass conditions: T-CPI-15..19/22 green.

## Task 7 — Implement safe deletion and completions

### Task 7A — RED destructive-scope tests

**Tests:** extend `tests/cli/test_claude_parent.py` and completion tests

Add T-CPI-20 and the completion portion of T-CPI-15:

- no `--yes` in noninteractive mode refuses safely;
- prompt defaults no;
- exact consent deletes only selected store record;
- multiple sources require `--source`;
- planned deletion warning differs from inferred deletion;
- missing child/source is no-op failure;
- transcript, history, live registration, branch, worktree, registry, and other
  lineage records are byte-identical;
- Bash, Zsh, and Fish expose nested actions/options contextually.

### Task 7B — Implement deletion and completion grammar

**Production:**

- Modify `src/agent_fork/cli.py`
- Modify `src/agent_fork/completion.py`
- Extend store APIs only as required

Resolve records by decoded store key, never user-provided filesystem paths.
Use existing consent conventions and terminal escaping. Planned deletion calls
the existing planned-store removal; inferred deletion calls only its own store.
No cascade behavior.

Verification:

```bash
pytest -q tests/cli/test_claude_parent.py tests/conformance/test_process_contract.py
```

Pass conditions: T-CPI-15/20 green and all current completion/conformance tests
remain green.

### Gate: CPI-G5

The installed command family, output contracts, source-aware record management,
consent behavior, and completions pass. Preview is read-only, plain inspection
never scans, and delete reaches only the selected Agent Fork metadata record.

## Task 8 — Harden process, limits, documentation, and packaging

### Task 8A — RED adversarial process tests

**Tests:**

- Extend `tests/conformance/test_process_contract.py`
- Extend `tests/cli/test_claude_parent.py`
- Implement T-CPI-23

Cover terminal controls in stored IDs/notices, hostile locale, closed stdout and
stderr, SIGPIPE, SIGINT/SIGTERM during scan and before write, cancellation,
read-only/unwritable cache/state directories, cache corruption, and cleanup of
temporary files/locks.

### Task 8B — Documentation and final hermetic implementation

**Production/docs:**

- Modify `README.md`
- Modify `EXPERIMENTS.md` after real tests only
- Modify `docs/testing/TEST-MATRIX.md` statuses as gates pass
- Modify `REQUIREMENTS.md` traceability if implementation reveals an approved
  clarification
- Modify `src/agent_fork/completion.py`, output, or error handling as tests demand

Document the command family, costs, cache/store paths, evidence vocabulary,
algorithm, observed experiment, privacy boundary, ambiguity cases, staleness,
refresh, and deletion scope. State explicitly that this is not an Anthropic
lineage API.

Run CPI-G6:

```bash
just all
just check-matrix
just strict-collect
just clean-install
just test-git-matrix
just test-signals
```

Pass conditions: all green, no unexpected skips, clean wheel behavior, no
fixture residue, and G-CPI may advance from `tdd` to `live` only after all
non-real rows pass.

### Gate: CPI-G6

Every hermetic repository, matrix, collection, clean-install, Git-topology, and
signal gate is green with no unexpected skip or fixture/cache/state residue.

## Task 9 — Real Claude cross-validation

### Task 9A — RED/live acceptance definitions

**Tests:** extend `tests/live/test_exp.py` with T-CPI-24..26 and T-CPI-32 behind
`requires_real_cli`.

Define sanitized assertions before running:

1. Known parent/child: exact shared boundary and correct direction.
2. Siblings at the same boundary: related but immediate parent ambiguous.
3. Multi-generation: select the middle parent only when child inherited a
   middle-parent-specific record.
4. Preview does not write; record appears in ordinary session; refresh is
   deterministic; delete removes metadata only.
5. A sanitized real-corpus run records cold, warm, and one-file incremental
   counters plus elapsed diagnostics; warm lookup does not rescan unchanged
   unrelated transcript bytes.

### Task 9B — Execute and record

Use disposable Claude sessions where possible; never edit the user's existing
transcripts. The existing known pair may be read as corroboration but should
not be mutated or deleted. Record CLI versions, sanitized IDs, structural
counts, clock availability/deltas, classification, runtime, bytes scanned, and
outcomes in `EXPERIMENTS.md`.

Run:

```bash
just test-live
```

Pass conditions: T-CPI-24..26 and T-CPI-32 green or an owner-reviewed version-specific
limitation is recorded; no prompt/response content enters repository files.
Then move G-CPI to `done` only if every canonical row passes.

### Gate: CPI-G7

Real Claude parent/child, sibling, and multi-generation results agree with the
known construction history; sanitized evidence is recorded; metadata refresh
and delete preserve all Claude-owned files.

## Task 10 — Reviews and owner gate

### Correctness review

Review:

- graph-path semantics and boundary selection;
- evidence precedence and validation behavior;
- deterministic output and exit contracts;
- cache invalidation and source revalidation;
- atomicity, lock order, and partial bulk behavior;
- compatibility with all G-SES and planned lineage behavior.

### Adversarial review

Repeat the design's A1–A15 attacks against actual code and add:

- hash/UUID amplification and candidate fan-out;
- crafted cyclic graphs and exponential path enumeration;
- filesystem replacement between stat/open/read/write;
- concurrent infer/record/delete and planned-claim creation;
- malicious state/cache JSON and terminal content;
- disk-full and interrupted atomic writes;
- source deletion/restoration during bulk analysis;
- evidence downgrade/overwrite attempts;
- proof that ordinary session imports no heavy inference path;
- proof that deletion reaches no Claude/Git path.

### Final verification

```bash
git diff --check
just all
just check-matrix
just strict-collect
just clean-install
just test-git-matrix
just test-signals
just test-live
git status --short
```

### Gate: CPI-G8

No unresolved high or medium correctness/adversarial finding, all approved
matrix rows green, documentation and experiment record complete, and worktree
contains only intended changes. Stop for owner review. Do not open a PR or
merge until explicitly requested after this gate.

## Dependency map

```text
Task 0 contract/tracking
  -> Task 1 extractor/graph
      -> Task 2 index
          -> Task 3 inference policy
              -> Task 4 persistence
                  -> Task 5 fast inspection integration
                      -> Task 6 CLI/output
                          -> Task 7 delete/completions
                              -> Task 8 hardening/docs
                                  -> Task 9 real Claude
                                      -> Task 10 reviews/owner gate
```

Tasks are intentionally sequential because each later boundary depends on the
evidence semantics and safety invariants established earlier. Parallelize only
independent test-fixture or documentation work after its governing contract is
locked; do not parallelize shared production-file edits.

## Definition of done

- The complete `session claude-parent` command family is installed and
  documented.
- Expensive inference always requires `--current`, `--session-id`, or `--all`.
- Plain session inspection performs no discovery or index work.
- Planned and inferred evidence remain distinguishable and precedence-safe.
- Sibling and multi-generation ambiguity is never hidden by timestamps.
- Cache/state contain structural metadata only and all reads/writes are bounded.
- Preview is read-only; recording and deletion are explicit and safe.
- All canonical G-CPI (T-CPI-01..09), G-SES, repository, clean-install, signal, and real-Claude gates are
  green.
- Correctness and adversarial reviews have no unresolved high/medium findings.
- Owner approves CPI-G8 before any PR or merge.
