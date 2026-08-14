# CLI Standard Conformance — agent-fork

| | |
|---|---|
| **Standard** | CLI Design Standard v1.4.14 |
| **Profile** | Small-CLI (Appendix A) — criteria check in REQUIREMENTS.md §3.1; migration trigger: second resource type ⇒ noun-verb next major |
| **Tier** | publishable |
| **Owner** | Steve Morin |

## Applicability

| Axis | Applies | Reason if N/A |
|---|---|---|
| Config (§5) | yes | — |
| Networked (§10) | no | fully local tool; zero runtime network calls (REQ-40) |
| Destructive ops (§8) | yes | `cleanup` removes worktrees/branches |
| Scripted consumers (R7.2/R7.8) | yes | the agent-fork *skill* consumes `--json` (REQ-04/REQ-49/REQ-50) |
| Async / long-running | no | synchronous local operations; no operation IDs |
| Streaming / watch | no | no streaming output |
| Plugins (R9.11) | no | no extension model planned |
| Caching / offline (R5.9) | yes | Claude parent inference uses bounded, prompt-free, sharded local cache metadata (REQ-48); runtime remains offline |
| Secrets handled (R5.5/R5.6) | no | accepts no secrets; R5.5 argv ban still honored. Note: `--with-ignored` can *copy* secret-bearing files (e.g. `.env`) between working trees — documented behavior + off-default (REQ-15), not secret input/output handling |

## Waived SHOULDs

| Rule | Deviation | Rationale | Owner / date |
|---|---|---|---|
| R2.1 | `cleanup` used instead of core `delete` | domain verb: removes worktree + optionally branch + prunes + registry update — broader than `delete`; name specified in the project kickoff. **Confirmed at Phase 3 (D13, 2026-07-21)** | Steve Morin / 2026-07-21 |

> D1 resolved 2026-07-21: bare invocation prints help (R7.9-conforming); no amendment needed. Small-CLI profile confirmed by owner same date.

## Audit history

| Date | Standard version | Mode | Result |
|---|---|---|---|
| 2026-07-21 | 1.4.14 | plan | Interface spec seeded into REQUIREMENTS.md §3; no code exists yet; fixtures (R9.14) deferred to implementation start |
| 2026-08-10 | 1.4.14 | Phase D implementation | CLI, row matrix, adversarial fixtures, and disposable wheel install green; companion skill and release channels remain gated to Phases E and F |
| 2026-08-10 | 1.4.14 | Phase E companion skill | Shared Claude/Codex skill, deterministic JSON orchestration, failure contracts, and real dual-host paste-command demos green; release channels remain gated to Phase F |
| 2026-08-10 | 1.4.14 | built-binary audit (P01-T19) | Pass after fixing semantic help/exit-code catalog (CLI-AUD-01) and inert diagnostic flags (CLI-AUD-02); existing R2.1 `cleanup` waiver unchanged; no new waivers. Evidence: `docs/testing/CLI-STANDARDS-AUDIT.md` |
| 2026-08-10 | 1.4.14 | second-level hardening | Authoritative 21-code catalog, specific `config_error`, semantic three-shell completions, and help consistency rows T-OUT-14..16/T-CLI-16..20 green; no new waiver |
| 2026-08-10 | 1.4.14 | local portability and test-gate repair | PTY capture drains concurrently; ITA transport passes Apple/Flox Git; Claude JSON object/event-array outputs normalize; hermetic, real-agent, Git-matrix, and unrestricted-Linux signal gates are explicit; no public CLI change or new waiver |
| 2026-08-10 | 1.4.14 | issue #14 output-contract repair | `fork --dry-run -o json` and `--json` now emit the same stable preview schema instead of human text; T-OUT-21 protects R4.2/R7.2/R8.6; no waiver |
| 2026-08-10 | 1.4.14 | macOS signal and live-agent gate repair | Git cleanup preserves active signal exceptions after macOS `EPERM`; real-agent failures expose captured output; preflight reports host executable identity/version; Flox retains the four-system development toolchain without pinning agent CLIs; no public CLI change or waiver |
| 2026-08-10 | 1.4.14 | issue #16 cleanup-safety reporting | Cleanup enumerates bounded dirty/unpushed risk, preserves full inspection under forced previews, adds compatible JSON `details` and granular overrides, escapes Git-controlled terminal text in human diagnostics, keeps raw JSON values, and preserves separate consent plus the non-overridable cwd guard; T-CLN-16..23 protect R7.1/R7.2/R7.8/R8.1/R8.6/R9.3; no waiver |
| 2026-08-11 | 1.4.14 | direct companion skill and session context | Skill delegates directly to `session --json` and `fork --require-agent --json`; session output adds directory and repository context; the wrapper is removed; local, host-managed, and fresh Claude/Codex forward gates pass; no new waiver |
| 2026-08-14 | 1.4.14 | read-only native session command | Codex OBJECT and Claude Code CONCUR WITH AMENDMENTS were reconciled before implementation. Session inspection additively reports a constructible, non-preflighted native command; terminal-unsafe inputs return a null command; help examples, exact skill routes, open JSON schema, and no-write behavior pass T-EMT-08..10/T-SES-28..32. Full local and clean-install gates pass; no new waiver. Fresh authenticated host acceptance is tracked separately because its additional private-context export was not authorized. |

