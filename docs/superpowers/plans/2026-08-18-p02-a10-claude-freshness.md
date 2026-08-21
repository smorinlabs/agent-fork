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
`CONFORMANCE.md` again before the gate-6 review). A10 affects scripted machine
output, one new stable error code, one additive session object, additive
`work` counters, additive delete-result fields, cleanup disclosure text, and
one internal storage-path relocation (freshness index moves from
`XDG_CACHE_HOME` to `XDG_STATE_HOME`, migrated lazily per child session ID, no
CLI surface change). It adds no new command or flag — the owner decided against an opt-in cleanup
pruning flag; see "Owner decisions" below. It does not add configuration,
network access, streaming, plugins, or interactive behavior.

| P02 gate | State |
|---|---|
| 1. Adversarial verification, including Codex | **CONFIRMED-WITH-CORRECTIONS** on 2026-08-18; recap below |
| 2. Owner scope decision | **approved**; six subproblem decisions recorded below, plus two follow-up decisions on 2026-08-20 |
| 3. Design document | **complete**; revalidated against `origin/main` on 2026-08-20 |
| 4. Implementation plan and adversarial review, including Codex | **APPROVE-WITH-CHANGES** on 2026-08-20; both required lenses concurred, every required change incorporated; see "Plan-review outcome" below |
| 5. Test-driven implementation | **complete** on 2026-08-20; 31 new tests, all four repository gates pass; see "Implementation evidence" below |
| 6. Adversarial implementation review, including Codex | Two review rounds completed 2026-08-20, both by the two required lenses (Opus + independent Codex), both returning **APPROVE-WITH-CHANGES**: round 1 found 13 required findings against the fix commit, all corrected (`fc35365`); round 2, a confirmation pass against that fix commit, found 2 new defects introduced by the round-1 fixes plus 3 independently-double-confirmed test-coverage gaps, all corrected in this working tree but **not yet independently re-reviewed** — see "Gate-6 findings and corrections" and "Gate-6 confirmation round" below for full detail and open status |

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
  same landed work before this revalidation. That sixteen counts IDs lost to
  the 2026-08-18 renumbering; it is not the number of IDs this plan allocates,
  which is 31 (see "Test-driven implementation plan"). The test tables below
  have been renumbered to the next free IDs as of this revalidation;
  **re-check `docs/testing/TEST-MATRIX.md` again immediately before
  implementation**, per the note there.
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
   exactly which records survive, where they live, and the exact
   source-qualified command that removes each one. No new cleanup flag is
   added (owner decision 2).
5. **`session claude-parent delete` must not leave freshness data behind.** It
   removes the matching freshness entry — from both the state and legacy
   locations, and before the record itself — and reports exactly which record
   and which freshness entry were removed and which shared cache remains.
6. **Corpus limits must return a structured incomplete-analysis result.**
   Exceeding the file, entry, byte, candidate, or time limit produces a typed
   refusal naming the exceeded limit, its allowed and observed values, and
   remediation, and the run exits 3. The three whole-corpus limits refuse the
   entire invocation; the two per-target limits refuse only their own target
   and are reported per target inside a `--all` batch (section 7). Recording is
   refused for any target with an incomplete analysis, because incomplete
   evidence is unsafe. No unlimited index is built.

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
   conditional. It resolves one entry for `record.child_session_id` from the
   state path, falling back per child to the legacy path exactly as section 2a
   specifies:
   - the state index is a symlink, oversized, unreadable, not JSON, not
     `version == 1`, or lacks a dict `targets` → `freshness_unknown`, without
     consulting the legacy path (a corrupt state store is a fault to disclose,
     not a cache miss to paper over). The same structural failure at the legacy
     path also yields `freshness_unknown`, but only when the legacy path is
     actually consulted — that is, only when the state path yielded no usable
     entry for this child;
   - no usable entry for `record.child_session_id` in **either** location —
     because both files are absent, because neither file's `targets` holds the
     key, or because every entry found for the key is not a dict or lacks
     `candidate_universe_digest` → `freshness_unknown`;
   - the resolved entry's `candidate_universe_digest` differs from the
     record's → `stale_candidate_universe`;
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

Migration is lazy and **per child session ID, never per file**, following the
module's existing small-safe-change posture. The distinction is load-bearing,
so state it plainly before the rules: both `index_freshness_path()` and its
legacy counterpart resolve to **one shared JSON file** whose `targets`
dictionary holds an entry for every child session. A per-file rule — "read the
legacy file only when the state file is absent", or "delete the legacy file
after a successful write" — would mass-invalidate or mass-destroy every
un-migrated session's evidence the moment any single session is re-inferred.
That is the exact spurious-invalidation class A10 exists to eliminate. Every
rule below therefore keys on `child_session_id`, and no rule ever creates or
unlinks a whole file as a migration act.

- `index_freshness_path(env)` calls the shared `agent_fork.xdg.xdg_path()`
  helper with `"XDG_STATE_HOME"` / `".local/state"` instead of
  `"XDG_CACHE_HOME"` / `".cache"` — the same helper `inference_path()` and
  `lineage_path()` already use, so this is a one-line change to an existing
  call, not new path-resolution code. Add
  `_legacy_index_freshness_path(env)` calling the same helper with the old
  `"XDG_CACHE_HOME"` / `".cache"` arguments, kept for backward-compatible
  reads and for per-entry removal during migration.
- **Read** (`assess_inference` step 4): read the state path first, using the
  existing validation rules. Fall back to the legacy path **whenever the state
  path yields no usable entry for this specific `record.child_session_id`** —
  that is, when the state file is absent, when it is present but its `targets`
  holds no entry for this child, or when its entry for this child is not a
  dict or lacks `candidate_universe_digest`. A state file that exists and
  holds entries for *other* children is not evidence about *this* child, so it
  must not short-circuit the fallback. Only after both locations fail to
  produce a usable entry for this child does step 4 yield `freshness_unknown`.
  A structurally invalid state file (symlink, oversized, not JSON, not
  `version == 1`, no dict `targets`) still yields `freshness_unknown` outright
  and is never repaired from the legacy path — an unreadable state store is a
  fault to disclose, not a cache miss to paper over. A legacy-only entry is
  otherwise treated as an ordinary hit — the file moved, the evidence did not.
  `assess_inference` still performs no writes, so this fallback costs at most
  one extra stat/read and preserves the read-only cost guarantee in section 3.
- **Write** (`update_index_freshness`, called only from `infer_one`, never
  from `session`): always writes this child's entry to the state path. After
  that write succeeds, remove **only this child's key** from the legacy file's
  `targets` dictionary by read-modify-atomic-rewrite of the legacy file
  (decode, `targets.pop(child_session_id, None)`, `atomic_write_json`). Skip
  the rewrite entirely when the legacy file is absent or holds no key for this
  child, so the common post-migration case costs one stat. **Never unlink the
  legacy file**, and never rewrite it with anything but its own remaining
  entries: other children's legacy entries are still the only corroboration
  they have. When popping this child's key leaves `targets` empty, rewrite the
  legacy file with an empty `targets` dictionary rather than unlinking it —
  one uniform, testable rule with no special case. Any `OSError` or
  `ValueError` from the legacy rewrite alone is swallowed inside
  `update_index_freshness` and is **not** counted as a freshness write failure:
  the state-path write already succeeded, so the freshness index is current,
  and the surviving legacy duplicate is inert because reads for this child now
  find the state-path entry first. Counting it would fire the
  "will report `freshness_unknown`" notice for a record that will report
  nothing of the kind. Only a failure of the state-path write itself
  propagates to `infer_one().finish()` and increments the counters below.
- **Delete** (`remove_index_freshness`, subproblem 5): removes this child's
  key from **both** locations, not from whichever is found first. It pops the
  key from the state path and then from the legacy path, rewriting each file
  that actually changed, and returns `True` when either removal changed
  anything. Removing from only one location would leave a duplicate entry in
  the other, silently reviving corroboration for a record the user asked to
  delete. As on the write path, neither file is ever unlinked.
- **Duplicate entries.** If both locations hold an entry for the same
  `child_session_id`, reads use the state-path entry (it is by construction
  the more recent write) and deletes remove both. This is expected during
  migration, not an anomaly.
- **Lock ordering for cross-file mutations.** `registry_lock(path)` derives its
  lock file from the exact path (`path.with_suffix(path.suffix + ".lock")`), so
  the state file and the legacy file have **different, independent locks**; a
  state-file write and a legacy-file rewrite are not mutually exclusive under
  one lock. Any operation touching both files therefore acquires **both** locks
  in one fixed order: **state path first, then legacy path**, releasing in the
  reverse order. Both `update_index_freshness` and `remove_index_freshness`
  follow this order, which makes deadlock between two concurrent Agent Fork
  processes structurally impossible and makes the state-write-then-legacy-pop
  pair atomic with respect to any other Agent Fork process.
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
fingerprint plus at most two small JSON reads — the state-path index always,
and the legacy index only when the state path yields no usable entry for this
child. The recorder caps fingerprints at
`max_candidates + 1`, but a hand-edited store must not be able to make
`session` do unbounded I/O, so add `MAX_SOURCE_FINGERPRINTS = 1_024` to
`_decode`: a record exceeding it is rejected as an invalid store, consistent
with the module's existing `MAX_STORE_BYTES` posture.

