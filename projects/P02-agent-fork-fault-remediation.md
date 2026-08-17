# P02 — agent-fork fault remediation

**References**
- **Trunk:** [PROJECTS.md](../PROJECTS.md)
- **Depends on:** [P01 — agent-fork v1](P01-agent-fork-v1.md) — faults found in the shipped v1 surface; A8 extends the already-tracked P01-T51
- **Discussion:** fault analysis session 2026-08-16 (three-agent code sweep: pipeline, session/lineage, UX/config; findings spot-checked against source before recording)

## [~] Project P02: agent-fork fault remediation (v1.x)
**Goal**: Work the thirteen faults A1–A13 found in the 2026-08-16 analysis,
one at a time in order, each through the gated process below. A fault is
closed when its fix has passed adversarial post-implementation review, or
when its adversarial verification refutes the hypothesis (recorded as
refuted, no fix).

**Process (applies to every item)**
1. **Adversarial verification gate — validation-first** (owner decision
   2026-08-17, after A2's register entry proved overstated). Reading the code
   is not verification. Before any fix, build an **exhaustive probe matrix**
   for the item and run it: enumerate every input the hypothesis implicates
   (each environment variable, each configuration key, each state shape) and
   cross it with every operation that could be affected — worktree creation,
   branch creation, materialization, verification, cleanup — then record what
   each cell actually does. A cell is only "a problem" when a probe
   demonstrates it, with captured output.

   The register entry is then **rewritten to match the evidence** before any
   implementation: claims that did not reproduce are struck, severity is
   re-rated, and untested surface is listed explicitly as unverified. Only
   then does design begin. A Codex pass reviews the matrix and the rewritten
   claim as the independent second-model lens.

   Outcomes: *confirmed, scoped to what reproduced* → proceed;
   *scope creep / divergence from core functionality* → pause and raise to
   the owner with clear context; *refuted or overstated* → rewrite the entry,
   record why, and re-decide whether it is still worth fixing.

   Rationale: A2 was registered as high-impact wrong-repository mutation.
   Probing showed an existing guard already refuses the headline case, and the
   real defect is narrower. Implementing the original entry would have built
   defenses against a threat that does not exist while missing the one that
   does.
2. **Auto-proceed unless flagged** — a clean confirmed verdict flows
   straight into planning; only scope questions, refutations, and surprises
   come back to the owner (owner decision 2026-08-16).
3. **Design doc per item** (owner amendment 2026-08-16) — every gate
   A1, A2, … gets its own design doc at
   `docs/superpowers/plans/<date>-p02-a<NN>-<slug>.md` recording the
   verification verdict and evidence, the chosen design, and the outcomes
   of both adversarial reviews. The doc is created at plan time and
   updated as the item's gates close; the item's task lines link to it.
4. **Implementation plan** (inside that design doc), then adversarial
   review of the plan (incl. Codex).
5. **Implementation** — TDD (failing test first) and subagent-driven, in its
   own worktree per house discipline.
6. **Adversarial review of the implementation** (incl. Codex); loop until clean.

**Gate-6 routing (owner decision 2026-08-17).** When an item's adversarial
implementation review raises findings beyond that item's minimal remediation,
the item absorbs only what its own approved design promised plus defects the
work introduced; everything else is opened as a GitHub issue and, where it
matches a registered fault, noted against that fault. A1's routed findings are
issues #28 (root-confined hashing → overlaps A2), #29 (intent-to-add pathspec
magic → A13(e)), #30 (latency gate and progress output → A13(h)), #31
(coverage gaps: dirty submodules → A6, sparse checkout, exotic filenames), and
#32 (pre-existing guard-error and hook-output sinks that render
repository-controlled text raw).

**Out of Scope**
- Enhancements B1–B4 (separate project: [P03](P03-agent-fork-core-enhancements.md))
- Enhancements B5–B9 from the same analysis — dropped entirely by owner
  decision 2026-08-16 (bulk/merged cleanup, agent extensibility seam, JSON
  schema versioning, unsealed-config test tier as a standalone effort,
  Windows policy). A fix may still add the specific tests it needs.
- New features of any kind; each fix is the minimal correct remediation.

### Fault register