## Requirement trace

`Implemented` means product behavior and direct test evidence exist. `Documented`
means the requirement is a policy or packaging property verified by inspection.
`Deferred` identifies work outside the approved implementation boundary rather than an
open implementation finding.

| Requirement | Disposition | Evidence |
|---|---|---|
| REQ-01 | Implemented | CLI owns repository detection through cleanup; G-GRD..G-CLN |
| REQ-02 | Implemented | Direct skill routes exact `--session`, exact `--session-only`, and fork intent to the existing JSON CLI commands; focused skill tests validate the route contract |
| REQ-03 | Implemented | G-DET explicit precedence and ambient Claude/Codex detection; the direct skill uses ambient detection as its primary path |
| REQ-04 | Implemented | Skill consumes and validates G-OUT JSON, then renders the returned command; malformed output fails diagnostically |
| REQ-05 | Implemented | Canonical `.agents/skills/agent-fork` artifact is shared through `.claude/skills/agent-fork`; missing CLI emits install hint |
| REQ-06 | Implemented | T-CLI-01 bare help, exit 0 |
| REQ-07 | Implemented + waived | `cleanup` service/command; R2.1 waiver above |
| REQ-08 | Implemented | Boolean negations, kebab-case, reserved shorts, and no-abbreviation regression |
| REQ-09 | Implemented | Fork creates without consent; G-GRD refusals are pre-mutation |
| REQ-10 | Implemented | Global help/version/verbosity/quiet/config/debug and per-result output flags; T-CLI-02 |
| REQ-11 | Implemented | Usage/not-found/precondition/runtime/signal mappings across G-CLI/G-OUT/G-RBK |
| REQ-12 | Implemented | G-CFG discovery boundaries and G-REG locked XDG state |
| REQ-13 | Implemented | G-CFG truth table and G-EMT per-agent `extra_args` boundary |
| REQ-14 | Implemented | Curated config env plus read-only host-agent signals; sealed-env fixtures |
| REQ-15 | Documented | No argv secrets; ignored-file/`.env` risk documented in README |
| REQ-16 | Implemented | G-OUT stream purity, final paste block, and TTY invariance |
| REQ-17 | Implemented | G-OUT minimum completed-result, dry-run-preview, and error schemas plus stable error catalog; cleanup error/result `details` protected by T-CLN-19/T-CLN-21 and terminal-safe human rendering by T-CLN-23 |
| REQ-18 | Implemented | T-OUT-08 human local-only plan, T-OUT-21 JSON preview contract, and cleanup dry-run/no-mutation reporting T-CLN-13/T-CLN-16/T-CLN-21 |
| REQ-19 | Implemented | G-GRD 14-row pre-mutation refusal matrix |
| REQ-20 | Implemented | G-ANC eight topologies and atomic branch/worktree creation |
| REQ-21 | Implemented | G-MAT 20-row exact/ignored/no-state transport matrix |
| REQ-22 | Implemented | G-RBK failure, manual recovery, producer, SIGINT, and SIGTERM rows |
| REQ-23 | Implemented | G-VER full ladder, ignored-aware comparison, opt-out, rollback |
| REQ-24 | Implemented | G-INC include precedence and non-fatal setup hook |
| REQ-25 | Implemented | Opaque gitlink handling and submodule notices in G-MAT |
| REQ-26 | Implemented | G-DET ambient strict detection; the direct skill selects it through `--require-agent`; pre-0.95 Codex ladder remains tombstoned per A7 |
| REQ-27 | Implemented | G-PRE CLI/version/rollout matrix |
| REQ-28 | Implemented + real-validated | G-EMT locked templates; E1–E3 rerun 2026-08-10 |
| REQ-29 | Implemented | G-PRE diagnostic refusals and no-mutation proof |
| REQ-30 | Implemented | One name feeds branch/path/Claude title; quoted extras |
| REQ-31 | Implemented | G-CLN target forms, worktree/branch/registry removal |
| REQ-32 | Implemented | Dirty/unpushed/cwd guards, bounded diagnostics, granular overrides, and the unchanged force boundary; T-CLN-05..08/T-CLN-14/T-CLN-16..22 |
| REQ-33 | Implemented | Consent, no-input, force separation, PTY prompt, dry-run |
| REQ-34 | Implemented | T-CLN-12 external session file invariant and resumability notice |
| REQ-35 | Implemented | Python floor, minimal dependencies, wheel, and console entry point clean-install |
| REQ-36 | Deferred | Publishing/release automation and channel validation are Phase F |
| REQ-37 | Implemented | MIT license present; fresh implementation uses behavioral corpus only |
| REQ-38 | Implemented for Phase D | Doctor, locale, signals/SIGPIPE, SemVer/deprecation docs, telemetry statement, blocking conformance CI |
| REQ-39 | Implemented | Four-system Flox/uv/just/ruff/ty/Git toolchain; host-managed agent CLIs; explicit hermetic/live/Git-matrix/signal gates |
| REQ-40 | Implemented/documented | No runtime network client dependency or call; ignored-mode cost documented |
| REQ-41 | Implemented | Atomic registry replacement, advisory timeout/death, concurrent forks, Git race |
| REQ-42 | Implemented | G-EMT hostile shell execution with `shlex.quote` per element |
| REQ-43 | Implemented | Sole PATH-resolved Git primitive plus shim canary/fault injection |
| REQ-44 | Implemented | G-LOC-08..17, G-NAM-08..12, T-CLI-13..14, and T-OUT-12..13 cover independent destination composition, validation, collisions, and output compatibility |
| REQ-45 | Implemented | G-DET/T-CLI-21..23 cover adaptive auto, strict, and Git-only behavior |
| REQ-46 | Implemented | G-CEX and T-CLI-24 cover bounded Codex app-server name resolution and UUID-only behavior |
| REQ-47 | Implemented | G-SES T-SES-01..22 cover agent-neutral inspection, validation, local evidence, and real-agent acceptance |
| REQ-48 | Implemented | G-CPI covers bounded structural inference, sharded screening cache, separate persistence, and management actions |
| REQ-49 | Implemented | G-SES T-SES-22..27; 8 focused skill tests; skill validation; editable dual-host placement; fresh Claude/Codex inspection, named, unnamed, refusal, collision, absent-Git, ambiguous-host, and hostile-name forward tests |
| REQ-50 | Implemented | G-EMT T-EMT-08..10 and G-SES T-SES-28..32 cover exact templates, terminal safety, identity/lineage independence, UUID lifetime, open JSON, human output, no mutation, and help; focused skill tests and skill validation cover both exact forms |

