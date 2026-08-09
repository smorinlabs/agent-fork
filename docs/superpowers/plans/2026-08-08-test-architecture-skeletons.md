# agent-fork Test-Architecture Skeleton Phase — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the approved test-architecture spec into its committed skeleton-phase artifacts: corpus amendments executed, `TEST-MATRIX.md` authored, the full stub tree with conftest signatures, and a working `check-matrix.py` drift guard — everything §10 of the spec orders, nothing implemented beyond signatures.

**Architecture:** The spec (`docs/superpowers/specs/2026-08-08-test-architecture-design.md`, in this worktree) is the single source of truth; this plan mechanizes its §10 steps 0–5. The matrix document leads; stubs copy from it; the checker enforces the doc↔stub contract both directions. No product code, no fixture bodies — signatures raise `NotImplementedError`.

**Tech Stack:** Python ≥3.11, uv, pytest ≥9.1.1, ruff, ty, just. Checker is stdlib-only.

**Working directory for every task:** `/Users/stevemorin/c/agent-fork-test-arch` (worktree, branch `docs/test-architecture-spec`). Never touch `~/c/agent-fork` (the live checkout).

## Global Constraints

- Spec supersedes corpus until Task 1 lands (spec §1 Precedence); after Task 1 they agree.
- `TEST_HARNESS_GIT_MIN = 2.43` — copy verbatim wherever cited; suite-only constant, never in REQUIREMENTS.
- No `xfail` anywhere in stubs; lifecycle states are `pending | tdd | done` (spec §7.2). All stubs in this phase are `pending` → `skip(reason="pending: <row-id>")`.
- Exactly one `@pytest.mark.matrix("T-<GRP>-NN")` per collected item; for parametrized stubs the marker rides `pytest.param(..., id=<row-id>, marks=...)` and marker arg == param id.
- Parametrize lists are literals in stubs — never computed by calling conftest helpers (import-time collection safety, spec §6.1).
- Row IDs `T-<GRP>-NN` are never renumbered; `row_status ∈ {live, n/a, tombstone, retired, blocked}` (spec §4).
- Conventional Commits; commit at the end of every task; every commit message ends with the Claude-Session trailer used on this branch.
- `tests/test_package.py` and `tests/test_check_matrix.py` sit outside tier dirs and outside checker direction-2 scope.
- Python files pass `just all` (format, lint, typecheck, test) — run it before each commit that touches Python.

---

### Task 1: Execute amendments A1–A14 into the corpus

**Files:**
- Modify: `REQUIREMENTS.md`
- Modify: `DESIGN-DECISIONS.md`
- Modify: `IMPLEMENTATION-PROMPT.md`

**Interfaces:**
- Consumes: spec §8 table (A1–A14 with *Amends* targets).
- Produces: a corpus that agrees with the spec, so IMPLEMENTATION-PROMPT's "stop on contradiction" guardrail never fires on a decided amendment.

- [ ] **Step 1: Read spec §8 fully** (`docs/superpowers/specs/2026-08-08-test-architecture-design.md`), and skim REQUIREMENTS.md §3–§9, DESIGN-DECISIONS.md, IMPLEMENTATION-PROMPT.md §1 and §4.

- [ ] **Step 2: Apply each amendment at its named target.** Edit instructions (each adds a dated note `**Amended 2026-08-08 (owner, test-architecture spec A<n>):** …`):