Freshness-index write failure. `ClaudeLineageCorpus.infer_one().finish()`
already swallows `update_index_freshness` failures into
`work.cache_write_failures`, which today counts **both** screen-shard write
failures and freshness-index write failures. That existing field keeps its
current meaning and its current increments exactly as they are: it stays the
aggregate write-failure count, and anything already reading it keeps reading
the same number. This is **not** a split. Add
`work.freshness_write_failures` as a new, purely additive counter that
increments **in addition to**, never instead of, `work.cache_write_failures`,
and only for the freshness-index write path. A freshness-index write failure
therefore increments both counters; a screen-shard write failure increments
only `cache_write_failures`, so the difference between them is exactly the
freshness-specific count.

When `work.freshness_write_failures` is non-zero, the user is told that the
record was written but will report `freshness_unknown` until the freshness
index becomes writable. **That notice is emitted at the CLI layer, not inside
`claude_lineage_inference.py`.** Two facts force that placement: `Result.document()`
hard-codes `"notices": []` (`claude_lineage_inference.py:162`) and would have
to grow a notice-assembly responsibility it does not have today, and only
`cli.py` knows whether `--record` or `--record-all` was actually requested —
the counter increments identically on a preview run, where "the record was
written" would be false. So `cli.py` appends the notice to the per-target
document it already builds, and only when recording was requested and that
target was recorded. A preview run emits no such notice; its non-zero counter
is still visible in `work`. Do not refuse the record — see rejected
alternatives.

### 3. Session inspection surfaces `last_known_good` (subproblem 1's fix)

`inspect_session()` stops discarding the record. It keeps the existing
`parent_session` and `lineage.status` semantics exactly as they are today —
they remain **strict** fields — and reports the retained record through one new
additive top-level object, following the `agent_signal` precedent set by A9.

Behavior in `session.py:417-437` (the `claim is None` branch that today calls
`inference_freshness` and discards the record) becomes:

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

Field shape per status — this table is the exact assertion `T-SES-49` proves:

| `status` | `freshness` | `parent_session_id`, `analyzed_at`, `changed_sources` |
|---|---|---|
| `not_consulted` | null | null / null / `[]` |
| `absent` | null | null / null / `[]` |
| `unreadable` | null | null / null / `[]` |
| `superseded` | `"stale_algorithm"` | null / null / `[]` |
| `current` | `"current_at_last_analysis"` | populated |
| `last_known_good` | `"stale_sources"` or `"stale_candidate_universe"` | populated |
| `freshness_unknown` | `"freshness_unknown"` | populated |

`superseded` nulls those three fields for the same reason section 1 gives for
suppressing its display: a record written by a different algorithm version
carries fields whose meaning is not guaranteed, so `status` is the only
interpretable thing about it. Its `freshness` value stays populated because
`stale_algorithm` is the diagnosis itself, not a field of the untrusted
record. Only `status: "current"` is strict parent evidence; there is
deliberately no redundant boolean that could drift from that rule.

Notices, one per non-current status, each naming the remediation command
`agent-fork session claude-parent infer --current --record` (or
`--session-id UUID --record` when the target is not the current session). The
`stale_sources` notice varies by `changed_sources`: target-only says the
session's own transcript grew and newer messages were not analyzed;
parent or other says analyzed evidence transcripts changed. Every notice
states that the parent is shown as last known good and does not satisfy
`session validate --has-parent`.

Human output, one fixed location: **immediately after the `lineage:` line
(`cli.py:1021`) and before the `notice:` loop (`cli.py:1022-1023`)**, inside
the same `current_session is not None` branch that prints `lineage:`. The
resulting reading order is lineage status, then parent-inference status, then
any explanatory notices — each notice follows the line it explains. Nothing is
printed near `transcript:` (`cli.py:1073-1077`), which is unrelated P05 output.
Print one line when `status` is not `not_consulted` or `absent`:

```text
parent inference: last_known_good 6b0a…  (analyzed 2026-08-17T20:11:04Z; target transcript changed)
```

`superseded` prints its status and nothing else — `parent inference:
superseded` — since its parent ID and timestamp are null per the field-shape
table. That is what "not displayed" in section 1's contract table means: the
*parent* is not shown, while the *status* explaining its absence always is.

Every store-derived scalar on that line — the status, the parent session ID,
and the timestamp — passes through `agent_fork.output.terminal_text`, the
helper the neighboring `lineage:`, `parent session:`, and `notice:` lines
already use for untrusted scalars in this block.

`validate_session()` is **unchanged**. Because `parent_session` stays null for
every non-current status, `--has-parent`, `--parent-session-id`, and the
`has_parent` assertion behave exactly as they do today. That is the mechanical
guarantee behind "must NOT satisfy strict parent validation."

Cost guarantee: `session` still performs no corpus discovery, no screening, no
deep parse, and no cache or freshness write. It reads at most three small JSON
stores — the lineage store, the inference store, and the freshness index (plus
the legacy freshness index only on the per-child fallback of section 2a) — and
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
and only after the same ownership and symlink checks `_screen` already performs
before writing (`claude_lineage_inference.py:369-379`: the root is a real
directory, is not a symlink, and `st_uid == os.getuid()`) pass for that root,
it:

1. removes the entire legacy `claude-lineage-index-v2/` tree once (regular
   files then `rmdir`) — flat naming makes every legacy shard unreadable
   anyway, so migrating them buys no cache reuse. **The v2 root is a different
   directory from the v3 root, so the v3 ownership check does not authorize
   touching it.** Before unlinking anything under v2, run the identical
   ownership and symlink checks against the v2 root itself — real directory,
   not a symlink, `st_uid == os.getuid()` — and abandon the legacy removal
   (counting nothing, raising nothing) if any check fails. Never follow the v2
   root if it is a symlink, and never recurse below its immediate children;
2. removes entries whose name does not match `^<uuid>\.json$`, **excluding the
   `.sweep` marker itself**, which is by design both non-matching and older
   than any grace period. Every other such entry is subject to an age guard,
   not just a literal `.tmp` name: an
   in-flight atomic write is visible in this directory as a dot-prefixed
   temporary file named `.{shard.name}.<random>` — `atomic_write_json` is
   called with `prefix=f".{shard.name}."` at
   `claude_lineage_inference.py:488-493`, and its own default prefix is
   `.{path.stem}-`; **no temporary file this codebase writes has ever ended in
   `.tmp`**. The guard is therefore: remove a non-`<uuid>.json` entry only when
   its mtime is older than `CACHE_TEMP_GRACE_SECONDS = 3_600`. That covers
   every naming shape, including one another Agent Fork process is writing
   right now, so the sweep can never unlink a live in-flight write;
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

The sweep touches exactly two directories and nothing else: the v3 index root,
and — once, under its own independent ownership and symlink check — the v2
index root. It can never touch `claude-lineage-freshness.json` at either its
new `XDG_STATE_HOME` location or its legacy `XDG_CACHE_HOME` location, because
both are sibling *files* of the index roots rather than entries inside them,
and it never touches anything else under `XDG_STATE_HOME`.

### 5. Cleanup disclosure (subproblem 4)

The default retention behavior does **not** change. `cleanup.py` gains a
read-only disclosure step, executed for both real and `--dry-run` runs, that
answers "what did you keep and how do I remove it?"

Correlation: `LineageClaim` records `worktree` at fork time
(`pipeline.py:177`), so match `read_lineage()` claims whose resolved
`worktree` equals `plan.worktree`. Handle zero matches (no Agent Fork claim
referenced this worktree), one match (the ordinary case), and several matches
(list all). For each matched claim's `child_session_id`, check
`read_inferences()` for an inferred record and the freshness index for an
entry. Inferred records correlate to a worktree only through a matched claim;
an inferred record with no claim is never attributed to a cleanup target.

The existing notice string at `cleanup.py:385-388` is preserved verbatim as the
first notice so current assertions stay stable; new notices are appended:

- which child session IDs retain a planned lineage claim, and the store path
  `$XDG_STATE_HOME/agent-fork/session-lineage.json`;
- which retain an inferred record
  (`…/session-lineage-inferences.json`) and a freshness entry
  (`$XDG_STATE_HOME/agent-fork/claude-lineage-freshness.json`, or the legacy
  `$XDG_CACHE_HOME` location per section 2a if that child's entry is not yet
  migrated);
- why the default keeps them: the forked agent session remains resumable and
  the claim is Agent Fork's strongest local parent evidence;
- one removal command per retained record, source-qualified (below);
- one sentence that transcript screen cache shards are shared, hold no parent
  conclusion, are rebuilt on demand, and are reclaimed by the bounded cache
  sweep rather than by cleanup.

**Escaping.** These notices interpolate store-derived, untrusted text — child
session IDs read out of the lineage and inference stores, and resolved store
paths. Every such value passes through
`agent_fork.text.escape_terminal_text`, which `cleanup.py` already imports as
`_escape_terminal_text` (`cleanup.py:13`) and already applies to branch names,
worktree paths, registry entry names, and commit subjects. Escaping happens
where the notice is **constructed, inside `cleanup.py`**, because the human
CLI branch prints notices raw (`print(notice)`, `cli.py:1132-1133`) and adds
no escaping of its own.

**Removal commands are per record and source-qualified.** A single
`removal_command` string cannot express the real cases. `session claude-parent
delete` takes one `--session-id` (`cli.py:244`) and an optional `--source`
restricted to `planned` or `inferred` (`cli.py:245`); when both a planned claim
and an inferred record exist for the same child, omitting `--source` makes the
lookup match two records and the command refuses with "Claude parent record not
found or source is ambiguous" (`cli.py:777-784`). Cleanup therefore emits one
command per retained record, always naming `--source`:

```text
agent-fork session claude-parent delete --session-id <ID> --source planned --yes
agent-fork session claude-parent delete --session-id <ID> --source inferred --yes
```

Several retained children produce several such lines; a child with both record
kinds produces two lines, one per source. Zero retained records produce no
command lines at all.

`CleanupResult` gains `retained_metadata`, rendered as an additive object in
machine output alongside the existing `notices`. `removal_commands` is a list
of per-record objects, never one global string:

```json
{"retained_metadata": {"lineage_claims": ["…"], "inferred_records": ["…"],
 "freshness_entries": ["…"],
 "removal_commands": [
   {"session_id": "…", "source": "planned",
    "command": "agent-fork session claude-parent delete --session-id … --source planned --yes"},
   {"session_id": "…", "source": "inferred",
    "command": "agent-fork session claude-parent delete --session-id … --source inferred --yes"}]}}
```

**Machine-output wiring.** `CleanupResult` is a plain dataclass with no
`document()` method, and cleanup's JSON document is assembled by hand in
`cli.py:1115-1121` from five named keys (`removed`, `target`, `keep_branch`,
`dry_run`, `notices`). Adding `retained_metadata` to `CleanupResult`
alone would therefore never reach machine output. The implementation step must
touch **both** files: `cleanup.py` to compute and carry the field, and
`cli.py`'s cleanup JSON assembly to emit `"retained_metadata":
result.retained_metadata` alongside `"notices"`.

Any failure to read the stores degrades to a single neutral notice and an
empty `retained_metadata`; disclosure must never fail a cleanup.

### 6. Complete deletion and its report (subproblem 5's fix)

Add to the store:

```python
def remove_index_freshness(
    child_session_id: str, *, env: Mapping[str, str] | None = None
) -> bool: ...
```

It mirrors `update_index_freshness`: take `registry_lock` on the state path and
then, in that fixed order (section 2a), `registry_lock` on the legacy path;
read and validate each document, pop the key from **both**, and write via
`agent_fork.storage.atomic_write_json` each file that actually changed (the
shared helper `update_index_freshness` itself now uses, per the 2026-08-20
revalidation above — it already carries the `0o600` mode via its temp-file
`chmod`, so `remove_index_freshness` needs no separate mode handling). Neither
file is ever unlinked; a file whose `targets` becomes empty is rewritten with
an empty `targets` dictionary. It returns `True` when either location changed,
`False` when the key was present in neither, and it raises the same
`ValueError` as its sibling on an invalid index.

CLI `delete` (`cli.py:777-835`) composes it with this rule:

- `source == "inferred"` → `remove_index_freshness(...)` **first**, then
  `remove_inference(...)`. No record for that child remains, so its
  corroboration must not survive.
- `source == "planned"` → `remove_lineage(...)`. Remove the freshness entry
  **only if** no inferred record for the same child survives; otherwise keep it
  and say so. Removing it would silently downgrade a surviving inferred record
  to `freshness_unknown` — the exact class of defect A10 exists to remove. When
  the freshness entry *is* due for removal, it is removed **before**
  `remove_lineage(...)`, for the same reason as the `inferred` branch.

**Why freshness is removed first.** The two removals are separate writes to
separate files; nothing makes the pair atomic, and `remove_index_freshness`
can itself raise `ValueError` on a structurally invalid index. Order therefore
decides which half-completed state a failure between them leaves behind:

| Order | State after a failure between the two writes | Consequence |
|---|---|---|
| record first, then freshness | inference record gone, freshness entry orphaned | an orphaned freshness entry — the exact defect A10 exists to remove |
| **freshness first, then record** | freshness entry gone, inference record survives | the surviving record assesses as `freshness_unknown`: excluded from strict parent validation, displayed with its rerun notice, never silently treated as current |

The second row is safe by construction under this design, because
`freshness_unknown` is already a fully specified, disclosed, non-authoritative
state. The first row is not. Freshness-first is therefore mandatory, not a
preference.

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
`False` when a limit trips during pre-record revalidation — its
`except (OSError, ValueError)` at `claude_lineage_inference.py:937-938` already
covers both `CorpusLimitError` (a `ValueError`) and `TimeoutError` (an
`OSError`), so the "refuse to record incomplete evidence" posture holds without
new code.

The five limits split into two scopes that need different handling, because
they are raised at different points relative to bulk spooling. State the split
before the raise sites; the implementer must not treat them uniformly.

| Limit | Raised in | Scope | Effect |
|---|---|---|---|
| `max_entries` | `discover()` (`claude_lineage_inference.py:222`, `237`) | `corpus` | refuses the whole invocation |
| `max_total_bytes` | `discover()` (`:263`) | `corpus` | refuses the whole invocation |
| `max_files` | `discover()` (`:266`) | `corpus` | refuses the whole invocation |
| `max_candidates` | `infer_one()` (`:788`) | `target` | fails this target only |
| `max_seconds` | `infer_one()` (`:776-777`, as `TimeoutError`) | `target` | fails this target only |

**Whole-corpus limits.** `max_entries`, `max_total_bytes`, and `max_files`
raise inside `discover()`, which runs from `ClaudeLineageCorpus.__init__` at
`cli.py:859` — before `ids` is computed, before any `BulkSpool` is created, and
before the per-target loop begins. No spool is open and no target has been
processed, so the invocation refuses as a whole: one typed error, exit 3,
nothing recorded. This is true for `--current`, `--session-id`, and `--all`
Note that these three limits occupy **four** raise sites, because `max_entries`
is checked in two separate scan loops; all four must raise `CorpusLimitError`.

**Per-target limits.** `max_candidates` and `max_seconds` raise inside
`infer_one()`, which the loop at `cli.py:876-904` calls per target **inside an
existing `try` whose `except Exception` turns any failure into a per-target
`"relationship": {"status": "unavailable"}` document**. Under `--all` the bulk
spool is already open and earlier targets may already be spooled and recorded.
Two consequences the implementation must honor:

1. Add `except (CorpusLimitError, TimeoutError)` to that loop, ordered
   **before** the existing generic `except Exception`. Python matches `except`
   clauses in order, and `CorpusLimitError` subclasses `ValueError`, so a
   clause placed after the generic one would never run and the typed refusal
   would silently degrade back into today's untyped `"unavailable"` document.
   `TimeoutError` must be named explicitly: it derives from `OSError`, not
   `ValueError`, so a `CorpusLimitError`-only clause would not catch it. The
   handler converts either exception into the same structured shape, with
   `scope: "target"` and `limit.name` of `max_candidates` or `max_seconds`.
2. Per-target failure stays per-target, matching the isolation the loop
   already provides. The target that hit the limit contributes its own typed
   incomplete-analysis document to the bulk output and is **not** recorded;
   earlier targets that already completed keep their results and keep any
   record already written for them; remaining targets continue to be
   processed; the spool is closed cleanly on every path, exactly as today; and
   the run exits 3 overall if any target failed, through the existing
   `failures` counter and its `bulk_spool.render_json(sys.stderr, …)` /
   `close()` / `return 3` path at `cli.py:905-931`. One target's limit breach
   never voids the batch's other recordings, and never converts a partial
   batch into a whole-run refusal.

Add to `errors.py`:

```python
"claude_parent_incomplete_analysis": ErrorSpec(
    3, "Claude transcript corpus exceeded a bounded analysis limit"
),

class ClaudeParentIncompleteAnalysisError(ClaudeParentError):
    code = "claude_parent_incomplete_analysis"

    def __init__(self, message: str, **kwargs):
        super().__init__(message, code=self.code, **kwargs)
```

The forwarding `__init__` is required, not boilerplate. `ClaudeParentError.__init__`
takes `code: str = "claude_parent_unavailable"` and unconditionally assigns
`self.code = code` (`errors.py:163-177`), so a subclass that declares only the
class attribute publishes `claude_parent_unavailable` on every instance and the
new code never reaches machine output. This is exactly the shape the two
existing subclasses use — `ClaudeParentNotRecordableError` (`errors.py:179-183`)
and `ClaudeParentPartialRecordError` (`errors.py:186-190`) — and the new class
matches them character for character apart from the code.

In `cli.py`, guard the unguarded `ClaudeLineageCorpus(environment)`
construction at line 859 for the whole-corpus limits, and the per-target
`infer_one` call at line 878 for the per-target limits, per the two-scope split
above. Raise the typed error with an analysis document in `details`, matching
the existing `ClaudeParentError(..., details={"analysis": …})` contract:

```json
{"analysis": {"agent": "claude", "session_id": null,
  "relationship": {"status": "incomplete"},
  "limit": {"name": "max_files", "allowed": 10000, "observed": 10001, "scope": "corpus"},
  "recorded": false,
  "remediation": "the Claude transcript corpus exceeds agent-fork's bounded analysis limit; archive or relocate older project transcripts under ~/.claude/projects, then rerun. agent-fork does not record a parent inferred from an incomplete corpus."}}
