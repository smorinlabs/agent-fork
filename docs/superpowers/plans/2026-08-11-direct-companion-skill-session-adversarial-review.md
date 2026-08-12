# Adversarial review — direct companion skill and repository-aware session context

**Date:** 2026-08-11
**Status:** Review complete; required amendments incorporated; owner approved
the recommended dispositions on 2026-08-11
**Reviewed plan:**
[`2026-08-11-direct-companion-skill-session.md`](2026-08-11-direct-companion-skill-session.md)
**Baseline:** `main` at `49b7caf`

## Review purpose

Determine whether the `agent-fork` skill can safely delete
`scripts/fork_session.py`, call the existing CLI directly, and use the new
`agent-fork session --json` command for inspection and omitted-name decisions.

The review tried to refute the simplification at five boundaries:

1. command routing and automatic naming;
2. responsibilities lost with the wrapper;
3. the new session JSON contract;
4. what static and real-agent tests can actually prove; and
5. corpus, matrix, and P01 tracking consistency.

Severity meanings:

- **Critical:** the proposed flow would produce materially wrong behavior in a
  normal use case.
- **High:** a correctness, safety, proof, or tracking gap that must be resolved
  before implementation.
- **Medium:** an intentional tradeoff or residual risk that must be explicit.

## Executive verdict

The simplification is architecturally sound. `fork_session.py` does not own Git
or agent-specific functionality that requires a separate executable. The CLI
already owns those mechanisms.

The first draft was not implementation-ready. Its most important defect was
turning an inferred topic branch into an explicit positional name. That would
disable the CLI's existing date suffix and automatic collision suffixing—the
very behavior the simplified skill should reuse.

The revised recommendation is:

```text
inspect                         agent-fork session --json
explicit name                  agent-fork fork '<normalized>' --require-agent --json
unnamed, known topic branch    agent-fork fork --require-agent --json
unnamed, default/unclear       recommend and ask, then use explicit name
```

No additional CLI command is needed. The existing `session` command needs an
additive repository-context result. The skill must retain the wrapper's useful
failure guidance in its instructions, and real Claude Code/Codex forward tests
must replace the behavioral proof lost when the executable wrapper is deleted.

## Architectural disposition

| Existing element | Disposition | Reason |
|---|---|---|
| `agent-fork session --json` | Reuse as-is, then extend additively | It is the implemented read-only identity route. |
| `agent-fork fork --require-agent --json` | Reuse as-is | It already owns ambient identity, strict refusal, mutation, and machine output. |
| CLI automatic naming | Reuse as-is | It owns date-bearing names and collision suffixes. |
| `RepositoryInfo` and `run_git()` | Reuse with adaptation | They already own topology and PATH-resolved Git execution. |
| Dry-run state counting | Reuse at the counting seam | Session needs actual state regardless of `with_state`; ignored-state behavior remains dry-run-specific. |
| `scripts/fork_session.py` | Remove | Its agent detection and CLI assembly duplicate current CLI capability. |
| Wrapper JSON/install diagnostics | Move into skill instructions | These remain necessary even though they do not justify an executable. |
| New `--status`, validator, or combined command | Reject for this change | They increase surface without closing a required baseline gap. |

## Critical finding

### AR-C1 — Passing an inferred branch as an explicit name disables automatic naming guarantees

**Draft behavior:** inspect a topic branch, normalize its branch name, then call
`agent-fork fork '<branch-name>' --require-agent --json`.

