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

Analysis uses a bounded manifest, superficial streaming UUID screens, exact
candidate parsing, and bounded graph comparison. Cache shards live under
`$XDG_CACHE_HOME/agent-fork/claude-lineage-index-v2/`; unchanged unrelated
transcripts are not reread on warm lookup. Inferred records live separately at
`$XDG_STATE_HOME/agent-fork/session-lineage-inferences.json`. Neither cache nor
state stores prompt/response content, although session IDs and UUID correlation
remain sensitive local metadata.

`inferred` and `strongly_inferred` are evidence labels, not proof of immediate
parentage. Same-boundary siblings remain ambiguous regardless of timestamps.
Recorded freshness means `current_at_last_analysis`: the analyzed source files,
algorithm version, index generation, and target-specific candidate-universe
digest are retained, but ordinary `session`, `list`, and `show` never rescan the
Claude corpus and therefore do not claim global currentness. A later explicit
inference refresh can detect relevant candidate-universe changes. Stale records
remain manageable with `list`/`show` but are not used as parent evidence. This
heuristic relies on observed Claude transcript structure, not a documented
Anthropic lineage API.
