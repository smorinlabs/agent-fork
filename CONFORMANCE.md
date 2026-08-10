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
| Scripted consumers (R7.2/R7.8) | yes | the agent-fork *skill* consumes `-o json` (REQ-04) |
| Async / long-running | no | synchronous local operations; no operation IDs |
| Streaming / watch | no | no streaming output |
| Plugins (R9.11) | no | no extension model planned |
| Caching / offline (R5.9) | no | no remote data; nothing cached (state registry is not a cache) |
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

## Phase D requirement trace

`Implemented` means product behavior and direct test evidence exist. `Documented`
means the requirement is a policy or packaging property verified by inspection.
`Deferred` identifies work outside the approved Phase D boundary rather than an
open implementation finding.

| Requirement | Disposition | Phase D evidence |
|---|---|---|
| REQ-01 | Implemented | CLI owns repository detection through cleanup; G-GRD..G-CLN |
| REQ-02 | Implemented | Phase E skill detects the host/session and passes explicit identity to the CLI; focused tests plus real Claude/Codex demos |
| REQ-03 | Implemented | G-DET explicit precedence and Claude/Codex fallback detection |
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
| REQ-17 | Implemented | G-OUT minimum result/error schemas and stable error catalog |
| REQ-18 | Implemented | T-OUT-08 complete local-only dry-run plan; cleanup dry-run T-CLN-13 |
| REQ-19 | Implemented | G-GRD 14-row pre-mutation refusal matrix |
| REQ-20 | Implemented | G-ANC eight topologies and atomic branch/worktree creation |
| REQ-21 | Implemented | G-MAT 20-row exact/ignored/no-state transport matrix |
| REQ-22 | Implemented | G-RBK failure, manual recovery, producer, SIGINT, and SIGTERM rows |
| REQ-23 | Implemented | G-VER full ladder, ignored-aware comparison, opt-out, rollback |
| REQ-24 | Implemented | G-INC include precedence and non-fatal setup hook |
| REQ-25 | Implemented | Opaque gitlink handling and submodule notices in G-MAT |
| REQ-26 | Implemented | G-DET; pre-0.95 Codex ladder remains tombstoned per A7 |
| REQ-27 | Implemented | G-PRE CLI/version/rollout matrix |
| REQ-28 | Implemented + real-validated | G-EMT locked templates; E1–E3 rerun 2026-08-10 |
| REQ-29 | Implemented | G-PRE diagnostic refusals and no-mutation proof |
| REQ-30 | Implemented | One name feeds branch/path/Claude title; quoted extras |
| REQ-31 | Implemented | G-CLN target forms, worktree/branch/registry removal |
| REQ-32 | Implemented | Dirty/unpushed/cwd guards and force boundary |
| REQ-33 | Implemented | Consent, no-input, force separation, PTY prompt, dry-run |
| REQ-34 | Implemented | T-CLN-12 external session file invariant and resumability notice |
| REQ-35 | Implemented | Python floor, minimal dependencies, wheel, and console entry point clean-install |
| REQ-36 | Deferred | Publishing/release automation and channel validation are Phase F |
| REQ-37 | Implemented | MIT license present; fresh implementation uses behavioral corpus only |
| REQ-38 | Implemented for Phase D | Doctor, locale, signals/SIGPIPE, SemVer/deprecation docs, telemetry statement, blocking conformance CI |
| REQ-39 | Implemented | Flox/uv/just/ruff/ty development environment and gates |
| REQ-40 | Implemented/documented | No runtime network client dependency or call; ignored-mode cost documented |
| REQ-41 | Implemented | Atomic registry replacement, advisory timeout/death, concurrent forks, Git race |
| REQ-42 | Implemented | G-EMT hostile shell execution with `shlex.quote` per element |
| REQ-43 | Implemented | Sole PATH-resolved Git primitive plus shim canary/fault injection |
| REQ-44 | Implemented | G-LOC-08..17, G-NAM-08..12, T-CLI-13..14, and T-OUT-12..13 cover independent destination composition, validation, collisions, and output compatibility |

## Phase D decision trace

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

## Blocking conformance evidence

- `tests/cli/`: help shape, bare/malformed/unknown invocation, streams, TTY,
  exit codes, JSON, doctor, completion, cleanup consent, and output contracts.
- `tests/conformance/test_process_contract.py`: closed stdout/stderr SIGPIPE
  behavior without traceback or hang.
- `scripts/check_clean_install.sh`: sdist/wheel build, disposable venv install,
  packaged `--version`, help, bare invocation, completion, and import smoke.
- `.github/workflows/ci.yml`: separate blocking “Clean-install CLI conformance”
  job; no publish or release action.
