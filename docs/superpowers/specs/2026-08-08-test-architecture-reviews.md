# agent-fork test-architecture — adversarial review findings index

Companion to [`2026-08-08-test-architecture-design.md`](2026-08-08-test-architecture-design.md) (§9).
Four rounds, two independent lenses per round (Fable = `F`, Codex = `C`), 74 findings.
Each line: ID · severity · the claim, compressed · disposition (spec section or amendment).
Full finding texts live in the 2026-08-08 planning-session transcript; this index is the durable registry.

## Round 1 — whole design (tiers/groups/matrix)

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| R1-F01 | H | D5 worktree-location had no group or axis | G-LOC added (§3) |
| R1-F02 | H | REQ-26 pre-0.95 ladder is dead code under D14 — corpus contradiction | Owner ruling → A7 (removed, tombstoned) |
| R1-F03 | H | Fixed 6-check G-VER drops RESEARCH §4's per-topology conditional asserts | G-VER = 6 base + conditional checks (§3, §5) |
| R1-F04 | H | Porcelain byte-equality blind to files inside untracked dirs | Manifest+hash oracle (§6.5) |
| R1-F05 | H | No fault-injection path for verify-fail → rollback → exit 1 | Clean-filter injection row (§5 G-VER, §6.6) |
| R1-F06 | H | Mode axis as `--clean` contradicts D2; mode is an output of tri-state resolution | Toggle-expressed mode + conflict rows (§4) |
| R1-F07 | MH | D4 naming pipeline had no group; detached auto-name undefined | G-NAM added; owner ruling → A5 |
| R1-F08 | MH | Codex-only obligations die under claude baseline | Agent axis varies in G-PRE/G-OUT/G-EMT (§4) |
| R1-F09 | MH | Row-level checker can't see missing parametrizations | Cell-level checker (§7.4) |
| R1-F10 | MH | R-tier auto-skip + skip/xfail stubs = two vacuous-green paths | Require-real toggle + lifecycle (superseded by R3 → §7.2) |
| R1-F11 | M | Bare topology conflates layout with invocation point | Topology values split (§4) |
| R1-F12 | M | No hermetic git/env contract for fixtures | Sealed env (§6.2; upgraded whitelist per R2) |
| R1-F13 | M | Consent-prompt + TTY-format rows untestable over pipes | pty harness (§6.6; per-fd per R2) |
| R1-F14 | M | Signals/concurrency groups had no fixture mechanism | Stall/barrier primitives (§6.6; redesigned per R2) |
| R1-F15 | M | Submodule + .worktreeinclude/setup-hook rows missing | G-INC added; submodule rows in G-MAT (§3, §5) |
| R1-F16 | M | doctor content, config set/validate, completion, clipboard uncovered | Rows added (§3 G-CFG/G-CLI/G-OUT) |
| R1-F17 | L | Config walk-up boundary in linked worktree undefined | Owner ruling → A6 (worktree root) |
| R1-F18 | L | Exit-code traps unpinned; E4/E6 restorable from stale docs | Explicit rows; tombstone/retired conventions (§5, §7.3) |
| R1-C01 | H | Unmerged-index and intent-to-add states unhandled and unfixtured | Owner rulings → A3 (support ITA), A4 (refuse unmerged) |
| R1-C02 | H | Test oracle can't prove tracked contents/modes were copied | ls-files --stage + hash oracle (§6.5) |
| R1-C03 | H | Baseline scheme misses linked-worktree × dirty-state interaction | Mandatory interaction row (§4) |
| R1-C04 | H | Producer-side git diff failure mistaken for empty-diff success | Producer-failure shim rows, G-RBK (§5, §6.6) |
| R1-C05 | M | Exact-copy silently excludes empty dirs; contract unlocked | Empty-dir contract row (§5 G-MAT) |
| R1-C06 | M | E4 silently dropped vs REQ §9's E1–E4 | Owner ruling → A8 (retired until v1.1) |

