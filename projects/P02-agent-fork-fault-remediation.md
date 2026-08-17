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
1. **Adversarial verification gate** — validate the hypothesis against the
   real code before any fix. Includes a Codex pass as the independent
   second-model lens. Outcomes: *confirmed in-scope* → proceed;
   *scope creep / divergence from core functionality* → pause and raise to
   the owner with clear context; *refuted* → record and move on.
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
- **A2 — Raw environment and gitconfig passthrough.**
  `cli.py:667` forwards `os.environ` verbatim to every git call; no `git -c`
  hardening, no unsetting of `GIT_DIR`/`GIT_WORK_TREE`/`GIT_INDEX_FILE`/
  `GIT_CONFIG_*` anywhere in `src/`. Invoked from a git hook or a shell
  exporting these, probes and mutations target the wrong repository. The
  sealed test harness (`tests/conftest.py:809-863`) makes this class
  untestable today. Root cause under A1. Impact: high. Type: robustness.
  Sequenced immediately after A1; A1's review marks any overlap explicitly
  rather than treating it as scope creep.
- **A3 — Global flat fork registry clobbers across repositories.**
  One machine-wide `forks.json`; `RegistryEntry` (`models.py:53-75`) has no
  repo field. `add_entry` (`registry.py:111`) silently deletes a same-named
  entry from another repo; `find_owned` (`registry.py:127-136`) matches a
  bare name/branch across all repos, so cleanup can resolve to another
  repo's worktree. Auto-name collision check (`collision_state()` at
  `cli.py:477-488`, selection through `cli.py:490-516`) never consults the
  registry. Proposed direction: add repo/common-dir field, scope uniqueness
  and cleanup resolution per-repo (registry has a version field for
  migration). Impact: high. Type: data-safety fix. Spot-checked 2026-08-16.
  **Amended 2026-08-17 (TS03 verification):** severity is higher than
  recorded — the collision fires on the *default* auto-named path (two repos
  on `main` forked the same day derive the same name and branch), and the
  consequence is destructive rather than lost bookkeeping: cleanup issued
  from the clobbered repo resolves and deletes another repo's worktree and
  branch, with no repository-containment check anywhere in `cleanup.py`. The
  original `cli.py:487-514` citation was stale and is corrected above.
  **Owner decision 2026-08-17:** the auto-name bullet is recorded as
  over-broad, not unfixed — once uniqueness is `(repo, name)`, equal names in
  different repos are legal, so auto-naming is left untouched.
- **A4 — Agent-CLI recipe drift is undetectable; failure lands post-fork.**
  Emitted recipes live in `agents.py:286-301` guarded only by version
  floors (`agents.py:65-68`) — a future CLI that drops `--fork-session`
  passes every check and fails in the user's fresh terminal after branch,
  worktree, registry, and lineage were created. `parse_version`
  (`agents.py:88-93`) grabs the first `\d+.\d+` anywhere in output. Recipe
  duplicated as prose in four docs with no drift check. Proposed direction:
  doctor recipe-probe against installed `--help`, recorded
  verified-against-version fingerprint, above-ceiling preflight warning.
  Impact: high. Type: robustness.
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

- [x] [P02-TS01] A1 adversarial verification (incl. Codex): reproduce status-preserving content divergence end to end — CONFIRMED-WITH-CORRECTIONS 2026-08-16: empirical repro (apply.whitespace=fix diverged child bytes, identical porcelain, `verification.passed: true`) + Codex pass confirming mechanism, repro fairness, in-scope verdict, and sibling vectors; see [design doc](../docs/superpowers/plans/2026-08-16-p02-a1-content-verification.md)
- [x] [P02-T01] A1 fix per process: plan + adversarial plan review (APPROVE-WITH-CHANGES), TDD implementation, adversarial post-review (REJECT → findings absorbed or routed to issues #28–#31 per the owner's gate-6 routing) — whitespace pinned at the transport site, carried-state inventory drives both transport and verification, `content-match`/`parent-content` rungs with structured `failed_checks`, escaped repository-controlled text; 22 A1 rows green, 405 passed; see the [design doc](../docs/superpowers/plans/2026-08-16-p02-a1-content-verification.md)
- [ ] [P02-TS02] A2 adversarial verification (incl. Codex): demonstrate wrong-repo/config-sensitive behavior with hostile env/gitconfig
- [ ] [P02-T02] A2 fix per process
- [x] [P02-TS03] A3 adversarial verification (incl. Codex): two-repo registry clobber and cross-repo cleanup resolution repro — CONFIRMED-WITH-CORRECTIONS 2026-08-17: four live-git probes reproduced the clobber, the cross-repo cleanup resolution, the same-name auto-derivation on the default path, and the destructive consequence (cleanup from repoE plans to delete repoF's worktree and branch); Codex confirmed the mechanism by source trace plus non-writing execution probes, corrected the root-cause framing and the stale `cli.py` citation, and found the missing repository-containment defense in `cleanup.py:331-356` — its sandbox blocked live-git repros, so that evidence is single-source; see [design doc](../docs/superpowers/plans/2026-08-17-p02-a3-registry-repo-scope.md)
- [ ] [P02-T03] A3 fix per process (registry schema migration)
- [ ] [P02-TS04] A4 adversarial verification (incl. Codex): recipe-drift blindness and post-fork failure demonstration
- [ ] [P02-T04] A4 fix per process
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
