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
- **A2 — [x] RESOLVED: environment claim refuted on the fork and cleanup
  paths; four configuration defects found and fixed. Unprobed configuration
  sources are recorded as coverage gaps in issue #38.** *(Second rewrite 2026-08-17, after probing all 13 canonical
  inputs. Evidence: `docs/superpowers/plans/2026-08-17-p02-a2-environment-hardening.md`.)*

  **Original claim, refuted.** The entry asserted that forwarding `os.environ`
  to all 50 `run_git` call sites meant "probes and mutations target the wrong
  repository", rated high. Twelve environment inputs were probed against full forks
  **and against cleanup** with controls (one, `GIT_ATTR_NOSYSTEM`, is untestable
  on this machine for lack of a system attributes file): **zero wrong-repository
  mutations, zero wrong-target deletions, zero silent divergences attributable
  to agent-fork.** Every refusal left both the intended
  and the unintended repository untouched — checked for branches, worktrees,
  status, and content. Where a variable did change behavior
  (`GIT_CONFIG_SYSTEM` flattening a committed symlink), plain
  `git worktree add` behaves identically, so agent-fork matches the command it
  wraps rather than misbehaving.

  **What was actually wrong: configuration reaching Git.** Three defects found,
  all fixed:
  1. *Transport used porcelain `git diff`*, whose display drivers produce
     patches Git documents as unappliable. A repository shipping a textconv
     driver in committed `.gitattributes` was **unforkable**; a lossy driver
     emptied the patch instead. Fixed by moving transport to `diff-index` and
     `diff-files` (T-MAT-21..24).
  2. *`diff.external`* replaced the diff engine repository-wide. Same fix.
  3. *Inline configuration injection* (`GIT_CONFIG_COUNT`/`KEY`/`VALUE`) flattened
     a **committed** symlink in the child while the fork reported success —
     verification is scoped to carried paths, and committed content arrives via
     the checkout. Fixed by sanitizing the injection triple at the `run_git`
     chokepoint (issue #35, T-GRD-17..20).

  **The "untestable under the sealed harness" claim is narrowed, not refuted.**
  T-GRD-17, T-GRD-18, and T-GRD-21 show targeted rows can opt into hostile
  configuration without a new framework, so no test tier was needed. They do not
  refute the narrower point that the *baseline* sealed environment masks ambient
  passthrough, because they call the pipeline directly rather than through the
  CLI boundary that copies `os.environ`.

  **The pinning policy is not required by any observed defect**, though not
  fully disproven: clean/smudge filters, `extensions.worktreeConfig`, and
  conditional `includeIf` sources remain unprobed, and the setup hook runs after
  verification with an inherited environment and can write shared repository
  configuration — so "file-based configuration is user intent" is not a safe
  categorical rule for a cloned repository.

  Impact: was high → medium → **resolved**. Type: correctness fixes, not the
  robustness/hardening the entry predicted.

  **Closed with named coverage gaps (issue #38), not with a claim of
  completeness.** Unprobed: clean/smudge filters under the new plumbing
  transport (the most plausible of the group, since filters caused real
  divergence in A1 and the transport layer changed beneath them),
  `extensions.worktreeConfig`, conditional `includeIf`, and `GIT_ATTR_NOSYSTEM`
  — the last untestable on this machine for lack of a system attributes file.
  Observed but not demonstrated: the setup hook runs after verification with an
  inherited environment and can write shared repository configuration, and the
  Codex app-server and agent version probes inherit unfiltered environments.
  None is a suspected defect; each is listed so the gap is visible rather than
  implied.

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
- [x] [P02-TS02] A2 validation-first probe matrix (incl. Codex) — all 13 canonical inputs probed against full forks with controls; environment claim refuted (zero wrong-repository mutations); register entry rewritten to match
- [x] [P02-T02] A2 fix — three configuration defects found and fixed: porcelain transport replaced with plumbing (T-MAT-21..24), and inline configuration injection sanitized at the `run_git` chokepoint (issue #35, T-GRD-17..20). The pinning policy was retired as unnecessary on the evidence.
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