## Decision trace

| Decision | Disposition | Evidence |
|---|---|---|
| D1 | Implemented | Bare CLI prints help; T-CLI-01 |
| D2 | Implemented | `--no-with-state`; `--clean` explicitly rejected by T-CLI-12 |
| D3 | Implemented | Exact copy default; G-CFG/G-MAT |
| D4 | Implemented | Optional/derived/collision-safe names; G-NAM |
| D5 | Implemented | Sibling/mirror/central/subdirectory/template locations; G-LOC |
| D6 | Implemented | NamingPlan feed-through and Claude `-n`; G-NAM/G-EMT |
| D7 | Implemented | Trimmed fork schema plus per-agent extras; G-CFG |
| D8 | Implemented | Verify default/opt-out; G-VER |
| D9 | Implemented | OSC52-first, then platform helpers; failure is notice-only |
| D10 | Implemented | Ordered human/JSON `list`; G-REG |
| D11 | Implemented | Config-only, individually quoted extras in dry-run/JSON |
| D12 | Implemented | Registry targeting, force guard boundary, separate consent |
| D13 | Implemented + waived | `cleanup` name retained under R2.1 waiver |
| D14 | Implemented | Native-fork impossibility refuses diagnostically before mutation |
| D15 | Implemented | Independent base/leaf overrides compose after D5 derivation; exact paths remain parser-exclusive |
| D16 | Implemented | Adaptive auto/strict/Git-only agent mode; G-DET/T-CLI-21..23 |
| D17 | Implemented | Bounded Codex app-server name resolution; G-CEX/T-CLI-24 |
| D18 | Implemented | Agent-neutral session inspection and assertions; G-SES T-SES-01..22 |
| D19 | Implemented | Explicit bounded Claude parent inference and separate evidence; G-CPI |
| D20 | Implemented | Direct skill delegation and additive repository-aware session context; G-SES T-SES-22..27 plus focused, host-managed, and fresh-agent skill gates |
| D21 | Implemented | Shared native renderer and read-only session command; G-EMT T-EMT-08..10, G-SES T-SES-28..32, focused skill tests, and clean-install verification |

## Blocking conformance evidence

- `tests/cli/`: help shape, bare/malformed/unknown invocation, streams, TTY,
  exit codes, JSON, doctor, completion, cleanup consent, and output contracts.
- `tests/conformance/test_process_contract.py`: closed stdout/stderr SIGPIPE
  behavior without traceback or hang.
- `scripts/check_clean_install.sh`: sdist/wheel build, disposable venv install,
  packaged `--version`, help, bare invocation, completion, and import smoke.
- `.github/workflows/ci.yml`: separate blocking “Clean-install CLI conformance”
  job; no publish or release action.
