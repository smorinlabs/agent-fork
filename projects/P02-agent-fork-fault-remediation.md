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

- **A3 — [x] RESOLVED: confirmed as registered and worse — the collision
  fires on the default auto-named path and the consequence is destructive,
  not lost bookkeeping. Fixed by making a registry record authorize nothing
  until confirmed against live state.** *(Evidence:
  `docs/superpowers/plans/2026-08-17-p02-a3-registry-repo-scope.md`.)*

  Original claim as registered:
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
- **A4 — [x] RESOLVED: Agent-CLI recipe drift is undetectable; failure lands
  post-fork. Headline drift scenario partially refuted — unreproducible by
  construction, impact downgraded high → medium; the one today-testable
  defect fixed (`parse_version` read a banner's version, not the CLI's), plus
  two warn-level detectors: version ambiguity and a three-state `--help`
  recipe-flag probe. Merged in PR #37.**
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
  *(Rewritten 2026-08-17 after probing; see "Corrected claim" below.)*
  Socket/fifo raises at `materialize.py:58-59`; unreadable or mid-copy
  deleted file raises at `materialize.py:156-157`; both roll back the whole
  worktree. The include path already has the right policy — notice and skip
  (`include.py:77`). Also: concurrent parent edits between snapshot and
  post-materialize check trip `parent-untouched` (`verify.py:64-68`) and
  roll back a correct fork. Proposed direction: skip-with-notice for
  non-regular/unreadable entries; retry-once or warn for the parent-status
  race. Impact: medium-high. Type: robustness.

  **Corrected claim.** The entry bundles three faults that probing on
  2026-08-17 separates into three different verdicts. Probe environment:
  macOS 25.4 (APFS), this repository's `.venv` build, a scratch parent of 200
  tracked files with one modified and one untracked file, baseline fork
  1.1 s wall clock. Every citation below was re-checked against `origin/main`
  on 2026-08-17: the original entry's line numbers predate the A1 fix and no
  longer resolve.

  - **(a) Socket/fifo — refuted; no work.** Git does not report FIFOs or
    Unix-domain sockets as untracked at all. With both present in the parent,
    `git status --porcelain` and `git ls-files --others --exclude-standard`
    listed neither, and a fork of that parent succeeded normally:

    ```bash
    mkfifo dev.sock
    python3 -c "import socket; socket.socket(socket.AF_UNIX).bind('real.sock')"
    git ls-files --others --exclude-standard   # only new.txt
    git status --porcelain                     # only  M tracked.txt / ?? new.txt
    agent-fork fork sockcase --no-agent        # succeeds
    ```

    `Inventory.untracked` is exactly that listing (`collect_inventory`'s untracked listing), so the
    `unsupported untracked file type` raise (`_copy_entry`'s non-regular branch) is
    unreachable from an entry that existed when the fork started. It is
    reachable only if a listed regular file is *replaced* by a non-regular
    one inside the fork window — which is case (c), not a file-type fault.
    Keep the raise as a cheap guard.

  - **(b) Unreadable file — confirmed, but it fails earlier than recorded and
    outside `materialize.py`.** With verification on (the default) the fork
    dies *before any worktree exists*: `capture_state` (`fork`'s `capture_state` call)
    runs ahead of `create_worktree_at_anchor` (`create_worktree_at_anchor`), and
    `_digest` (`content.py:_digest`) opens every carried path with no guard.
    There is therefore nothing to roll back on the default path; the original
    "rolls back the whole worktree" holds only under `--no-verify`, which
    skips the snapshot and reaches `_copy_entry` (`_copy_entry`).

    ```bash
    echo secret > locked.txt && chmod 000 locked.txt
    agent-fork fork lk1 --no-agent              # exit 1, no worktree created
    # runtime_error: [Errno 13] Permission denied: .../locked.txt
    agent-fork fork lk2 --no-agent --no-verify  # exit 1, worktree rolled back
    ```

    Both surface as an untyped `runtime_error` carrying a raw errno string:
    no step attribution, no statement that skipping the entry was possible.
    "Mid-copy deleted file" is **not** part of this case: it is case (c)
    reaching a different tripwire (`_copy_entry`'s `lstat`,
    `_copy_entry`'s `lstat`).

    **Corrected 2026-08-20 by the gate 1 matrix, on two points.** First, the
    earlier claim that `copy_worktree_includes`'s unsupported-type branch "already implements the intended
    policy" is only half true: it skips an unsupported file *type* but has no
    guard for *readability*, so an unreadable file matched by
    `.worktreeinclude` still kills the fork, after verification has already
    passed. Second, the fault is not confined to untracked entries — an
    unreadable **tracked, modified** file fails identically, because
    `capture_state` digests every carried path regardless of tracking state.
    The entry's title, "One bad **untracked** filesystem entry", is therefore
    too narrow; read it as "one bad carried entry".

  - **(c) Parent edited mid-fork — confirmed, deterministically reproduced;
    the rollback is correct and must stay.** The window runs from the status
    snapshot (`fork`'s parent status snapshot) through the content snapshot
    (`fork`'s `capture_state` call), worktree creation, and materialization
    (`fork`'s `materialize` call) to the final parent re-read (the `parent-untouched` bracket)
    — measured at roughly 0.5 s to 0.7 s of a 1.1 s command, and it widens
    with repository size because untracked entries are copied one at a time
    (`materialize`'s untracked copy loop). Sweeping the delay of a single background
    write pins the edges:

    ```bash
    # each line races one fork; run from the parent
    ( sleep 0.55; echo autosave >> f1.txt ) & agent-fork fork c055 --no-agent
    # -> verify_failed: verification failed: parent-content (f1.txt: content differs)
    ( sleep 0.65; echo autosave >> f1.txt ) & agent-fork fork c065 --no-agent
    # -> same failure
    ( sleep 0.75; echo autosave >> f1.txt ) & agent-fork fork c075 --no-agent
    # -> succeeds; the write landed after the window closed
    ```

    A write that changes a path's *status class* trips `parent-untouched`
    (the `parent-untouched` bracket); a write that only changes bytes in an
    already-modified path trips `parent-content` (the `parent-content` rung), the
    rung A1 added. When the write lands *before* transport reads the path,
    `content-match` (the `content-match` rung) fires alongside it — re-validated
    2026-08-17 against `722e1fd`:
    `parent-content (f1.txt: content differs), content-match (f1.txt: content
    differs)`. That second rung is the torn copy made visible: the child holds
    post-write bytes the snapshot never saw. That is not a regression from A1: before A1 this exact
    race passed silently and produced a child whose relationship to the
    snapshot was never checked. Failing is right — a write inside the window
    can tear the copy, leaving the child matching no single moment of the
    parent. The defects are the *reporting* and the *absence of recovery*:
    the message names a check, not a cause, and never says that nothing was
    lost and that a rerun will likely succeed.

    Retry-once cures a one-shot autosave and does nothing for a continuous
    writer — a dev-server log, a watch build, or another agent session working
    in the parent — which fails every attempt until the writer stops. That is
    what the original "or warn" half must cover.

  **Re-validated 2026-08-20 against `46201c1`**, 51 commits later — A9, A13's
  remediations, the P04/P05 session work, release plumbing, and PR #53's
  consolidation of duplicated primitives. All three cases reproduce unchanged:
  `_copy_entry` and every verification rung are behaviourally identical, so
  only the line numbers cited above moved (`materialize.py` by 4 and 10 lines,
  `verify.py` by 3; `content.py`, `pipeline.py`, and `include.py` unmoved).
  The window re-measured on *fresh* repositories at roughly 0.45–0.8 s of a
  ~1.0 s command, with run-to-run jitter large enough that a single trial
  proves little. Direct evidence for the size-dependence claim: a parent
  already carrying several fork worktrees stayed vulnerable past a 1.15 s
  delay, where a fresh parent had closed the window before 0.8 s.

  One re-evaluation finding for the fix design: PR #53 consolidated three
  duplicated primitive families but left `_copy_entry` and the
  `.worktreeinclude` copy loop (`copy_worktree_includes`'s copy loop) unmerged — a near-duplicate
  pair whose *only* substantive divergence is the policy A5(b) is about, raise
  versus notice-and-skip. The (b) remedy should therefore land as one shared
  copy primitive taking the policy as a parameter, matching #53's pattern,
  rather than as a second independent edit.

  Revised impact: **(a) none** (refuted); **(b) medium** — one unreadable
  carried path makes the repository unforkable, with an unattributable error;
  **(c) medium** — no data is ever at risk, the cost is an undiagnosable
  failure and, for continuous writers, a repository that cannot be forked at
  all. Type: robustness + error reporting. Not data loss on current evidence.

  **Gate 1 probe matrix executed 2026-08-20.** Eleven static entry shapes,
  five mid-window mutations, and three cleanup shapes were run with captured
  output; the full matrix lives in the
  [A5 design doc](../docs/superpowers/plans/2026-08-20-p02-a5-skip-and-race-policy.md).
  It confirmed the three verdicts above, and produced four findings beyond
  them: N1 unreadable tracked files fail identically (absorbed here, as a
  typed error rather than a skip), N2 a mode-000 directory makes the fork
  *silently* omit data while reporting success (filed as
  [#59](https://github.com/smorinlabs/agent-fork/issues/59)), N3
  `.worktreeinclude` has no readability guard (absorbed here), N4 an
  unreadable directory makes `cleanup` fail and leaves the worktree behind
  (filed as [#60](https://github.com/smorinlabs/agent-fork/issues/60),
  cross-referenced to A7). A5 also absorbs one narrow slice of
  [#28](https://github.com/smorinlabs/agent-fork/issues/28): `lstat` must
  classify only `ENOENT` and `ENOTDIR` as absent, because a `PermissionError`
  currently masquerades as a deletion and would be silently swallowed by this
  item's rule that absence is always legitimate.

  **Unverified surface — the gate must probe before any fix.** macOS/APFS
  only, one Git version, `--no-agent` only. Untested: Linux and
  case-sensitive filesystems; whether any Git version lists non-regular
  entries; the `--with-ignored` listing (`collect_inventory`'s ignored listing), which shares the
  same `ls-files` mechanism but was not probed; unreadable *directories* as
  opposed to files; a regular file swapped for a FIFO inside the window; and
  the interaction with A6's dirty-submodule case. The window figures come
  from one machine at one repository size — indicative, not a bound.

  **Decided direction (owner, 2026-08-20, narrowed to Option A).** This
  supersedes every earlier direction recorded for A5, including the
  snapshot-versus-copy timing rule, the fail-on-swap resolution, and the
  retry. A5 now fixes exactly one defect: *agent-fork must not refuse to work
  because of a single entry it cannot copy.*

  **The copy loop never fails the fork on a *qualifying* entry.** It skips
  what it may skip and names it; verification remains the sole arbiter of
  whether the result is acceptable. A skip requires all three preconditions —
  untracked or ignored, successful `lstat`, and no carried deletion — and
  anything else raises `entry_unreadable`. The design doc's "Skip
  preconditions" section governs; the table below summarises it. Verified by the third gate 1 review: a regular file swapped for
  a FIFO mid-fork is still caught, because `compare_states` reports the type
  loss, both content rungs fail, and rollback runs.

  | Condition while copying | Default | `--strict` |
  |---|---|---|
  | Untracked or ignored file cannot be read | skip, warn, name every skipped path | fail, same warning |
  | Untracked or ignored non-regular entry (socket, FIFO) | skip, warn, name every skipped path | fail, same warning |
  | **Tracked** file cannot be read | fail, with a typed error naming the path | same |
  | Parent changed during the fork | fail and revert, unchanged from today | same |

  Skipping is restricted to untracked and ignored entries (owner, 2026-08-20).
  A tracked path cannot be skipped safely without rename handling, because
  `--no-renames` decomposes `old -> new` into unassociated endpoints and
  excluding only an unreadable `new` would silently drop `old` from the child.

  **A skip requires all three preconditions**, or the entry is the typed
  failure `entry_unreadable` (exit 1): the entry is untracked or ignored;
  `lstat` succeeded so a stability sentinel exists; and the fork carries no
  deletion that could pair with it, determined from an explicit
  `--diff-filter=D` facet rather than inferred from absence. The sentinel is
  `(st_dev, st_ino, st_mode, st_size, st_mtime_ns, st_ctime_ns)`, recorded at
  observation and rechecked before success. Strict refusal is
  `strict_skip_refused` (exit 1). Both codes now exist in `errors.py`, are
  published in `README.md`, and have stable `details` schemas. The design doc
  is the normative contract, and its
  "Skip preconditions" section governs: a skip requires an untracked or
  ignored entry, a successful `lstat`, and no carried deletion. Anything else
  raises `entry_unreadable`.

  Exit status is 0 when only skips occurred, non-zero under `--strict`. No
  skip is ever triggered by *absence*: `collect_inventory` keeps deletion and
  rename endpoints deliberately, so treating absence as a skip or a failure
  would break ordinary deletions, which `T-VER-26` guards. The retry is
  dropped. `.worktreeinclude` gains the same readability guard, with its
  residual post-verification race accepted as a known limit. Flag name and
  strict exit code are subject to the CLI Design Standard check. Full record,
  including the probe matrix and three review rounds: the
  [A5 design doc](../docs/superpowers/plans/2026-08-20-p02-a5-skip-and-race-policy.md).
- **A6 — Submodule working-tree state makes the repo unforkable, and is
  silently dropped when verification is off.** Rewritten 2026-08-17 to match
  the probe matrices; see the [design doc](../docs/superpowers/plans/2026-08-17-p02-a6-dirty-submodules.md).
  Reproduced end to end: an edited file, an untracked file, or an unstaged
  submodule advance all yield parent ` M vendor/module` with no child
  counterpart, and the fork fails and rolls back. **Two rungs fail, not one** —
  `exact-copy-status` and also `content-match`, because
  `collect_inventory` (`content.py:158`) lists `vendor/module` as unstaged, so
  a status-only exemption would not have sufficed; the original entry predates
  that rung. **Narrower than first written**: a submodule advance *staged* in
  the parent already forks correctly (the gitlink travels in the
  `diff-index --cached` patch), so the fault is confined to working-tree state.
  Rollback is clean. Under `--no-verify` the fork succeeds and drops the state
  silently, while `materialize.py:109` claims "submodules copied opaquely" over
  an empty directory. Direction (owner decision 2026-08-17, superseding
  "verification exemption at minimum"): **carry submodules identically by
  default**, opt out with `--no-with-submodules`. Feasibility shown across eight
  local, depth-1, status-comparison cells under a manual prototype — not yet
  proven in production shape (gate 4 finding 5). Impact: medium-high for
  submodule users. Type: correctness fix, feature-shaped by owner decision.

  **Split into two remediations (owner decision 2026-08-20)**, after two gate-4
  passes returned NOT-READY on integration complexity rather than on the carry
  mechanism, which matched on 8 of 8 cells at first attempt:
  - **A6a — unblock forking.** `--ignore-submodules` filtering at
    `verify.py:103`, `verify.py:146`/`pipeline.py:114` (matched pair), and the
    unstaged inventory listing at `content.py:158`, plus a notice that names
    what was not carried instead of claiming submodules were "copied opaquely"
    over an empty directory. Already validated against real child worktrees:
    the edited-file, untracked-file, and mixed-dirt cells go from rollback to
    success, and the staged-gitlink case keeps the check it passes today.
    The unstaged-gitlink-advance case gets a typed `PreconditionError` refusal
    before any mutation (exit 5, owner decision 2026-08-20). That guard is
    **conditional, not permanent**: matrix 2 shows the case forks correctly once
    submodules are carried, so it is written against a "submodules not carried"
    condition and survives A6b only on the `--no-with-submodules` path.
    A6a's own gate-4 pass is waived (owner decision 2026-08-20); gate 6 is
    unchanged.
  - **A6b — carry submodules identically.** The full recipe, recursive
    snapshot, `config_pins` at the `run_git` chokepoint, and recursive
    verification, per the design doc. Requires a further gate-4 pass.
  Rationale: A6a ends the unforkable-repository fault on validated evidence in
  days; A6b keeps the owner's carry-by-default decision intact and gets the
  review depth two passes say it needs.
- **A7 — Stale registry entries are uncleanable; no prune/repair verb.**
  Reproduced: hand-delete a fork worktree, then `cleanup <name> --yes` dies
  with raw git `runtime_error` (`cleanup.py:126-166` runs `git -C
  <missing-dir>`); `list` reports `worktree_exists: false` forever;
  `git worktree move` orphans the stored path. Only remedy is hand-editing
  `forks.json`. Proposed direction: typed error for the missing-worktree
  case + `prune`/`cleanup --missing`. Impact: medium-high. Type:
  robustness. (The remedial verb is minimal-remediation here, not a P03
  feature.)
  **Amended 2026-08-17 (A3 overlap, owner decision).** A3 ships **`prune`**
  and the typed missing-worktree refusal, because A3's actionability
  predicate makes a row that no longer matches disk permanently unusable and
  therefore creates the need for the exit. A7 retains: `cleanup --missing`,
  moved-worktree repair (`git worktree move` orphaning the stored path), and
  the case A3's `prune` deliberately declines — a row whose recorded path
  exists but hosts something other than the recorded fork, which `prune`
  reports and leaves alone because it may be another repository's live
  worktree. Re-scope A7 against A3's shipped surface before starting it.
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
- **A11 — `config validate` passes configs that crash `fork`.** Reproduced
  2026-08-20 against `46201c1`: `worktree_location = "{bogus}/x"` validates
  clean and `doctor` reports it valid, then `fork --dry-run` fails as bare
  `runtime_error`/exit 1 instead of `config_error`/exit 2 (`location.py:115`
  wraps but does not retype the `ValueError`), violating the exit-code
  contract; an invalid `branch_prefix` (e.g. `"bad prefix/"`) passes
  `validate`/`doctor`/`fork --dry-run` and only fails inside real
  `git worktree add` (confirmed via `git check-ref-format`, rc=128); an
  unsupported `{session-id}` placeholder renders as an empty or even
  *absolute-parent-directory* path with no refusal; `config get
  agents.claude.extra_args` returns `unknown config key` while an
  undocumented `hasattr` fallback leaks internal attribute names instead;
  `config set` writes malformed **supported scalar** values (`worktree_location`,
  `branch_prefix`) unchecked, while array/feature keys (`extra_args`, `output`)
  are rejected outright as unknown rather than written. One originally-claimed
  cell is now fixed on its four tested surfaces: invalid `AGENT_FORK_OUTPUT`
  used to select human output silently, closed by A13-B (`f27a2d2`) — though
  `list`/`session` still ignore it entirely and `config view` doesn't honor a
  *valid* `AGENT_FORK_OUTPUT=json`. One is changed in nature: `README.md` no
  longer documents `[fork].output` as accepted — A13-B deleted that row and
  wrote an explicit denial, and the owner has now ratified accepting it.
  Impact: medium. Type: correctness fix; `[fork].output` is a ratified
  feature addition, not docs-code drift.
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
A T task is skipped (flipped `[-]`) if its TS verdict is *refuted* or the
owner decides will-not-fix (per `PROJECTS.md` status legend).

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
- [x] [P02-TS02] A2 validation-first probe matrix (incl. Codex) — 12 canonical inputs probed against the fork path and the cleanup path with controls and bystander comparison (1, `GIT_ATTR_NOSYSTEM`, untestable here); environment claim refuted: no wrong-repository mutation, no wrong-target deletion, no silent divergence attributable to agent-fork. Register entry rewritten twice to match the evidence; remaining gaps recorded in issue #38
- [x] [P02-T02] A2 fix — four configuration defects found and fixed: porcelain transport replaced with plumbing, closing both the unappliable-patch and empty-patch modes (T-MAT-21..24), and both inline injection channels sanitized — the `GIT_CONFIG_COUNT` triple and `GIT_CONFIG_PARAMETERS`, the latter missed by the first fix and caught in review (issue #35, T-GRD-17..21). `config.py`'s direct Git launch now uses the same filter. The pinning policy is **not required by any observed defect**, but is not disproven for the sources in issue #38.
- [x] [P02-TS03] A3 validation-first probe matrix (incl. Codex): two-repo registry clobber and cross-repo cleanup resolution repro — CONFIRMED-WITH-CORRECTIONS 2026-08-17: four live-git probes reproduced the clobber, the cross-repo cleanup resolution, the same-name auto-derivation on the default path, and the destructive consequence (cleanup from repoE plans to delete repoF's worktree and branch); Codex confirmed the mechanism by source trace plus non-writing execution probes, corrected the root-cause framing and the stale `cli.py` citation, and found the missing repository-containment defense in `cleanup.py:331-356` — its sandbox blocked live-git repros, so that evidence is single-source; see [design doc](../docs/superpowers/plans/2026-08-17-p02-a3-registry-repo-scope.md). **Gate-1 rule change 2026-08-17:** this gate predates the validation-first probe-matrix rule A2 introduced; see the coverage note in the design doc
- [x] [P02-T03] A3 fix per process — plan + adversarial plan review (four rounds, all REJECT; loop stopped by owner and the design reshaped around one resolution rule rather than more site-specific guards), TDD implementation, adversarial post-review (six rounds, all REJECT; every finding absorbed, none declined). Shipped: a `repository` field and v2 registry with conservative migration; the **actionability predicate** — a record authorizes nothing unless its `(worktree, branch)` pair is live in the repository freshly identified from the invoking directory; a stored repository that **vetoes but never authorizes**; `ConfirmedFork`, which makes an unconfirmed target unrepresentable so the values Git receives can only come from an observation; a lock-held cleanup transaction closing the post-consent window; `prune`, absorbing that half of A7; and `conflict_fork_registered`, which stops a fork silently clobbering a live same-named record *within* one repository — A3's own fault one level in. T-REG-14..36; 636 passed. Known limitation recorded: pre-v2 recovery goes through `--force`, which waives the dirty and unpushed guards (owner decision 2026-08-20). See the [design doc](../docs/superpowers/plans/2026-08-17-p02-a3-registry-repo-scope.md)
- [x] [P02-TS04] A4 adversarial verification: **inline adversarial review 2026-08-17 — PARTIALLY REFUTED.** Findings: (a) impact inflated relative to A1/A3, downgraded high → medium (loud, non-destructive, recoverable failure); (b) the headline drift scenario is unreproducible by construction — it requires a CLI release that does not exist, so any repro fabricates a stub, making A4 the item's strongest partial-refutation candidate; (c) `--help` grepping is itself a drift surface (detects removal, not semantic change), which forces the remedy to warn rather than refuse; (d) only `parse_version` is a today-testable defect. Remedy re-scoped from three mechanisms to two. **Codex second lens RUN 2026-08-17** against the implemented diff (`aefcda0..HEAD`) — verdicts: claim 1 (semver) PARTIALLY REFUTED, claim 2 (warn-vs-refuse) PARTIALLY REFUTED, claim 3 (implementation) REFUTED, claim 4 (tests) REFUTED, claim 5 (misses) CONFIRMED. Two defects reproduced independently before acting: `UnicodeDecodeError` escaping `read_help` (breaking the never-refuse guarantee) and notices rendering after mutation. Full report: [TS04 Codex review](../docs/reviews/2026-08-17-p02-a4-codex-review.md). Reviewing the diff rather than the design proved the better target — every finding cited a line. **Process deviation recorded:** A4 predates the validation-first gate that landed with A2 (`1f8e038`); it ran review → rewrite → implement → Codex-on-diff rather than probe-matrix-first, and built no exhaustive input matrix. See the [A4 design doc](../docs/superpowers/plans/2026-08-17-p02-a4-recipe-flag-probe.md)
- [x] [P02-T04] A4 fix per process (revised scope) — TDD, RED first: the ambiguity row demonstrated the real defect (`parse_version` returned the banner's `(10, 2, 3)` instead of the CLI's `2.1.233`). Shipped: `version_tokens` + ambiguity notice, `recipe_flags`/`missing_recipe_flags`/`read_help` with a warn-level probe in `preflight_agent` (detection pre-mutation; notice rendered with the fork result), `.`-guard on `_VERSION`, and T-PRE-21..26. Test-stub fidelity fix in `tests/cli/test_out.py` — the fake CLI answered `--help` with its version string, so the probe correctly reported the *stub's* missing flags; the stub now serves real help (the TS04 review independently confirmed this as fidelity repair, not evidence suppression). Post-review fixes: `UnicodeDecodeError` caught in `read_help`; option-declaration parsing so deprecation prose cannot prove a flag survives; three-state unverified notice; ambiguity counted across stdout and stderr; `doctor` drift scoped to the selected agent so an unused CLI cannot change the exit contract; T-PRE-26 tightened to equality; T-PRE-27/28 and T-CLI-26 added. PR #37 review added T-PRE-29 (the unverified notice named `codex --help` while the probe ran `codex fork --help`). Final state at merge: `just all` green, 430 passed, 1 skipped; `just check-matrix` clean (earlier snapshots in this item's history recorded 415/419/424 as the suite grew — the merge figure is the one to trust)
- [x] [P02-TS05] A5 adversarial verification (incl. Codex) — **CONFIRMED-WITH-CORRECTIONS 2026-08-20.** Eleven static entry shapes, five mid-window mutations, and three cleanup shapes separated the bundled claim: socket/FIFO entries are not enumerated by Git and therefore do not block ordinary forks; unreadable carried files fail as raw errors; and parent-race rollback is correct and remains required. The matrix also found the `.worktreeinclude` readability gap, the tracked-file variant, and the narrow `lstat`/absence dependency on issue #28. Silent enumeration and cleanup defects were routed to #59 and #60. See the [A5 design and evidence record](../docs/superpowers/plans/2026-08-20-p02-a5-skip-and-race-policy.md).
- [x] [P02-T05] A5 fix per process — qualifying unreadable or unsupported untracked/ignored entries now skip with one named notice and a final metadata sentinel; tracked paths, failed `lstat`, and any skip while carrying a deletion fail as typed `entry_unreadable`. `--strict` aggregates capture/materialize/include skips into one byte-wise ordered exit-1 `strict_skip_refused` and rolls back. JSON additively exposes `skipped[]`; `.worktreeinclude` shares the readability policy without reopening known skips. Gate 6 and PR review found and fixed five implementation defects (same-observation sentinel, verify re-open, undocumented reason values, duplicate include reporting, and post-`lstat` symlink following) and filled the missing evidence rows. Final gate: 682 passed, 1 expected skip, 20 deselected; 623-row matrix clean. See the [A5 design and evidence record](../docs/superpowers/plans/2026-08-20-p02-a5-skip-and-race-policy.md).
- [x] [P02-TS06] A6 adversarial verification (incl. Codex): CONFIRMED-WITH-CORRECTIONS 2026-08-17 — matrix 1 reproduced the rollback across four dirty shapes and refuted the "unforkable by default" breadth (staged gitlink advance already forks); matrix 2 showed identical carry is feasible across eight local depth-1 cells. Codex second lens returned CONFIRM-WITH-CORRECTIONS; its findings 5 and 6 narrowed the verdict wording and corrected the cleanup evidence provenance. Register entry rewritten; see the [design doc](../docs/superpowers/plans/2026-08-17-p02-a6-dirty-submodules.md)
- [~] [P02-T06] A6 remediation umbrella — close after **A6a** (unblock: `--ignore-submodules` filtering plus an accurate notice; evidence already validated; merged to `main`) and **A6b** (carry submodules identically by default, `--with-submodules` / `--no-with-submodules`, owner decision 2026-08-17) both merge. Split 2026-08-20 after two gate-4 passes returned NOT-READY on integration complexity, not on the carry mechanism. **A6b status (2026-08-21):** implementation complete on `worktree-p02-a6b-carry-submodules`, merged with `origin/main` (A3/A10/A11/A12), gate 6 (adversarial implementation review) complete after four rounds — round 1: 8 findings absorbed; round 2 (post-merge): 10 findings, 9 absorbed, 1 documented as a pre-existing pattern shared with `main`; round 3: confirmed round 2's absorptions, found round 2's own trap fix itself broken, re-absorbed; round 4: confirmed clean. `just all` 718 passed/1 skipped, `just check-matrix` clean, `just test-git-matrix` green on Git 2.50.1 and 2.54.0. Branch is PR-ready; PR not yet opened. Plan and all gate reports in the [design doc](../docs/superpowers/plans/2026-08-17-p02-a6-dirty-submodules.md)
- [ ] [P02-TS07] A7 adversarial verification (incl. Codex): stale-entry dead-end repro (already reproduced once; re-verify + bound the fix)
- [ ] [P02-T07] A7 fix per process
- [x] [P02-TS08] A8 adversarial verification (incl. Codex) — **CONFIRMED-WITH-CORRECTIONS 2026-08-17.** Executed dry-run/real pairs reproduced collision suffix drift, local-midnight name drift, cross-confirmation anchor drift, same-count carried-file substitution, and distinct dry-run/real Claude child UUIDs; an instrumented real fork also observed three independent `HEAD^{commit}` resolutions and produced a detached-derived name from one commit while materializing another. P01-T51 covers only candidate-name drift and is absorbed here. The proposed `{name, branch, destination, anchor, child_session_id}` tuple is incomplete: the immutable execution plan must also bind carry mode plus the complete approved source-state inventory or a collision-resistant digest and refuse pre-mutation on drift. Owner declined that remedy in T08; confirmation-boundary drift remains a known limitation.
- [-] [P02-T08] A8 fix per process — **WILL NOT FIX (owner decision 2026-08-18).** Plan-token/immutable-plan remedy (opaque plan ID binding name/branch/destination/anchor/carry-mode/source-state digest, `fork --plan <token>` execution, typed `plan_stale` refusal on drift) judged overly complex for this CLI's needs; confirmation-boundary drift accepted as a known limitation. Also declines P01-T51's narrower deferred plan-token fix (absorbed here per TS08).
- [x] [P02-TS09] A9 adversarial verification (incl. Codex) — **CONFIRMED-WITH-CORRECTIONS, MEDIUM IMPACT 2026-08-18.** An executed eight-shape matrix crossed every supported Claude/Codex environment combination with automatic and strict fork resolution, `session`, automatic and strict `doctor`, and current-session Claude inference. Both partial-Claude shapes collapsed to absence: automatic fork silently selected Git-only, strict fork returned `agent_not_detected`, `session` reported `not_detected`, and doctor selected Git-only. Either partial-Claude shape plus Codex collapsed to Codex-only, while complete dual signals were ambiguous except current Claude inference ignored Codex and entered its Claude analysis path. Codex-only fork still reached the existing strict rollout preflight and refused with `session_not_found` before mutation. Explicit Git-only, complete explicit identity, and explicit-agent environment-ID fallback controls passed. Keep T09 at medium robustness priority: centralize one `absent` / `incomplete` / `detected` / `ambiguous` assessment across all five consumers, add a typed pre-mutation incomplete refusal, and preserve the existing strict preflight. Do not add public candidate/validated or liveness states.
- [x] [P02-T09] A9 fix per process — one pure `absent` / `incomplete` / `detected` / `ambiguous` assessment now feeds fork resolution, session inspection, doctor, and current Claude inference; incomplete automatic/strict forks refuse before mutation as typed exit-3 `agent_signal_incomplete`, while explicit identity, Git-only mode, and strict preflight remain intact. The 20-failure RED run became 115 focused GREEN items; source, contract, and independent Codex implementation reviews all returned APPROVE after their findings were absorbed; final gates passed with 454 tests, 1 expected skip, 9 deselections, the 398-row matrix, strict collection, and clean installation. See the [design and evidence record](../docs/superpowers/plans/2026-08-18-p02-a09-shared-agent-signal-assessment.md)
- [x] [P02-TS10] A10 adversarial verification (incl. Codex) — **CONFIRMED-WITH-CORRECTIONS 2026-08-20.** The executed matrix reproduced the freshness treadmill, unbounded cache growth, and corpus-limit hard failures; the reviewed scope and decisions are recorded in the [A10 design and evidence record](../docs/superpowers/plans/2026-08-18-p02-a10-claude-freshness.md).
- [x] [P02-T10] A10 fix per process — inferred-parent freshness now preserves last-known-good evidence without accepting it as strict proof, the freshness index and transcript cache are bounded and safely migrated, corpus limits are typed exit-3 refusals, and cleanup discloses retained metadata. Gate 6 completed after two independent review rounds; merged in [PR #63](https://github.com/smorinlabs/agent-fork/pull/63). Final merged gates: 583 passed, 1 expected skip, 9 deselections; `just check-matrix`, `just strict-collect`, and `just clean-install` green. See the [A10 design and evidence record](../docs/superpowers/plans/2026-08-18-p02-a10-claude-freshness.md).
- [x] [P02-TS11] A11 adversarial verification (incl. Codex) — **CONFIRMED-WITH-CORRECTIONS 2026-08-20.** Executed against `origin/main` @ `46201c1` in an isolated scratch repo (isolated XDG roots, `--config`/`AGENT_FORK_CONFIG` pinned per probe; validate/dry-run surfaces only, no real fork mutation triggered), then independently re-executed by Codex in its own sandbox (per-cell evidence, source-line audit of `config.py:311-339`, and a source-code confirmation that `location.py:115` raises plain `ValueError`, not `ConfigError`). Per-cell verdict: **D1 CONFIRMED** — `worktree_location = "{bogus}/x"` passes `config validate` (rc=0) and `doctor`'s config-validity subcheck, but `fork --dry-run` fails as `runtime_error`/exit 1, not `config_error`/exit 2. **D4 CONFIRMED** — `branch_prefix = "bad prefix/"` passes `config validate`/`doctor`/`fork --dry-run` (rc=0 throughout; dry-run accepts and prints the composed branch), while real `git check-ref-format --branch 'bad prefix/ok'` independently rejects that ref at rc=128 — a real mutating `fork` was not executed, only the ref-format proxy check. **D5 CONFIRMED** — `{session-id}` in `worktree_location` renders as `/w` for `{session-id}/w` and as the **parent directory** `/Users/stevemorin/worktrees` for `~/worktrees/{session-id}`, both passing `fork --dry-run` at rc=0 with no refusal. **D6 CONFIRMED** — `config get agents.claude.extra_args`, `agents.codex.extra_args`, and `fork.branch_prefix` all return `unknown config key` (rc=2) while the internal-attribute `hasattr` fallback leaks `claude_extra_args`, `config_path`, `mode`, and `worktree_location_explicit` at rc=0; `config set` writes malformed **supported scalar** values (`worktree_location`, `branch_prefix`) unchecked (source audit: `config.py:311-339` calls no validator before `path.write_text()`), while `agents.claude.extra_args` and `output` are rejected outright as unknown keys, not written — dotted array/feature keys remain unaddressable rather than unsafely writable. **D3 REFUTED as a live defect, with a narrower residual gap** — `AGENT_FORK_OUTPUT=bogus` is rejected (rc=2 `config_error`) by `config validate`, `config view`, and `fork`, and reported as a failed check (rc=1) by `doctor`; fixed by A13-B (`f27a2d2`), covered by `T-CFG-18`/`T-CLI-32`. Codex's independent sweep found this fix is surface-specific: `list` and `session` never resolve configuration at all and silently ignore an invalid `AGENT_FORK_OUTPUT` (rc=0 either way), and `config view` validates a *valid* `AGENT_FORK_OUTPUT=json` but still prints human text instead of honoring it — both now folded into A11's scope as the "list/view/doctor `AGENT_FORK_OUTPUT` divergence" item. The shipped message also omits key/value/source (owner decision 3 unmet), and the same naming gap exists for `AGENT_FORK_AGENT_MODE=bogus`'s error text. **D2 PARTIALLY REFUTED** — the original "docs-code drift" premise no longer holds: `[fork].output` is still rejected by `load_config()` (`unknown key fork.output`, rc=2), but A13-B deliberately deleted the README row and wrote an explicit denial (`README.md:521-523`), reserving the decision for A11 by name; **owner ratified ACCEPT 2026-08-20**, making this an implementation item, not an open question or drift repair. Corrected pointers: `location.py:104` → `location.py:115` (confirmed exact raise site by Codex); `README.md:458` → deleted, denial now at `README.md:521-523`. **Matrix gaps found by Codex's independent sweep, folded into the design doc:** the `worktree_location` template grammar is wider than originally tested — `{repo-root[0]}w` (a subscript/index expression, not just a conversion or format spec) also renders successfully to `/w`; grammar rejection must therefore also block indexing, not only conversions and non-empty format specs. Keep T11 at medium correctness/docs priority; make validation semantic rather than adding one-off catches. Full matrix, both agents' captured evidence, and this session's probe script are retained at `/private/tmp/claude-501/-Users-stevemorin-c-agent-fork/caa9aff9-b953-4393-8146-31a5e1c7f5ab/scratchpad/a11-probe/` (session-local, not repo-tracked); revalidated design doc: [A11 design doc](../docs/superpowers/plans/2026-08-18-p02-a11-config-validation.md). **Procedural note:** Codex's own sandbox could not create a fresh scratch directory or a persistent empty TOML target, so it substituted a source-line audit (`config.py:311-339`) and an `/dev/null`-target accept test for the byte-level persisted-write check; the actual persisted bytes for the poison-write case were captured directly by the first agent (`cfg-d6b-user.toml` after `config set worktree_location '{bogus}/x'` contains the unchecked value verbatim). Combined, both lenses' evidence is sufficient to confirm D6's poison-write claim; a write-enabled rerun by a third party is not required to unblock gate 4.
- [x] [P02-T11] A11 fix per process — one declarative `KEY_SPECS` registry (`src/agent_fork/config.py`) now drives `config validate`/`get`/`set`, `doctor`, and `fork` (dry-run and real) with per-field provenance (`ConfigFinding`); `worktree_location`/`branch_prefix` are validated against their *composed* render (D1/D4/D5), `[fork].output` is accepted (owner decision 4, ACCEPT), and the `config get`/`set` internal-attribute leak (D6) is closed. Gate 4 (design + implementation-plan review, incl. Codex) returned APPROVE-WITH-CHANGES; Gate 5 (TDD) implemented all required changes; Gate 6 (adversarial implementation review, incl. Codex) ran four rounds — three full passes fixed 14 real defects (severity strictly decreasing each round), and a fourth, narrower pass re-verified the last two fixes clean with both independent reviewers (Opus and Codex), converging independently on one related-but-out-of-scope finding (a pre-existing, non-regression `Path.expanduser()`-with-empty-`HOME` bug class in `cli.py`'s `--worktree-dir` flag, `doctor.py`'s XDG check, and elsewhere) filed as [smorinlabs/agent-fork#61](https://github.com/smorinlabs/agent-fork/issues/61) per owner scope decision rather than folded into this item. 441-row test matrix (28 new/amended rows); full hermetic suite, `ruff format`/`check`, `ty check`, `check_matrix.py`, strict-collect, and clean-install all green. See the [A11 design and evidence record](../docs/superpowers/plans/2026-08-18-p02-a11-config-validation.md).
- [x] [P02-TS12] A12 adversarial verification (incl. Codex) — **CONFIRMED-WITH-CORRECTIONS 2026-08-20.** A real black-box `agent-fork fork` run against sealed scratch repos reproduced every claim: an index-untracked `.agent-fork/worktree-setup.sh` still executed with no notice; a committed hook modified on disk (uncommitted) ran its modified content, not the committed blob; a `sleep 25` hook had no timeout, and `SIGINT` to the CLI exited it in 0.576 s with exit code 1 and an uncaught `OperationInterrupted` traceback rather than 130, while the hook's `sleep` grandchild was orphaned, reparented to PID 1, and kept running 21.7 s past CLI exit (rollback itself correctly removed the worktree/branch); successful hook stdout/stderr never reached the user, human or JSON; and neither `--dry-run` nor `doctor` disclosed the hook in any form, with no opt-out key present. An independent Codex source-trace (read-only; the sandbox permitted no signals/`ps`/scratch writes) confirmed the mechanism behind every claim by file:line — `include.py:97`'s existence-only gate, `include.py:107-109`'s missing `timeout=`/`start_new_session`, `rollback.py:19`'s `OperationInterrupted(BaseException)` bypassing `cli.py:1229`'s `except Exception`, `include.py:112-116`'s success-path output discard, and the absence of any hook field in `output.py`'s `DryRunOutput`, `doctor.py`, or `config.py`'s `_FORK_KEYS` — with one caveat: the orphan/reparent-to-PID-1 *outcome* specifically requires live observation and could not be independently re-derived from source, only the general kill-only-direct-child mechanism could. Two findings sharpen the original 2026-08-17 verdict (lost uncommitted, redone here): the interrupt-exit-code gap is not hook-specific — `OperationInterrupted` escapes uncaught on *every* interrupted fork, not only ones running a hook — and "require the hook be tracked" is an insufficient remedy by itself, since a tracked-but-modified hook still runs its uncommitted content. Keep T12 at medium repository-safety priority: explicit policy, a provenance check against on-disk bytes (not `git status`), bounded process-group execution and reaping, a CLI-level fix for the general interrupt-exit-code gap, and dry-run/doctor/output visibility. See the [A12 design plan](../docs/superpowers/plans/2026-08-18-p02-a12-setup-hook-execution.md) and the [reverification record](../docs/reviews/2026-08-20-p02-a12-ts12-reverification.md).
- [x] [P02-T12] A12 fix per process — repository setup-hook execution is now disclosed, provenance-gated, process-group-bounded, and correctly interruptible. Shipped: a tracked-and-byte-identical eligibility check (compares the anchor's committed blob against on-disk bytes, not `git status`); a `--setup-hook-policy {tracked,any,off}` opt-out plus `--setup-hook-timeout` (default 300s), both validated at `config validate`/`load_config()` time per the A11 lesson (a key that validates clean and crashes at use); bounded process-group execution (`start_new_session=True`, a SIGTERM→SIGKILL reap ladder gated on the process group's actual emptiness, a two-stage bounded pipe drain rather than an unbounded final read); correct interrupt exit codes (`OperationInterrupted` now caught at `main()`'s boundary as 130/143 with a rendered error, not an uncaught traceback — closing a gap that affected every interrupted fork, not just hook-running ones); `fork --dry-run`/`doctor` disclosure (`doctor` hard-fails when a hook is present but ineligible under the default `tracked` policy); and a structured `setup_hook` JSON object whose bounded success-output tail is always present, never gated behind a flag. Gate 4 (implementation-plan review) had no separate artifact — folded into gate 6's rounds rather than run standalone, recorded as such in the design doc. Gate 6 (adversarial implementation review, incl. Codex) ran five rounds, not one: round 1 (Claude + Codex) found and fixed two blocking process-safety defects — reaping gated on the hook's leader exiting rather than on the group actually being empty let a backgrounded descendant hang the CLI forever or get mislabeled as timed out, and a signal path skipped `killpg` once the leader had already exited. Round 2's independent Codex confirmation found that fix left the `Popen()`-to-registration signal window still open and introduced a new PID-reuse hazard. Round 3 closed both (`pthread_sigmask` blocking around the spawn/registration critical section; a group-emptiness latch) and closed a config-resolved-JSON-interrupt gap — but round 3's own tightening of the PID-reuse fix (skipping the emptiness probe whenever `Popen.poll()` reported the leader alive) was independently found unsound in round 4: CPython's `poll()` can also return `None` under lock contention from a re-entrant signal handler, which is not proof of a live leader. Round 5 reverted that specific optimization back to the previously-verified always-probe behavior and corrected the design doc's disclosure rather than shipping a false safety claim. What remains, honestly disclosed rather than claimed closed: a sub-syscall PID-reuse race between the group-emptiness probe and the real signal, bounded to a couple of adjacent syscalls, not closable with primitives portable to both of this project's supported platforms (Known limit 9 in the design doc). Merged onto `origin/main` (`885bbfa`) with a single merge commit (`ef9db83`) resolving a three-prefix test-ID collision against A11, which had independently claimed the same `T-CFG`/`T-CLI`/`T-OUT` ranges landing concurrently — following the same merge-not-rebase precedent A10 set for the identical problem (`1f9dcff`). Final gates, independently reverified on the merged tip: `just all` 635 passed/1 skipped/17 deselected, `just test-signals` 10 passed, `just check-matrix`/`just strict-collect`/`just clean-install` all clean, 573-row matrix (30 new A12 rows). See the [A12 design and evidence record](../docs/superpowers/plans/2026-08-18-p02-a12-setup-hook-execution.md).
- [x] [P02-TS13] A13 adversarial verification (incl. Codex) — **MIXED, EXECUTED 2026-08-17.** Confirmed: (a) one notice appears on both streams; (b) `table` and `text` were byte-identical on six public surfaces; (c) a real Codex `thread/read` error became successful `not_found` with no notice; (d) all three line parsers truncated newline paths and public fork rolled back a valid worktree; (g) ordinary cleanup, without public `--force`, reported `dirty_count: 0` and destroyed distinct child-only ignored `.env`/`local.db` bytes; (h1) parent peak RSS above baseline was about 3.0 times staged binary bytes. Partially refuted: (e) one ITA magic collision copied correctly, but two overlapping patterns double-applied an ordinary patch and rolled back; issue #29 is the same fault; (f) no-remote “unpushed” classification is correct, but “push first” omits remote setup. Refuted on current main: (h2) A1 already uses `untracked_set`; production timing was approximately linear through 500,000 plus 500,000 paths. T13 is split below, with no H2 task.
- [ ] [P02-T13] A13 remediation umbrella — close after the five separate remediations merge
  - [x] [P02-T13A] Emit completed-fork notices once on stderr while preserving JSON `notices[]`; RED/GREEN and final gates are recorded in the [A13 design and evidence record](../docs/superpowers/plans/2026-08-18-p02-a13-small-fault-remediation.md)
  - [x] [P02-T13B] Remove the byte-identical `table` CLI value and make `text` the default; implementation complete, with R4.1 and R9.3 release blockers recorded in `CONFORMANCE.md`
  - [x] [P02-T13C] Preserve typed Codex `thread/read` failure semantics, parent-name evidence, and parent-assertion honesty
  - [x] [P02-T13D] Make worktree parsing newline-safe without breaking the Git 2.19 floor — completed in [PR #53](https://github.com/smorinlabs/agent-fork/pull/53), which closed [issue #46](https://github.com/smorinlabs/agent-fork/issues/46). Worktree enumeration uses NUL-delimited porcelain on Git 2.36+. Git 2.19–2.35 safely retry line-delimited porcelain, where newline-bearing worktree paths remain unsupported.
  - [x] [P02-T13E] Treat every ITA-derived operand as a literal Git pathspec; implements the remediation for issue #29, which can close after merge
  - [x] [P02-T13F] Explain remote setup when cleanup refuses unpushed commits in a repository with no remote
  - [ ] [P02-T13G] Prevent cleanup from deleting changed ignored worktree-local data; tracked separately in [issue #44](https://github.com/smorinlabs/agent-fork/issues/44)
  - [ ] [P02-T13H1] Bound staged-binary materialization memory; tracked separately in [issue #45](https://github.com/smorinlabs/agent-fork/issues/45)
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