**Contradictory implementation:** the CLI appends `<MMDD>` only for automatic
names ([`naming.py:28`](../../../src/agent_fork/naming.py#L28)). Automatic names
receive numbered collision suffixes, while explicit names refuse a collision
([`naming.py:46`](../../../src/agent_fork/naming.py#L46),
[`naming.py:55`](../../../src/agent_fork/naming.py#L55)).

**Failure example:** on branch `review/auth`, the first draft would pass
`review-auth` as explicit. A second fork would refuse instead of becoming the
next collision-free automatic name. The explicit value also omits the existing
date component.

**Required amendment:** after session inspection proves a known topic branch,
call:

```bash
agent-fork fork --require-agent --json
```

The inspection still decides whether it is acceptable to proceed without a
human-selected name. The CLI remains the only component that derives and
uniquifies the automatic name.

**Disposition:** incorporated.

## High findings

### AR-H1 — Deleting the wrapper also deletes useful diagnostics unless the skill adopts them

The wrapper does more than duplicate agent detection. It emits the exact install
hint when the binary is absent and rejects exit-0 output that is not a complete
fork result ([`fork_session.py:84`](../../../.agents/skills/agent-fork/scripts/fork_session.py#L84),
[`fork_session.py:112`](../../../.agents/skills/agent-fork/scripts/fork_session.py#L112)).

Without replacement instructions, a direct skill could report shell
`command not found` output poorly, treat malformed JSON as success, or invent a
continuation command from incomplete fields.

**Required amendment:** the skill must show `uv tool install agent-fork` when
the executable is missing, reject malformed/incomplete success JSON, preserve
nonzero errors, and present the returned `command` string exactly.

**Disposition:** incorporated. These are skill response rules, not reasons to
keep a helper executable.

### AR-H2 — The omitted-name route must stop before asking when naming cannot unblock the fork

`agent-fork session --json` deliberately returns exit 0 for missing and
ambiguous identity. A naive flow can mistake that process success for permission
to continue, ask the user for a name, then fail under `--require-agent`.

The same problem exists outside Git: a name cannot turn a non-repository
directory into a valid fork source.

**Required amendment:** for an omitted-name fork, stop when `agent` or
`current_session` is null, or when `repository` is null. Report the observed
reason. Do not ask a question whose answer cannot make the operation succeed.

**Disposition:** incorporated.

### AR-H3 — The session-context draft did not define bare, failure, default, or conflicted-state semantics

`RepositoryInfo.worktree_root` is null for a bare repository
([`repository.py:14`](../../../src/agent_fork/repository.py#L14),
[`repository.py:70`](../../../src/agent_fork/repository.py#L70)). The current
default classification always includes locally present `main` and `master`,
even if `origin/HEAD` names another branch
([`repository.py:197`](../../../src/agent_fork/repository.py#L197)). The first
draft described those branches only as fallback candidates, which would have
changed existing fork behavior.

The original three status counts could also label an empty mid-operation as
clean and did not state how unmerged paths behave.

**Required amendment:** define a bare root and null bare status; expose the
remote default separately from a deterministic candidate list; preserve the
current candidate rule; include unmerged count and recognized operation; and
define `clean` from all counts plus operation. Repository-context failures are
observational `repository: null` results with a bounded notice.

**Disposition:** incorporated.

### AR-H4 — Context can disappear on early returns, and positional dataclass construction can silently misbind

`inspect_session()` returns early for ambiguous signals, no signals, unavailable
Codex, and several successful agent branches
([`session.py:116`](../../../src/agent_fork/session.py#L116)). The current
`SessionInspection` constructors are positional, with `notices` as the fifth
field ([`session.py:39`](../../../src/agent_fork/session.py#L39),
[`session.py:125`](../../../src/agent_fork/session.py#L125)).

Appending context only to the normal path would omit it from common
observational results. Inserting fields before `notices` could silently bind a
notice tuple to the wrong field.

**Required amendment:** compute context once for every identity outcome and
convert `SessionInspection` construction to keyword arguments before adding
fields. Human rendering must also append context outside the existing
current-session-only branch.

**Disposition:** incorporated.

### AR-H5 — Static skill tests cannot replace the wrapper's executable proof

Current tests execute the wrapper against a shim. They prove the exact child
argument vector, pre-invocation refusal, missing-executable behavior, malformed
JSON handling, and output preservation. After deletion, a test that searches
`SKILL.md` for command text proves only that the text exists.

It cannot prove model routing, multiword grouping, classification before
normalization, shell quoting, confirmation behavior, invocation count, working
directory, exact error preservation, or absence of a fallback.

**Required amendment:** keep static artifact tests, but treat fresh Claude Code
and Codex forward tests as the behavioral gate. Include hostile text, typo and
mixed-route refusal, missing/malformed CLI output, ambiguous identity, inferred
collision, and zero-mutation evidence.

**Disposition:** incorporated.

### AR-H6 — The first tracking proposal contradicted the live matrix

The live `G-SES` group ends at `T-SES-22` and is marked `done`
([`TEST-MATRIX.md:443`](../../testing/TEST-MATRIX.md#L443),
[`TEST-MATRIX.md:473`](../../testing/TEST-MATRIX.md#L473)). The first draft
started new rows at `T-SES-45`, duplicated the existing outside-Git case, and
proposed adding matrix rows before their test markers while keeping the matrix
checker green.

`tests/skill/` is not an enforced matrix tier, so proposed `T-SKL-*` values
would have looked canonical without bidirectional checking.

**Required amendment:** allocate `T-SES-23..27`, extend `T-SES-22` for the
outside-Git fields, change `G-SES` to `tdd`, and land every new row with its RED
test marker atomically. Use unnumbered focused skill tests rather than
untracked pseudo-IDs.

**Disposition:** incorporated.

### AR-H7 — The governing corpus is already stale in places this change must touch

The D19 heading currently interrupts the D18 heading and body. The consolidated
command surface omits the already-implemented `session` command. REQ-02,
REQ-03, and REQ-26 retain wrapper-owned assumptions. `CONFORMANCE.md` stops at
REQ-44/D15 and says no cache exists, although Claude inference now has a cache.
P01 still cites older decision/requirement ranges and says the completed Claude
parent plan needs pre-G0 revision.

Adding only D20/REQ-49 would make the corpus more misleading.

**Required amendment:** repair the named stale entries and ranges as part of
contract locking. Run `project-refine` after plan approval and before execution,
not in the middle of implementation.

**Disposition:** incorporated.

### AR-H8 — Broad natural-language triggers could hijack ordinary Git questions

The first draft routed “current branch,” “current directory,” and “Git status”
questions through `agent-fork session --json` without requiring agent-session
context. That overlaps ordinary repository inspection and can invoke an
unrelated skill.

The direct fork also discovers the repository from its current working
directory. The replacement plan must not lose the current skill's instruction
to run from the user's repository.

**Required amendment:** natural-language session triggers must mention the
current agent session or `agent-fork`; generic Git requests remain generic Git
requests. Every direct CLI call runs from the active repository, and both calls
in the omitted-name route use the same directory.

**Disposition:** incorporated.

## Medium findings and recorded judgments

### AR-M1 — The skill normalizer is deliberately narrower than the CLI normalizer

The CLI removes a selected set of Git-illegal characters and otherwise retains
some punctuation ([`naming.py:12`](../../../src/agent_fork/naming.py#L12),
[`naming.py:16`](../../../src/agent_fork/naming.py#L16)). The proposed skill
normalizer accepts only lowercase ASCII letters, digits, and internal hyphens.

This is duplication, but it serves two agentic boundaries: it prevents
option-like or hostile text from reaching a shell command, and it gives the user
a predictable visible name before mutation. The restricted result is a valid,
idempotent subset of the CLI's name space.

**Judgment:** keep the narrow skill normalizer; classify option-like input first,
quote the one resulting argument, report changes, and forward-test hostile and
multiword inputs. Do not change the CLI's broader sanitizer in this work.

### AR-M2 — Removing advanced option pass-through is a compatibility break

The current skill forwards destination, state, verification, clipboard, and
dry-run controls while reserving identity/output controls. The minimal agentic
interface accepts only a name hint or exact `--session`.

**Consequence:** users who currently invoke advanced CLI flags through the skill
must call the CLI directly. Keeping pass-through would require the skill to
distinguish free-form name hints from a growing CLI grammar and would undermine
the requested minimal interface.

**Recommendation:** accept the compatibility break and document the direct-CLI
escape hatch. This remains an owner-approval item because it removes supported
skill behavior.

### AR-M3 — A residual branch race remains without a new CLI contract

The omitted-name path inspects the repository and forks in two processes. An
external actor can change branches between them. Omitting the positional name
prevents a stale branch-derived name, but a topic-to-default transition could
bypass the desired default-branch name prompt.

**Recommendation:** accept this residual risk for the requested no-hardening
version. Closing it requires a conditional fork precondition or a combined
inspect-and-fork command, which would expand the CLI surface.

## Adversarial scenario verdicts

| Scenario | Required outcome in the revised plan |
|---|---|
| Topic branch, no name | Inspect, then unnamed strict JSON fork; CLI adds date and collision suffix. |
| Default branch, no name | Recommend one conversation-derived name and ask. |
| Detached branch, no name | Recommend and ask; do not invent a SHA-based user-facing choice in the skill. |
| No agent or dual agent signals | Report `not_detected` or `ambiguous`; no name question and no mutation. |
| Outside Git or unavailable repository context | Report the directory/context failure; no name question and no mutation. |
| Bare repository | Report bare topology and null working-tree status; naming follows branch classification. |
| Multiword or hostile explicit hint | Classify options first, normalize to one restricted slug, shell-quote once. |
| Explicit collision | Preserve refusal; do not silently suffix. |
| Automatic collision | Let CLI suffix. |
| Missing executable | Show `uv tool install agent-fork`; stop. |
| Exit-0 malformed JSON | Report invalid CLI JSON; do not infer success. |
| Nonzero CLI result | Preserve the error; no retry, transcript search, or Git fallback. |
| `/agent-fork --status` | Refuse and point to `/agent-fork --session`. |
| Branch changes between inspect/fork | Residual risk accepted for this no-hardening version. |

## Gate disposition

The owner approved these two visible behavior decisions on 2026-08-11:

1. an unnamed topic-branch fork omits the positional name so the CLI owns date
   and collision suffixing; and
2. advanced CLI flags no longer pass through the skill.

The P01 decomposition is recorded as P01-TS26 and P01-T39..41. Execute only the
revised plan in its dedicated worktree. Do not implement from the earlier draft.