| A# | File · location | Edit |
|---|---|---|
| A1 | REQUIREMENTS.md · REQ-11 exit table row 5 + REQ-41 | Add to code-5 meaning: "incl. the atomic worktree/branch collision loss in a guard race — caught and mapped to 5 with `conflict_branch_exists`; nothing left behind (rollback runs)". REQ-41: replace "collision guards make the race a clean exit-5" with "the mid-mutation collision loss is classified as exit 5 (A1)". |
| A2 | REQUIREMENTS.md · REQ-19 + REQ-11/R7.12 catalog note (REQ-17) | Add guard: "unborn HEAD (zero-commit repo) → refuse exit 5, code `repo_no_commits`, message contains the remedy (make an initial commit … and re-run)". Add `repo_no_commits` to the stable-codes list in REQ-17. |
| A3 | REQUIREMENTS.md · REQ-21 | Append: "Intent-to-add entries are supported: cached diff uses `--ita-invisible-in-index`; ITA paths transported via `git apply --intent-to-add`; verification is ITA-aware." |
| A4 | REQUIREMENTS.md · REQ-19 + REQ-17 codes | Add guard: "unmerged index entries (`git ls-files -u` non-empty, markers present or not) → refuse exit 5, code `unmerged_index`, message lists conflicted paths + resolve/reset remedy." Add `unmerged_index` to the codes list. |
| A5 | DESIGN-DECISIONS.md · D4 section | Append: "Detached HEAD auto-name: `detached-<short-sha>-<mmdd>`, collision-suffixed normally (owner 2026-08-08)." |
| A6 | REQUIREMENTS.md · REQ-12 | Append: "In a linked worktree the walk-up boundary is the worktree's own root." |
| A7 | REQUIREMENTS.md · REQ-26 | Replace the pre-0.95 fallback sentence with: "Pre-0.95.0 Codex fallback ladder removed (owner 2026-08-08, spec A7): detection is `CODEX_THREAD_ID`-only; below-matrix versions refuse per D14/REQ-29." |
| A8 | REQUIREMENTS.md · §9 | Change "Experiments E1–E4 (RESEARCH §7) run as gated integration tests" to "Experiments E1–E3 run as gated integration tests (E4 retired until v1.1 per spec A8; E5 absorbed into the §4 pipeline TDD; E6 tombstoned with A7)". |
| A9 | REQUIREMENTS.md · REQ-38 doctor bullet | Change "git version" check to "git version vs `PRODUCT_GIT_MIN` (named constant; value fixed by the implementation-phase git-feature audit)". |
| A10 | REQUIREMENTS.md · §8 | Add: "**REQ-43** Testability: the CLI resolves `git` via PATH at each invocation — never a cached absolute path (spec A10; canaried in the test suite)." |
| A11 | REQUIREMENTS.md · §9 | Append: "Implementation-phase TDD and suite runs are dispatched to subagents per the house SDD model matrix; the driving session orchestrates (owner directive 2026-08-08)." |
| A12 | REQUIREMENTS.md · REQ-13 note | Append: "Cross-source conflicts: an explicit flag beats config **and suppresses dependent config settings** (config `with_ignored=true` + `--no-with-state` → no state carried). The RESEARCH §1.1 implication rule applies only within a single source." |
| A13 | REQUIREMENTS.md · REQ-41 + REQ-17 codes | Append: "Registry locking: OS advisory lock (self-clearing on process death); contending process waits ≤ ~5s then fails with `registry_busy`." Add `registry_busy` to the codes list. |
| A14 | REQUIREMENTS.md · REQ-38 doctor bullet + §3.3 flag table + REQ-17 codes | doctor: "failing checks → non-zero exit". §3.3 fork flags: add row `--force` — "override the `PRODUCT_GIT_MIN` refusal only (stderr warning; verify still on); never overrides correctness refusals". Codes list gains none (refusal reuses precondition family). |

- [ ] **Step 3: Update IMPLEMENTATION-PROMPT.md §1** — add the spec + plan to the precedence list, after DESIGN-DECISIONS.md: `docs/superpowers/specs/2026-08-08-test-architecture-design.md` (test architecture + amendments A1–A14) and note "corpus amended 2026-08-08 to match". In §4 (Phase B), change "E1–E4"/"old E4/E6 are moot" wording to cite A7/A8 tombstone/retired rows.

- [ ] **Step 4: Verify no contradiction remains** — grep the corpus for the amended claims: `grep -n "pre-0.95\|E1–E4\|E1-E4" REQUIREMENTS.md IMPLEMENTATION-PROMPT.md` → every hit is either amended text or a historical note citing an A-number.

- [ ] **Step 5: Commit**

```bash
git add REQUIREMENTS.md DESIGN-DECISIONS.md IMPLEMENTATION-PROMPT.md
git commit -m "docs: execute test-architecture amendments A1-A14 into the corpus"
```

---

### Task 2: pyproject — register the `matrix` marker, enable strict markers

**Files:**
- Modify: `pyproject.toml` (the `[tool.pytest.ini_options]` block shown below)

**Interfaces:**
- Produces: marker `matrix(row_id)` usable by every stub; `--strict-markers` active for the whole suite.

- [ ] **Step 1: Edit `[tool.pytest.ini_options]`** from the current block to:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q --strict-markers"
markers = [
    "requires_real_cli: integration tests against real claude/codex binaries (skipped when absent)",
    "matrix(row_id): maps a collected test to its TEST-MATRIX.md row (exactly one per item; arg equals the param id for parametrized cells)",
]
```

- [ ] **Step 2: Verify collection still works**

Run: `uv run pytest --collect-only -q`
Expected: existing `tests/test_package.py` items listed, exit 0, zero `PytestUnknownMarkWarning`.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "test: register matrix marker and enable strict markers"
```

---

### Task 3: TEST-MATRIX.md — document skeleton and conventions

**Files:**
- Create: `docs/testing/TEST-MATRIX.md`

**Interfaces:**
- Produces: the machine-readable schema every later task depends on — group heading format `## G-XXX — <name>`, a `Status: pending` line directly under each heading, and row tables with header `| ID | Scenario | Axes | Tier | row_status | Source |`. The checker (Task 9) parses exactly these shapes.

- [ ] **Step 1: Write the document header + conventions section.** Content (verbatim schema, prose may be tightened):

```markdown
# agent-fork TEST-MATRIX — the leading test document

Spec: docs/superpowers/specs/2026-08-08-test-architecture-design.md (§4–§5 define this file).
Stubs copy from this document, never the reverse. scripts/check-matrix.py enforces both directions.

## Conventions
- Row IDs `T-<GRP>-NN`, never renumbered. Retired/tombstoned IDs keep their numbers forever.
- `row_status`: live | n/a | tombstone (no stub may ever exist) | retired (exempt skip stub, returns at the named milestone) | blocked (named unblock gate).
- Group `Status:` field: pending | tdd | done — the single source of truth for the stub lifecycle (spec §7.2).
- Axes: mode = exact | exact+ignored | no-state · topology = plain@branch | plain@main | detached | linked-worktree | bare@bare | bare@wt | dot-bare@wt | nested-bare | unborn(plain) | unborn(bare) · agent = claude | codex · backend = git (jj reserved, no v1 values).
- Baseline (pinned unless a group varies it): plain@branch × exact × claude × git.
- Harness git floor: TEST_HARNESS_GIT_MIN = 2.43 (F/C/R tiers hard-error below; unit runs anywhere).
```

