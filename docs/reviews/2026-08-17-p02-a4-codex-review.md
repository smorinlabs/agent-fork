# P02-TS04 independent Codex review — A4 recipe-flag probe

Review target: `git diff aefcda0..HEAD` (`48b0d29`, `9b9b9b0`) only.

## Claim 1 — Semantic versioning cannot solve recipe drift

**Verdict: PARTIALLY REFUTED**

**Severity: minor**

The narrow claim is sound: the existing lower bounds cannot prove that a capability still exists. `CODEX_ENV_MIN = (0, 95, 0)` and `CLAUDE_FORK_MIN = (2, 0, 73)` at `src/agent_fork/agents.py:65-68` answer only whether a release is new enough. The project text is also right that a vendor compatibility contract would be needed to infer flag preservation from a major or minor number (`projects/P02-agent-fork-fault-remediation.md:95-114`).

The absolute claim is too strong. A conservative tested-version range would work as an **unknown-version detector**, even though it could not identify which capability changed. For example, `>=0.95.0,<0.148.0` for the currently installed Codex 0.147.0 would warn or refuse every unreviewed future minor, including one that removed `fork` or `-C`. An explicit allowlist of tested releases would do the same. This mechanism has high maintenance and false-warning costs, but it is not “structurally vacuous.” The real tradeoff is capability precision versus update noise, not possibility versus impossibility.

Empirical current state:

```text
$ codex --version
WARNING: proceeding, even though we could not create PATH aliases: Operation not permitted (os error 1)
codex-cli 0.147.0

$ claude --version
2.1.234 (Claude Code)
```

Recommendation: retain feature detection, but rewrite `projects/P02-agent-fork-fault-remediation.md:95-106` to say that version ranges cannot identify removal and were rejected because an upper tested bound would warn on every unreviewed release.

## Claim 2 — Warn-and-proceed is better than refusal

**Verdict: PARTIALLY REFUTED**

**Severity: major**

The downgrade from destructive corruption to recoverable residue is fair, but the implementation does not issue a user-visible warning before mutation:

- `preflight_agent` computes the notice before `validate_fork_guards` and worktree creation (`src/agent_fork/pipeline.py:72-95`).
- The fork then creates the worktree at `src/agent_fork/pipeline.py:127-129`, adds the registry entry at `src/agent_fork/pipeline.py:154-163`, and writes Claude lineage at `src/agent_fork/pipeline.py:164-180`.
- Only after `fork(...)` returns does the CLI render the notice (`src/agent_fork/cli.py:587-625`; `src/agent_fork/output.py:68-81`).

Therefore T-PRE-23’s matrix wording, “warns before mutation and proceeds” (`docs/testing/TEST-MATRIX.md:105`), is false at the user-visible CLI boundary. Detection happens before mutation; warning happens after mutation. A user who sees the warning already has the branch, worktree, registry record, and, for Claude, a lineage claim for a child session that never started.

The residue is not destructive, but it is operationally material. A retry with the same name collides with the existing branch/path; cleanup is an extra recovery operation; and the lineage claim can describe a nonexistent child. The project itself admits the last two records at `projects/P02-agent-fork-fault-remediation.md:157-162`.

Refusal is still unsafe if based on the current free-form regex, because help prose can produce false results. The better choices are either:

1. make capability failure a pre-mutation refusal with an explicit override after making the probe reliable; or
2. keep it advisory but accurately document that the warning is reported in the completed fork result and does not prevent residue.

## Claim 3 — The implementation is correct

**Verdict: REFUTED**

**Severity: major**

### 3.1 Free-form token search false-passes removal prose

`missing_recipe_flags` searches the entire help document with `(?<![\w-]){flag}(?![\w-])` (`src/agent_fork/agents.py:117-123`). It proves only that a token appears, not that the token is a declared option.

Reproduced:

```text
missing_recipe_flags(
  "claude",
  "This option replaces --fork-session; use --resume and --session-id with -n."
)
=> ()

missing_recipe_flags(
  "codex",
  "The old -C flag is no longer supported; change directory first."
)
=> ()
```

Both inputs explicitly say the recipe flag is obsolete, yet the probe reports complete coverage. This directly refutes `projects/P02-agent-fork-fault-remediation.md:149`, which says the probe detects flag removal.

The current installed help happens to use structured option lines and passes:

```text
claude 2.1.234: --fork-session at line 93; -n at 128; --resume at 175; --session-id at 189
codex 0.147.0 fork help: -c, --config at line 20; -C, --cd at line 79
missing_recipe_flags("claude", live_help) => ()
missing_recipe_flags("codex", live_help) => ()
```

T-PRE-24 correctly proves case sensitivity for `-c` versus `-C`; it does not address prose false-passes.

### 3.2 Unreadable help hides removal, and malformed bytes turn a warning probe into a hard failure

