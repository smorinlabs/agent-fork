# P02-A4 — Recipe-flag drift detection

Design doc for fault A4, per the P02 process ("Design doc per item").
Register entry: [P02 fault register](../../../projects/P02-agent-fork-fault-remediation.md).
Independent review: [TS04 Codex review](../../reviews/2026-08-17-p02-a4-codex-review.md).

## Process deviation — read this first

A4 did **not** follow the validation-first gate that landed on `main` in
A2's merge (`1f8e038`). That gate requires an exhaustive probe matrix and a
rewritten register entry *before* implementation, with the Codex lens
reviewing the matrix. A4 instead ran: inline adversarial review → register
entry rewritten → TDD implementation → Codex review of the finished diff.

The owner directed this order on 2026-08-17, and A4's work began from a base
(`aefcda0`) that predated the new gate. What the deviation cost and did not
cost:

- **Not cost:** claims were still evidence-backed rather than reasoned. The
  headline defect was demonstrated by a failing test before any fix, and the
  Codex lens independently reproduced two further defects with captured
  output.
- **Cost:** no exhaustive input matrix was built. The probe's input space —
  help-text shapes, exit codes, stream splits, encodings — was explored
  reactively, driven by review findings rather than enumerated up front.
  Three of the four implementation defects were found by the reviewer, not
  by the author, which is the failure mode the new gate exists to prevent.

Sequencing A4 after A2/A3 was also an owner-directed exception to the
A1 → A13 order.

## The fault

`agent-fork` prints a recipe — the command a user pastes into a fresh
terminal to resume a forked session:

```text
cd <worktree> && claude --session-id <child> --resume <parent> --fork-session -n <name>
codex fork <parent> -C <worktree>
```

Those flags were guarded only by version floors (`agents.py`,
`CLAUDE_FORK_MIN` / `CODEX_FORK_MIN` / `CODEX_ENV_MIN`). A floor proves a
capability *arrived*; it cannot prove the capability still exists. A CLI that
drops `--fork-session` passes every check, and the failure surfaces only
after the branch, worktree, registry entry, and lineage record exist.

## Why version arithmetic cannot close it

| Dependency | Floor | Installed at design time | Majors elapsed |
|---|---|---|---|
| Codex | `0.95.0` | `0.147.0` | 0 |
| Claude Code | `2.0.73` | `2.1.233` → `2.1.234` mid-review | 0 |

Codex is `0.x`, where semver §4 withholds any stability guarantee, so its
major is a constant. Claude Code's own `CLAUDE_RELIABLE_MIN = (2, 1, 100)`
records a behavior change relevant to `agent-fork` *inside* a minor. Neither
vendor publishes a flag-deprecation policy.

A tested-version upper bound (`>=0.95.0,<0.148.0`) would work as an
*unknown-version detector* — the TS04 review was right to reject the
stronger "structurally vacuous" claim. It is declined because it cannot say
which capability changed and warns on every unreviewed release. Claude Code
moved 2.1.233 → 2.1.234 during this review, which is the noise rate in
practice.

Prior art routes an uncontracted dependency to feature detection: autoconf
("test for features, not versions"), browser feature detection replacing UA
sniffing, Docker client/daemon API negotiation, LSP capability exchange.
Declared-range mechanisms (Terraform `required_version`, npm `engines`) and
skew policies (`kubectl` ±1 minor) all presuppose a contract that does not
exist here.

## Design

Two warn-level mechanisms. Neither refuses, because the fault is recoverable
— the worktree materializes correctly and only session resumption fails — so
a blocking guard would trade a recoverable failure for a new pre-fork one
firing on a help-text reorganization.

1. **Ambiguity detection.** `version_tokens` counts distinct version-like
   tokens across stdout and stderr; more than one appends a notice naming the
   tuple actually read, and the three floor-refusal messages carry the same
   hint (an exception discards `notices`, so the refusal path needed its
   own).
2. **Recipe-flag probe.** `read_help` reads the installed help;
   `missing_recipe_flags` checks the recipe's tokens against
   `option_declarations` — the leading part of lines starting with `-`, so
   prose like "this replaces `--fork-session`" cannot count as evidence.

The probe is **three-state**: supported, absent, or unverified. Silence on
unreadable help would make "no evidence" indistinguishable from verified
support.

## Where the warning appears — precisely

Detection is pre-mutation: `preflight_agent` runs before any write. The
**notice is not**. `cli.py` renders `result.notices` only after `fork(...)`
returns, so the user reads it attached to a completed fork. The warning tells
them to expect the paste command to fail and to run `cleanup`; it does not
spare them the residue (branch, worktree, registry row, and for Claude a
lineage claim for a child session that never started). Surfacing it earlier
needs a CLI-level change and is out of A4's scope.

## Known limits

The probe detects *absence of an exact token from a readable option
declaration*. It does not detect semantic change, and it cannot distinguish
removal of the Codex `fork` subcommand from any other unreadable help, since
that subcommand carries the help being read.

## Verification

| Row | Proves |
|---|---|
| T-PRE-21/22 | ambiguous output warns and names the parse; single token stays quiet |
| T-PRE-23 | absent flag notices and proceeds |
| T-PRE-24 | probe is case-sensitive (`-c` ≠ `-C`) |
| T-PRE-25 | unreadable help reports unverified, not silence |
| T-PRE-26 | rendered and declared flags match exactly, both directions |
| T-PRE-27 | deprecation prose is not an option declaration |
| T-PRE-28 | undecodable bytes return unverified instead of raising |
| T-CLI-25/26 | `doctor` reports coverage; drift fails only for the selected agent |

`just all`: 424 passed, 1 skipped. `just check-matrix` clean. Verified
end-to-end against the real CLIs: `agent recipe flags: claude: 4 documented;
codex: 1 documented`.

## Review outcomes

The TS04 Codex pass refuted claims 3 (implementation) and 4 (tests), and
partially refuted 1 (semver) and 2 (warn-vs-refuse). Two defects were
reproduced locally before acting: `UnicodeDecodeError` escaping `read_help`,
which broke the never-refuse guarantee, and the post-mutation notice timing.
All findings inside A4's remediation were absorbed; the rest are listed for
gate-6 routing below.

## Gate-6 routing — findings beyond A4's minimal remediation

These were raised by the TS04 review, are real, and are **not** fixed here:

1. Surface capability warnings before mutation (CLI-level change).
2. `doctor` repeats the same first-token parse rather than disambiguating an
   ambiguous version.
3. Derive the renderer and the probe's expectations from one structured
   option declaration, replacing the hardcoded list plus equality test.
4. Bound version tokens on the right if four-component versions are
   unsupported; `release 2.1.234.5` currently reads as `2.1.234`.
5. Both new `subprocess.run` call sites pass the caller environment
   unsanitized — the surface A2 exists to harden, now merged and to be swept
   across these sites.