```

`relationship.status` reuses the existing `incomplete` value rather than adding
one, so no documented value set expands; the additive `limit` block carries the
specifics.

Output shape follows the scope:

- **Whole-corpus limit, any invocation.** Under `--json` this is one JSON error
  object on stderr with nothing on stdout (R7.8), exit 3 (R6.1). With `--all`
  the failure precedes both `ids` computation and bulk spooling, so it is still
  a single error object and no spool is ever opened. With `--record` or
  `--record-all`, nothing is recorded because the failure precedes every
  inference.
- **Per-target limit, single target** (`--current` or `--session-id`). One
  target, one failure, so the run's only document is the incomplete-analysis
  document and the existing `if failures:` path raises the typed error: one
  JSON error object on stderr, nothing on stdout, exit 3, nothing recorded.
- **Per-target limit under `--all`.** The bulk spool stays open and receives
  this target's incomplete-analysis document alongside every other target's
  result. The spooled batch is rendered to stderr with its summary, closed, and
  the run exits 3 through the existing bulk failure path. Targets that
  completed before or after the failing one are recorded normally when
  `--record-all` was requested; the failing target is not recorded.

## Sequencing

Step numbers here are the same eight steps the "Test-driven implementation
plan" below expands test by test; there is one numbering scheme in this
document, not two.

| Step | Work | Depends on |
|---|---|---|
| 1 | Store assessment type, mandatory per-child index check, state-path relocation with per-entry legacy fallback (subproblems 2, 2a) | — |
| 2 | `remove_index_freshness` across both locations (5) | 1 |
| 3 | Session `parent_inference` object and notices (1) | 1 |
| 4 | Session and delete CLI output (1, 5) | 2, 3 |
| 5 | v3 flat shards, guarded legacy removal, bounded sweep, freshness write-failure counter and its CLI notice (3) | — |
| 6 | Typed `CorpusLimitError` and incomplete-analysis result (6) | — |
| 7 | Cleanup disclosure in `cleanup.py` **and** `cli.py`'s cleanup JSON assembly (4) | 1, 5 |
| 8 | Documentation, catalog, conformance, matrix | all |

The dependency graph is not a single chain. Step 1 comes first. Steps 2 and 3
each depend only on step 1 and **not on each other**, so they are siblings that
may run in either order or in parallel. Step 4 depends on both of them, since
it wires their production code into the CLI. Steps 5 and 6 are independent of
that whole chain and of each other. Step 7 depends on step 1 for the
state-path helper and step 5 for the `v3` cache-directory name it discloses.
Step 8 depends on everything.

## Test-driven implementation plan

Every production change follows a demonstrated failing test. This plan allocates
**31 new test IDs**: `T-CPI-40` through `T-CPI-57` (18), `T-SES-48` through
`T-SES-50` (3), `T-CLI-36` through `T-CLI-41` (6), and `T-CLN-25` through
`T-CLN-28` (4). Each range starts at the first free ID for its prefix as of the
2026-08-20 revalidation against `origin/main` (commit `46201c1`) and is
contiguous with no gaps. Add each ID to `docs/testing/TEST-MATRIX.md` with tier
and requirement source, and refresh the asserted row-count line — 413 today,
444 once all 31 rows exist — only after the rows exist. Confirm against
`docs/testing/TEST-MATRIX.md` again immediately before implementation, since
other in-flight work can claim IDs first.

These are the same eight steps the "Sequencing" table above lists, expanded
test by test; the dependency graph stated there governs here unchanged. In
short: step 1 first; steps 2 and 3 are siblings that each depend only on step 1
and not on each other; step 4 depends on both; steps 5 and 6 are independent of
that chain and of each other; step 7 depends on steps 1 and 5 for the
store/cache path names it discloses; step 8 depends on everything. The order
they are written in below is one valid topological order, not the only one.

### Step 1 — RED and GREEN: freshness assessment, mandatory corroboration, and relocation

Add to `tests/unit/test_lineage_inference_store.py`:

| Test ID | Required proof |
|---|---|
| `T-CPI-40` | The full status/evidence mapping table (section 1), one row per status, including `changed_sources` for target-only, parent, and mixed mismatches. |
| `T-CPI-41` | Deleting the freshness index at **both** locations yields `freshness_unknown`, not `current_at_last_analysis` — the exact gate-1 revival repro. |
| `T-CPI-42` | With no legacy file present, a state index whose `targets` lacks this child yields `freshness_unknown`; an invalid, symlinked, or oversized index yields `freshness_unknown`. (The case where a legacy entry *does* exist for that child is `T-CPI-53`, which must not yield `freshness_unknown`.) |
| `T-CPI-43` | Appending one blank line to the target transcript yields `stale_sources` with `changed_sources == ("target",)`; the record is still readable and its parent ID unchanged. |
| `T-CPI-45` | A record with more than `MAX_SOURCE_FINGERPRINTS` entries is rejected as an invalid store. |
| `T-CPI-50` | `index_freshness_path` resolves under `XDG_STATE_HOME`, `_legacy_index_freshness_path` under `XDG_CACHE_HOME`; `update_index_freshness` writes this child's entry to the state path via `atomic_write_json` and, when the legacy file holds a key for the same child, removes **only that key** from the legacy file's `targets` by read-modify-atomic-rewrite. The legacy file still exists afterwards. |
| `T-CPI-51` | `assess_inference` reads a state-path entry when present; when the state file is entirely absent, it falls back to a legacy cache-only entry and evaluates it identically (not `freshness_unknown`). |
| `T-CPI-53` | **The per-entry migration repro.** A state file that exists and holds entries for other children, but no entry for this child, still falls back to that child's legacy entry and evaluates it normally — it does **not** yield `freshness_unknown`. Re-inferring one session therefore does not invalidate any other un-migrated session. A structurally invalid state file (symlink, oversized, non-JSON, wrong `version`, non-dict `targets`) still yields `freshness_unknown` without consulting the legacy path. |
| `T-CPI-54` | A legacy file holding entries for several children loses exactly the one child's key on that child's `update_index_freshness`; every other child's legacy entry is byte-identical afterwards and still resolves through the fallback. The legacy file is never unlinked, and a pop that empties `targets` rewrites the file with an empty `targets` dictionary. |
| `T-CPI-55` | With an entry for the same child in **both** locations: `assess_inference` uses the state-path entry (proved by giving the two entries different `candidate_universe_digest` values); `update_index_freshness` leaves only the state-path entry; `remove_index_freshness` removes the key from **both** and returns `True`. |
| `T-CPI-56` | Deterministic lock ordering. With `registry_lock` instrumented to record acquisition order, both `update_index_freshness` and `remove_index_freshness` acquire the state-path lock before the legacy-path lock and release in reverse order, on every path that touches both files. Asserted by recorded order, not by a timing race. |

Run the focused file and capture RED before touching production code. Then in
`src/agent_fork/lineage_inference_store.py` (section 1, 2, and 2a above):

1. add `FreshnessStatus`, `EvidenceStatus`, `ChangedSource`, `InferenceAssessment`,
   and `assess_inference()`, in the fixed five-step evaluation order (section 2);
2. re-express `inference_freshness()` as `assess_inference(...).status` and
   `inference_is_current()` as `assess_inference(...).satisfies_strict_parent`,
   keeping both signatures so no existing caller changes;
3. add `MAX_SOURCE_FINGERPRINTS = 1_024` and its rejection in `_decode`;
4. change `index_freshness_path()` to call `xdg_path(env, "XDG_STATE_HOME",
   ".local/state", "agent-fork", "claude-lineage-freshness.json")`; add
   `_legacy_index_freshness_path()` with the old `XDG_CACHE_HOME` arguments;
5. in `assess_inference`'s freshness-index step, resolve the entry **per
   child**: read the state path first and fall back to the legacy path whenever
   the state path yields no usable entry for this `child_session_id` — file
   absent, key absent, or entry unusable — never only when the state file as a
   whole is absent. A structurally invalid index at either location still
   yields `freshness_unknown` outright;
6. in `update_index_freshness`, acquire the state-path lock then the
   legacy-path lock, `atomic_write_json` this child's entry to the state path,
   then pop **only this child's key** from the legacy file's `targets` and
   rewrite that file (skipping the rewrite when the file is absent or the key
   is not present, and writing an empty `targets` rather than unlinking when
   the pop empties it). Swallow `OSError`/`ValueError` from the legacy rewrite
   without counting it as a freshness write failure, per section 2a — the
   state-path write already succeeded. Never unlink the legacy file.

Run `tests/unit/test_lineage_inference_store.py` until GREEN. No other file
changes in this step.

### Step 2 — RED and GREEN: complete freshness-entry deletion

Add to `tests/unit/test_lineage_inference_store.py`:

| Test ID | Required proof |
|---|---|
| `T-CPI-44` | `remove_index_freshness` removes only the named key from the state path, leaves every other child's entry intact, is a no-op returning `False` when the key is present in neither location, never unlinks either file, and leaves mode `0o600`. |
| `T-CPI-52` | `remove_index_freshness` removes the entry from the state path when present there, from the legacy cache path when present there, and from **both** when present in both — never from only one — returning `True` whenever either location changed. |

Add `remove_index_freshness()` to `lineage_inference_store.py` per section 6:
acquire the state-path lock then the legacy-path lock, decode each file, pop
the key from both, and `atomic_write_json` each file that actually changed.
Never unlink either file. Run until GREEN.

### Step 3 — RED and GREEN: session `parent_inference` surfacing

Add to `tests/unit/test_session.py`:

| Test ID | Required proof |
|---|---|
| `T-SES-48` | A stale-source record produces `parent_inference.status == "last_known_good"` with the recorded parent ID, while `parent_session` stays null and `lineage.status` stays `not_found`. |
| `T-SES-49` | The `parent_inference` object is present for all seven statuses with the exact field shape in section 3's field-shape table, including `not_consulted` when a planned claim exists and for Codex, and coexists with the existing `transcript` object without displacing it. It asserts specifically that `superseded` carries `freshness == "stale_algorithm"` while `parent_session_id`, `analyzed_at`, and `changed_sources` are null, null, and empty — the same three fields nulled for `not_consulted`, `absent`, and `unreadable`. |
| `T-SES-50` | `session validate --has-parent` still fails with only a `last_known_good` or `freshness_unknown` record, and passes after a re-inference makes it `current`. This is the strict-validation guarantee. |

In `session.py` (section 3): add `parent_inference` to `SessionInspection`
(alongside the existing `transcript` field, at every construction site, per
the 2026-08-20 revalidation note above); rewrite the Claude branch's stale
handling to call `assess_inference()` instead of discarding the record; add
`document()`'s `parent_inference` key. Do not touch `validate_session()` —
`T-SES-50` proves it needs no change, since `parent_session` stays null for
every non-`current` status.

### Step 4 — RED and GREEN: session and delete CLI output

Add:

| Test ID | File | Required proof |
|---|---|---|
| `T-CLI-36` | `tests/cli/test_session.py` | Human and JSON session output for `last_known_good` and `freshness_unknown`, including the exact notice and the rerun command, with no corpus discovery, no cache write, and no freshness write during `session`. The human `parent inference:` line appears immediately after the `lineage:` line and before every `notice:` line, asserted by output line order. |
| `T-CLI-37` | `tests/cli/test_claude_parent.py` | `delete --source inferred` reports every additive field and actually removes the freshness entry; `delete --source planned` with a surviving inferred record retains the freshness entry and says so. |
| `T-CLI-39` | `tests/cli/test_claude_parent.py` | Deletion ordering and its fault tolerance. `delete --source inferred` calls `remove_index_freshness` **before** `remove_inference`, proved by recorded call order. With `remove_inference` monkeypatched to raise after the freshness removal committed, the surviving state is the inference record with no freshness entry, and a following `session` reports that record as `parent_inference.status == "freshness_unknown"` with `parent_session` still null — never as `current`. |

In `cli.py`: add the `parent_inference` human-output line immediately after the
`lineage:` line and before the `notice:` loop, escaping every store-derived
scalar with `agent_fork.output.terminal_text` (section 3); compose
`remove_index_freshness` into the `delete` action per section 6, **freshness
entry first, then the record**, for the `inferred` branch always and for the
`planned` branch whenever the freshness entry is due for removal (that is, when
no inferred record for the same child survives); add the additive result
fields; extend `emit()`'s human branch to print list-valued keys one per line
for `notices`.

### Step 5 — RED and GREEN: bounded screen cache

Add to `tests/unit/test_claude_parent_inference.py`:

| Test ID | Required proof |
|---|---|
| `T-CPI-46` | Three successive appends plus re-inference leave exactly one shard for that stem; the shard name is `{stem}.json`. |
| `T-CPI-47` | The sweep removes the legacy v2 tree once, removes orphan stems, honors the age and byte caps oldest-first, respects the marker interval, counts failures without raising, and never touches the freshness index at either location or anything else under the state store. It also proves the two safety guards: a v2 root that is a symlink or is owned by another user is left completely untouched even though the v3 root passed its own check; and a dot-prefixed in-flight temporary named `.{stem}.json.<random>` newer than `CACHE_TEMP_GRACE_SECONDS` survives the sweep while an identically named one older than the grace period is removed. The `.sweep` marker itself is never removed. |
| `T-CPI-49` | A freshness-index write failure increments `freshness_write_failures` **and** `cache_write_failures` — the existing aggregate keeps counting freshness failures exactly as it does today — and still returns a result. A screen-shard write failure increments only `cache_write_failures`, leaving `freshness_write_failures` at zero. |

Add to `tests/cli/test_claude_parent.py`:

| Test ID | Required proof |
|---|---|
| `T-CLI-41` | With the freshness index unwritable, `infer --current --record` succeeds, records the inference, and emits the freshness-write-failure notice in its analysis document; the same run **without** `--record` records nothing and emits **no** such notice, while `work.freshness_write_failures` is non-zero in both. Proves the notice is composed at the CLI layer, where recording is decided. |

In `claude_lineage_inference.py` (section 4): move `_cache_root()` to
`claude-lineage-index-v3`; flatten the shard filename to `{path.stem}.json`;
add `sweep_cache()` with the marker-gated, bounded, six-step sweep including
the independent v2-root ownership and symlink check and the age guard on every
non-`<uuid>.json` entry; call it once from `ClaudeLineageCorpus.__init__` after
`discover()`; add `work.freshness_write_failures` as an **additional**
increment on the freshness-index write path in `infer_one().finish()`, leaving
the existing `work.cache_write_failures` increment in place unchanged; add the
six new `Work` counters. In `cli.py`: append the freshness-write-failure notice
to the per-target document when `work.freshness_write_failures` is non-zero and
that target was actually recorded. Independent of steps 1-4; may run before or
after them.

### Step 6 — RED and GREEN: structured corpus-limit refusal

Add:

| Test ID | File | Required proof |
|---|---|---|
| `T-CPI-48` | `tests/unit/test_claude_parent_inference.py` | Each of `max_files`, `max_entries`, `max_total_bytes`, and `max_candidates` raises `CorpusLimitError` with exact `limit`, `allowed`, `observed`, and `scope` — `corpus` for the first three, `target` for `max_candidates`. |
| `T-CPI-57` | `tests/unit/test_claude_parent_inference.py` | With `max_seconds` driven to expiry, `infer_one` raises `TimeoutError` at its deadline guard, and the CLI-boundary mapping function turns that exception into the structured shape with `limit.name == "max_seconds"`, `scope == "target"`, and the configured `allowed` value. Covers the limit R6 lists but that no existing or previously planned test exercised, and asserts the mapping explicitly because `TimeoutError` derives from `OSError` and is therefore never caught by a `CorpusLimitError` clause. Its end-to-end behavior under `--all` is `T-CLI-40`. |
| `T-CLI-38` | `tests/cli/test_claude_parent.py` | Exceeding a **whole-corpus** limit (`max_files`) with `infer --current`, `--session-id`, `--all`, and `--record` exits 3 with `claude_parent_incomplete_analysis`, emits one JSON error on stderr and nothing on stdout, opens no bulk spool, and writes no inference, freshness, or registry state. |
| `T-CLI-40` | `tests/cli/test_claude_parent.py` | Per-target limits under `--all`. With `max_candidates` and then `max_seconds` tripped on one target of several, under `--json` and with `--record-all`: the run exits 3; the failing target's own typed incomplete-analysis document appears in the bulk output with `scope == "target"` and not as an untyped `"unavailable"` document; that target is not recorded; every other target is processed and recorded normally; and the spool is closed cleanly. Also asserts the same single-target shape for `--current`. |

In `claude_lineage_inference.py` (section 7): add `class CorpusLimitError(ValueError)`;
raise it at the five bare-`ValueError` limit sites — four in `discover()`
(`max_entries` twice, `max_total_bytes`, `max_files`, all `scope: "corpus"`)
and `max_candidates` in `infer_one()` (`scope: "target"`). In `errors.py`: add
`claude_parent_incomplete_analysis` to `ERROR_CATALOG` and
`ClaudeParentIncompleteAnalysisError(ClaudeParentError)` **with the forwarding
`__init__`**, matching the existing `ClaudeParentNotRecordableError` subclass
pattern exactly — without it every instance publishes
`claude_parent_unavailable`. In `cli.py`, honor the two scopes separately:
guard the `ClaudeLineageCorpus(environment)` construction at line 859 so a
whole-corpus limit refuses the entire invocation before any spooling; and add
`except (CorpusLimitError, TimeoutError)` to the per-target loop **ordered
before** the existing generic `except Exception`, so a per-target limit yields
that target's typed incomplete-analysis document while the batch continues and
still exits 3 through the existing `failures` counter. Raise the typed error
with the `analysis`/`limit`/`remediation` document from section 7. Independent
of every other step.

### Step 7 — RED and GREEN: cleanup disclosure

Add to `tests/cli/test_cln.py`:

| Test ID | Required proof |
|---|---|
| `T-CLN-25` | Real and `--dry-run` cleanup of a fork with a lineage claim disclose the retained claim, inferred record, freshness entry, store paths, and the exact source-qualified removal command, and remove none of them. |
| `T-CLN-26` | Cleanup of a target with no matching claim (zero retained records, no command lines) and cleanup when a store read fails both succeed with the neutral notice and an empty `retained_metadata`. |
| `T-CLN-27` | `retained_metadata` actually reaches machine output: `cleanup --json` emits it alongside `notices`, proving `cli.py`'s hand-assembled cleanup document was extended and not only the `CleanupResult` dataclass. |
| `T-CLN-28` | Removal commands are per record and source-qualified. Several matched claims produce one command per retained record; a child holding **both** a planned claim and an inferred record produces two command lines, one `--source planned` and one `--source inferred`, and neither omits `--source` — an unqualified command would be rejected as ambiguous. Store-derived session IDs and paths in the human notices are escaped with `_escape_terminal_text`, proved with a control character embedded in a stored value. |

In `cleanup.py` (section 5): correlate `read_lineage()` claims by resolved
`worktree == plan.worktree`; for each matched `child_session_id`, check
`read_inferences()` and the freshness index (state path, then legacy, per
child); preserve the existing generic notice verbatim as the first notice, then
append the disclosure notices, escaping every store-derived value with the
module's existing `_escape_terminal_text` import; add
`CleanupResult.retained_metadata` carrying `removal_commands` as a list of
per-record, source-qualified objects.

**This step also edits `cli.py`.** `CleanupResult` has no `document()` and
cleanup's JSON is hand-assembled at `cli.py:1115-1121`, so the new field must
be added there too — `"retained_metadata": result.retained_metadata` beside the
existing `"notices"` — or it never reaches machine output. Depends on step 1 for
the state-path helper and step 5 for the `v3` cache-directory name used in the
disclosure sentence about shared cache shards.

### Step 8 — Documentation, conformance, and repository gates

Apply the "Documentation and conformance delta" section below. Run focused
tests after each GREEN step above, then:

```bash
just all
just check-matrix
just strict-collect
just clean-install
```

Then obtain the gate-6 adversarial implementation review and an independent
Codex second lens against the complete A10 diff. Absorb only findings promised
by this design or introduced by A10; route unrelated findings under P02 Gate
6.

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
  the new cache directory name, the freshness-index relocation and its lazy
  per-child-session-ID migration (section 2a), and the delete report fields.
- `REQUIREMENTS.md`: amend the Claude-inference and cleanup requirements to
  describe last-known-good disclosure, mandatory corroboration, bounded cache,
  complete deletion, and the typed corpus-limit refusal.
- `CONFORMANCE.md`: one CLI Standard review-history row; refresh affected
  requirement evidence. No new waiver is expected.
- `docs/testing/TEST-MATRIX.md`: all **31** new IDs — 18 `T-CPI-40` through
  `T-CPI-57`, 3 `T-SES-48` through `T-SES-50`, 6 `T-CLI-36` through
  `T-CLI-41`, and 4 `T-CLN-25` through `T-CLN-28` — one implementation per
  live row, and the asserted row-count line refreshed from 413 to **444**
  (413 + 31) only after every row exists.

CLI Standard review scope:

| Rule | A10 requirement |
|---|---|
| R6.1 | Keep the new corpus-limit refusal in exit code 3. |
| R7.2, R9.3 | `parent_inference`, `retained_metadata`, new `work` counters, and new delete fields are additive; `lineage.status`, `fork_command.status`, `parent_session`, and `relationship.status` value sets are unchanged. `work.cache_write_failures` keeps its current meaning and its current increments — `work.freshness_write_failures` is added alongside it, never carved out of it — so no existing machine field changes semantics. |
| R7.6 | Session and cleanup results stay observational on stdout. |
| R7.8 | One JSON error object for the incomplete-analysis refusal. |
| R7.12 | Publish `claude_parent_incomplete_analysis`. |
| R8.6 | Prove `cleanup --dry-run` and `session` perform no metadata mutation. |
| R9.10 | Every non-current freshness status names its remediation command. |
| R9.14 | Permanent conformance rows in the existing matrix. |

Groups not affected: command structure and vocabulary, configuration
precedence, networked behavior, streaming, plugins, interactive setup. The
flag group is N/A: A10 adds no flag to any command (owner decision 2).

## Plan-review outcome

Two independent read-only lenses reviewed this implementation plan before any
production code was written; both returned **APPROVE-WITH-CHANGES**:

1. An Opus phase-gate review, verified against the live source in this
   worktree at commit `5fa8aeb`.
2. An independent Codex second lens, run against the same checkout.

Both lenses independently found the **same most-severe defect**: the
freshness-index migration in section 2a was written per *file* rather than per
*entry*. Because one shared JSON file holds every session's entry, the original
read rule ("fall back to the legacy path only when the state file is absent")
would have mass-invalidated every un-migrated session the moment any single
session was re-inferred, and the original write rule ("delete the legacy file
for that session") named a per-session file that does not exist. That is the
exact spurious-invalidation class A10 exists to eliminate. Section 2a is now
keyed on `child_session_id` throughout: per-child read fallback regardless of
the state file's other contents, per-key removal from the legacy `targets`
dictionary by read-modify-atomic-rewrite, removal from both locations on
delete, and a fixed state-before-legacy lock order for every cross-file
mutation, since `registry_lock` derives a different lock per path.

Each lens also required distinct further changes, all of them incorporated:

- The Opus lens required the forwarding `__init__` on
  `ClaudeParentIncompleteAnalysisError`; the whole-corpus versus per-target
  split of the five limits and the `except` clause ordering that split
  implies; a single decided location for the human `parent inference:` line;
  `max_seconds` test coverage; removal of the stale opt-in-pruning-flag
  language; one reconciled step-numbering scheme; the true new-ID count and
  matrix total; the two wrong test-file citations; a temp-file age guard that
  matches the real `.{name}.<random>` naming; and terminal-text escaping for
  the store-derived values in cleanup's new notices.
- The Codex lens required wiring `retained_metadata` through `cli.py`'s
  hand-assembled cleanup JSON rather than `cleanup.py` alone; per-record,
  source-qualified removal commands in place of one global string; reversing
  the delete order so the freshness entry is removed before the record;
  preserving `work.cache_write_failures` as the unchanged aggregate while
  adding `freshness_write_failures` as a purely additive counter; placing the
  freshness-write-failure notice at the CLI layer, where recording is decided;
  an explicit field shape for `superseded`; an independent ownership and
  symlink check on the legacy v2 cache root before deleting anything under it;
  and deferring the `claude-parent show` freshness idea out of this sweep.

Every required change from both reviews is incorporated in this document, and
every review claim about the current source was re-verified against this
worktree before being applied. That re-verification refined exactly one review
claim without changing its conclusion: `atomic_write_json` has **two** temp-file
naming shapes, not one. Its own default prefix is `.{path.stem}-`, and the
cache-shard call site overrides it with `prefix=f".{shard.name}."`
(`claude_lineage_inference.py:488-493`), giving `.{stem}.json.<random>`. Both
reviews cited only the second shape. Neither ends in `.tmp`, so the age guard in
section 4 is written to cover **every** non-`<uuid>.json` entry rather than any
name pattern, which is strictly safer than matching either shape. Neither review requested a scope expansion, a
new owner decision, or a change to strict parent validation, the default
cleanup retention policy, or any existing v1 machine-field semantics. Gate 4 is
therefore complete and implementation may proceed test-first.

## Implementation evidence

**Complete.** All eight steps were implemented test-first, in the dependency
order the Sequencing table specifies: step 1, then steps 2 and 3, then step 4,
then steps 5 and 6 (in either order), then step 7, then step 8. Seven
production files changed — `lineage_inference_store.py`, `session.py`,
`claude_lineage_inference.py`, `cli.py`, `errors.py`, `cleanup.py`, and
`bulk_output.py` — the last one not originally named in the plan; see the
deviation below. Six test files changed before any of them:
`tests/unit/test_lineage_inference_store.py`,
`tests/unit/test_session.py`, `tests/unit/test_claude_parent_inference.py`,
`tests/cli/test_session.py`, `tests/cli/test_claude_parent.py`, and
`tests/cli/test_cln.py`. All 31 planned test IDs were implemented; each
step's RED run failed for the missing name or behavior the step introduces
(`AttributeError`/`ImportError`/plain assertion mismatches), never for an
unrelated reason, before its GREEN change landed.

One planned test was written after its production code rather than before it:
`T-CLI-41` (the freshness-write-failure notice at the CLI layer). Step 5's
GREEN change added the `work.freshness_write_failures` counter and its test
coverage (`T-CPI-49`) correctly test-first, but the CLI-layer notice-append
half of that same step — explicitly specified in the plan's step 5 prose —
was skipped in the first pass and only caught during the step-8 completeness
sweep before matrix/documentation work, not by a human reviewer. The gap was
closed by writing `T-CLI-41` and confirming it failed for the right reason
(the notice was simply absent) before adding the four-line notice-append in
`cli.py`. Recorded here rather than smoothed over, since the discipline this
document exists to enforce is exactly "watch it fail before you trust it
passes."

**One plan-vs-reality deviation, resolved during step 6.** The design's
worked example for a per-target limit under `--all` did not anticipate that
`BulkSpool.append()` routes every document through `compact_result()`
(`bulk_output.py`), a strict field-projection function that silently drops
any key outside its fixed set. The typed `limit` object this design adds to
an incomplete-analysis document was being dropped on the bulk path — `T-CLI-40`
caught this immediately (the per-target document showed
`relationship.status: "incomplete"` with no `limit` key, indistinguishable
from the corpus's own pre-existing `work.corpus_incomplete` status). Fixed by adding an
explicit, bounded `limit` passthrough to `compact_result()`, following the
existing precedent there for the `error` key. This is a small, necessary
addition the design did not name because it did not anticipate the
bulk-output projection layer; it does not change any decision in this
document.

A second small, necessary correction: `T-CPI-23`, an existing pre-A10 test,
asserted on the literal old error text `"entry limit"` via regex match against
`str(error)`. `CorpusLimitError`'s new message format no longer contains that
exact substring. That assertion was testing incidental wording, not the
underlying requirement (`max_entries` enforcement), so it was updated to check
`CorpusLimitError.limit == "max_entries"` directly — a stronger, more direct
assertion of the same requirement, not a weakening.

Repository gates after the gate-5 matrix and documentation updates (superseded
by the gate-6 corrections below):

| Gate | Result |
|---|---|
| `just all` | **pass** — Ruff format, Ruff lint, `ty`, version sync, 542 tests passed, 1 skipped, 9 deselected |
| `just check-matrix` | **pass** — 444 rows across 20 groups, one collected item per live row |
| `just strict-collect` | **pass** — clean collection across every test directory, no unknown markers or import errors |
| `just clean-install` | **pass** — sdist and wheel built; disposable venv install and smoke check completed |

## Gate-6 findings and corrections

Two independent lenses reviewed the real committed diff (`d82ddf8`), both
using empirical probes and mutation testing against the live worktree rather
than reading code alone, and both returned **APPROVE-WITH-CHANGES**: 8
required-before-merge findings from the Opus lens, 10 from the independent
Codex lens, substantially overlapping. The core architecture held up under
both — the per-child migration mechanism, the lock ordering, the delete
ordering, the `except` clause ordering, the sweep's `.sweep` exemption, and
counter additivity were all independently verified correct by direct
empirical proof (mutation testing that killed the right assertions when a
production line was reverted). What both lenses found were implementation
gaps around that correct core: two genuine crash bugs, several places where
the "never fails, always degrades neutrally" promise wasn't actually
enforced, one cumulative-counter false positive, one silently misrouted error
code, one misleading corpus-vs-target label, and several tests whose
assertions didn't actually prove what their matrix row claimed.

All required findings were fixed test-first, each with a genuine RED
confirmation before its GREEN change:

1. **`_read_targets()` crashed with `AttributeError` on non-dict top-level
   JSON** (a malformed freshness-index file), which propagated through
   `assess_inference`, `remove_index_freshness`, and — most severely —
   `cleanup`'s new disclosure step, meaning a corrupted advisory cache file
   could block a destructive worktree removal that pre-A10 code was
   completely unaffected by. Fixed by rejecting non-`dict` JSON in
   `_read_targets` explicitly, tested at both the state and legacy paths
   through all four call sites (`T-CPI-58`).
2. **A malformed fingerprint entry (no `:` separator) crashed with
   `UnboundLocalError`** in `assess_inference`'s per-file loop — the `except`
   block referenced a variable that was never bound when the unpacking itself
   was what failed. Fixed by validating the separator before the `try`, so
   the exception handler's variable is always bound; resolves to
   `stale_sources` with `changed_sources == ("other",)` (`T-CPI-59`).
3. **A broken symlink at either freshness-index path was treated as an
   absent (empty) store**, silently proceeding as "no recorded freshness
   data" instead of the codebase's existing symlink-rejection convention.
   Fixed by checking `is_symlink()` before `exists()` (`T-CPI-60`).
4. **The cache sweep was neither bounded nor confined the way the design
   promised**: `list(root.iterdir())` materialized every entry before the
   `CACHE_SWEEP_MAX_ENTRIES` bound was checked, defeating a "bounded" sweep;
   the one-time legacy-`v2` removal used recursive `rglob("*")`, contradicting
   the design's explicit immediate-children-only boundary; and the `.sweep`
   marker's `stat()`/touch could follow a symlink. Fixed by switching to a
   lazily-iterated `os.scandir()` that stops reading before the bound is
   exceeded, immediate-children-only legacy removal (an unexpected
   subdirectory is left alone and the final `rmdir` simply fails, counted
   rather than destroying anything beneath it), and an `O_NOFOLLOW` open for
   the marker (`T-CPI-47` corrected, plus `T-CPI-61` through `T-CPI-67`
   covering the byte cap, age cap, bounded scan, foreign/symlinked legacy
   root, and marker symlink safety individually).
5. **The freshness-write-failure CLI notice fired as a false positive on
   every target after the first failure in an `--all` run**, because it
   checked the corpus-wide `Work` object's counter for merely being nonzero
   rather than whether *this* target's call caused a new failure. Fixed by
   snapshotting the counter immediately before and after each target's
   `infer_one()` call.
6. **Cleanup disclosure had three defects**: an invalid freshness store was
   silently converted to an empty dict instead of the design-promised neutral
   notice; a legacy-only entry was reported as if it lived at the new state
   path; and session IDs/paths were terminal-escaped before being placed in
   *JSON* output, which would corrupt a value a script pastes back into a
   command. Fixed by propagating "couldn't read" as a distinct signal
   (`T-CLN-31`), reporting each entry's real location (`T-CLN-30`), and
   keeping `retained_metadata` raw with escaping applied only to the human
   `notices` strings — proved with an actual embedded control character, not
   a plain UUID that would pass either way (`T-CLN-29`).
7. **`analyzed_at` was not escaped on the human `parent inference:` output
   line**, unlike its neighbors on the same line. Fixed by wrapping it in
   `terminal_text()` too.
8. **The interactive delete confirmation prompt was missing the two lines
   the design specified** — what will be removed and what will remain — this
   section of `cli.py` had not been touched at all. Added both lines.
9. **`retained_planned_record` was hardcoded to `False`** in the `inferred`
   delete branch, never checking whether a planned claim actually survives
   for the same child. Fixed to compute it via `find_lineage(...)`.
10. **A single-target (non-`--all`) limit-breach failure surfaced the wrong
    error code** — the typed per-target handling was correct, but the
    post-loop error-raising logic downgraded it to the generic
    not-recordable/unavailable classes instead of
    `claude_parent_incomplete_analysis`. Fixed by tracking whether the
    failure was specifically a limit breach and raising the typed error
    class when it was (`T-CLI-38` extended to cover this end to end; a
    dedicated `T-CLI-42` added because the original `max_files` scenario is a
    *whole-corpus* limit that never touched this code path in the first
    place — the bug was specifically in the *per-target* `max_candidates`
    routing for a single-target invocation).
11. **`max_seconds` reported a misleading `scope: "target"`.** It bounds one
    shared corpus-wide clock (pre-existing, not something A10 should turn
    into independent per-target budgets — that would be a real architecture
    change, not a bug fix), so once it expires, every subsequent target in an
    `--all` run reports "this target ran out of time" when the corpus-wide
    clock actually expired, possibly before that target was even reached.
    Changed the reported scope to `"corpus"`, leaving `max_candidates`
    correctly at `"target"` (`T-CPI-57` updated; `T-CLI-43` added for the
    `--all` case).
12. **`TEST-MATRIX.md`'s asserted total was wrong** (`413 + 31 = 444`, not
    recounted per the header's own instruction). Corrected to the actual
    count after every new row, including the sixteen added during this
    gate-6 pass.
13. **Eight tests had gaps between what they asserted and what their matrix
    row claimed**: `T-CLI-38` asserted only exit code and non-recording for
    one invocation shape, despite the new stable error code having zero
    coverage anywhere in the suite — rewritten to assert the code, empty
    stdout, and one JSON error object across `--session-id`, `--record`,
    `--current`, and `--all`. `T-CLN-28`'s escaping proof embedded no control
    character, so it passed even with escaping removed — the genuine proof
    moved to the new `T-CLN-29`. `T-CPI-47` expected the recursive-deletion
    bug as correct behavior — corrected to the design's immediate-children
    boundary and extended to actually exercise the byte cap, age cap, and
    failure counter, none of which appeared anywhere in the suite before.
    `T-CPI-49` covered only the freshness-failure half of the additivity
    claim — the shard-only half is now `T-CPI-68`. `T-CPI-54` asserted
    `isinstance(..., dict)` after a pop that empties the dict, which passes
    even if the pop never ran — now asserts the real value is `{}`.
    `T-SES-49` claimed all seven statuses but never exercised `unreadable` —
    added. `T-CLI-40` claimed `max_seconds` coverage it didn't have and
    checked only that an unaffected target's status "wasn't incomplete"
    rather than confirming what actually happened to it — split into
    `T-CLI-40` (strengthened `max_candidates` case) and the new `T-CLI-43`
    (`max_seconds`, since that scenario has no plausible "unaffected target"
    given the shared-clock finding above). `T-CLN-25` claimed exact store
    paths and exact removal commands without asserting them — now does.

One item from the merged review findings was corrected in scope rather than
implemented as literally specified: finding 10's fix instruction named
`T-CLI-38` as the vehicle for proving the single-target routing fix, but
`T-CLI-38`'s existing `max_files` scenario is a whole-corpus limit that
already routed correctly before this pass — it never exercised the bug.
`T-CLI-38` was still strengthened as instructed (real error-code assertion,
`--current`/`--all` coverage), and a separate `T-CLI-42` was added
specifically for the per-target `max_candidates` case, which is what
actually exercises finding 10's fix. Confirmed by temporarily reverting the
`cli.py` fix and observing `T-CLI-42` fail for the exact predicted reason
before restoring it — see the sixteen new IDs below for the equivalent
proof pattern applied throughout.

Sixteen new test IDs were added during this gate-6 pass, beyond the original
31: `T-CPI-58` through `T-CPI-68` (11), `T-CLI-42` and `T-CLI-43` (2), and
`T-CLN-29` through `T-CLN-31` (3). Total new A10 test IDs: 47. `TEST-MATRIX.md`
now asserts 488 total rows (472 pre-existing + 16 net new to this branch,
matching the review's own independently recomputed pre-fix count of 472).

Repository gates after the gate-6 corrections, matrix, and documentation
updates:

| Gate | Result |
|---|---|
| `just all` | **pass** — Ruff format, Ruff lint, `ty`, version sync, 558 tests passed, 1 skipped, 9 deselected |
| `just check-matrix` | **pass** — 488 rows across 20 groups, one collected item per live row |
| `just strict-collect` | **pass** — clean collection across every test directory, no unknown markers or import errors |
| `just clean-install` | **pass** — sdist and wheel built; disposable venv install and smoke check completed |

## Gate-6 confirmation round

The fix commit above (`fc35365`) was itself reviewed a second time by the
same two independent lenses, against the real diff rather than prose, per
this repository's standing rule that a phase gate before a mutating sweep
needs both lenses to concur — the same discipline applied to gate 4's plan
review, now applied to the corrected implementation. Both again used
empirical probes and mutation testing, not just reading code, and both again
returned **APPROVE-WITH-CHANGES**: this is expected convergence, not a sign
of a runaway process — each round found fewer and smaller defects than the
last.

Three findings were independently confirmed by both lenses, the highest-
confidence class:

- `T-CPI-60` (the broken-symlink-is-invalid test) asserted only the
  downstream `assess_inference` status, which is `freshness_unknown` whether
  the symlink is correctly rejected or incorrectly treated as absent — the
  test could not distinguish the fix from the bug it was meant to prove.
  Fixed by asserting `_read_targets(path) is None` directly at both
  locations; confirmed to fail when the `is_symlink()`-before-`exists()`
  ordering is reverted.
- `retained_planned_record: true` had zero regression coverage — the only
  existing delete test covers the case with no surviving planned claim,
  where `false` is correct either way. Added `T-CLI-44`: a child holding
  both a planned claim and an inferred record, deleted via `--source
  inferred`, asserting the field is `true` and that a follow-up `list`
  confirms the claim survives; confirmed to fail when the computation is
  reverted to a hardcoded `False`.
- The per-target freshness-write-failure notice fix had zero regression
  coverage — the existing single-target test cannot distinguish a per-target
  delta check from the original shared-counter bug, since with one target
  they are mathematically identical. Added `T-CLI-45`: two independently
  recordable transcript pairs in one `--all --record-all` run, only the
  first target's `update_index_freshness` call failing; confirmed both that
  only the first target's document carries the notice under the fix, and
  that reverting the delta check back to a raw nonzero check makes both
  targets carry it (the exact false-positive the original fix addressed).

Two genuinely new defects were caught — introduced by the gate-6 fix pass
itself, which is exactly the risk a confirmation round exists to catch:

- **Command injection in cleanup's generated removal commands** (`cleanup.py`).
  The `retained_metadata.removal_commands[].command` string interpolated the
  raw `session_id` directly; a hostile or corrupted session ID containing a
  newline or shell metacharacters could make the suggested copy-paste command
  execute something other than what it displays. Fixed with `shlex.quote()`
  around the identifier in the command string only — the JSON `session_id`
  field itself stays raw, per the existing raw-JSON/escaped-human split.
  `T-CLN-32` embeds an actual hostile identifier and round-trips the command
  through `shlex.split()` to confirm it parses back as one argument.
- **The cache-sweep marker's symlink-safe open could block indefinitely on a
  FIFO** (`claude_lineage_inference.py`). `O_NOFOLLOW` correctly refuses a
  symlinked `.sweep` marker, but opening a named pipe `O_WRONLY` without
  `O_NONBLOCK` blocks forever waiting for a reader that will never arrive,
  hanging the whole invocation. Fixed by adding `O_NONBLOCK` (so a FIFO open
  fails immediately with `ENXIO`) and an `fstat()`-based regular-file check
  after opening, rejecting anything else as a fault. `T-CPI-70` places a real
  FIFO at the marker path and bounds the sweep call in a subprocess with a
  timeout, so a regression fails the test instead of hanging the suite —
  confirmed to actually hang (subprocess killed after the timeout) against
  the pre-fix code.

One structural defect this round's fix pass introduced in the process of
fixing another: `_retained_metadata`'s original degrade-on-invalid-freshness
path returned the same neutral shape regardless of whether a *real,
independently-readable* lineage claim existed for the target — an unrelated
fault in one store suppressed disclosure of information from a completely
different, healthy store. Fixed by nulling only the freshness-specific parts
of the disclosure on a freshness-read failure, never the whole result;
`T-CLN-33` and the corrected `T-CLN-31` (which uses `_forked`'s own baseline
lineage claim, previously masked by this exact bug) both cover it.

Two smaller items from the confirmation round, both cheap and folded in:
`assess_inference`'s per-file fingerprint loop had narrowed its caught
exceptions from `(OSError, ValueError)` to `OSError` during an earlier fix,
so a fingerprint path containing a NUL byte (which makes `Path.stat()` raise
`ValueError`, not `OSError`) now escaped uncaught instead of degrading to
`stale_sources` like every other malformed-path case — restored, covered by
`T-CPI-69`. And `session claude-parent delete` had no fault tolerance around
`remove_index_freshness()` at all — a corrupted freshness index at the
target's own location made the *entire* delete fail with a generic
`runtime_error`, meaning a user could not remove their own primary record
because an unrelated advisory cache file was unreadable, contradicting the
"an advisory store must never block a real operation" posture already
applied to `cleanup`. Fixed by catching the `ValueError`, reporting
`removed_freshness_entry: false` with an explanatory notice, and still
removing the primary record; `T-CLI-47` confirms the delete still succeeds
and the record is genuinely gone.

**One item from the confirmation round's fix list was judged impractical and
is honestly left uncovered rather than forced.** The interactive delete
confirmation prompt's consent text (added during the first gate-6 pass, item
8 above) has no test in this round: proving its exact content requires a
PTY harness with *both* stdin and stderr attached to a terminal
simultaneously (the delete action's prompt-eligibility gate checks both),
and this codebase's existing `pty_run` test helper attaches only one file
descriptor to a pty at a time. Building genuine dual-TTY test infrastructure
for one line of prompt text was judged disproportionate; the prompt's
substantive behavior (that some form of consent is required, and that
`--yes`/`--no-input` control it) is already covered elsewhere, and the
production code itself was directly verified by hand.

Six new test IDs were added during this confirmation round beyond the 47
from the two gate-6 passes combined: `T-CLN-32`, `T-CLN-33`, `T-CPI-69`,
`T-CPI-70`, and `T-CLI-44` through `T-CLI-47` (8 total — `T-CLI-45`/`46`/`47`
plus `T-CLI-44`). Total new A10 test IDs across all three implementation
passes: 55. `TEST-MATRIX.md` now asserts 496 total rows (488 + 8 net new).

Repository gates after the confirmation round's corrections:

| Gate | Result |
|---|---|
| `just all` | **pass** — Ruff format, Ruff lint, `ty`, version sync, 566 tests passed, 1 skipped, 9 deselected |
| `just check-matrix` | **pass** — silent, 496 rows across 20 groups |
| `just strict-collect` | **pass** — clean collection across every test directory |
| `just clean-install` | **pass** — sdist and wheel built; disposable venv install completed |

Every finding from both confirmation-round reviews is addressed. No file
outside the 13 findings' scope was touched, and no pre-existing passing
assertion was weakened — `T-CLN-31`'s assertion changed from "empty
`retained_metadata`" to "the fork's own real claim is disclosed, only
freshness is empty," which is a strengthening (it now proves the fault is
scoped correctly) not a relaxation.

## Non-goals

- `session` never triggers inference, corpus discovery, screening, cache
  writes, or freshness writes to re-establish currency. Re-establishing
  freshness is always an explicit, user-invoked `infer` run.
- No content-prefix or append-aware fingerprinting; the owner chose the
  last-known-good route.
- No unlimited or incremental corpus index, and no relaxation of the file,
  entry, byte, candidate, or time limits.
- No change to cleanup's default metadata retention, and no new cleanup flag
  (owner decision 2).
- **No live freshness evaluation on `session claude-parent show` or `list`.**
  `show` keeps rendering the stored record exactly as it does today. Adding an
  additive live `freshness` object to `show` — one assessment, bounded stats,
  `list` deliberately left alone so a bulk listing never stats thousands of
  transcript paths — is a reasonable follow-up, but it is outside the six
  settled A10 outcomes, has no RED/GREEN step in this plan, and is deferred to
  a separate item rather than implied to be part of this work.
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
  an additional `freshness_write_failures` counter, incrementing alongside the
  unchanged `cache_write_failures` aggregate, is proportionate.
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
   back to the legacy `$XDG_CACHE_HOME` location whenever the state path
   yields no usable entry for that specific child; writes always target the new
   path and then remove only that child's key from the legacy file's `targets`;
   deletes remove that child's key from both locations. Migration is lazy and
   per child session ID — no bulk job, no startup scan, and no file-level
   action that could invalidate other children's evidence.
2. **Cleanup pruning: disclosure only, no new flag.** `cleanup` does not gain
   `--prune-agent-metadata`. Its default retention is unchanged, and the
   disclosure step (section 5) already names one exact, source-qualified
   `agent-fork session claude-parent delete --session-id <ID> --source
   <planned|inferred> --yes` command per retained record, for anyone who wants
   to remove retained metadata explicitly. This adds no
   new v1 CLI surface, no new confirmation semantics, and no new destructive
   path.

A third point was raised and is now closed as out of scope: `claude-parent show`
currently renders a stored record without evaluating freshness. Adding a live
`freshness` object to `show` is **not part of this implementation sweep** — see
"Non-goals" — because it is outside the six settled A10 outcomes and has no
RED/GREEN step of its own.