- [ ] **Step 2: Write all 18 group sections as headings + `Status: pending` + purpose line + "Varying axes:" line + an empty row table**, in spec §3 order: G-CFG, G-DET, G-PRE, G-GRD, G-ANC, G-NAM, G-LOC, G-MAT, G-VER, G-RBK, G-REG, G-CLN, G-INC, G-EMT, G-OUT, G-CLI, G-EXP, G-FIX. Copy each group's purpose and varying axes from spec §3's table (e.g. G-ANC varies `topology`; G-MAT varies `mode` + file-state inventory; G-DET/G-PRE/G-EMT/G-OUT/G-EXP vary `agent`).

- [ ] **Step 3: Commit**

```bash
git add docs/testing/TEST-MATRIX.md
git commit -m "test: scaffold TEST-MATRIX.md schema and group sections"
```

---

### Task 4: TEST-MATRIX.md — pipeline-group rows

**Files:**
- Modify: `docs/testing/TEST-MATRIX.md` (fill tables for G-GRD, G-ANC, G-MAT, G-VER, G-RBK, G-REG, G-INC, G-LOC)

**Interfaces:**
- Consumes: Task 3's schema.
- Produces: final row IDs the pipeline/unit stub files (Tasks 7–8) cite verbatim.

Row content sources are fixed: RESEARCH §2.1/§2.2/§2.3/§4 tables + spec §5 obligations. Enumerations below are the required minimum row set per group — write one table row per bullet, numbering in order from 01. Worked example of the format (first two G-GRD rows):

```markdown
| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
| T-GRD-01 | branch already exists → refuse, exit 5, conflict_branch_exists, nothing created | baseline | F | live | REQ-19; RESEARCH §2.1 step 2 |
| T-GRD-02 | branch already has a worktree → refuse, exit 5, nothing created | baseline | F | live | REQ-19 |
```