`read_help` returns `None` for nonzero exit, `OSError`, timeout, or empty stdout, and callers intentionally stay silent (`src/agent_fork/agents.py:126-141`, `285-297`). A stub that printed `error: unknown subcommand fork` and exited 2 reproduced `read_help("codex", stub, env) => None`. Thus removal of the `fork` subcommand produces exactly the silence already admitted at `projects/P02-agent-fork-fault-remediation.md:149-155`.

This is not a necessary consequence of warn-level policy. “Capability could not be verified” can itself be a nonblocking notice. Silence makes absence of evidence indistinguishable from successful capability validation.

The exception boundary is also incomplete. A stub that emitted byte `0xff` with exit 0 reproduced:

```text
UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff in position 0
```

`text=True` decoding occurs inside `subprocess.run`, but `read_help` catches only `OSError` and `subprocess.SubprocessError` (`src/agent_fork/agents.py:133-138`). This converts the advertised “warn-and-proceed, never refuse” mechanism into an uncaught pre-fork runtime failure for undecodable output.

### 3.3 The ambiguity detector does not observe both subprocess streams, and `doctor` cannot resolve its warning

The live Codex command demonstrated split streams: the version is on stdout and a warning is on stderr. Production selects `completed.stdout or completed.stderr`, never both (`src/agent_fork/agents.py:184-192`). T-PRE-21 injects a pre-concatenated string directly (`tests/unit/test_pre.py:61-68`), so it does not test the subprocess boundary. A future updater version printed in stderr while the CLI version remains in stdout will be invisible to `version_tokens`.

When ambiguity is detected, the notice directs the user to `agent-fork doctor` (`src/agent_fork/agents.py:207-212`). Doctor uses the same first-token parser and does not call `version_tokens` (`src/agent_fork/doctor.py:59-80`). It can repeat the wrong tuple rather than disambiguate it. The three floor messages carry only a token-count hint (`src/agent_fork/agents.py:204-235`); no test asserts any of those messages.

The `_VERSION` left guard change itself did not regress the supported live shapes or `git version 2.19.0.windows.1`. It intentionally changes malformed `.2.1.234` from an old parse of `2.1.234` to `ValueError`. No supported input regression was reproduced. A remaining parser limitation is that `release 2.1.234.5` is silently read as `2.1.234` with one token.

### 3.4 The new `doctor` check silently changes the command’s exit contract

`_recipe_flag_check` sets `ok=False` for any installed agent with a missing documented flag (`src/agent_fork/doctor.py:31-56`). It checks both Claude and Codex before agent-mode optionalization and is never made optional (`src/agent_fork/doctor.py:83-104`, `139-148`, `172`). The CLI returns 1 when any check is false (`src/agent_fork/cli.py:705-728`).

Consequences:

- A warn-only preflight condition becomes a failing diagnostic.
- An unused installed agent can make `doctor`, `doctor --no-agent`, or a Claude-only doctor run exit 1 because the other CLI drifted.
- Existing callers or CI that treat doctor exit 0 as environment readiness gain a new failure without a contract test.

T-CLI-25 tests only the all-documented exit-0 path. It never tests drift, an unused agent, `--no-agent`, JSON `ok`, or exit 1.

### 3.5 Added process cost is bounded but not free, and the help commands are not side-effect-free in this sandbox

The new subprocess has a 10-second timeout (`src/agent_fork/agents.py:133-136`). Live timings were:

```text
claude --help: 0.77s cold, then 0.15s, 0.15s
codex fork --help: 0.07s, 0.06s, 0.06s
```

Each Codex help call also emitted:

```text
WARNING: proceeding, even though we could not create PATH aliases: Operation not permitted (os error 1)
```

`read_help` suppresses that stderr because it returns stdout only. The command therefore attempted environment setup under the sandbox even for help. `env=dict(env)` (`src/agent_fork/agents.py:134-136`) faithfully passes the caller environment; it is not sanitized or minimized. This is a minor latency/sandbox risk, not a demonstrated security defect, but it contradicts the project’s statement that the remedy “adds no ... environment surface” (`projects/P02-agent-fork-fault-remediation.md:266-271`).

## Claim 4 — The tests test the claims

**Verdict: REFUTED**

**Severity: major**

The 12 new/parameterized A4 tests pass, but they do not establish the end-to-end claims.