## Round 2 — Section 3 (fixture infrastructure)

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| R2-C01 | H | Registry-lock barrier can't position the race; loser exits 1 not 5 | Shim barrier; owner ruling → A1 (§6.6) |
| R2-C02 | H | ITA not transported by diff/apply; unmerged unreconstructable | A3 transport recipe; A4 refusal (§5 G-MAT, §8) |
| R2-C03 | H | Env seal missed GIT_DIR/GIT_CONFIG_COUNT/EXEC_PATH/etc. | Whitelist-from-empty env (§6.2) |
| R2-C04 | M | Clean filter fires at wrong pipeline phase (apply runs smudge) | Staged-new-file scenario + parent-side stall (§6.6) |
| R2-C05 | M | Submodule fixtures break manifest oracle; protocol.file.allow blocks setup | Gitlink pruning (§6.5); scoped allow=always (§6.3) |
| R2-C06 | M | stdlib pty merges streams and cooks bytes | Per-fd openpty harness (§6.6) |
| R2-F01 | M | Filter injection works (verified) but narrow + version-sensitive | Staged-new-file pin + G-FIX canary (§5, §6.6) |
| R2-F02 | H | Barrier stages the sequential test, not the race; REQ-41 exit-5 unimplementable | Shim barrier + registry race re-task + A1 (§6.6) |
| R2-F03 | M | Child-side signal stall races rollback; leaked filter processes | Parent-side stall, process groups, self-terminating filters (§6.6) |
| R2-F04 | M | TTY byte-equality is empirically false (ONLCR, merged streams) | Per-fd wiring, ONLCR cleared (§6.6) |
| R2-F05 | H | Blacklist-shaped seal leaks CLAUDECODE/CLAUDE_CODE_SESSION_ID into every test | Whitelist env + G-FIX leak assertion (§6.2, §5) |
| R2-F06 | M | All shim machinery assumes per-call PATH resolution of git | A10 + shim-interception canary (§8, §5) |
| R2-F07 | M | macOS /tmp→/private/tmp aliasing breaks path-equality oracles | Realpath discipline (§6.5) |
| R2-F08 | M | Nothing verifies the oracles; FIFO hangs a hashing walk; empty-dir ambiguity | Oracle mutation rows; lstat-only; per-mode empty-dir semantics (§5, §6.5) |
| R2-F09 | L | origin/HEAD auto-set is version-dependent | Constructor runs set-head; fallback row (§6.4; verified 2026-08-08) |
| R2-F10 | L | Unborn-HEAD parents pass guards, die raw at anchor | Owner ruling → A2 (§8) |
| R2-F11 | L | Midnight retry reruns into its own debris; worktree templates uncopyable | Rebuild-fresh rule; no worktree template caching (§6.6, §6.7) |
| R2-F12 | M | Plain teardown fails on hostile rows' own machinery | Hardened finalizer order + orphan sweep (§6.7) |

