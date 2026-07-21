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