| Row | Adversarial result |
|---|---|
| T-PRE-21 | Fails the old implementation, but injects already-combined output and never tests real stdout/stderr selection. It also asserts the wrong first token remains the operative version. |
| T-PRE-22 | Would pass the old code unchanged: old preflight parsed `2.1.233` and emitted no ambiguity notice. It proves no new behavior. |
| T-PRE-23 | Calls `preflight_agent(..., help_output=...)` directly. It proves notice construction, not subprocess probing, pipeline ordering, user-visible timing, or absence of mutation. |
| T-PRE-24 | Correctly tests `-c` versus `-C` in the helper only. It does not test option declarations versus prose. |
| T-PRE-25 | The exact new signature would not exist in old code, but the asserted behavior—silence when help cannot be read—is the old system behavior. It does not invoke `read_help`, a nonzero subprocess, timeout, stderr-only help, or decode failure. |
| T-PRE-26 | Fails old code because the new API is absent, but its one-way `rendered <= declared` assertion (`tests/unit/test_pre.py:135-142`) allows stale extra declarations. If the renderer stops emitting `-n` while `CLAUDE_RECIPE_FLAGS` retains it, the test passes and the probe checks an irrelevant flag. |
| T-CLI-25 | Fails old code because the new doctor row is absent, but tests only success and asserts only `claude: 4 documented` (`tests/cli/test_cli.py:171-187`). The matrix says “per installed CLI” (`docs/testing/TEST-MATRIX.md:475`), yet the test would pass if Codex coverage vanished. It does not test failing status or exit behavior. |

The changes to `_agent_env` and `_doctor_env` are legitimate fixture-fidelity repairs, not evidence suppression. Before the change, those stubs returned a version string for every argument; the new probe correctly interpreted that fake help as missing flags. Tests whose purpose is unrelated to drift need a stub that distinguishes `--version` from `--help`. The defect is that no separate integration fixture now exercises an actually removed flag through the CLI.

Verification run:

```text
12 targeted new/parameterized tests: passed
normal `just test` lane: 416 passed, 1 skipped, 9 deselected
full unfiltered pytest: blocked by 7 real-CLI failures/errors
  - Claude: Not logged in; /login required
  - Codex: sandbox denied app-server/SQLite initialization
```

Those seven failures are external auth/sandbox failures, not evidence against this diff.

## Claim 5 — Missed failure modes, simpler designs, and documentation overstatement

**Verdict: CONFIRMED**

**Severity: major**

The prior review missed or under-recorded these items:

1. **The warning is surfaced after mutation.** The design and matrix conflate pre-mutation detection with pre-mutation communication.
2. **Free-form help token presence is not option support.** Deprecation/removal prose false-passes the regex.
3. **Unreadable help should be an explicit unknown result.** Silence loses the distinction between verified support and no evidence, including whole-subcommand removal.
4. **Doctor’s failure semantics contradict “two warn-level mechanisms.”** `projects/P02-agent-fork-fault-remediation.md:116` calls both mechanisms warn-level, but doctor returns a failing check and changes exit status.
5. **The flag-list sync test is one-way.** `rendered <= declared` does not prevent stale declared flags. Equality for the canonical recipe, or deriving the renderer and probe from one structured option declaration, is simpler and stronger.
6. **The ambiguity test bypasses real stream handling.** The production `stdout or stderr` boundary can hide the second token that the unit test claims to detect.
7. **The project task line names a nonexistent helper.** `projects/P02-agent-fork-fault-remediation.md:280` says `_read_help`; the implementation exports `read_help` at `src/agent_fork/agents.py:126`.
8. **The order-exception rationale is stale.** `projects/P02-agent-fork-fault-remediation.md:266-271` says the remedy touches only `agents.py` and adds no environment surface. Commit `9b9b9b0` also changes `doctor.py`, and both new call sites pass the full environment to agent subprocesses.
9. **“Probe detects flag removal” is overstated.** At most it detects absence of an exact token from readable stdout; it misses removal prose, whole-subcommand removal, stderr-only help, and semantic drift.

## Must fix before merge

1. Make probe outcomes three-state: supported, missing, or unverified. Emit a nonblocking unverified notice for nonzero exit, timeout, empty/stdout-missing help, stderr-only help, and decode failure; specifically cover removal of the Codex `fork` subcommand.
2. Stop treating arbitrary prose token presence as an option declaration. Parse the current structured option-line forms, and add removal/deprecation-prose tests for both CLIs.
3. Resolve the `doctor` contract: keep a warn-level recipe result from changing exit status, or explicitly approve and test the new exit-1 behavior with agent-mode scoping. An unused agent must not unexpectedly fail a selected-agent or `--no-agent` diagnosis.
4. Add end-to-end CLI tests that prove when the warning becomes visible relative to mutation, and either surface it before mutation or correct the matrix/project claims and accept the residue explicitly.
5. Test real subprocess stream handling for ambiguous versions and make `doctor` provide useful disambiguation rather than repeating the same first-token parse.
6. Strengthen T-PRE-26 to reject stale declared flags, and strengthen T-CLI-25 to assert both installed CLIs plus drift/exit behavior.
7. Correct the stale and overstated project text: `read_help` name, files/surfaces touched, warning timing, range-mechanism tradeoff, and the exact limits of token probing.

## Optional

1. Cache help capability per resolved executable/version for a single invocation or process if repeated probes become measurable; current warm cost is modest, but the 10-second timeout is user-visible.
2. Bound version tokens on the right as well as the left if four-component versions are not supported, and add direct parser contract tests.
3. Derive both command rendering and capability expectations from one structured recipe-option declaration instead of maintaining a hardcoded list plus a regex sync test.