- **A1 — Verification compares status codes, never content.**
  `verify.py:56-60` compares parent/child `git status --porcelain=v1 -z`
  bytes only. Content mutations that preserve the status letter pass
  verification: user `apply.whitespace=fix` rewrites hunks silently
  (`materialize.py:71` runs `git apply` without `--whitespace=nowarn`);
  CRLF/clean-smudge/LFS asymmetries behave the same. Attacks the core
  "copied and verified" promise. Proposed direction: content-hash rung in
  the ladder for staged/modified files + pin `apply.whitespace` on apply
  calls. Impact: high. Type: correctness fix. Spot-checked 2026-08-16.
- **A2 — No policy pins the Git settings correctness depends on; the harness
  hides the class.** *(Rewritten 2026-08-17 after probing; see "Corrected
  claim" below.)*
  `cli.py:667` forwards `os.environ` verbatim to all 50 `run_git` call sites
  across 10 modules, and no call pins configuration — there is no `git -c`
  anywhere in `src/`. Git takes instructions from arguments, configuration
  files, and environment variables, and the environment overrides the
  directory it is pointed at. Meanwhile the sealed harness
  (`tests/conftest.py:809-863`) pins `GIT_CONFIG_NOSYSTEM`, a controlled
  `GIT_CONFIG_GLOBAL`, and `defaultBranch`/`quotePath`/`autocrlf`/`symlinks`,
  so every test runs where this cannot occur.

  **Corrected claim.** The original entry rated this *high* and asserted that
  "probes and mutations target the wrong repository." Two probes on 2026-08-17
  did **not** reproduce that:
  - `GIT_DIR` + `GIT_WORK_TREE` aimed at a second repository: Git was
    redirected (`rev-parse --show-toplevel` reported the other repository),
    but agent-fork **refused** with `config_error` — "cannot discover project
    config outside worktree root" — because a config-discovery boundary check
    caught the mismatch. No mutation.
  - `GIT_INDEX_FILE` aimed at a genuinely divergent index (verified: different
    blob for the same path), chosen because it does not move the repository
    root and so cannot trip that check: the fork succeeded and carried the
    correct content. Because one environment reaches every Git call, reads,
    transport, and verification agree with each other — self-consistent, not
    corrupt.

  What survives: (1) **configuration is unpinned** — this is A1's confirmed
  root cause, where a user's `apply.whitespace = fix` silently rewrote
  transported content; A1 pinned `--whitespace=nowarn` and
  `--untracked-files=all` as one-offs, which is the ad-hoc pattern a policy
  should replace; (2) **the class is untestable** under the sealed harness,
  which is why A1's fault survived 400 passing tests.

  Impact: **medium** (was high). Type: robustness + test architecture.
  Not data loss on current evidence.

  **Unverified surface — the gate must probe before any fix.** Only two
  environment variables have been tested, on macOS only. The **canonical inventory of
  untested inputs — 13, with priorities and exclusions — lives in the A2 design
  doc** (`docs/superpowers/plans/2026-08-17-p02-a2-environment-hardening.md`,
  "Canonical input inventory"); it is authoritative and is not restated here,
  because three divergent copies previously disagreed on both membership and
  count. Each must be probed against each mutating operation — worktree
  creation, branch creation, materialization, verification, and cleanup —
  because the boundary check that caught `GIT_DIR` guards discovery, not every
  operation. **If any probe
  produces a wrong-repository mutation, restore the high rating.**

  Proposed sequencing (reordered 2026-08-17): unsealed-configuration test tier
  **first** — it is what makes the class visible and would have caught A1 —
  then environment sanitization at the single `run_git` chokepoint, then the
  per-subcommand pinning policy, which is the design-heavy part.
  Rough size: about a week, dominated by deciding what to pin. Pinning too
  little admits the next `apply.whitespace`; pinning too much overrides
  settings a repository legitimately needs, such as `core.autocrlf` or a
  required content filter.
- **A3 — Global flat fork registry clobbers across repositories.**
  One machine-wide `forks.json`; `RegistryEntry` (`models.py:53-75`) has no
  repo field. `add_entry` (`registry.py:111`) silently deletes a same-named
  entry from another repo; `find_owned` (`registry.py:127-136`) matches a
  bare name/branch across all repos, so cleanup can resolve to another
  repo's worktree. Auto-name collision check (`cli.py:487-514`) never
  consults the registry. Proposed direction: add repo/common-dir field,
  scope uniqueness and cleanup resolution per-repo (registry has a version
  field for migration). Impact: high. Type: data-safety fix. Spot-checked
  2026-08-16.
- **A4 — Agent-CLI recipe drift is undetectable; failure lands post-fork.**
  Emitted recipes live in `agents.py:286-301` guarded only by version
  floors (`agents.py:65-68`) — a future CLI that drops `--fork-session`
  passes every check and fails in the user's fresh terminal after branch,
  worktree, registry, and lineage were created. `parse_version`
  (`agents.py:88-93`) grabs the first `\d+.\d+` anywhere in output. Recipe
  duplicated as prose in four docs with no drift check.
  **Re-scoped and downgraded 2026-08-17** (owner-directed, and pulled ahead
  of A2/A3 in the same session — see the order note under Tests & Tasks).

  *Why semantic versioning cannot carry this.* The natural remedy — treat a
  dropped flag as a breaking change and detect the major bump — cannot work
  for either dependency. (Narrowed after the TS04 review, which correctly
  objected that "structurally vacuous" overstated it: a tested-range upper
  bound such as `>=0.95.0,<0.148.0` *would* function as an unknown-version
  detector. It cannot identify *which* capability changed, and it warns on
  every unreviewed release — so it is rejected for precision and noise, not
  for impossibility.) Codex is `0.147.0` against
  the `CODEX_ENV_MIN = (0, 95, 0)` floor: 52 minor releases, zero major
  bumps, and semver §4 gives `0.x` no stability guarantee at all, so the
  major is a constant that never moves. Claude Code is `2.1.233` against
  `CLAUDE_FORK_MIN = (2, 0, 73)`; `CLAUDE_RELIABLE_MIN = (2, 1, 100)` is
  this repo's own evidence that behavior `agent-fork` depends on changed
  inside a minor. Neither vendor publishes a flag-deprecation policy.
  A floor answers "has the feature arrived?" (testable); a ceiling asks
  "has it since been removed?" — unanswerable by version arithmetic,
  because it is a claim about releases that do not exist yet.

  *Prior art routes this to feature detection.* Declared-range mechanisms
  (Terraform `required_version`, npm `engines`, Cargo `rust-version`) and
  skew policies (`kubectl` ±1 minor) work only where the dependency
  publishes a compatibility contract. Where none exists, mature tools probe
  or negotiate capabilities instead: autoconf ("test for features, not
  versions"), browser feature detection replacing UA sniffing, Docker
  client/daemon API negotiation, LSP `initialize` capability exchange.

  *Revised remedy — two warn-level mechanisms, both cheap:*
  (a) detect *ambiguous* version output rather than trying to out-guess it.
  Demonstrated during implementation: given
  `"notice: new version 10.2.3 available\n2.1.233 (Claude Code)"`,
  `parse_version` returns `(10, 2, 3)` — the banner's version, not the
  CLI's — which then silently passes or fails a floor. Restricting the scan
  to the first non-empty line was tried and rejected: leftmost-match already
  wins within a line, so it adds no detection power while breaking the
  tolerated `"warning…\ncodex-cli 0.147.0"` shape. Instead `version_tokens`
  counts distinct version-like tokens and preflight warns when more than one
  is present, naming the tuple it read, so a wrong parse is visible in the
  refusal message rather than silent. The regex also gains a `.` guard
  (`(?<![\d.])`) so a mid-version fragment cannot match;
  (b) probe the installed CLI's `--help` in `preflight_agent` for the flag
  tokens the recipe emits, appending a `PreflightResult.notices` entry when
  one is absent. Only *option declarations* count — the leading part of a
  help line that starts with `-`, description stripped — because prose such
  as "this replaces `--fork-session`" would otherwise prove the flag still
  exists. Warn-and-proceed, never refuse: the fault being fixed is
  recoverable, so a blocking probe would convert it into a new pre-fork
  failure firing on a mere help-text reorganization. The probe is
  three-state — supported, absent, or **unverified** — because silence on
  unreadable help would make "no evidence" indistinguishable from verified
  support, and would hide removal of the Codex `fork` subcommand entirely.
  A rendered-command/flag-list equality test keeps (b) honest in both
  directions, since the flag list is the same drift problem one level in.

  *Timing, stated precisely (corrected after the TS04 review).* Detection is
  pre-mutation — `preflight_agent` runs before any branch, worktree,
  registry, or lineage write. The **notice is not**: `cli.py` renders
  `result.notices` only after `fork(...)` returns, so the user reads the
  warning attached to a completed fork, not while deciding. The warning
  therefore tells them to expect the paste command to fail and to run
  `cleanup`; it does not spare them the residue. Surfacing it before
  mutation would need a CLI-level change and is deliberately not in A4.

  *Prose duplication — no action, by disposition.* The recipe is repeated in
  four docs, but T-EMT-01/02 already pin the rendered template byte-exact, so
  the executable copy is drift-tested; the prose copies are display-only and
  a doc-drift checker would gate more than it protects.

  *Dropped from the original direction:* the recorded
  verified-against-version fingerprint (re-encodes the floor problem; the
  probe subsumes it) and the above-ceiling preflight warning (on `0.x`
  Codex it fires on essentially every run, training users past the
  warnings that matter).

  *Known limits (sharpened by the TS04 review).* The probe detects the
  **absence of an exact token from a readable option declaration** — which
  is narrower than "detects removal". It does not catch semantic change (a
  flag still listed but with a new precondition), and it cannot distinguish
  removal of the Codex `fork` subcommand from any other unreadable help;
  that case reports unverified rather than absent. A second spawn against
  `codex --help` would separate them and was judged not worth it at warn
  level. Ambiguity counting now spans stdout and stderr, but only one
  stream is parsed for the version itself.

  Impact: medium (downgraded from high — the failure is loud, non-
  destructive, and recoverable: the worktree materializes correctly and
  the paste command fails visibly with the CLI's own error, unlike the
  silent-and-destructive A1 and A3. Residue is non-zero: registry and
  lineage records reference a child session that never ran). Type:
  robustness.
- **A5 — One bad untracked filesystem entry destroys the whole fork.**
  Socket/fifo raises at `materialize.py:58-59`; unreadable or mid-copy
  deleted file raises at `materialize.py:156-157`; both roll back the whole
  worktree. The include path already has the right policy — notice and skip
  (`include.py:77`). Also: concurrent parent edits between snapshot and
  post-materialize check trip `parent-untouched` (`verify.py:64-68`) and
  roll back a correct fork. Proposed direction: skip-with-notice for
  non-regular/unreadable entries; retry-once or warn for the parent-status
  race. Impact: medium-high. Type: robustness.
- **A6 — Dirty submodules likely make the repo unforkable by default.**
  `git worktree add` leaves submodules uninitialized; `materialize.py:89-99`
  only emits a (misleading "copied opaquely") notice; parent ` M vendor/mod`
  status has no child counterpart → `exact-copy-status` fails → rollback.
  Tests cover only the clean-submodule case. Proposed direction:
  verification exemption for submodule status lines at minimum. Impact:
  medium-high for submodule users. Type: correctness fix. Reasoned, not yet
  reproduced — verification gate must build the dirty-submodule repro first.
- **A7 — Stale registry entries are uncleanable; no prune/repair verb.**
  Reproduced: hand-delete a fork worktree, then `cleanup <name> --yes` dies
  with raw git `runtime_error` (`cleanup.py:126-166` runs `git -C
  <missing-dir>`); `list` reports `worktree_exists: false` forever;
  `git worktree move` orphans the stored path. Only remedy is hand-editing
  `forks.json`. Proposed direction: typed error for the missing-worktree
  case + `prune`/`cleanup --missing`. Impact: medium-high. Type:
  robustness. (The remedial verb is minimal-remediation here, not a P03
  feature.)
- **A8 — Confirmation TOCTOU family (extends P01-T51).**
  Beyond the tracked auto-name drift: date rollover in the derived name
  (`naming.py:35-36`, local midnight); third independent anchor resolution
  at `repository.py:307`; recomputed counts; and the dry-run JSON's Claude
  `launch.command` carrying a different child UUID than the real run
  (`cli.py:554` calls `build_launch_command` without `child_session_id` so
  `agents.py:315` mints one; `pipeline.py:95-99` mints another — confirmed;
  skill confirmation does not display that command, so machine-consumer
  inconsistency). Proposed direction: the T51 plan-token fix widened to
  cover the family — dry run emits an opaque plan
  `{name, branch, destination, anchor, child_session_id}`; `fork --plan
  <token>` executes exactly it or refuses typed. Impact: medium-high.
  Type: correctness fix.
- **A9 — Agent detection is asymmetric, env-only, duplicated five times.**
  Codex detection is one inherited env var (`CODEX_THREAD_ID`,
  `agents.py:376-379`) — any shell inheriting it is "a live Codex session";
  no process-tree corroboration. Partial Claude signal (`CLAUDECODE=1`
  without session ID) collapses silently to a misleading "no agent signal".
  Predicate duplicated in `agents.py` (×2), `session.py:244-247`,
  `doctor.py:82-85`, `cli.py:872-874`. Proposed direction: single detection
  function, corroborating signal or staleness heuristic for Codex, honest
  partial-signal notice. Impact: medium. Type: robustness.
- **A10 — Lineage inference self-invalidates; stores never shrink.**
  Freshness fingerprint includes transcript `st_size`/`st_mtime_ns`
  (`claude_lineage_inference.py:172-177`) so any new message marks the
  recorded inference stale and discards it (`session.py:309-311`). Screen
  cache grows a permanent shard per transcript-append, no GC; `cleanup`
  never removes lineage/inference records; cache eviction silently weakens
  staleness detection (digests under `XDG_CACHE_HOME`, records under
  `XDG_STATE_HOME`, `lineage_inference_store.py:40-53`); corpus limits are
  hard failures even for `--current` (>10k transcripts or >2 GiB refuses
  entirely). Proposed direction: content-prefix fingerprinting or
  last-known-good fallback, cache GC, lineage cleanup hook, per-target
  limits. Impact: medium. Type: robustness.
- **A11 — `config validate` passes configs that crash `fork`; README
  documents a rejected key.** Reproduced: `worktree_location = "{bogus}/x"`
  validates clean then fails `fork` as bare `runtime_error`/exit 1 instead
  of `config_error`/exit 2 (`location.py:104` raises unwrapped
  `ValueError`), violating the exit-code contract. `README.md:458`
  documents `output` under `[fork]`, which `_FORK_KEYS` (`config.py:21-29`)
  rejects — env-var-only in practice. `config set` cannot set the shipped
  `extra_args` (D11). Impact: medium. Type: correctness fix + docs-code
  drift.
- **A12 — Repository setup hook: no timeout, no opt-out, unreviewed
  execution.** `include.py:100-102` runs `.agent-fork/worktree-setup.sh`
  with no `timeout=` (hang forever; Ctrl-C deletes the worktree around the
  still-running hook), no `--no-hooks`/config opt-out (a cloned repo's hook
  runs on the next fork; an untracked hook file works, `include.py:89`),
  stdout swallowed on success; absent from dry-run plan and doctor.
  Proposed direction: timeout, opt-out, surface in dry-run plan, require
  the hook be tracked. Impact: medium (security-adjacent). Type:
  robustness/hardening.
- **A13 — Small-fault bundle (one entry; verification may split it).**
  (a) fork notices print twice (`output.py:79` + `cli.py:624-625`);
  (b) `-o table` is a documented no-op identical to `text`;
  (c) Codex `thread/read` errors conflated with "no parent", zero notice
  (`codex_app_server.py:137-139` → `session.py:399-410`);
  (d) `worktree list --porcelain` parsed without `-z` in three files —
  newline-in-path desyncs parsers, can roll back a good fork;
  (e) `:(exclude)` pathspecs not literal — `src/[id].tsx` intent-to-add
  paths glob-match (`materialize.py:141-146`);
  (f) remote-less repos mark every commit unpushed with an unexplaining
  message (`cleanup.py:223-228`);
  (g) cleanup's dirty check ignores ignored files, so `--force` silently
  destroys the `.env`/local-DB content `.worktreeinclude` carried in
  (`cleanup.py:194`) — data-safety;
  (h) staged binary patch held ~3× resident (`materialize.py:118-123`) and
  O(n·m) list-membership in the `--with-ignored` loop
  (`materialize.py:175`) — efficiency.
  Impact: low→medium individually. Type: mixed (UX, robustness,
  data-safety, efficiency).

### Tests & Tasks

Order is A1 → A13; each item's TS gate precedes its T fix (TDD bias).
A T task is skipped (flipped `[-]`) if its TS verdict is *refuted*.

**Order exception (owner-directed 2026-08-17):** A4 was pulled ahead of A2
and A3, which remain open with worktrees in flight. Reason: the A4 review
found one sub-item that is testable today and cheap, while the rest of the
item was speculative. A4's remedy touches `agents.py` preflight and
`doctor.py`, and adds no registry surface, so it does not collide with the
A3 (registry scoping) worktree. It is **not** environment-neutral, contrary
to this note's first version: both probe call sites pass the caller
environment to an agent subprocess via `env=dict(env)`, which is the same
unsanitized passthrough A2 exists to harden. A2 has since merged
(`1f8e038`); when its hardening lands over this, the two new `subprocess.run`
call sites in `agents.py` and the one reached from `doctor.py` must be
swept with the rest.

- [x] [P02-TS01] A1 adversarial verification (incl. Codex): reproduce status-preserving content divergence end to end — CONFIRMED-WITH-CORRECTIONS 2026-08-16: empirical repro (apply.whitespace=fix diverged child bytes, identical porcelain, `verification.passed: true`) + Codex pass confirming mechanism, repro fairness, in-scope verdict, and sibling vectors; see [design doc](../docs/superpowers/plans/2026-08-16-p02-a1-content-verification.md)
- [x] [P02-T01] A1 fix per process: plan + adversarial plan review (APPROVE-WITH-CHANGES), TDD implementation, adversarial post-review (REJECT → findings absorbed or routed to issues #28–#31 per the owner's gate-6 routing) — whitespace pinned at the transport site, carried-state inventory drives both transport and verification, `content-match`/`parent-content` rungs with structured `failed_checks`, escaped repository-controlled text; 22 A1 rows green, 405 passed; see the [design doc](../docs/superpowers/plans/2026-08-16-p02-a1-content-verification.md)
- [ ] [P02-TS02] A2 validation-first probe matrix (incl. Codex): every `GIT_*` variable and correctness-relevant config key × every operation (worktree create, branch create, materialize, verify, cleanup); record actual behavior per cell with captured output; rewrite the register entry to match; decide whether a fix is still warranted. Partial evidence already recorded in the A2 entry — `GIT_DIR`+`GIT_WORK_TREE` refuses, `GIT_INDEX_FILE` is self-consistent
- [ ] [P02-T02] A2 fix per process, scoped to whatever the matrix confirms — sequencing per the entry: test tier, then sanitization, then pinning policy
- [ ] [P02-TS03] A3 adversarial verification (incl. Codex): two-repo registry clobber and cross-repo cleanup resolution repro
- [ ] [P02-T03] A3 fix per process (registry schema migration)
- [x] [P02-TS04] A4 adversarial verification: **inline adversarial review 2026-08-17 — PARTIALLY REFUTED.** Findings: (a) impact inflated relative to A1/A3, downgraded high → medium (loud, non-destructive, recoverable failure); (b) the headline drift scenario is unreproducible by construction — it requires a CLI release that does not exist, so any repro fabricates a stub, making A4 the item's strongest partial-refutation candidate; (c) `--help` grepping is itself a drift surface (detects removal, not semantic change), which forces the remedy to warn rather than refuse; (d) only `parse_version` is a today-testable defect. Remedy re-scoped from three mechanisms to two. **Codex second lens RUN 2026-08-17** against the implemented diff (`aefcda0..HEAD`) — verdicts: claim 1 (semver) PARTIALLY REFUTED, claim 2 (warn-vs-refuse) PARTIALLY REFUTED, claim 3 (implementation) REFUTED, claim 4 (tests) REFUTED, claim 5 (misses) CONFIRMED. Two defects reproduced independently before acting: `UnicodeDecodeError` escaping `read_help` (breaking the never-refuse guarantee) and notices rendering after mutation. Full report: [TS04 Codex review](../docs/reviews/2026-08-17-p02-a4-codex-review.md). Reviewing the diff rather than the design proved the better target — every finding cited a line. **Process deviation recorded:** A4 predates the validation-first gate that landed with A2 (`1f8e038`); it ran review → rewrite → implement → Codex-on-diff rather than probe-matrix-first, and built no exhaustive input matrix. See the [A4 design doc](../docs/superpowers/plans/2026-08-17-p02-a4-recipe-flag-probe.md)
- [x] [P02-T04] A4 fix per process (revised scope) — TDD, RED first: the ambiguity row demonstrated the real defect (`parse_version` returned the banner's `(10, 2, 3)` instead of the CLI's `2.1.233`). Shipped: `version_tokens` + ambiguity notice, `recipe_flags`/`missing_recipe_flags`/`read_help` with a warn-level probe in `preflight_agent` (detection pre-mutation; notice rendered with the fork result), `.`-guard on `_VERSION`, and T-PRE-21..26. Test-stub fidelity fix in `tests/cli/test_out.py` — the fake CLI answered `--help` with its version string, so the probe correctly reported the *stub's* missing flags; the stub now serves real help (the TS04 review independently confirmed this as fidelity repair, not evidence suppression). Post-review fixes: `UnicodeDecodeError` caught in `read_help`; option-declaration parsing so deprecation prose cannot prove a flag survives; three-state unverified notice; ambiguity counted across stdout and stderr; `doctor` drift scoped to the selected agent so an unused CLI cannot change the exit contract; T-PRE-26 tightened to equality; T-PRE-27/28 and T-CLI-26 added. `just all` green: 419 passed, 1 skipped; `just check-matrix` clean
- [ ] [P02-TS05] A5 adversarial verification (incl. Codex): socket/fifo, unreadable-file, and parent-race rollback repros
- [ ] [P02-T05] A5 fix per process
- [ ] [P02-TS06] A6 adversarial verification (incl. Codex): dirty-submodule fork repro (currently reasoned, not reproduced)
- [ ] [P02-T06] A6 fix per process
- [ ] [P02-TS07] A7 adversarial verification (incl. Codex): stale-entry dead-end repro (already reproduced once; re-verify + bound the fix)
- [ ] [P02-T07] A7 fix per process
- [ ] [P02-TS08] A8 adversarial verification (incl. Codex): full TOCTOU-family inventory against the plan-token remedy; reconcile with P01-T51
- [ ] [P02-T08] A8 fix per process (supersedes/absorbs P01-T51 if confirmed)
- [ ] [P02-TS09] A9 adversarial verification (incl. Codex): inherited-env misfire and partial-signal repros
- [ ] [P02-T09] A9 fix per process
- [ ] [P02-TS10] A10 adversarial verification (incl. Codex): staleness-treadmill and store-growth repros; corpus-limit hard failure
- [ ] [P02-T10] A10 fix per process
- [ ] [P02-TS11] A11 adversarial verification (incl. Codex): re-verify both repros; sweep for further validate/exit-contract gaps
- [ ] [P02-T11] A11 fix per process
- [ ] [P02-TS12] A12 adversarial verification (incl. Codex): hang/interrupt and untracked-hook execution repros
- [ ] [P02-T12] A12 fix per process
- [ ] [P02-TS13] A13 adversarial verification (incl. Codex): verify all eight sub-items; split into follow-up tasks if warranted
- [ ] [P02-T13] A13 fixes per process (per surviving sub-item; batched confirmation acceptable per owner)
- [ ] Regression Test Status

### Deliverable

All thirteen register entries closed — fixed (with tests) or recorded as
refuted — with `just all` green and no v1 behavioral contract broken except
where a fix's approved plan says otherwise.

### Automated Verification
- `make check` passes; `just all` (format, lint, typecheck, test) green after every merged fix
- Each fix lands with its failing-test-first evidence in the PR

### Manual Verification
- Each adversarial verification verdict recorded in the task line (confirmed / refuted / paused-scope)
- Codex participation noted per adversarial review
