# CLI Design Standard v1.4.14 audit

**Date:** 2026-08-10  
**Scope:** P01-T19 only  
**Mode:** audit of the built `agent-fork 1.0.0` console script
**Profile:** Small-CLI, verb-first, publishable tier

> **Current-branch status:** This historical P01-T19 audit passed on
> 2026-08-10. P02 A13(B) later removed `table`; the follow-up below records
> current R4.1 and R9.3 `MUST` failures. The current branch is not conforming
> and must not be released while they remain unresolved.

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
| Identity/profile (R1, R2) | conforming with the existing R2.1 waiver | lowercase hyphenated binary; seven-command Small-CLI tree; one implicit resource; migration trigger documented |
| Arguments/options (R3, R4) | conforming after CLI-AUD-04 and the issue #16 check below | kebab-case long flags, reserved short flags, no prefix abbreviation, standard global flags, output/JSON surface including dry-run, boolean negations; G-CLI/G-CFG/G-OUT/G-CLN |
| Config/environment (R5) | conforming | XDG discovery/state, explicit-config precedence, curated environment, locked writes; G-CFG/G-REG |
| Exit behavior (R6) | conforming | exit 0/1/2/3/5/130/143 mapping in built help and G-CLI/G-OUT/G-RBK |
| Output/help/errors (R7) | conforming after CLI-AUD-01, CLI-AUD-04, and the issue #16 check below | stdout/stderr separation, stable open completed-result and dry-run-preview JSON schemas, additive cleanup details, TTY/locale invariance, semantic help, error catalog; G-OUT/G-CLN and conformance tests |
| Destructive safety (R8) | conforming | cleanup target guards, bounded risk reporting, independent overrides, explicit consent, `--no-input`, full-inspection dry-run, invoking-cwd refusal; G-CLN |
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

## Issue #16 additive cleanup-safety check

- **Date:** 2026-08-10
- **Scope:** issue #16 sections 1, 2, and 4 plus additive granular overrides
- **Mode:** check against CLI Design Standard v1.4.14 and the built console script

| Rules | Result | Evidence |
|---|---|---|
| R3.3, R3.10 | conforming | `--allow-dirty` and `--allow-unpushed` are exact kebab-case command-local flags and are present in Bash, Zsh, and Fish completion output |
| R7.1 | conforming | A human forced preview keeps the requested plan on stdout and sends the at-risk warning to stderr; T-CLN-16 |
| R7.2, R7.8, R9.3 | conforming compatible addition | JSON refusals remain one stderr error object and add optional bounded `details`; JSON dry runs expose the same object on stdout; T-CLN-19/T-CLN-21 |
| R8.1 | conforming | `--force` keeps its approved guard overrides without replacing `--yes`; the granular flags override only their named guard and never the cwd guard; T-CLN-15/T-CLN-20/T-CLN-22 |
| R8.6 | conforming | Dry-run executes the full local safety inspection, reports overridden risk, returns exit 0, and performs no mutation; T-CLN-16/T-CLN-21 |

No MUST or SHOULD deviation was introduced, so no new waiver or upstream
standard amendment is required.

The standard delegates detailed terminal rendering to a separate standard. A
late security review of PR #17 nevertheless found that Git-controlled paths and
commit subjects could inject terminal control bytes into human diagnostics.
T-CLN-23 protects the product fix: human output uses visible C-style escapes,
while the stable JSON values remain unchanged.

## P02 A13(B) output-value follow-up

- **Date:** 2026-08-18
- **Scope:** owner-approved removal of the byte-identical `table` output value
- **Mode:** implementation audit against CLI Design Standard v1.4.14

| Rule | Result | Evidence and consequence |
|---|---|---|
| R4.1 | **nonconforming MUST; release blocker** | `-o/--output` now accepts `text` and `json`, with `text` as the default. T-CFG-18 and T-CLI-32 protect the intended behavior, but the pinned standard requires `table` as the default human format. |
| R9.3 | **nonconforming MUST; release blocker** | `table` was an accepted value under the repository's declared `1.0.0` Production/Stable interface. Removing it requires an approved compatibility or version transition before release. |

Neither result is a waiver. Release remains blocked until the governing
standard and compatibility contract are satisfied or the removed interface is
restored. The companion skill is unaffected because it invokes only JSON; its
Markdown presentation tables are not CLI output-format values.
