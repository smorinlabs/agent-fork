# CLI Design Standard v1.4.14 audit

**Date:** 2026-08-10  
**Scope:** P01-T19 only  
**Mode:** audit of the built `agent-fork 0.1.0` console script  
**Profile:** Small-CLI, verb-first, publishable tier

## Authority and method

The standalone `cli-standards` skill/package was unavailable in this execution
environment. The audit therefore used the pinned v1.4.14 obligations already
approved and transcribed into `REQUIREMENTS.md` §3 and `CONFORMANCE.md`, then
exercised the built console script rather than inspecting parser declarations
alone.

Commands audited:

```text
agent-fork --help
agent-fork --version
agent-fork help fork
agent-fork help cleanup
agent-fork help list
agent-fork help doctor
agent-fork help config
agent-fork help completion
```

The conformance and matrix suites supply the behavioral evidence cited below;
`scripts/check_clean_install.sh` repeats the public-surface smoke tests against
a wheel installed into a disposable environment.

## Findings

| ID | Severity | Rule / requirement | Finding | Disposition |
|---|---|---|---|---|
| CLI-AUD-01 | must-fix | R7.9, R7.12; REQ-11 | Built help exposed syntax but omitted semantic descriptions and the required exit-code catalog. | Fixed with descriptions for commands and core arguments/options, cleanup safety text, and the stable exit-code summary. Protected by `test_help_documents_commands_options_and_exit_codes`. |
| CLI-AUD-02 | must-fix | R4.4; REQ-10 | `-v`, `-q`, and `--debug` parsed successfully but did not alter diagnostics. | Fixed: `-v` identifies the command, `-vv` also identifies cwd, `-q` suppresses those diagnostics, and `--debug` emits a traceback for human-format failures while preserving JSON error purity. Covered by T-CLI-15. |
| CLI-AUD-03 | reviewed waiver | R2.1; REQ-07, D13 | `cleanup` differs from the nearest core verb `delete`. | Existing owner-approved waiver remains sufficient: cleanup removes a worktree, optionally its branch, prunes metadata, and updates the registry. No new waiver. |
| CLI-AUD-04 | must-fix | R4.2, R7.2, R8.6; REQ-17, REQ-18 | `fork --dry-run` accepted `-o json` and `--json` but emitted human text with exit 0. | Fixed with a distinct stable preview object carrying every planned mutation and no-mutation status. Covered by T-OUT-21. |

## Rule-family disposition

| Rule family | Result | Evidence |
|---|---|---|
| Identity/profile (R1, R2) | conforming with CLI-AUD-02 waiver | lowercase hyphenated binary; seven-command Small-CLI tree; one implicit resource; migration trigger documented |
| Arguments/options (R3, R4) | conforming after CLI-AUD-04 | kebab-case long flags, reserved short flags, no prefix abbreviation, standard global flags, output/JSON surface including dry-run, boolean negations; G-CLI/G-CFG/G-OUT |
| Config/environment (R5) | conforming | XDG discovery/state, explicit-config precedence, curated environment, locked writes; G-CFG/G-REG |
| Exit behavior (R6) | conforming | exit 0/1/2/3/5/130/143 mapping in built help and G-CLI/G-OUT/G-RBK |
| Output/help/errors (R7) | conforming after CLI-AUD-01 and CLI-AUD-04 | stdout/stderr separation, stable open completed-result and dry-run-preview JSON schemas, TTY/locale invariance, semantic help, error catalog; G-OUT and conformance tests |
| Destructive safety (R8) | conforming | cleanup target guards, explicit consent, `--no-input`, dry-run, invoking-cwd refusal; G-CLN |
| Publishable tier (R9) | conforming for pre-release product surface | completions, SemVer/deprecation policy, locale/signals, dedicated unrestricted-Linux signal CI gate, doctor, telemetry disclosure, CI conformance, clean wheel install |
| Network behavior (R10) | not applicable | fully local runtime; no network client or runtime network call |

## Verdict

**Pass after fixes.** CLI-AUD-01, CLI-AUD-02, and CLI-AUD-04 are closed, the existing R2.1 waiver is unchanged,
and no new waiver is required. This audit does not configure release automation,
publish a package, or perform P01-T20/P01-T21.

## Approved second-level hardening

The owner approved the follow-up adversarial plan. The implementation replaces
the self-referential seven-code check with an authoritative 21-code catalog,
uses `config_error` for handled configuration failures, provides semantic Bash,
Zsh, and Fish completions with syntax gates, and aligns help metavariables and
config-action ordering with the locked interface. Evidence is T-OUT-14..16 and
T-CLI-16..20. Reserved exit 4 remains documentation-only and help examples stay
in README, as recommended by the review.
