# P02-A10 — Claude inferred-parent freshness, cache growth, and corpus limits

This document defines and tracks `P02-T10`, the remediation for fault A10 in
the P02 fault-remediation project. The intended reader is the engineer
implementing or reviewing A10. The required action is to make recorded Claude
parent inference degrade into typed, disclosed states instead of silently
vanishing or silently reviving, to bound the transcript screen cache, and to
convert two hard failures into structured refusals — without changing the
default cleanup retention policy, the strict parent-validation contract, or any
existing v1 machine-field semantics.

The CLI interface review in this document uses CLI Design Standard 1.4.14 at
the existing publishable tier (confirm the current standard version in
`CONFORMANCE.md` before the gate-4 review). A10 affects scripted machine
output, one new stable error code, one additive session object, additive
`work` counters, additive delete-result fields, cleanup disclosure text, and
one internal storage-path relocation (freshness index moves from
`XDG_CACHE_HOME` to `XDG_STATE_HOME`, migrated lazily, no CLI surface change).
It adds no new command or flag — the owner decided against an opt-in cleanup
pruning flag; see "Owner decisions" below. It does not add configuration,
network access, streaming, plugins, or interactive behavior.

| P02 gate | State |
|---|---|
| 1. Adversarial verification, including Codex | **CONFIRMED-WITH-CORRECTIONS** on 2026-08-18; recap below |
| 2. Owner scope decision | **approved**; six subproblem decisions recorded below, plus two follow-up decisions on 2026-08-20 |
| 3. Design document | **complete**; revalidated against `origin/main` on 2026-08-20 |
| 4. Implementation plan and adversarial review, including Codex | pending |
| 5. Test-driven implementation | pending |
| 6. Adversarial implementation review, including Codex | pending |

## Revalidation against main (2026-08-20)

Two days of unrelated work landed on `origin/main` between this document's
first draft and implementation start: PR #53 ("refactor/src-duplication",
merged as `46201c1`) plus the P05 session-transcript-path item and further A13
remediation. This worktree branch was rebased onto that commit and every claim
below was re-checked against the current source, not re-derived from memory.

**Conclusion: no design decision in this document changed.** All six defect
sites (below) are present with byte-identical defect logic; only line numbers
shifted and two files gained new shared helpers this design should now use.
Concretely:

- `src/agent_fork/xdg.py` (`xdg_path()`) and `src/agent_fork/storage.py`
  (`atomic_write_json()`) are new, extracted from what were previously five
  duplicated hand-rolled XDG-path and temp-file-plus-`os.replace` blocks
  across `lineage.py`, `lineage_inference_store.py`, and
  `claude_lineage_inference.py`. New code in this design (`remove_index_freshness`,
  the relocation in section 2a) must call these helpers rather than
  hand-rolling atomic writes, matching the rest of the codebase.
- `session.py` gained an unrelated `SessionTranscript` object and a new
  required `transcript` field on `SessionInspection` (the P05 item). This
  design's additive `parent_inference` field is unaffected but must be added
  alongside `transcript`, not in place of it — every `SessionInspection(...)`
  construction site already sets `transcript=`, and the new field joins it at
  each of those sites.
- `validate_session()` gained an unrelated Codex-only check
  (`if inspection.lineage_status == "unavailable": raise ...`). It does not
  intersect the Claude path this design touches: a stale, unknown, or
  superseded Claude inference still resolves `lineage_status` to `"not_found"`,
  not `"unavailable"`, so "`validate_session()` is unchanged" (section 3) still
  holds.
- `cleanup.py` gained unrelated remote-less push guidance and switched its
  worktree-list parsing to a shared `list_worktrees()` helper (A13
  remediation). Neither touches the notice-generation function this design
  extends.
- Sixteen of this design's originally-numbered test IDs were claimed by that
  same landed work before this revalidation. The test table below has been
  renumbered to the next free IDs as of this revalidation; **re-check
  `docs/testing/TEST-MATRIX.md` again immediately before implementation**, per
  the note there.