- [ ] **Step 1: G-GRD rows** — branch exists · branch has worktree · worktree path exists · parent mid-rebase / mid-merge / mid-cherry-pick / mid-revert / mid-bisect (5 rows, each with its abort hint asserted) · not-a-repo · **unborn HEAD plain** (A2: exit 5, `repo_no_commits`, remedy text asserted) · **unborn HEAD bare** · **unmerged index, markers present** and **markerless** (A4: `unmerged_index`, conflicted paths listed) · **race loss** (A1: shim-barrier parks A post-guard; B wins; A exits 5, nothing left).
- [ ] **Step 2: G-ANC rows** — one per topology value (plain@branch, plain@main + branch≠default recorded for G-VER, detached + metadata recorded, linked-worktree + anchor-is-this-worktree's-HEAD, bare@bare, bare@wt, dot-bare@wt, nested-bare), each asserting anchor == parent HEAD^{commit} at the parent's own path.
- [ ] **Step 3: G-MAT rows** — staged-only · unstaged-only · staged+unstaged same file (split preserved: `A `/`AM`/` M` shapes) · untracked incl. nested dirs (manifest oracle proves inner files) · ignored opt-in second pass · symlink relative · symlink absolute · exec-bit-only change · binary staged · binary unstaged · rename+edit · **ITA transported** (A3 recipe) · empty-dir contract (documented absence) · submodule opaque (gitlink OID compared; constructed with scoped `protocol.file.allow=always`) · parent strictly read-only (before/after full snapshot) · **linked-worktree × dirty-both-checkouts** mandatory interaction row · linked-worktree × exact+ignored interaction row · mode variants: each of `exact` / `exact+ignored` / `no-state` full-materialize row.
- [ ] **Step 4: G-VER rows** — the 6 base ladder checks (one row each, asserted as product behavior) · conditional checks: branch≠default (plain@main), common-dir match (linked-worktree), detached-recorded · **fault injection**: non-idempotent clean filter on a staged new file → verify fails → rollback → exit 1 → `verify_failed` (+ canary reference) · `--no-verify` skips the ladder.
- [ ] **Step 5: G-RBK rows** — materialize failure → rollback (worktree removed, branch removed only if created) · rollback-fails → manual-recovery command text · SIGINT mid-materialize → 130 + clean rollback (parent-side stall) · SIGTERM → 143 · **producer-pipe-failure** (fake git `diff --cached` exit 1, empty stdout) with verify **on** · same with verify **off** (both must fail, exit 1).
- [ ] **Step 6: G-REG rows** — registry write on fork (schema fields) · `list` ordering by creation time (U) · locked-write atomicity · **different-name concurrent race** (A13: both succeed, both entries present, bounded wait observed) · **timeout row** (lock held past bound → `registry_busy`, fork rolled back) · registry ownership check feeds cleanup.
- [ ] **Step 7: G-INC rows** — `.worktreeinclude` copies listed ignored files · precedence: materialized copies win (file exists → not overwritten) · setup hook runs with cwd=new worktree + env vars (repo root, worktree path) · hook failure → non-fatal, stderr notice · **pipeline order**: include/hook run after verify; their changes excluded from the verify comparison.
- [ ] **Step 8: G-LOC rows** — U: `sibling` default path derivation · `central` (XDG data path) · `subdirectory` (`<root>/.worktrees/<slug>`) · template with each placeholder (`{repo-name}` `{repo-root}` `{branch}`) · explicit config suppresses mirror heuristic. F: mirror-parent heuristic when parent is a linked worktree · bare-at-root placement override (child of bare dir).
- [ ] **Step 9: Cross-check** each group's rows against spec §5's obligation bullets — every named obligation has a row; note N/A cells explicitly where an axis combination is impossible.
- [ ] **Step 10: Commit**

```bash
git add docs/testing/TEST-MATRIX.md
git commit -m "test: author pipeline-group matrix rows (G-GRD..G-LOC)"
```

---

### Task 5: TEST-MATRIX.md — logic/surface/experiment/fixture rows

**Files:**
- Modify: `docs/testing/TEST-MATRIX.md` (fill G-CFG, G-NAM, G-DET, G-PRE, G-EMT, G-OUT, G-CLI, G-CLN, G-EXP, G-FIX)

**Interfaces:**
- Consumes: Task 3 schema; spec §5 obligations; amendment outcomes A5, A7, A8, A12, A14.
- Produces: final row IDs for the unit/cli/live stub files.

- [ ] **Step 1: G-CFG rows** — tri-state accessor defaults (unset⇒true for with_state, unset⇒false for with_ignored) · explicit-false honored (single source) · within-source implication (`--no-with-state --with-ignored` → exact+ignored) · **A12 cross-source rows**: config-false + `--with-ignored` flag → exact+ignored; config-ignored-true + `--no-with-state` flag → **no-state**; all-unset → exact · precedence chain flags>env>config file order · `branch_prefix` whitespace → default · env vars `AGENT_FORK_CONFIG`/`AGENT_FORK_OUTPUT` · walk-up stops at repo boundary (F) · **A6 row**: linked worktree boundary = worktree root (F) · `config set`/`validate` round-trip via CLI (C) · `--config` replaces discovery.
- [ ] **Step 2: G-NAM rows** — sanitizer table (git-illegal chars, spaces→dashes, collapse, leading dots, trailing `.lock`) · auto-name `<branch-slug>-<mmdd>` (expectation computed at runtime; midnight retry = rebuild) · **A5 detached auto-name** `detached-<short-sha>-<mmdd>` · collision suffix `-2`,`-3` in auto mode · explicit-name collision → refusal not suffix · 1000-cap hard stop · name feeds branch + worktree + session name.
- [ ] **Step 3: G-DET rows** — Claude env detection (`CLAUDECODE` + `CLAUDE_CODE_SESSION_ID`) · Codex `CODEX_THREAD_ID` · explicit flags win over env · both-present ambiguity → exit 3 · neither + no flags → exit 3 · **tombstone rows** (pre-0.95 ladder: ancestry walk, fd probe, rollout scan — `row_status: tombstone`, source cites A7).
- [ ] **Step 4: G-PRE rows** — agent CLI missing → refusal exit 3 diagnosis · Claude below 2.0.73 → refuse · Claude warn-band (<~2.1.1xx) → warn-and-proceed, `notices[]` asserted (agent=claude) · Codex below 0.81.0 → refuse · Codex rollout not flushed → refuse before mutation (agent=codex) · injected-version rows for `PRODUCT_GIT_MIN` boundary (`row_status: blocked`, gate: A9 audit) · **A14 rows**: below-floor fork refusal (exit 5, remedy) and `--force` override (stderr warning, verify on) — blocked on the same gate · D14: nothing created on preflight refusal.
- [ ] **Step 5: G-EMT rows** — Claude template byte-exact prefix (`cd '<worktree>' && claude --session-id … --resume … --fork-session`) with `-n` cell marked pending-E1 · Codex template (`cd '<worktree>' && codex fork <id>`) pending-E2 cells · uniform quoting: worktree path with spaces/quotes/`$`/`;` · extra_args each element individually quoted (spaces, quotes, `$`, `;` cases) · extra_args visible in `--dry-run` and `-o json` (agent axis varies).
- [ ] **Step 6: G-OUT rows** — stdout carries only the result; progress on stderr · paste command is final stdout block · TTY does not change format (pty row) · `-o json` minimum fields incl. `cwd_prompt_expected` (codex) and its absence (claude) · error object shape on stderr under machine format · stable codes present (`conflict_branch_exists`, `parent_mid_operation`, `session_not_found`, `verify_failed`, `repo_no_commits`, `unmerged_index`, `registry_busy`) · `--dry-run` lists every planned mutation + local-validation note · copy-failure = stderr notice, exit unchanged · non-C locale row (machine output byte-identical).
- [ ] **Step 7: G-CLI rows** — bare `agent-fork` → help, exit 0 · `-h/--help`, `-V/--version` (`agent-fork <semver>`), `-v` repeatable, `-q`, `--config`, `--debug` present · exit-code catalog rows incl. unknown `--agent` → **3** · `completion bash|zsh|fish` smoke · doctor content rows (git version vs PRODUCT_GIT_MIN named check, agent CLIs vs matrix, env signals, config valid, XDG writable) · **A14**: doctor failing check → non-zero exit.
- [ ] **Step 8: G-CLN rows** — cleanup by name / branch / path · worktree removed + pruned · branch deleted unless `--keep-branch` · registry updated · guards: dirty worktree · unpushed commits · target-is-cwd (each exit 5) · `--force` extends targets + overrides guards · `--yes` consent bypass · `--no-input` without consent → exit 2 · TTY consent prompt on stderr (pty row) · session files never deleted + resumable note in output · `--dry-run` removal plan.
- [ ] **Step 9: G-EXP rows** — E1 Claude flag combo (live) · E2 Codex cross-cwd + `-C` (live) · E3 Claude E2E paste command (live) · E4 `.jsonl` copy (**retired**, milestone v1.1, cites A8) · E5 mapping row (**absorbed** → G-MAT/G-VER, prevents restoration) · E6 mapping row (**tombstone**, cites A7) · results recorded in EXPERIMENTS.md noted in Source column.
- [ ] **Step 10: G-FIX rows** — builder-vs-spec verification per topology constructor · oracle **mutation rows** (flip byte / chmod / retarget symlink / add file / update-index one entry — oracle must fail on exactly that cell) · env-seal leak assertion (no `^(CLAUDE|CODEX|AI_AGENT|GIT_)` outside whitelist) · realpath rule (`handle.path == realpath(handle.path)`) · git-version canaries: filter-divergence, origin/HEAD determinism (`set-head` applied; deletion row exercises fallback), unborn rc=128, ITA flags present · shim-interception canary (logs non-empty argv) · harness git-floor gate (hard error below 2.43, F/C/R only).
- [ ] **Step 11: Sweep the whole document** — every spec §5 bullet maps to a row; every `blocked` row names its gate; every tombstone/retired row cites its A-number; count total rows (expect roughly 120–150; note the count at the top of the doc).
- [ ] **Step 12: Commit**

```bash
git add docs/testing/TEST-MATRIX.md
git commit -m "test: author logic, surface, experiment, and fixture matrix rows"
```

---

### Task 6: conftest signatures

**Files:**
- Create: `tests/conftest.py`

**Interfaces:**
- Produces (later tasks and the whole TDD phase rely on these exact names): `RepoSpec`, `StateSpec` constructors `staged()`, `unstaged()`, `untracked()`, `ignored()`, `symlink_state()`, `exec_bit()`, `binary_state()`, `rename_edit()`, `intent_to_add()`, `unmerged()`, `empty_dir()`, `submodule()`, `worktreeinclude()`; `origin(pushed, unpushed)`; fixture `repo_scenario`; `WorldHandle` with `.parent_path`, `.child_path`, `.env`, oracle methods `manifest_diff()`, `index_diff()`, `parent_snapshot()`; helpers `sealed_env()`, `pty_run()`, `shim_git()`, `stall_filter()`, `run_cli()`.

- [ ] **Step 1: Write `tests/conftest.py`** — dataclasses + fixture signatures, every body `raise NotImplementedError("skeleton phase: implemented in VM TDD")`, every docstring citing its spec section. Skeleton (write in full, with docstrings for every public name):

```python
"""Shared fixture layer for the agent-fork test suite.

Signatures only (skeleton phase). Bodies land via TDD in the VM, G-FIX first.
Spec: docs/superpowers/specs/2026-08-08-test-architecture-design.md §6.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

TEST_HARNESS_GIT_MIN = (2, 43)  # spec §2/§7.5 — F/C/R tiers hard-error below this


@dataclass(frozen=True)
class StateSpec:
    """One file-state element of a scenario (spec §6.3 vocabulary)."""
    kind: str
    path: str
    target: str | None = None
    content: bytes | None = None


@dataclass(frozen=True)
class OriginSpec:
    """Local bare-repo remote: wired, fetched, set-head applied (spec §6.4)."""
    pushed: int = 0
    unpushed: int = 0


@dataclass(frozen=True)
class RepoSpec:
    """Declarative world description consumed by repo_scenario (spec §6.1)."""
    topology: str = "plain@branch"
    states: tuple[StateSpec, ...] = ()
    remote: OriginSpec | None = None


def staged(modify: str | None = None, add: str | None = None) -> StateSpec:
    """Staged modification or staged new file."""
    raise NotImplementedError("skeleton phase: implemented in VM TDD")

# ... one constructor per vocabulary item, same shape:
# unstaged(), untracked(path|symlink=..., target=...), ignored(), symlink_state(),
# exec_bit(), binary_state(staged: bool), rename_edit(), intent_to_add(),
# unmerged(markerless: bool), empty_dir(ignored: bool), submodule(), worktreeinclude()


def origin(pushed: int = 0, unpushed: int = 0) -> OriginSpec:
    return OriginSpec(pushed=pushed, unpushed=unpushed)


class WorldHandle:
    """Built world: paths (realpathed), sealed env, and the test-side oracles (spec §6.5)."""

    parent_path: Path
    child_path: Path | None
    env: dict[str, str]

    def manifest_diff(self, a: Path, b: Path) -> list[str]:
        """lstat-only manifest+hash comparison; empty list means identical."""
        raise NotImplementedError("skeleton phase: implemented in VM TDD")

    def index_diff(self, a: Path, b: Path) -> list[str]:
        """git ls-files --stage comparison (blob IDs + modes), ITA-aware."""
        raise NotImplementedError("skeleton phase: implemented in VM TDD")

    def parent_snapshot(self) -> object:
        """Full manifest+index snapshot for the parent-inviolate assertion."""
        raise NotImplementedError("skeleton phase: implemented in VM TDD")


@pytest.fixture
def repo_scenario():
    """Build a WorldHandle from a RepoSpec. Sealed whitelist env (spec §6.2)."""
    def _build(topology: str = "plain@branch", states=(), remote=None) -> WorldHandle:
        raise NotImplementedError("skeleton phase: implemented in VM TDD")
    return _build


def sealed_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Whitelist-from-empty subprocess environment (spec §6.2)."""
    raise NotImplementedError("skeleton phase: implemented in VM TDD")


def run_cli(args: list[str], env: dict[str, str], cwd: Path):
    """Run the built agent-fork console script via subprocess (tier C black box)."""
    raise NotImplementedError("skeleton phase: implemented in VM TDD")


def pty_run(args: list[str], env: dict[str, str], tty_fd: int):
    """Per-fd pty harness: only tty_fd on the pty, others piped; ONLCR cleared (spec §6.6)."""
    raise NotImplementedError("skeleton phase: implemented in VM TDD")


def shim_git(fail_call: str | None = None, park_at: str | None = None):
    """PATH git shim: fault injection and the race barrier (spec §6.6)."""
    raise NotImplementedError("skeleton phase: implemented in VM TDD")


def stall_filter(world: WorldHandle):
    """Parent-side step-2 diff clean-filter stall with readiness file (spec §6.6)."""
    raise NotImplementedError("skeleton phase: implemented in VM TDD")
```

(The `# ...` comment line above is an instruction to the implementer of THIS task: write every listed constructor out explicitly with its own signature and docstring — no comment placeholders may remain in the committed file.)

- [ ] **Step 2: Verify import + collection**

Run: `uv run pytest --collect-only -q`
Expected: exit 0 (conftest imports cleanly; bodies never execute at collection).

- [ ] **Step 3: Run `just all`** — format/lint/typecheck must pass on the new file (add `# noqa`/type ignores only if ty flags the abstract bodies; prefer real annotations).

- [ ] **Step 4: Commit**

```bash
git add tests/conftest.py
git commit -m "test: declare fixture-layer signatures (RepoScenario, oracles, harnesses)"
```

---

### Task 7: Stub tree — fixtures/ and unit/

**Files:**
- Create: `tests/fixtures/test_fix.py`, `tests/unit/test_cfg.py`, `tests/unit/test_nam.py`, `tests/unit/test_loc.py`, `tests/unit/test_emt.py`, `tests/unit/test_det.py`, `tests/unit/test_pre.py`, `tests/unit/test_reg.py`

**Interfaces:**
- Consumes: row IDs from Tasks 4–5 (copy exactly); conftest names from Task 6.
- Produces: collected items the checker validates.

- [ ] **Step 1: Write every live-row stub for these groups' U-tier rows (and G-FIX's F rows in `tests/fixtures/`).** One stub per row (or one parametrized function per scenario family with per-param ids). Exact stub shape — copy this pattern:

```python
import pytest


@pytest.mark.matrix("T-CFG-01")
@pytest.mark.skip(reason="pending: T-CFG-01")
def test_with_state_unset_defaults_true(repo_scenario):
    """T-CFG-01 — with_state unset resolves to True.

    Given:  no config file, no flags
    Expect: resolved plan carries state (exact)
    Source: REQ-13; RESEARCH §1.1 tri-state accessors
    """
    raise NotImplementedError
```

Parametrized family shape (marker rides each param; the list is a literal):

```python
@pytest.mark.parametrize(
    "topology",
    [
        pytest.param("bare@bare", id="T-ANC-05", marks=pytest.mark.matrix("T-ANC-05")),
        pytest.param("bare@wt", id="T-ANC-06", marks=pytest.mark.matrix("T-ANC-06")),
    ],
)
@pytest.mark.skip(reason="pending: T-ANC-05/T-ANC-06 family")
def test_anchor_matches_parent_head(repo_scenario, topology):
    """Anchor equals the parent's HEAD commit in bare layouts. Source: REQ-20."""
    raise NotImplementedError
```

Rules: tombstone rows get **no stub**; retired rows (E4 — Task 8's live/ file) get `skip(reason="retired: <row-id> until v1.1 (A8)")`; blocked rows **do** get a pending stub (they are authored, their assertions cite the gate in the docstring).

- [ ] **Step 2: Collect and eyeball counts**

Run: `uv run pytest tests/fixtures tests/unit --collect-only -q | tail -3`
Expected: item count equals the live+blocked row count for these groups; zero warnings.

- [ ] **Step 3: `just all`, then commit**

```bash
git add tests/fixtures tests/unit
git commit -m "test: stub fixtures/ and unit/ tier rows"
```

---

### Task 8: Stub tree — pipeline/, cli/, live/

**Files:**
- Create: `tests/pipeline/test_grd.py`, `test_anc.py`, `test_mat.py`, `test_ver.py`, `test_rbk.py`, `test_reg.py`, `test_cln.py`, `test_inc.py`, `test_det.py`, `test_pre.py`, `test_loc.py`, `test_cfg.py`
- Create: `tests/cli/test_out.py`, `test_cli.py`, `test_cln.py`, `test_cfg.py`, `test_reg.py`
- Create: `tests/live/test_exp.py`

**Interfaces:**
- Consumes: same as Task 7. `tests/live/test_exp.py` additionally stacks `@pytest.mark.requires_real_cli` on E1–E3 stubs (skip-reason class exempt from lifecycle, spec §7.2).

- [ ] **Step 1: Write every remaining live/blocked/retired stub**, same shapes as Task 7. E4's retired stub in `tests/live/test_exp.py`:

```python
@pytest.mark.matrix("T-EXP-04")
@pytest.mark.skip(reason="retired: T-EXP-04 until v1.1 (A8 — D14 mooted the .jsonl-copy fallback)")
def test_jsonl_copy_last_resort():
    """T-EXP-04 — retired. Returns with the v1.1 fallback ladder."""
    raise NotImplementedError
```

- [ ] **Step 2: Full collection**

Run: `uv run pytest --collect-only -q | tail -3`
Expected: total items = live + blocked + retired rows across all groups (+ the pre-existing package tests); zero warnings, exit 0.

- [ ] **Step 3: `just all`, then commit**

```bash
git add tests/pipeline tests/cli tests/live
git commit -m "test: stub pipeline, cli, and live tier rows"
```

---

### Task 9: check-matrix.py — parsers (TDD)

**Files:**
- Create: `scripts/__init__.py` (empty — makes `scripts` importable for `from scripts.check_matrix import …` and `-p scripts.collect_dump`)
- Create: `scripts/check_matrix.py` (module) and `scripts/check-matrix.py` (thin runner calling `main()`)
- Create: `scripts/collect_dump.py` (pytest plugin)
- Test: `tests/test_check_matrix.py` (outside tier dirs — exempt from direction 2, like `test_package.py`)

**Interfaces:**
- Produces: `parse_matrix(text) -> dict[group_id, Group]` where `Group` has `.status` (`pending|tdd|done`) and `.rows: dict[row_id, Row]` with `Row.row_status`, `Row.tier`; `collect_items(repo_root) -> list[Item]` with `Item.nodeid`, `Item.path`, `Item.matrix_id`, `Item.skip_reason`; `main(argv) -> int` (0 clean, 1 findings).
- `scripts/collect_dump.py`: pytest plugin whose `pytest_collection_finish` writes one JSON object per item (`{"nodeid", "path", "matrix", "skip_reason"}`) to the file named by env `COLLECT_DUMP_OUT`.

- [ ] **Step 1: Write the failing parser test**

```python
from pathlib import Path

from scripts.check_matrix import parse_matrix

SAMPLE = """\
## G-GRD — fork guards
Status: pending
Varying axes: none

| ID | Scenario | Axes | Tier | row_status | Source |
|---|---|---|---|---|---|
| T-GRD-01 | branch exists refuses | baseline | F | live | REQ-19 |
| T-GRD-99 | old thing | baseline | F | tombstone | A7 |
"""


def test_parse_matrix_reads_groups_rows_and_statuses():
    groups = parse_matrix(SAMPLE)
    assert groups["G-GRD"].status == "pending"
    assert groups["G-GRD"].rows["T-GRD-01"].row_status == "live"
    assert groups["G-GRD"].rows["T-GRD-01"].tier == "F"
    assert groups["G-GRD"].rows["T-GRD-99"].row_status == "tombstone"
```

- [ ] **Step 2: Run it — expect FAIL** (`uv run pytest tests/test_check_matrix.py -v` → import error / not defined).
- [ ] **Step 3: Implement `parse_matrix`** (stdlib regex over `## G-…` headings, `Status:` lines, table rows). Minimal, no YAML/markdown deps.
- [ ] **Step 4: Run — expect PASS.**
- [ ] **Step 5: Write the failing collector test** (uses the plugin against a tiny synthetic tree in `tmp_path` with one marked stub; asserts nodeid/matrix/skip_reason captured).

```python
def test_collect_items_reads_marker_and_skip_reason(tmp_path):
    (tmp_path / "tests" / "unit").mkdir(parents=True)
    (tmp_path / "tests" / "unit" / "test_x.py").write_text(
        "import pytest\n"
        "@pytest.mark.matrix('T-CFG-01')\n"
        "@pytest.mark.skip(reason='pending: T-CFG-01')\n"
        "def test_a():\n    raise NotImplementedError\n"
    )
    from scripts.check_matrix import collect_items
    items = collect_items(tmp_path)
    assert items[0].matrix_id == "T-CFG-01"
    assert items[0].skip_reason.startswith("pending:")
```

- [ ] **Step 6: FAIL → implement `collect_items`** (subprocess `uv run pytest --collect-only -q -p scripts.collect_dump` with `COLLECT_DUMP_OUT` temp file; parse JSON lines) **→ PASS.**
- [ ] **Step 7: `just all`, then commit**

```bash
git add scripts/ tests/test_check_matrix.py
git commit -m "feat: check-matrix parsers for matrix doc and collected items"
```

---

### Task 10: check-matrix.py — the five checks + just recipe

**Files:**
- Modify: `scripts/check_matrix.py` (add `run_checks(groups, items, tier_dirs) -> list[str]` + `main`)
- Modify: `tests/test_check_matrix.py`
- Modify: `justfile`

**Interfaces:**
- Consumes: Task 9 parsers.
- Produces: `just check-matrix` exit 0/1; findings printed one per line `CHECK<n>: <message>`.

- [ ] **Step 1: Write failing tests for the five checks** (synthetic groups/items built inline — one test per check, spec §7.4):

```python
from scripts.check_matrix import Group, Item, Row, run_checks

TIER_DIRS = {
    "tests/unit": "U", "tests/pipeline": "F", "tests/cli": "C",
    "tests/live": "R", "tests/fixtures": "F",
}


def _group(gid, status, rows):
    return {gid: Group(status=status, rows={r.row_id: r for r in rows})}


def _row(rid, status="live", tier="U"):
    return Row(row_id=rid, row_status=status, tier=tier)


def _item(mid, path="tests/unit/test_x.py", skip="pending: x"):
    return [Item(nodeid=f"{path}::t[{mid}]", path=path, matrix_id=mid, skip_reason=skip)]


def test_check1_live_cell_without_item_fails():
    findings = run_checks(_group("G-CFG", "pending", [_row("T-CFG-01")]), [], TIER_DIRS)
    assert any("CHECK1" in f and "T-CFG-01" in f for f in findings)


def test_check2_retired_and_requires_real_cli_skips_are_exempt():
    groups = _group("G-EXP", "done", [_row("T-EXP-04", status="retired", tier="R")])
    items = _item("T-EXP-04", path="tests/live/test_exp.py", skip="retired: T-EXP-04 until v1.1 (A8)")
    assert run_checks(groups, items, TIER_DIRS) == []


# Same shape, one violation each — write every body out fully in this file:
# test_check1_item_citing_unknown_id_fails
# test_check2_pending_group_with_unskipped_stub_fails   (skip_reason=None in a pending group)
# test_check2_tdd_group_with_lifecycle_skip_fails       (skip_reason="pending: …" in a tdd group)
# test_check3_experiments_e1_to_e6_all_mapped           (drop T-EXP-06 → finding names it)
# test_check4_tombstone_cited_by_item_fails
# test_check4_na_cell_cited_by_item_fails
# test_check5_item_directory_mismatches_row_tier_fails  (tier "F" row, item under tests/unit/)
```

Each remaining test builds the minimal groups/items that violate exactly one rule and asserts the finding substring, exactly like the two worked examples. Direction-2 scope: only items whose path starts with a `TIER_DIRS` key are checked; `tests/fixtures/` maps to tier F.

- [ ] **Step 2: FAIL → implement `run_checks` + `main` → PASS.**
- [ ] **Step 3: Add the just recipe**

```make
# Validate TEST-MATRIX.md against the collected stub tree
check-matrix:
    uv run python scripts/check-matrix.py
```

- [ ] **Step 4: Run the real thing**

Run: `just check-matrix`
Expected: exit 0 against the Task 7–8 stub tree. Every finding it prints is a genuine doc↔stub drift — fix the stub or the row, re-run until clean.

- [ ] **Step 5: `just all`, then commit**

```bash
git add scripts/check_matrix.py tests/test_check_matrix.py justfile
git commit -m "feat: check-matrix five checks and just recipe"
```

---

### Task 11: P01 tracking + final validation

**Files:**
- Modify: `PROJECTS.md` (row stays `[~] P01`), `projects/P01-agent-fork-v1.md`

**Interfaces:**
- Consumes: everything above, green.

- [ ] **Step 1: Add skeleton-phase rows to P01** using the next free TS/T numbers (read the file for the current maximum; TS rows before T rows per house convention). Titles to add, checked `[x]` since this phase completes them:
  - `[TS<next>] Test architecture spec + matrix authored (docs/testing/TEST-MATRIX.md, ~N rows, 18 groups) — spec docs/superpowers/specs/2026-08-08-test-architecture-design.md`
  - `[TS<next+1>] Stub tree committed (tiers U/F/C/R, pending lifecycle) + conftest signatures`
  - `[T<next>] Corpus amendments A1–A14 executed (REQUIREMENTS/DESIGN-DECISIONS/IMPLEMENTATION-PROMPT)`
  - `[T<next+1>] check-matrix drift guard + just check-matrix`
  Also annotate P01-TS01..TS03: "authored as T-EXP-01..03 stubs (skeleton phase); flip G-EXP to tdd at Phase B" and the CI task (T18): "check-matrix + strict-collection CI job moves to implementation start (spec §7.6); T18 keeps the full R9.14 conformance job".
- [ ] **Step 2: Final validation sweep**

Run: `just all && just check-matrix && uv run pytest --collect-only -q | tail -2`
Expected: all green; collection warning-free.

- [ ] **Step 3: Commit**

```bash
git add PROJECTS.md projects/P01-agent-fork-v1.md
git commit -m "docs(projects): record skeleton-phase tasks in P01"
```

---

## Verification (whole plan)

`just all` green · `just check-matrix` green · `uv run pytest` runs with every matrix stub skipped (`pending:`/`retired:` reasons) and package + checker tests passing · `git log` shows one commit per task · corpus grep from Task 1 step 4 clean.