## Round 3 — Section 4 (skeletons/workflow)

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| R3-C01 | H | xfail(strict) absorbs fixture-setup errors as green XFAIL | No-xfail three-state lifecycle (§7.2) |
| R3-C02 | H | No machine-readable group/row state; tombstone-vs-stub contradiction | Status/row_status fields + per-state invariants (§4, §7.2) |
| R3-C03 | H | Function-level marker defeats cell accounting under parametrize | Per-param pytest.param(id=…, marks=…) (§7.2) |
| R3-C04 | M | One-file-per-group breaks on multi-tier groups | One file per (group, tier) (§7.1) |
| R3-C05 | M | AGENT_FORK_REQUIRE_REAL violates REQ-14; suite/product floors conflated | pytest option; TEST_HARNESS_GIT_MIN vs PRODUCT_GIT_MIN → A9 (§2, §8) |
| R3-C06 | M | "Local + CI" checker with no CI wiring in the deliverable | CI-ready posture + implementation-start job (§7.6) |
| R3-F01 | M | Lifecycle survives setup errors but hides vacuous red (fixture typos) | Superseded by no-xfail lifecycle (§7.2) |
| R3-F02 | H | "Group in implementation" had no source of truth — enforcement circular | Status field in TEST-MATRIX.md group headers (§7.2) |
| R3-F03 | H | Path-tells-group doesn't survive multi-tier groups | (group, tier) layout + directory-vs-tier checker rule (§7.1, §7.4) |
| R3-F04 | M | Product-namespace env var for a harness toggle | Renamed outside AGENT_FORK_* (§2) |
| R3-F05 | M | 2.43 floor exists nowhere; product floor undefined | A9: harness constant + PRODUCT_GIT_MIN amendment (§8) |
| R3-F06 | M | Multi-row functions + N/A cells unexpressible in the marker scheme | Per-param marks; N/A notation + checker exclusion (§4, §7.2) |
| R3-F07 | M | Retired (E4) collides with stub-freshness and tombstone rules | Distinct retired/tombstone contracts (§7.3) |
| R3-F08 | M | Collection mechanics: literal params, unregistered marker, test_package.py | Authoring rules + pyproject registration + scoping (§6.1, §7.1, §10) |
| R3-F09 | L | Checker/CI/just entry points unowned | just check-matrix + named CI owner (§7.4, §7.6) |

## Round 4 — the spec document itself

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| R4-C01 | H | "blocked: none" false — lock-wait + PRODUCT_GIT_MIN rows are blocked | Two named blocked classes with unblock gates (§4, §5) |
| R4-C02 | H | G-CFG U-only / G-REG missing C / producer row double-assigned | Tiers corrected; G-RBK sole owner; layout updated (§3, §5, §7.1) |
| R4-C03 | M | Mode axis values and conflict outcomes undefined | Token vocabulary + RESEARCH §1.1-pinned outcomes (§4) |
| R4-C04 | H | Lifecycle/checker contract inconsistencies (markers, retired skips, E1–E4) | Skip-marker wording, live-row invariants, E1–E6 accounting (§7.2, §7.4) |
| R4-C05 | M | Setup-hook contract referenced, never specified; pipeline order ambiguous | G-INC normative pipeline order + hook contract (§5) |
| R4-C06 | H | Experiment ordering unresolved; E1/E2 gate templates | Explicit dependency chain (§2) |
| R4-C07 | M | Amendments lack targets; review citations unresolvable | Amends targets (§8); this index |
| R4-F01 | H | Spec outside corpus precedence chain; amendments unexecuted | Precedence statement (§1) + §10 step 0 |
| R4-F02 | H | G-REG claims tier U but layout had no unit/test_reg.py | Layout corrected (§7.1) |
| R4-F03 | M | done-invariant vs tier-R conditional skips; "markers removed" ambiguous | Exempt skip classes; skip-marker wording (§7.2) |
| R4-F04 | M | Checker accounting stopped at E4 while §5 mandates E5/E6 rows | E1–E6 accounting (§7.4) |
| R4-F05 | M | Producer-pipe-failure row assigned to two groups | G-RBK sole owner (§3, §5) |
| R4-F06 | M | Mode axis had no value vocabulary | Token vocabulary (§4) |
| R4-F07 | ML | Blocked taxonomy contradiction with G-REG deferral | Blocked classes (§4, §5) |
| R4-F08 | M | Marker registration + strict-markers never scheduled | §10 step 1; §1 deliverables |
| R4-F09 | M | Phase silently forks P01 tracking; Phase B and T18 unreconciled | §2 chain (stubs become TS01–TS03); §7.6 T18 split; §10 step 5 |
| R4-F10 | L | A1/A2/A10 named no corpus target; R-citations unresolvable | Amends targets (§8); this index |
