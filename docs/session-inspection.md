# Session inspection and validation

The full reference for `agent-fork session`, `agent-fork session validate`,
and `agent-fork session claude-parent`. The [README](../README.md) carries the
summary; this page carries the complete semantics.

## Inspection

Use the same interface inside Claude Code or Codex:

```bash
agent-fork session
agent-fork session -o json
agent-fork session validate --agent codex --has-parent
agent-fork session validate \
  --session-id "$EXPECTED_CHILD" \
  --parent-session-id "$EXPECTED_PARENT" -o json
```

Inspection reports sourced evidence, the resolved invocation directory, and
nullable Git repository context. Repository context includes the worktree root,
branch or detached state, remote/default-branch candidates, default membership,
linked/bare topology, and clean/staged/unstaged/untracked/unmerged/operation
status. A bare repository has null working-tree status. Outside Git—or when Git
context is unavailable—the session evidence remains usable and `repository` is
null. Inspection also reports `fork_command`: one detected Claude Code or Codex
identity produces a shell-quoted native command using the resolved invocation
directory. Claude receives a fresh, single-use child UUID. No identity,
ambiguous identity, or terminal-unsafe identity/path data produces an explicit
unavailable status and a null command. Inspection succeeds with `not_detected`
in an ordinary terminal.

Machine output always includes an additive `agent_signal` object:

```json
{"status":"incomplete","present":["CLAUDECODE=1"],"missing":["CLAUDE_CODE_SESSION_ID"]}
```

`status` is one of `absent`, `incomplete`, `detected`, or `ambiguous`.
`present` and `missing` contain only supported environment variable names,
never their session or thread values. Either half of the Claude tuple by
itself is incomplete. Any Claude value together with `CODEX_THREAD_ID` is
ambiguous, including a partial Claude tuple. This assessment describes the
environment shape; it does not prove that the reported session exists.

Incomplete inspection remains observational and exits 0. It reports no
current identity, retains `lineage.status: not_detected` and
`fork_command.status: not_detected`, and adds a notice naming the missing
Claude value. Human output adds `agent signal: incomplete`. These additive
results distinguish incomplete input from an ordinary terminal without
redefining the existing lineage or command-status dimensions.

The native session commands have these shapes:

```text
cd '<resolved-directory>' && claude --session-id '<fresh-child-uuid>' --resume '<current-session-id>' --fork-session
codex fork '<current-thread-id>' -C '<resolved-directory>'
```

`available` means the command was constructible from ambient identity; it does
not run native CLI preflight. Use `agent-fork fork` when you need the supported
version and Codex-rollout checks before repository mutation. The ordinary
session command and both skill inspection forms never execute the returned
command, create a branch or worktree, copy files, write registry or lineage
state, or touch the clipboard. There is no direct CLI `--session-only` flag;
that spelling is a companion-skill presentation shortcut over the JSON field.

## Validation

Validation without constraints requires any unambiguous supported current
session. Optional `--agent`, `--session-id`, `--parent-session-id`, and
`--has-parent`/`--no-parent` assertions compose with AND semantics.

Parent means parent evidence, not proof that a transcript still exists. Codex
name and parent evidence comes from its bounded local app-server. Agent
Fork-created Claude children retain a prompt-free XDG provenance claim because
Claude transcripts do not preserve the source session UUID. Missing evidence
is not proof that a session was never forked. Inspection makes no network calls
and does not modify agent or repository state.

A Codex app-server `thread/read` error is unavailable evidence, not a successful
lookup with no parent. Inspection retains the current session ID, reports
`lineage.status: unavailable`, and adds a notice. If the current thread already
supplied a parent ID but reading the parent name fails, inspection retains that
parent ID and resolved lineage while marking only the parent name unavailable.
When lineage is unavailable, validation refuses both `--has-parent` and
`--no-parent`; neither assertion can be proven. Assertions limited to `--agent`
or `--session-id` can still succeed because they do not depend on parent
evidence. A successful `thread/read` response with no parent continues to
satisfy `--no-parent`.

## Claude parent inference

Claude does not expose an authoritative historical parent ID for ordinary
forks. An explicit, potentially expensive structural analysis can infer likely
relationships from copied message UUID/`parentUuid` ancestry:

```bash
agent-fork session claude-parent infer --current
agent-fork session claude-parent infer --session-id UUID -o json
agent-fork session claude-parent infer --session-id UUID --record
agent-fork session claude-parent infer --all
agent-fork session claude-parent infer --all --record-all
agent-fork session claude-parent list
agent-fork session claude-parent show --session-id UUID
agent-fork session claude-parent delete --session-id UUID --source inferred --yes
```