- `CONFORMANCE.md` currently records an unrelated, unresolved violation: A13(B)
  removed the `table` output format, which the CLI Design Standard v1.4.14
  requires as the human default; two waiver rows there ("Amend the governing
  standard or restore a real `table` default before release") are open. This
  design was never written in terms of `table` — it only ever distinguished
  machine (`json`) from human (`text`) output — so it does not compound that
  violation, but a gate-4 reviewer will see it in the same file and should not
  mistake it for an A10 finding.
- The project register (`projects/P02-agent-fork-fault-remediation.md`) on
  `origin/main` still shows `P02-TS10`/`P02-T10` unchecked and still carries
  the pre-verification "stores never shrink" phrasing this document's gate-1
  recap already refutes. A local, uncommitted edit recording the correct
  verdict existed in the main checkout as of 2026-08-18 (see the prior
  handoff) but has still not landed on `origin/main` as of this revalidation
  — reconcile that separately; this design doc does not depend on it.

## Outcome required

Six behaviors, one per approved owner decision. They are the acceptance
contract for `P02-T10`.

1. **A transcript append must not erase the recorded inference.** The
   previously inferred parent stays visible under a typed `last_known_good`
   status with a notice that messages added after the analysis were not
   examined. It must not satisfy strict parent validation until an explicit
   re-inference re-establishes freshness. The underlying behavior changes, not
   only the message: the record is retained, classified, and surfaced.
2. **A missing or unreadable freshness index must not revive rejected
   evidence.** Absent corroboration reports `freshness_unknown`, is excluded
   from strict parent validation, and tells the user to rerun inference.
3. **Screen-cache shards must not accumulate.** One shard per transcript,
   superseded shards removed, plus bounded age and size limits. Internal fix;
   no new interface.
4. **Ordinary `cleanup` keeps lineage metadata.** The default does not change,
   because it preserves resumability. Disclosure improves: cleanup names
   exactly which records survive, where they live, and the exact command that
   removes them. An explicit opt-in pruning flag is specified but not
   mandated.
5. **`session claude-parent delete` must not leave freshness data behind.** It
   removes the matching freshness entry and reports exactly which record and
   which freshness entry were removed and which shared cache remains.
6. **Corpus limits must return a structured incomplete-analysis result.**
   Exceeding the file, entry, byte, candidate, or time limit produces a typed
   exit-3 refusal naming the exceeded limit, its allowed and observed values,
   and remediation. Recording is refused because incomplete evidence is
   unsafe. No unlimited index is built.

## Gate-1 verification recap

The `P02-TS10` probe returned **CONFIRMED-WITH-CORRECTIONS**:

- Appending a single blank byte-line containing zero semantic JSONL records
  invalidated the recorded inference. Each append followed by re-inference grew
  the screen cache from one shard to two, three, then four shards for the same
  transcript.
- Cleanup left the associated lineage, inference, freshness, and shard files
  byte-identical.
- The register's phrase "stores never shrink" was **refuted literally**:
  explicit planned and inferred deletes do shrink the state stores. The
  surviving defect is narrower — deletes are incomplete (freshness survives)
  and cleanup discloses nothing.
- Deleting only the freshness index made a previously **rejected** ambiguous
  inference report as current again.
- Production `--current` hard-failed at 10,001 transcripts and above a 2 GiB
  logical corpus size.

Two corrections follow into this design. First, the remedy is not "make stores
shrink" but "make deletes complete and retention disclosed." Second, the
staleness treadmill is not a messaging defect: the record was discarded
entirely, so no amount of notice rewriting fixes it.

## Defect sites

Line numbers below are current as of the 2026-08-20 revalidation
(`origin/main` `46201c1`); re-confirm before implementation since the trunk
moves quickly.

| Subproblem | Site | Defect |
|---|---|---|
| 1 | `src/agent_fork/session.py:409-433` | When freshness is not `current_at_last_analysis`, the code appends a generic notice and sets `inference = None`, discarding the record instead of surfacing it. |
| 2 | `src/agent_fork/lineage_inference_store.py:149-190` | The `if path.is_file() and ...` guard skips the candidate-universe check when the freshness index is absent, then falls through to `return "current_at_last_analysis"`. A present index that has no entry for the child falls through the same way. Missing evidence is treated as proof of freshness. |
| 3 | `src/agent_fork/claude_lineage_inference.py:368` | `shard = root / f"{path.stem}-{fp}.json"` mints a new file name for every distinct size/mtime; nothing removes prior shards for the same stem, and nothing bounds shard age, count, or total bytes. |
| 4 | `src/agent_fork/cleanup.py:385-390` (the `_validate`/notices assembly, unchanged in this revalidation) | The only notice is generic; the module contains zero references to the lineage, inference, freshness, or cache paths. |
| 5 | `src/agent_fork/lineage_inference_store.py:223-233` (`remove_inference`), `src/agent_fork/cli.py:777-827` (the `delete` action) | `remove_inference` never touches `index_freshness_path()`'s `targets[child_session_id]`; the CLI reports only `deleted`, `session_id`, `source`. |
| 6 | `src/agent_fork/claude_lineage_inference.py:208-266` (`discover`), `src/agent_fork/cli.py:859` | `discover` raises bare `ValueError` for three limits; `corpus = ClaudeLineageCorpus(environment)` is unguarded, so the error escapes as an uncaught exception rather than a typed result. |

## Proposed design

### 1. One freshness assessment in the store

Replace the string-returning freshness check with a single immutable
assessment. Everything that asks "may I use this record?" consults exactly one
definition.

Add to `src/agent_fork/lineage_inference_store.py`:

```python
FreshnessStatus = Literal[
    "current_at_last_analysis",
    "stale_sources",
    "stale_candidate_universe",
    "stale_algorithm",
    "freshness_unknown",
]
EvidenceStatus = Literal["current", "last_known_good", "unknown", "superseded"]
ChangedSource = Literal["target", "parent", "other"]

@dataclass(frozen=True)
class InferenceAssessment:
    status: FreshnessStatus
    evidence: EvidenceStatus
    changed_sources: tuple[ChangedSource, ...] = ()

    @property
    def satisfies_strict_parent(self) -> bool:
        return self.evidence == "current"

    @property
    def displayable(self) -> bool:
        return self.evidence != "superseded"

    def notice(self) -> str: ...
    def document(self) -> dict[str, object]: ...

def assess_inference(
    record: InferenceRecord, *, env: Mapping[str, str] | None = None
) -> InferenceAssessment: ...
```

`inference_freshness()` becomes `assess_inference(...).status` and keeps its
signature and its five return values, so `T-CPI-28` and any other existing
caller stay green. `inference_is_current()` becomes
`assess_inference(...).satisfies_strict_parent`; it has no production callers
today, and re-expressing it prevents a second, divergent definition of
"usable."

Status-to-behavior mapping — this table is the contract:

| `status` | `evidence` | Strict parent evidence | Displayed | Meaning surfaced to the user |
|---|---|---|---|---|
| `current_at_last_analysis` | `current` | yes | yes | current as of the last explicit analysis |
| `stale_sources` | `last_known_good` | **no** | yes | one or more analyzed transcripts changed after the analysis; any newer messages were not examined |
| `stale_candidate_universe` | `last_known_good` | **no** | yes | the set of transcripts relevant to this session changed after the analysis |
| `freshness_unknown` | `unknown` | **no** | yes | the corroborating freshness entry is missing or unreadable, so this record cannot be confirmed or rejected |
| `stale_algorithm` | `superseded` | **no** | **no** | the record predates the current algorithm and is not interpretable |

`stale_algorithm` is the only status that suppresses display, because a record
written by a different algorithm version carries fields whose meaning is not
guaranteed. Every other status keeps the parent visible and out of strict
validation, which is precisely owner decisions 1 and 2.

### 2. Evaluation order (subproblem 2's fix)

`assess_inference` evaluates in this fixed order and returns at the first
match. State the order in the docstring; the implementer must not reorder it.

1. `algorithm_version != 1` or empty `source_fingerprints` → `stale_algorithm`.
2. Empty `analysis_index_generation` or empty `candidate_universe_digest` →
   `freshness_unknown` (unchanged from today).
3. Per-file fingerprint check over `source_fingerprints`. Any symlink, `OSError`,
   malformed entry, or digest mismatch → `stale_sources`, with
   `changed_sources` populated (below).
4. Freshness-index check. This step is now **mandatory** rather than
   conditional:
   - the index file is absent → `freshness_unknown`;
   - the index is a symlink, oversized, unreadable, not JSON, not
     `version == 1`, or lacks a dict `targets` → `freshness_unknown`;
   - `targets` has no entry for `record.child_session_id`, or the entry is not
     a dict, or it lacks `candidate_universe_digest` → `freshness_unknown`;
   - the entry's `candidate_universe_digest` differs from the record's →
     `stale_candidate_universe`;
   - otherwise fall through.
5. `current_at_last_analysis`.

Two deliberate non-changes inside step 4. The stored
`analysis_index_generation` is **not** compared, because it is a corpus-wide
hash: comparing it would mark every record stale on any unrelated corpus
change, recreating the treadmill at global scope. And a record whose sources
changed *and* whose index entry is missing resolves to `stale_sources`, not
`freshness_unknown`, because the stronger, locally provable fact wins.

### 2a. Freshness-index relocation to `XDG_STATE_HOME` (owner decision, 2026-08-20)

The owner decided to relocate the freshness index rather than defer: it moves
from `$XDG_CACHE_HOME/agent-fork/claude-lineage-freshness.json` to
`$XDG_STATE_HOME/agent-fork/claude-lineage-freshness.json`, alongside
`inference_path()`'s existing state-store location. This removes the
cache-eviction downgrade class entirely — the freshness index can no longer be
wiped by an ordinary cache-cleaning tool independently of the records it
corroborates.

Migration is lazy and per-entry, not a bulk job, following the module's
existing small-safe-change posture:

- `index_freshness_path(env)` calls the shared `agent_fork.xdg.xdg_path()`
  helper with `"XDG_STATE_HOME"` / `".local/state"` instead of
  `"XDG_CACHE_HOME"` / `".cache"` — the same helper `inference_path()` and
  `lineage_path()` already use, so this is a one-line change to an existing
  call, not new path-resolution code. Add
  `_legacy_index_freshness_path(env)` calling the same helper with the old
  `"XDG_CACHE_HOME"` / `".cache"` arguments, kept only for backward-compatible
  reads.
- **Read** (`assess_inference` step 4): check the new state path first using
  the existing validation rules; if it is absent, fall back to reading the
  legacy cache path with the same rules. A legacy-only entry is treated as an
  ordinary hit, not `freshness_unknown` — the file moved, the evidence did
  not. `assess_inference` still performs no writes, so this fallback costs at
  most one extra stat/read and preserves the read-only cost guarantee in
  section 3.
- **Write** (`update_index_freshness`, called only from `infer_one`, never
  from `session`): always writes to the new state path. After a successful
  write, best-effort-delete the legacy cache file for that session if it still
  exists (swallow `OSError`) — this is what completes the migration, one
  session at a time, as each gets re-inferred.
- **Delete** (`remove_index_freshness`, subproblem 5): must remove the entry
  from wherever it currently lives, so it checks the new state path first and,
  if the entry is not there, the legacy cache path — removing from whichever
  is found. This preserves the "no freshness data left behind" guarantee even
  for a session whose entry has not yet been migrated by a write.
- If, unexpectedly, both locations hold an entry for the same
  `child_session_id`, the state-path entry wins (it is by construction the
  more recent write).
- No forced bulk migration and no startup scan: an entry that is never
  re-inferred or deleted simply stays served from the legacy path indefinitely,
  which is correct — it is still valid corroborating evidence at its old
  location.

`changed_sources` classification, for `stale_sources` only: for each mismatching
fingerprint entry, take the path stem; `== record.child_session_id` →
`"target"`, `== record.parent_session_id` → `"parent"`, otherwise `"other"`.
Emit the sorted unique set. This is the difference between "your own live
session appended a message" (the common treadmill case) and "the evidence for
the recorded parent changed," and it costs nothing beyond string comparison.
Only these three category labels are reported — never candidate session IDs or
paths — so no new identifier is disclosed.

Bounded read cost: `assess_inference` performs one `lstat`/`stat` per recorded
fingerprint plus one small JSON read. The recorder caps fingerprints at
`max_candidates + 1`, but a hand-edited store must not be able to make
`session` do unbounded I/O, so add `MAX_SOURCE_FINGERPRINTS = 1_024` to
`_decode`: a record exceeding it is rejected as an invalid store, consistent
with the module's existing `MAX_STORE_BYTES` posture.

Freshness-index write failure. `ClaudeLineageCorpus.infer_one().finish()`
already swallows `update_index_freshness` failures into
`work.cache_write_failures`. Split that into a distinct
`work.freshness_write_failures` counter, and when it is non-zero on a `--record`
run, emit a notice in the analysis document: the record was written but will
report `freshness_unknown` until the freshness index becomes writable. Do not
refuse the record — see rejected alternatives.

### 3. Session inspection surfaces `last_known_good` (subproblem 1's fix)

`inspect_session()` stops discarding the record. It keeps the existing
`parent_session` and `lineage.status` semantics exactly as they are today —
they remain **strict** fields — and reports the retained record through one new
additive top-level object, following the `agent_signal` precedent set by A9.

Behavior in `session.py:358-381` becomes:

```python
assessment = assess_inference(inference, env=env)
if assessment.satisfies_strict_parent:
    # unchanged: parent_session is populated, lineage.status = inference.status
elif assessment.displayable:
    inference_view = ...   # retained for the additive object
    inference = None       # still not strict parent evidence
    notices.append(assessment.notice())
else:
    inference = None
    notices.append(assessment.notice())
```

`SessionInspection` gains one field, `parent_inference`, and `document()` gains
one always-present key. Always-present with a status is easier to test and
document than a sometimes-null object, and it matches `agent_signal`:

```json
{
  "parent_inference": {
    "status": "last_known_good",
    "freshness": "stale_sources",
    "parent_session_id": "…",
    "analyzed_at": "2026-08-17T20:11:04Z",
    "changed_sources": ["target"]
  }
}
```

`status` value set, all new, so no v1 value set is expanded:

| `status` | When |
|---|---|
| `not_consulted` | no Claude session detected, agent is Codex, or an authoritative planned claim exists |
| `absent` | consulted and no inferred record exists for this session |
| `current` | a record exists and satisfies strict parent evidence |
| `last_known_good` | `stale_sources` or `stale_candidate_universe` |
| `freshness_unknown` | corroboration missing or unreadable |
| `superseded` | `stale_algorithm` |
| `unreadable` | the inference store raised `ValueError` |

`freshness`, `parent_session_id`, `analyzed_at`, and `changed_sources` are null
or empty for `not_consulted`, `absent`, and `unreadable`. Only `status:
"current"` is strict parent evidence; there is deliberately no redundant
boolean that could drift from that rule.

Notices, one per non-current status, each naming the remediation command
`agent-fork session claude-parent infer --current --record` (or
`--session-id UUID --record` when the target is not the current session). The
`stale_sources` notice varies by `changed_sources`: target-only says the
session's own transcript grew and newer messages were not analyzed;
parent or other says analyzed evidence transcripts changed. Every notice
states that the parent is shown as last known good and does not satisfy
`session validate --has-parent`.

Human output, `cli.py:1029-1075`: after the `lineage:` line, print one line
when `status` is not `not_consulted` or `absent`:

```text
parent inference: last_known_good 6b0a…  (analyzed 2026-08-17T20:11:04Z; target transcript changed)
```

`validate_session()` is **unchanged**. Because `parent_session` stays null for
every non-current status, `--has-parent`, `--parent-session-id`, and the
`has_parent` assertion behave exactly as they do today. That is the mechanical
guarantee behind "must NOT satisfy strict parent validation."

Cost guarantee: `session` still performs no corpus discovery, no screening, no
deep parse, and no cache or freshness write. It reads two small JSON stores and
stats the recorded fingerprint paths.

### 4. Bounded screen cache (subproblem 3's fix)

Two changes in `src/agent_fork/claude_lineage_inference.py`.

**Flat, self-superseding shard names.** Move the cache root to
`~/.cache/agent-fork/claude-lineage-index-v3/` and name each shard
`{path.stem}.json` — one file per transcript, forever. The fingerprint stays
inside the payload at `source.fingerprint`, and the existing validation already
rejects a shard whose `source.fingerprint != fp`, so a superseded shard is a
cache miss that the next `os.replace` overwrites in place. Accumulation becomes
structurally impossible rather than something a collector must chase.

**Bounded, marker-gated sweep.** Add `sweep_cache(env, stems, work)` called
once per `ClaudeLineageCorpus.__init__`, after `discover()` and before any
screening, and never from `session`. It runs only when `root/.sweep` is missing
or older than `CACHE_SWEEP_INTERVAL = 86_400` seconds, then touches the marker.
Within the resolved v3 root only, never recursing and never following symlinks,
and only after the existing `cache_safe` ownership and symlink checks pass, it:

1. removes the entire legacy `claude-lineage-index-v2/` tree once (regular
   files then `rmdir`) — flat naming makes every legacy shard unreadable
   anyway, so migrating them buys no cache reuse;
2. removes entries not matching `^<uuid>\.json$`, and `.tmp` leftovers older
   than one hour;
3. removes shards whose stem is not in the discovered corpus (orphans from
   deleted transcripts);
4. removes shards older than `CACHE_MAX_AGE_SECONDS = 30 * 86_400`;
5. while total bytes exceed `CACHE_MAX_BYTES = 64 * 1024 * 1024`, removes
   oldest-first by mtime;
6. stops after `CACHE_SWEEP_MAX_ENTRIES = 20_000` scanned entries and reports
   the sweep as incomplete.

Every unlink failure is counted, never raised. `Work` gains
`cache_shards_pruned`, `cache_bytes_reclaimed`, `cache_prune_failures`,
`cache_sweep_incomplete`, `legacy_cache_removed`, and
`freshness_write_failures`. These appear inside the analysis document's `work`
object, which is an additive machine change (R7.2).

The sweep is confined to the index directory; it can never touch
`claude-lineage-freshness.json` (a sibling file, not inside the index root) or
anything under `XDG_STATE_HOME`.

### 5. Cleanup disclosure (subproblem 4)

The default retention behavior does **not** change. `cleanup.py` gains a
read-only disclosure step, executed for both real and `--dry-run` runs, that
answers "what did you keep and how do I remove it?"

Correlation: `LineageClaim` records `worktree` at fork time
(`pipeline.py:170`), so match `read_lineage()` claims whose resolved
`worktree` equals `plan.worktree`. Handle zero matches (no Agent Fork claim
referenced this worktree), one match (the ordinary case), and several matches
(list all). For each matched claim's `child_session_id`, check
`read_inferences()` for an inferred record and the freshness index for an
entry. Inferred records correlate to a worktree only through a matched claim;
an inferred record with no claim is never attributed to a cleanup target.

The existing notice string at `cleanup.py:379-382` is preserved verbatim as the
first notice so current assertions stay stable; new notices are appended:

- which child session IDs retain a planned lineage claim, and the store path
  `$XDG_STATE_HOME/agent-fork/session-lineage.json`;
- which retain an inferred record
  (`…/session-lineage-inferences.json`) and a freshness entry
  (`$XDG_STATE_HOME/agent-fork/claude-lineage-freshness.json`, or the legacy
  `$XDG_CACHE_HOME` location per section 2a if not yet migrated);
- why the default keeps them: the forked agent session remains resumable and
  the claim is Agent Fork's strongest local parent evidence;
- the exact removal command,
  `agent-fork session claude-parent delete --session-id <ID> --yes`;
- one sentence that transcript screen cache shards are shared, hold no parent
  conclusion, are rebuilt on demand, and are reclaimed by the bounded cache
  sweep rather than by cleanup.

`CleanupResult` gains `retained_metadata`, rendered as an additive object in
machine output alongside the existing `notices`:

```json
{"retained_metadata": {"lineage_claims": ["…"], "inferred_records": ["…"],
 "freshness_entries": ["…"], "removal_command": "agent-fork session claude-parent delete --session-id … --yes"}}
```

Any failure to read the stores degrades to a single neutral notice; disclosure
must never fail a cleanup.

### 6. Complete deletion and its report (subproblem 5's fix)

Add to the store:

```python
def remove_index_freshness(
    child_session_id: str, *, env: Mapping[str, str] | None = None
) -> bool: ...
```

It mirrors `update_index_freshness`: take `registry_lock`, read and validate the
document, pop the key, write via `agent_fork.storage.atomic_write_json` (the
shared helper `update_index_freshness` itself now uses, per the 2026-08-20
revalidation above — it already carries the `0o600` mode via its temp-file
`chmod`, so `remove_index_freshness` needs no separate mode handling). It
returns `False` when the file is absent or the key is not present, and it
raises the same `ValueError` as its sibling on an invalid index.

CLI `delete` (`cli.py:814-872`) composes it with this rule:

- `source == "inferred"` → `remove_inference(...)`, then
  `remove_index_freshness(...)`. No record for that child remains, so its
  corroboration must not survive.
- `source == "planned"` → `remove_lineage(...)`. Remove the freshness entry
  **only if** no inferred record for the same child survives; otherwise keep it
  and say so. Removing it would silently downgrade a surviving inferred record
  to `freshness_unknown` — the exact class of defect A10 exists to remove.

The result document gains flat scalar fields, which render correctly in both
`emit()` modes:

```json
{"deleted": true, "session_id": "…", "source": "inferred",
 "removed_record": "inferred", "removed_freshness_entry": true,
 "retained_planned_record": false, "retained_inferred_record": false,
 "retained_screen_cache": true,
 "notices": ["shared transcript screen cache retained at …/claude-lineage-index-v3/; it holds no parent conclusion and is rebuilt on demand"]}
```

Extend `emit()`'s human branch to print list-valued keys one line per item, so
`notices` renders readably instead of as a Python repr. The interactive
confirmation block gains two lines before the prompt: what will be removed (the
record and, when applicable, its freshness entry) and what will remain (the
shared screen cache, Claude transcripts, Git resources).

### 7. Structured incomplete analysis for corpus limits (subproblem 6's fix)

Add to `claude_lineage_inference.py`:

```python
class CorpusLimitError(ValueError):
    def __init__(self, limit: str, allowed: int, observed: int, *, scope: str = "corpus"):
        ...
```

Subclassing `ValueError` is deliberate: every existing `except ValueError`
handler keeps working, and in particular `evidence_stable()` still returns
`False` when a limit trips during pre-record revalidation — the "refuse to
record incomplete evidence" posture holds without new code.

Raise it at the four bare-`ValueError` limit sites: `max_entries` and
`max_total_bytes` and `max_files` in `discover()`
(`claude_lineage_inference.py:220`, `235`, `261`, `264`) and `max_candidates` in
`infer_one()`. `TimeoutError` from the `max_seconds` guard is mapped to the same
structured shape at the CLI boundary with `limit: "max_seconds"`, `scope:
"target"`.

Add to `errors.py`:

```python
"claude_parent_incomplete_analysis": ErrorSpec(
    3, "Claude transcript corpus exceeded a bounded analysis limit"
),

class ClaudeParentIncompleteAnalysisError(ClaudeParentError):
    code = "claude_parent_incomplete_analysis"
```

In `cli.py`, wrap the unguarded construction at line 896 and the per-target
`infer_one` call, and raise the typed error with an analysis document in
`details`, matching the existing `ClaudeParentError(..., details={"analysis":
…})` contract:

```json
{"analysis": {"agent": "claude", "session_id": null,
  "relationship": {"status": "incomplete"},
  "limit": {"name": "max_files", "allowed": 10000, "observed": 10001, "scope": "corpus"},
  "recorded": false,
  "remediation": "the Claude transcript corpus exceeds agent-fork's bounded analysis limit; archive or relocate older project transcripts under ~/.claude/projects, then rerun. agent-fork does not record a parent inferred from an incomplete corpus."}}
```

`relationship.status` reuses the existing `incomplete` value rather than adding
one, so no documented value set expands; the additive `limit` block carries the
specifics. Under `--json` this is one JSON error object on stderr with nothing
on stdout (R7.8), exit 3 (R6.1). With `--all`, the failure precedes bulk
spooling, so it is still a single error object. With `--record` or
`--record-all`, nothing is recorded because the failure precedes inference.

## Sequencing

| Step | Subproblem | Depends on |
|---|---|---|
| 1 | Store assessment type, mandatory index check, and state-path relocation with legacy-cache fallback (2, 2a) | — |
| 2 | Session `parent_inference` object and notices (1) | 1 |
| 3 | `remove_index_freshness` and delete reporting, including legacy-path fallback (5) | 1 |
| 4 | v3 flat shards, legacy removal, bounded sweep (3) | — |
| 5 | Typed `CorpusLimitError` and incomplete-analysis result (6) | — |
| 6 | Cleanup disclosure (4) | 1, 4 for path names |
| 7 | Documentation, catalog, conformance, matrix | all |

Steps 1–3 are one dependency chain; steps 4 and 5 are independent and may be
implemented in parallel or in any order.

## Test-driven implementation plan

Every production change follows a demonstrated failing test. Add each ID to
`docs/testing/TEST-MATRIX.md` with tier and requirement source, and refresh the
asserted row-count line only after the rows exist. IDs below are current as of
the 2026-08-20 revalidation against `origin/main` (commit `46201c1`); confirm
against `docs/testing/TEST-MATRIX.md` again immediately before implementation,
since other in-flight work can claim IDs first. Next free IDs at that
revalidation: `T-CPI-40`, `T-SES-48`, `T-CLI-36`, `T-CLN-25` (the P05
session-transcript-path item had already claimed `T-SES-39..47`, and other
landed work had claimed `T-CPI-37..39`, `T-CLI-33..35`, and `T-CLN-24`).

| Test ID | File | Required proof |
|---|---|---|
| `T-CPI-40` | `tests/unit/test_lineage_inference_store.py` | The full status/evidence mapping table, one row per status, including `changed_sources` for target-only, parent, and mixed mismatches. |
| `T-CPI-41` | same | Deleting the freshness index yields `freshness_unknown`, not `current_at_last_analysis` — the exact gate-1 revival repro. |
| `T-CPI-42` | same | A present index whose `targets` lacks this child yields `freshness_unknown`; an invalid, symlinked, or oversized index yields `freshness_unknown`. |
| `T-CPI-43` | same | Appending one blank line to the target transcript yields `stale_sources` with `changed_sources == ("target",)`; the record is still readable and its parent ID unchanged. |
| `T-CPI-44` | same | `remove_index_freshness` removes only the named key, is a no-op returning `False` for an absent file or key, and leaves mode `0o600`. |
| `T-CPI-45` | same | A record with more than `MAX_SOURCE_FINGERPRINTS` entries is rejected as an invalid store. |
| `T-CPI-46` | `tests/unit/test_claude_lineage_inference.py` | Three successive appends plus re-inference leave exactly one shard for that stem; the shard name is `{stem}.json`. |
| `T-CPI-47` | same | The sweep removes the legacy v2 tree once, removes orphan stems, honors the age and byte caps oldest-first, respects the marker interval, counts failures without raising, and never touches the freshness index or the state store. |
| `T-CPI-48` | same | Each of `max_files`, `max_entries`, `max_total_bytes`, and `max_candidates` raises `CorpusLimitError` with exact `limit`, `allowed`, `observed`, and `scope`. |
| `T-CPI-49` | same | A freshness-index write failure increments `freshness_write_failures`, not `cache_write_failures`, and still returns a result. |
| `T-CPI-50` | `tests/unit/test_lineage_inference_store.py` | `index_freshness_path` resolves under `XDG_STATE_HOME`; `update_index_freshness` writes there via `atomic_write_json` and, when a legacy `XDG_CACHE_HOME` file for the same session exists, deletes it after the successful write. |
| `T-CPI-51` | same | `assess_inference` reads a state-path entry when present; when the state path is absent, it falls back to reading a legacy cache-only entry and evaluates it identically (not `freshness_unknown`); when both exist for the same child, the state-path entry wins. |
| `T-CPI-52` | same | `remove_index_freshness` removes the entry from the state path if present there, else from the legacy cache path if present there; a no-op (`False`) only when absent from both. |
| `T-SES-48` | `tests/unit/test_session.py` | A stale-source record produces `parent_inference.status == "last_known_good"` with the recorded parent ID, while `parent_session` stays null and `lineage.status` stays `not_found`. |
| `T-SES-49` | same | The `parent_inference` object is present for all seven statuses with the exact documented field shape, including `not_consulted` when a planned claim exists and for Codex, and coexists with the existing `transcript` object without displacing it. |
| `T-SES-50` | same | `session validate --has-parent` still fails with only a `last_known_good` or `freshness_unknown` record, and passes after a re-inference makes it `current`. This is the strict-validation guarantee. |
| `T-CLI-36` | `tests/cli/test_session.py` | Human and JSON session output for `last_known_good` and `freshness_unknown`, including the exact notice and the rerun command, with no corpus discovery, no cache write, and no freshness write during `session`. |
| `T-CLI-37` | `tests/cli/test_claude_parent.py` | `delete --source inferred` reports every additive field and actually removes the freshness entry; `delete --source planned` with a surviving inferred record retains the freshness entry and says so. |
| `T-CLI-38` | `tests/cli/test_claude_parent.py` | Exceeding `max_files` with `infer --current`, `--session-id`, `--all`, and `--record` exits 3 with `claude_parent_incomplete_analysis`, emits one JSON error on stderr and nothing on stdout, and writes no inference, freshness, or registry state. |
| `T-CLN-25` | `tests/cli/test_cleanup.py` | Real and `--dry-run` cleanup of a fork with a lineage claim disclose the retained claim, inferred record, freshness entry, store paths, and the exact removal command, and remove none of them. |
| `T-CLN-26` | same | Cleanup of a target with no matching claim, and cleanup when a store read fails, both succeed with the neutral notice. |

Run each focused file RED before its production change, then GREEN, then the
repository gates: `just all`, `just check-matrix`, `just strict-collect`,
`just clean-install`.

## Documentation and conformance delta

- `src/agent_fork/errors.py` and `ERROR_CATALOG`: add
  `claude_parent_incomplete_analysis` at exit 3 plus
  `ClaudeParentIncompleteAnalysisError`.
- `README.md`: add the new code to the exit-code-3 row; describe
  `parent_inference` in the session-inspection section; describe the cleanup
  retention disclosure; note the freshness-index store now lives under
  `XDG_STATE_HOME` (state-store paths section).
- `docs/session-inspection.md`: replace the "stale records … are not used as
  parent evidence" paragraph with the full freshness vocabulary, the
  `parent_inference` object and its seven statuses, the strict-validation rule,
  the new cache directory name, the freshness-index relocation and its
  lazy per-entry migration (section 2a), and the delete report fields.
- `REQUIREMENTS.md`: amend the Claude-inference and cleanup requirements to
  describe last-known-good disclosure, mandatory corroboration, bounded cache,
  complete deletion, and the typed corpus-limit refusal.
- `CONFORMANCE.md`: one CLI Standard review-history row; refresh affected
  requirement evidence. No new waiver is expected.
- `docs/testing/TEST-MATRIX.md`: all sixteen new IDs, one implementation per
  live row, refreshed total.

CLI Standard review scope:

| Rule | A10 requirement |
|---|---|
| R6.1 | Keep the new corpus-limit refusal in exit code 3. |
| R7.2, R9.3 | `parent_inference`, `retained_metadata`, new `work` counters, and new delete fields are additive; `lineage.status`, `fork_command.status`, `parent_session`, and `relationship.status` value sets are unchanged. |
| R7.6 | Session and cleanup results stay observational on stdout. |
| R7.8 | One JSON error object for the incomplete-analysis refusal. |
| R7.12 | Publish `claude_parent_incomplete_analysis`. |
| R8.6 | Prove `cleanup --dry-run` and `session` perform no metadata mutation. |
| R9.10 | Every non-current freshness status names its remediation command. |
| R9.14 | Permanent conformance rows in the existing matrix. |

Groups not affected: command structure and vocabulary, configuration
precedence, networked behavior, streaming, plugins, interactive setup. Flags
are N/A unless the owner approves the optional pruning flag below.

## Non-goals

- `session` never triggers inference, corpus discovery, screening, cache
  writes, or freshness writes to re-establish currency. Re-establishing
  freshness is always an explicit, user-invoked `infer` run.
- No content-prefix or append-aware fingerprinting; the owner chose the
  last-known-good route.
- No unlimited or incremental corpus index, and no relaxation of the file,
  entry, byte, candidate, or time limits.
- No change to cleanup's default metadata retention.
- No change to `parent_session`, `lineage.status`, `fork_command.status`,
  `relationship.status`, `id_status`, or any other existing v1 value set.
- No change to `validate_session`, agent preflight, or the fork mutation
  pipeline.
- No inference-store version bump; the store stays at `VERSION = 2` because
  `_decode` has no migration path and a bump would invalidate every existing
  user record.
- No fixes for P02 faults A3, A5–A8, or A11–A13, and no release, commit, push,
  pull-request, or unrelated cleanup work.

## Rejected alternatives

- **Populating `parent_session` with a new `id_status` such as
  `last_known_good`.** Rejected: it expands a documented v1 value set and
  changes an existing field's meaning, which the A9 design records as a
  violation of CLI Design Standard rules R7.2 and R9.3, and it would silently
  flip `session validate --has-parent` from failing to passing. The additive
  `parent_inference` object supplies the new dimension without either effect.
- **Only rewording the "recorded Claude parent inference is stale" notice.**
  Rejected by owner decision 1: the record is discarded, so no wording change
  can display it.
- **Treating a missing freshness index as fresh, or re-deriving the candidate
  universe on read.** Rejected: the first is the gate-1 revival defect; the
  second turns a cheap read-only `session` into a corpus scan.
- **Comparing `analysis_index_generation` during freshness evaluation.**
  Rejected: it is a corpus-wide hash, so any unrelated transcript change would
  invalidate every record — a global-scope version of the treadmill A10 fixes.
- **Pattern-pruning legacy `{stem}-{fp}.json` shards in place inside the v2
  directory.** Rejected: flat naming makes every legacy shard unreadable
  anyway, so in-place pruning buys zero cache reuse while adding the most
  fragile code in the design. A one-time guarded removal of the v2 tree is
  simpler and strictly safer.
- **A background or `atexit` cache collector.** Rejected: unbounded lifetime
  outside the command's own bounded work budget. The marker-gated in-line sweep
  is bounded, observable in `work`, and never fatal.
- **Refusing to record when the freshness index cannot be written.** Rejected:
  it would make read-only or unwritable cache roots unable to record anything,
  while the resulting record is harmless by construction under this design —
  it is never strict evidence and always tells the user to rerun. A notice plus
  a distinct `freshness_write_failures` counter is proportionate.
- **Returning exit 0 with an `incomplete_analysis` success document for corpus
  limits.** Rejected: the command produced no answer, and the existing
  `ClaudeParentError(..., details={"analysis": …})` contract already covers
  "analysis ran but produced nothing usable" at exit 3. A silent exit 0 would
  let scripts treat a limit breach as "no parent found."
- **Adding a new `relationship.status` value for limit breaches.** Rejected:
  the existing `incomplete` value already means "the corpus was incomplete";
  the additive `limit` block carries the specifics without expanding a
  documented value set.

## Owner decisions (resolved 2026-08-20)

Two items required owner judgment; both are now decided and folded into the
design above. Nothing else in this document is an open question.

1. **Freshness-index location: relocate to `XDG_STATE_HOME` now.** Decided
   over deferring. Full design in section 2a: `index_freshness_path()` moves
   to `$XDG_STATE_HOME/agent-fork/claude-lineage-freshness.json`; reads fall
   back to the legacy `$XDG_CACHE_HOME` location when the state path is
   absent; writes always target the new path and best-effort-delete the
   matching legacy file; deletes act on whichever location currently holds the
   entry. Migration is lazy and per-entry — no bulk job, no startup scan.
2. **Cleanup pruning: disclosure only, no new flag.** `cleanup` does not gain
   `--prune-agent-metadata`. Its default retention is unchanged, and the
   disclosure step (section 5) already names the exact
   `agent-fork session claude-parent delete --session-id <ID> --yes` command
   for anyone who wants to remove retained metadata explicitly. This adds no
   new v1 CLI surface, no new confirmation semantics, and no new destructive
   path.

One smaller point remains worth a one-line ruling at gate 4, not blocking this
design: `claude-parent show` currently renders a stored record without
evaluating freshness. This design recommends adding an additive live
`freshness` object to `show` only (one assessment, bounded stats) and leaving
`list` unchanged, so a bulk listing never stats thousands of transcript paths.
