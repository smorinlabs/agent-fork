# CLI Standard Conformance — agent-fork

| | |
|---|---|
| **Standard** | CLI Design Standard v1.4.14 |
| **Profile** | Small-CLI (Appendix A) — criteria check in REQUIREMENTS.md §3.1; migration trigger: second resource type ⇒ noun-verb next major |
| **Tier** | publishable |
| **Owner** | Steve Morin |
| **Current status** | **nonconforming; release blocked by R4.1 and R9.3** |

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

## Release-blocking MUST nonconformances

These are not waivers. The pinned standard does not permit a local decision to
turn either `MUST` into an optional requirement.

| Rule | Current behavior | Why release is blocked | Required resolution |
|---|---|---|---|
| R4.1 | A13(B) removes `table`; `-o/--output` accepts `text` and `json`, and `text` is the human default. | CLI Design Standard v1.4.14 requires `table` as the default human result format. | Amend the governing standard or restore a real `table` default before release. |
| R9.3 | A13(B) removes an existing accepted CLI value while the repository declares version `1.0.0` and Production/Stable status. | Removing `-o table` without a compatible deprecation or major-version transition breaks the declared interface-stability contract. | Complete an approved compatibility/version transition, or restore `table`, before release. |

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
| 2026-08-18 | 1.4.14 | P02 A9 shared agent-signal assessment | One four-state assessment now feeds fork resolution, session inspection, doctor, and current Claude inference. Incomplete automatic/strict fork input returns typed exit-3 `agent_signal_incomplete` before mutation; session adds an open-schema `agent_signal` object; doctor names non-secret present/missing signals. T-DET-13..26, T-OUT-22, T-CLI-27..31, T-SES-33..35, and T-CPI-36 protect R6.1/R7.1/R7.2/R7.6/R7.8/R7.12/R8.6/R9.3/R9.10/R9.14; no new waiver. |
| 2026-08-18 | 1.4.14 | P02 A13(B) output-value removal | Owner-approved removal of the byte-identical `table` value makes `text` the default and retains `json`. T-CFG-18 and T-CLI-32 protect resolved configuration, all parser routes, diagnostics, precedence, and completions. This is a release-blocking R4.1 and R9.3 `MUST` nonconformance, not a waiver; current conformance result is **fail**. |
| 2026-08-20 | 1.4.14 | P02 A10 Claude inferred-parent freshness | Session inspection adds the additive `parent_inference` object (last-known-good/freshness-unknown disclosure without expanding `parent_session` or `lineage.status`); cleanup adds the additive `retained_metadata` disclosure object; `claude-parent delete` and corpus-limit refusals add additive result fields and the new stable `claude_parent_incomplete_analysis` exit-3 code; `work.cache_write_failures` keeps its existing aggregate meaning with `freshness_write_failures` added alongside it. T-CPI-40..57, T-SES-48..50, T-CLI-36..41, and T-CLN-25..28 protect R6.1/R7.2/R7.6/R7.8/R7.12/R8.6/R9.3/R9.10/R9.14; no new waiver. Pre-existing from A13(B): this A10 row does not touch the release-blocking R4.1/R9.3 `table`-removal nonconformance above, and does not resolve it. |
| 2026-08-20 | 1.4.14 | P02 A11 config validation | `config validate`, `doctor`, and `fork` (dry-run and real) now share one semantic validator (`validate_values()`), with per-field provenance; failures name key/value/allowed forms/source and refuse exit-2 before mutation (R6.1, R7.1, R7.6, R7.8, R7.12). `config set` is driven by the same `KEY_SPECS` registry and the same `ConfigFinding` message shape, sharing the *predicates* (`branch_prefix_reason()`, `worktree_location_reason()`) rather than calling `validate_values()` directly — it validates the single key being set, not the whole resolved document, so an unrelated pre-existing invalid key never blocks an otherwise-valid `set`. `[fork].output` is accepted (owner-ratified ACCEPT), grounded in R3.8/R5.1 flag/env/config parity, not a resurrected docs promise — `AGENT_FORK_OUTPUT` was the sole key without a `[fork]` counterpart. `list`/`session`/`cleanup` now detect an invalid `AGENT_FORK_OUTPUT` the same as every other consumer (R9.3); `config view` honors a valid one; an explicit `-o`/`--json`/`--require-agent`/`--no-agent` flag can now rescue an otherwise-invalid `AGENT_FORK_OUTPUT`/`AGENT_FORK_AGENT_MODE` for every one of these commands, matching `fork`'s pre-existing precedence (a Gate-6 finding: the flag was not being threaded into resolution for the newly-touched commands). A valid `AGENT_FORK_OUTPUT=json` also now survives a *later* unrelated error (T-CLI-58) instead of only applying to the specific key that carried it. Invalid dry-run input mutates nothing (R8.6). `config get`'s `hasattr` fallback — which answered `config_path`, `mode`, `worktree_location_explicit`, `claude_extra_args`, `codex_extra_args`, and the bare `codex_session_name_resolution` — is removed as a deliberate surface change (R9.10); no test previously covered the fallback itself. **Deliberate compatibility break (F6):** a `worktree_location` template that renders relative to the process CWD (e.g. `"{repo-name}-wt"`, previously accepted) now fails validation on every config-resolving command — the template grammar requires a render starting with `/`, `~`, or `{repo-root}`, closing a class of silent misplacement this fault exists to fix. **Named follow-up, not required for this item (F12):** `set_user_value()`'s write is a plain, non-atomic `path.write_text()` that re-emits the whole file; a crash mid-write can still corrupt the entire configuration, not just the key being set. **A targeted Gate-6 re-verification pass also found a related, pre-existing (not a regression from this item) bug class:** `Path.expanduser()` treats a present-but-empty `HOME` as a literal empty prefix rather than unset in several call sites this item's own fix (`derive_worktree_path()`) does not cover — most notably `cli.py`'s `--worktree-dir` flag resolution, reproduced live as accepting a destination with `"validation":{"passed":true}` despite it having silently anchored under filesystem root. F12 and this HOME-mis-anchoring class are both filed together as smorinlabs/agent-fork#61. T-CFG-24..36, T-LOC-19..24, T-CLI-51..60, T-OUT-24 protect this (R9.14). T-LOC-23 and T-CLI-60 were added during a third Gate-6 review pass, closing a present-but-empty-`HOME` gap in `derive_worktree_path()` and a duplicate output-fallback gap in `doctor.py`'s own `except ConfigError` branch that the top-level `_machine_error_output()` fix did not reach. T-CFG-36 and T-LOC-24 close two escaping gaps a PR #62 bot review found (`config.py`'s and `location.py`'s own direct `ConfigError` raises bypassed the `ConfigFinding.render()` convention); T-LOC-23's fallback assertion was also hardened to not depend on the runner's own passwd database (same review round). This item's own `T-CLI` IDs were renumbered twice at merge time — `T-CLI-36..45` → `T-CLI-39..48` → `T-CLI-51..60` — to resolve collisions with A6a's and then A10's independently-merged rows in this fast-moving trunk; see `docs/testing/TEST-MATRIX.md`'s total-rows line for the full history. This item does not resolve the pre-existing R4.1/R9.3 `table`-removal nonconformance recorded above; overall conformance result remains **fail** pending that separate transition. |
| 2026-08-20 | 1.4.14 | P02 A12 setup-hook execution policy | The repository setup hook becomes provenance-gated, process-group-bounded, and disclosed while staying non-fatal (D22). `--setup-hook-policy {tracked,any,off}` uses `choices` with `default=None` so an unset flag falls through to configuration; `--setup-hook-timeout SECONDS` names its unit in `--help`; `setup_hook_policy` and `setup_hook_timeout` are rejected at `config validate` time rather than at use (R6.1, the A11 lesson). `interrupted_sigint` (130) and `interrupted_sigterm` (143) join the stable catalog, making those exit codes reachable from `main()` for the first time and closing a pre-existing conformance gap against REQ-22 and README's published interrupt contract (R7.12). `setup_hook` is additive in `fork --json` and in the `--dry-run` plan; no existing field changes meaning (R7.2, R9.3); the hook's progress narration is suppressed in machine mode and a machine-mode *error* is still exactly one JSON object (R7.8) — but the hook's skip and failure *notices* still reach stderr as plain text alongside it, through the pre-existing duplicate-notice path A12 deliberately preserves for backward compatibility (A13(a), tracked as `P02-T13ABF`, and pinned by T-OUT-25 so the exception stays named rather than unnoticed); `--dry-run` still performs no mutation while disclosing the hook (R8.6); `doctor` names the exact reason a hook would not run and the exact override (R9.10). Two deliberate semantic changes to record: `doctor`'s exit code can now signal a repository working-tree problem, not only machine readiness; and the bound the hook runs under is its *process group*, so a descendant that calls `setsid()` escapes termination — waiting for it is bounded instead, and `setup_hook.descendants_cleared` reports it. T-INC-08..17, T-RBK-08..10, T-CLI-61..64, T-OUT-26..28, and T-CFG-37..39 protect all of it (R9.14); no new waiver. |
| 2026-08-21 | 1.4.14 | P02 A5 unreadable-entry skip policy | A qualifying untracked or ignored entry may be skipped with a named notice while `fork` exits 0. This is not R6.3 partial failure: `fork` creates one named branch/worktree resource, while carried paths are internal transport state; the requested resource succeeded. `--strict` is a CLI-only safety flag that instead raises the cataloged `strict_skip_refused` runtime error at exit 1 after all skip-producing phases report, consistent with R6.1 and R6.3. `fork --json` additively exposes byte-wise ordered `skipped[]`; `strict_skip_refused` and `entry_unreadable` have documented stable details schemas (R7.2, R7.8, R7.12). T-CLI-68, T-MAT-30..38, T-VER-40..45, T-INC-22..24, and T-OUT-29..31 protect the new contract (R9.14). No waiver; the existing R4.1/R9.3 release blockers remain. |

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
| REQ-10 | Implemented with release blocker | Global help/version/verbosity/quiet/config/debug and per-result `text`/`json` output flags; T-CLI-02/T-CLI-32. The missing R4.1 `table` default blocks release. |
| REQ-11 | Implemented | Usage/not-found/precondition/runtime/signal mappings across G-CLI/G-OUT/G-RBK |
| REQ-12 | Implemented | G-CFG discovery boundaries and G-REG locked XDG state |
| REQ-13 | Implemented | G-CFG truth table and G-EMT per-agent `extra_args` boundary |
| REQ-14 | Implemented | Curated config env plus read-only host-agent signals; sealed-env fixtures |
| REQ-15 | Documented | No argv secrets; ignored-file/`.env` risk documented in README |
| REQ-16 | Implemented | G-OUT stream purity, final paste block, and TTY invariance |
| REQ-17 | Implemented | G-OUT minimum completed-result, dry-run-preview, and error schemas plus stable error catalog; T-OUT-22 protects typed `agent_signal_incomplete` details; cleanup error/result `details` protected by T-CLN-19/T-CLN-21 and terminal-safe human rendering by T-CLN-23 |
| REQ-18 | Implemented | T-OUT-08 human local-only plan, T-OUT-21 JSON preview contract, and cleanup dry-run/no-mutation reporting T-CLN-13/T-CLN-16/T-CLN-21 |
| REQ-19 | Implemented | G-GRD 14-row pre-mutation refusal matrix |
| REQ-20 | Implemented | G-ANC eight topologies and atomic branch/worktree creation |
| REQ-21 | Implemented | G-MAT 20-row exact/ignored/no-state transport matrix |
| REQ-22 | Implemented | G-RBK failure, manual recovery, producer, SIGINT, and SIGTERM rows; T-RBK-08/T-RBK-09 extend the signal rows to the setup hook's process group, and T-CLI-63 asserts the 130/143 translation at the `main()` boundary the library-level rows never reached |
| REQ-23 | Implemented | G-VER full ladder, ignored-aware comparison, opt-out, rollback |
| REQ-24 | Implemented | G-INC include precedence and non-fatal setup hook; A12 adds provenance gating, process-group bounds, and disclosure — T-INC-08..17 (eligibility, policy, bounded escaped output, timeout reaping, bounded drain for a descendant that leaves the group), T-RBK-10 (the group is signalled after its leader exits), T-CLI-61 (`--dry-run` disclosure), T-CLI-62 (`doctor` row and its failure condition), T-OUT-25 (JSON contract and stderr narration), T-OUT-27/28 (human-mode output-tail echo), T-CFG-37..39 (key resolution and A11-guard rejection) |
| REQ-25 | Implemented | Opaque gitlink handling and submodule notices in G-MAT |
| REQ-26 | Implemented | G-DET ambient strict detection plus T-DET-13..20 exact shared signal truth table; the direct skill selects it through `--require-agent`; pre-0.95 Codex ladder remains tombstoned per A7 |
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
| REQ-38 | Release-blocked | Doctor shared-signal classification and optionality remain covered by T-CLI-27..28, but A13(B) has not satisfied the R9.3 compatibility transition required for release. |
| REQ-39 | Implemented | Four-system Flox/uv/just/ruff/ty/Git toolchain; host-managed agent CLIs; explicit hermetic/live/Git-matrix/signal gates |
| REQ-40 | Implemented/documented | No runtime network client dependency or call; ignored-mode cost documented |
| REQ-41 | Implemented | Atomic registry replacement, advisory timeout/death, concurrent forks, Git race |
| REQ-42 | Implemented | G-EMT hostile shell execution with `shlex.quote` per element |
| REQ-43 | Implemented | Sole PATH-resolved Git primitive plus shim canary/fault injection |
| REQ-44 | Implemented | G-LOC-08..17, G-NAM-08..12, T-CLI-13..14, and T-OUT-12..13 cover independent destination composition, validation, collisions, and output compatibility |
| REQ-45 | Implemented | G-DET/T-CLI-21..31 cover adaptive auto, strict, Git-only, incomplete typed refusal, and no-mutation behavior |
| REQ-46 | Implemented | G-CEX and T-CLI-24 cover bounded Codex app-server name resolution and UUID-only behavior |
| REQ-47 | Implemented | G-SES T-SES-01..35 cover agent-neutral inspection, validation, local evidence, four-state additive signal output, and real-agent acceptance |
| REQ-48 | Implemented | G-CPI covers bounded structural inference, sharded screening cache, separate persistence, management actions, and T-CPI-36 shared current-signal assessment before discovery |
| REQ-49 | Implemented | G-SES T-SES-22..27; 8 focused skill tests; skill validation; editable dual-host placement; fresh Claude/Codex inspection, named, unnamed, refusal, collision, absent-Git, ambiguous-host, and hostile-name forward tests |
| REQ-50 | Implemented | G-EMT T-EMT-08..10 and G-SES T-SES-28..35 cover exact templates, terminal safety, identity/lineage independence, UUID lifetime, open JSON including separate signal state, human output, no mutation, and help; focused skill tests and skill validation cover both exact forms |

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