Exactly one of `--current`, `--session-id`, or `--all` is required. Preview is
read-only. `--record` is single-target only; bulk persistence requires the
deliberate `--record-all` spelling. Delete removes only Agent Fork metadata,
never Claude transcripts, history, sessions, Git branches, or worktrees. It
prompts only in interactive human mode; use `--yes` for automation, while
`--no-input` makes missing consent fail immediately. Bulk JSON remains one
document and uses bounded per-target candidate projections.

`infer --current` uses the same `agent_signal` assessment before transcript
discovery. Incomplete Claude input returns `agent_signal_incomplete`, exit 3.
Any Claude value combined with Codex input is unavailable because the current
agent identity is ambiguous. Absent and Codex-only input retain
`claude_parent_unavailable`; complete Claude-only input supplies the target
session ID.

Analysis uses a bounded manifest, superficial streaming UUID screens, exact
candidate parsing, and bounded graph comparison. Screen-cache shards live under
`$XDG_CACHE_HOME/agent-fork/claude-lineage-index-v3/`, one flat, self-superseding
`<transcript-uuid>.json` shard per transcript — a re-screened transcript
overwrites its own shard rather than accumulating a new one. A bounded,
interval-gated sweep (at most once every 24 hours per corpus construction)
removes orphaned, aged, or over-budget shards and, once, the legacy
`claude-lineage-index-v2/` tree from an earlier shard-naming scheme; it never
touches an in-flight write from another `agent-fork` process. Inferred records
live separately at
`$XDG_STATE_HOME/agent-fork/session-lineage-inferences.json`. Neither cache nor
state stores prompt/response content, although session IDs and UUID correlation
remain sensitive local metadata.

`inferred` and `strongly_inferred` are evidence labels, not proof of immediate
parentage. Same-boundary siblings remain ambiguous regardless of timestamps.

**Freshness** is a separate axis from the inference itself: whether a
*recorded* inference is still trustworthy right now. `assess_inference`
resolves one of five statuses, each mapped to an evidence tier:

| Freshness status | Evidence tier | Meaning |
|---|---|---|
| `current_at_last_analysis` | `current` | the analyzed source files, algorithm version, and target-specific candidate-universe digest all still match |
| `stale_sources` | `last_known_good` | an analyzed transcript changed after the analysis; newer messages were not examined |
| `stale_candidate_universe` | `last_known_good` | the set of transcripts relevant to this session changed after the analysis |
| `freshness_unknown` | `unknown` | the corroborating freshness-index entry is missing or unreadable, so the record cannot be confirmed or rejected |
| `stale_algorithm` | `superseded` | the record predates the current inference algorithm and its fields are not interpretable |

Only the `current` tier satisfies strict parent evidence
(`session validate --has-parent`, `parent_session` in `session` output).
Every other tier is still *disclosed*, never silently discarded and never
silently treated as current: `session` reports the retained record through an
additive top-level `parent_inference` object with its own `status`
(`not_consulted`, `absent`, `current`, `last_known_good`,
`freshness_unknown`, `superseded`, or `unreadable`), the underlying
`freshness` value, and — for every status except `not_consulted`, `absent`,
`unreadable`, and `superseded` — the previously inferred `parent_session_id`,
`analyzed_at` timestamp, and `changed_sources` (`target`, `parent`, `other`,
or a combination, naming which analyzed transcript changed). A `superseded`
record shows only its status, since its other fields are not interpretable. A
human `parent inference: <status> <parent-id> (…)` line appears immediately
after `lineage:`, followed by a notice naming the exact rerun command
(`agent-fork session claude-parent infer --session-id <ID> --record`) for
every non-`current` status. `session` never rescans the Claude corpus to
compute this — it only reads what a prior `infer --record` already wrote;
re-establishing freshness always requires an explicit `infer --record` run.

The freshness index that corroborates `stale_candidate_universe` lives at
`$XDG_STATE_HOME/agent-fork/claude-lineage-freshness.json`, alongside the
inference records it corroborates (co-locating it with `session-lineage.json`
and `session-lineage-inferences.json` means an ordinary cache-clearing tool
can no longer silently downgrade every recorded inference). A legacy copy from
before this relocation may still exist at
`$XDG_CACHE_HOME/agent-fork/claude-lineage-freshness.json`; entries there are
read as an ordinary fallback per child session ID and are migrated to the new
location automatically, one entry at a time, the next time that specific
session is re-inferred. Deleting a record with
`session claude-parent delete` removes its freshness entry from both
locations, before removing the record itself, so no orphaned corroboration or
prematurely downgraded sibling record can result from a delete that fails
partway through.

This heuristic relies on observed Claude transcript structure, not a
documented Anthropic lineage API. Analysis that hits a bounded corpus limit
(transcript count, entry count, total byte size, per-target candidate count,
or per-target time) refuses with the typed `claude_parent_incomplete_analysis`
error (exit 3) rather than silently truncating; a whole-corpus limit refuses
the entire invocation before any work begins, while a per-target limit (under
`--all`) fails only that target and leaves every other target's analysis and
recording intact.
