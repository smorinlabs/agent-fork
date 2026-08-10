# Worktree destination controls — SDD/TDD implementation plan

**Date:** 2026-08-10
**Status:** Implemented; WTD-G5 evidence complete 2026-08-10
**Scope:** Phase E.5 only; add separable worktree base-directory and leaf-name
controls, preserve existing behavior, and stop before Phase F release work
**Project:** P01 — agent-fork v1

## 1. Outcome

### 0. Pre-implementation adversarial review

The owner-approved plan was challenged before code changes. Four amendments are
binding: validate the non-rectangular exact-vs-partial conflict immediately
after parsing; decide collision mutability from consecutive fully composed
resource plans; resolve an explicit base once but never resolve/follow its leaf;
and use stable precondition errors `invalid_worktree_base` and
`invalid_worktree_name` before mutation.

Add two optional `fork` flags:

```text
--worktree-base-dir <directory>
--worktree-name <single-directory-component>
```

They separate the fork/session identity, branch name, worktree parent directory,
and worktree leaf name while preserving the current one-name defaults and the
existing exact `--worktree-dir` override.

Target example:

```bash
agent-fork fork experiment \
  --branch feature/manual-branch \
  --worktree-base-dir /work/forks \
  --worktree-name manual-worktree
```

Expected identities:

```text
fork/session name = experiment
branch            = feature/manual-branch
worktree base     = /work/forks
worktree name     = manual-worktree
worktree path     = /work/forks/manual-worktree
```

This plan does not authorize configuration-schema expansion, release plumbing,
publishing, Homebrew work, or a version cut.

## 2. Locked proposed contract

The following becomes locked only after the S1 owner gate approves D15.

### 2.1 Composition

1. Derive the normal destination using the existing D5 location policy.
2. If `--worktree-base-dir` is present, replace the derived parent directory.
3. If `--worktree-name` is present, replace the derived final component.
4. Validate the composed destination before any mutation.

| Inputs | Effective destination |
|---|---|
| no path override | existing derived destination, byte-for-byte unchanged |
| `--worktree-dir P` | exact resolved `P`, current behavior |
| `--worktree-base-dir B` | resolved `B / derived.name` |
| `--worktree-name N` | `derived.parent / N` |
| both partial overrides | resolved `B / N` |

### 2.2 Precedence and incompatibility

- `--worktree-dir` is mutually exclusive with `--worktree-base-dir`.
- `--worktree-dir` is mutually exclusive with `--worktree-name`.
- The two partial overrides may be used together.
- Conflicting options fail in argument parsing with exit 2, before repository or
  agent inspection and before mutation.
- CLI partial overrides apply after `worktree_location`, including template,
  mirror-parent, and bare-at-root rules.

### 2.3 Relative paths and base existence

- A relative base resolves against the invocation cwd, matching the existing
  `--worktree-dir` rule.
- An explicit base must already exist and be a directory.
- Phase E.5 does not create missing base parents. Adding that later requires a
  separate rollback design for parent directories created before Git mutation.

### 2.4 Worktree leaf validation

`--worktree-name` is one filesystem component, used exactly as supplied.

- allow spaces, Unicode, dots inside the name, underscores, and hyphens;
- reject empty or whitespace-only values;
- reject `.` and `..`;
- reject `/`, `\\`, and embedded NUL;
- reject an absolute path;
- never silently sanitize or lowercase an explicit worktree name;
- after resolving a symlinked base, require `destination.parent == base`.

Windows remains out of scope, but backslash is rejected now so a stored command
cannot acquire different traversal semantics on a future Windows port.

### 2.5 Identity and collisions

- The positional fork name continues to feed the default branch, worktree
  suffix, and session display name.
- `--branch` overrides only the branch.
- `--worktree-name` overrides only the worktree leaf.
- `--worktree-base-dir` overrides only the worktree parent.
- Explicit resources are never renamed or auto-suffixed.
- Automatic `-2`, `-3`, … suffixing is allowed only when the colliding branch
  or destination is derived from the automatic fork name and therefore changes
  with the next candidate.
- A fixed explicit branch or destination collision refuses immediately rather
  than consuming the 1000-candidate loop.

### 2.6 Compatibility

- Existing invocations and default paths remain byte-for-byte compatible.
- `--worktree-dir` remains supported with its current meaning.
- Registry and JSON schemas remain unchanged; both already carry the final full
  worktree path.
- Cleanup continues to accept fork name, branch, or final worktree path.
- No new TOML keys ship in this increment. Persistent placement remains the
  existing `worktree_location`/template facility.

## 3. SDD authority and amendment

### WTD-SDD-01 — approve D15

Add D15, “Partial worktree destination overrides,” to the design corpus. It
must state the composition, precedence, validation, and collision rules above.

Required specification edits:

- `DESIGN-DECISIONS.md`: add D15 and update the consolidated CLI surface.
- `REQUIREMENTS.md`: amend the positional-name feed-through statement; add both
  flags, their mutual exclusions, validation, and compatibility contract.
- `IMPLEMENTATION-PROMPT.md`: record Phase E.5 and its stop boundary.
- `CONFORMANCE.md`: add the new requirement/decision disposition while work is
  pending, then attach final evidence.

No test or production implementation begins until the owner approves D15.

### WTD-SDD-02 — amend the leading matrix

Reserve the row IDs below in this plan. During execution, add each row to the
matrix atomically with its real RED test, set the affected group to `tdd` when
the first new row lands, and keep `just check-matrix` green even while the
behavioral test is red. Return each affected group to `done` only after all of
its added rows pass. Do not add lifecycle skips to existing green rows.

Proposed G-LOC rows:

| ID | Contract | Tier |
|---|---|---|
| T-LOC-08 | base-only override preserves derived leaf | U |
| T-LOC-09 | name-only override preserves derived parent and exact leaf | U |
| T-LOC-10 | base+name compose to exactly `base/name` | U |
| T-LOC-11 | invalid leaf inventory refuses | U |
| T-LOC-12 | relative base resolves from invocation cwd | C |
| T-LOC-13 | explicit base must exist and be a directory | C |
| T-LOC-14 | template result accepts parent/leaf replacement after derivation | U |
| T-LOC-15 | linked mirror-parent result accepts partial override after derivation | F |
| T-LOC-16 | bare-at-root result accepts partial override after derivation | F |
| T-LOC-17 | symlinked base resolves once and remains contained | F |

Proposed G-NAM rows:

| ID | Contract | Tier |
|---|---|---|
| T-NAM-08 | defaults still feed all identities unchanged | U |
| T-NAM-09 | explicit branch/leaf do not change fork or session display name | U |
| T-NAM-10 | derived-resource collision advances automatic name | U |
| T-NAM-11 | explicit branch/path collision refuses without suffix | C |
| T-NAM-12 | fixed explicit collision does not enter 1000-candidate loop | U |

Proposed G-CLI/G-OUT rows:

| ID | Contract | Tier |
|---|---|---|
| T-CLI-13 | help exposes both new flags | C |
| T-CLI-14 | exact and partial path overrides are parser-mutually-exclusive | C |
| T-OUT-12 | dry-run reports exact composed destination and mutates nothing | C |
| T-OUT-13 | human and JSON success report the same final path | C |

Skill regression IDs, tracked outside the product matrix unless the checker is
deliberately extended with G-SKL:

| ID | Contract |
|---|---|
| T-SKL-08 | skill passes base/name/branch options unchanged before managed identity flags |
| T-SKL-09 | skill still rejects attempts to override managed agent/session/JSON flags |

### WTD-SDD-03 — executable examples

Add specification examples covering no override, exact override, base only,
name only, both partial overrides, and parser conflict. Every example must be
copied verbatim into a test input so prose and executable behavior cannot drift.

## 4. Implementation design

### 4.1 Pure destination layer

Keep `derive_worktree_path()` responsible for current D5 policy. Add a separate
pure composition boundary in `location.py`, conceptually:

```python
def compose_worktree_destination(
    derived: Path,
    *,
    invocation_cwd: Path,
    base_dir: Path | None = None,
    worktree_name: str | None = None,
) -> Path: ...
```

This prevents CLI flags from leaking into the location-policy function and
makes the cross-product independently testable.

### 4.2 Resource-aware naming plan

The current `collides(candidate)` combines identity selection with branch/path
collision checks. Refactor it behind tests into a plan that distinguishes:

```text
fork name: derived or explicit
branch: derived or explicit
destination: derived, partially explicit, or exact explicit
```

The planner must answer whether another automatic name can change the colliding
resource. If not, return a typed conflict immediately.

Do not change `NamingPlan` merely to store CLI arguments. Introduce the smallest
immutable plan object justified by the new tests, or keep resource provenance
local to the CLI resolver if that remains clearer.

### 4.3 Unchanged downstream contracts

Pass only the final destination into `ForkRequest`. Materialization,
verification, rollback, registry, output, launch templates, and cleanup should
not learn about base/name flags. Their existing path-based interfaces are the
compatibility boundary and must be protected with regression tests.

## 5. Ordered TDD tasks

Every task follows RED → GREEN → REFACTOR → PROOF. RED means a failure caused
by absent behavior, not collection, fixture, or environment failure.

### WTD-TS-01 / P01-TS18 — pure composition tests

**Rows:** T-LOC-08..11, T-LOC-14

Write parameterized tests for the composition table and invalid leaf inventory.
First red command:

```bash
uv run pytest tests/unit/test_loc.py -k worktree_override -vv
```

Required red: missing `compose_worktree_destination` or equivalent behavior.

### WTD-T-01 / P01-T25 — implement pure composition

Implement exact preservation/replacement, single-component validation, and
relative-base resolution. Do not inspect Git or create directories.

Proof:

```bash
uv run pytest tests/unit/test_loc.py -vv
uv run pytest tests/unit/test_nam.py -vv
```

### WTD-TS-02 / P01-TS19 — parser and precondition tests

**Rows:** T-CLI-13..14, T-LOC-12..13, T-OUT-12

Write tests for help, mutual exclusion, relative resolution, missing/non-dir
base, and dry-run no-mutation behavior.

First red command:

```bash
uv run pytest tests/cli/test_cli.py tests/cli/test_out.py -k worktree -vv
```

For parser conflicts, assert exit 2, usage on stderr, empty stdout, and no Git
shim invocation. For base preconditions, assert the stable precondition exit
and no branch/path/registry mutation.

### WTD-T-02 / P01-T26 — wire CLI destination controls

- Add both arguments to `fork` help.
- Parse all three options, then perform an immediate command-shape validation
  that calls `parser.error` when exact and partial forms are mixed. A normal
  argparse mutually-exclusive group cannot express this rule because the two
  partial flags must remain combinable.
- Compose the final path after normal D5 derivation.
- Validate explicit base existence before agent/Git mutation.
- Preserve `--worktree-dir` resolution byte-for-byte.

Proof:

```bash
uv run pytest tests/cli/test_cli.py tests/cli/test_out.py tests/unit/test_loc.py -vv
```

### WTD-TS-03 / P01-TS20 — collision provenance tests

**Rows:** T-NAM-08..12

Test the derived/explicit cross-product. Instrument the collision callback so
T-NAM-12 proves one attempt, not merely eventual failure.

First red command:

```bash
uv run pytest tests/unit/test_nam.py -k 'resource or explicit' -vv
```

### WTD-T-03 / P01-T27 — implement resource-aware collision planning

Refactor automatic naming only as far as required to distinguish mutable
derived resources from fixed explicit resources. Preserve the existing 1000
cap for genuinely derived candidates.

Proof:

```bash
uv run pytest tests/unit/test_nam.py tests/pipeline/test_grd.py -vv
```

### WTD-TS-04 / P01-TS21 — topology and pipeline tests

**Rows:** T-LOC-15..17, T-NAM-11, T-OUT-13

Create real disposable forks across plain, linked-parent, bare-at-root,
template, and symlink-base scenarios. Assert:

- exact final worktree path;
- independently selected branch;
- parent manifest/index invariance;
- verification success;
- registry path;
- human/JSON agreement;
- launch command cwd;
- cleanup by name, branch, and path.

First red command:

```bash
uv run pytest tests/pipeline/test_loc.py tests/cli/test_out.py -k override -vv
```

### WTD-T-04 / P01-T28 — finish pipeline integration

Make only the orchestration changes needed for the topology tests. Keep
`ForkRequest`, registry schema, verification, and cleanup path-based unless a
red test proves a change is necessary.

Proof:

```bash
uv run pytest tests/pipeline/test_loc.py tests/pipeline/test_grd.py \
  tests/pipeline/test_ver.py tests/pipeline/test_rbk.py \
  tests/pipeline/test_cln.py tests/cli/test_out.py -vv
```

### WTD-TS-05 / P01-TS22 — companion-skill passthrough tests

**Rows:** T-SKL-08..09

Extend the fake CLI test to prove all three user-controlled overrides arrive
unchanged and precede the skill-managed identity/JSON suffix.

First red command:

```bash
uv run pytest tests/skill/test_companion_skill.py -k worktree -vv
```

### WTD-T-05 / P01-T29 — docs and conformance closure

Update README tutorial/examples, CLI help assertions, D15/requirements final
status, P01 checkboxes, and CONFORMANCE evidence. No new config keys.

Proof:

```bash
uv run pytest tests/skill/test_companion_skill.py tests/cli/test_cli.py -vv
git diff --check
```

## 6. Gates

### Gate WTD-G0 — baseline

Before any spec or test edit:

```bash
git status --short
make check
just all
just check-matrix
just strict-collect
```

Expected baseline at plan time: 225 passed, one retired T-EXP-04 skip. If the
baseline changes before execution, record the new count; counts are evidence,
not a frozen contract.

### Gate WTD-G1 — SDD approval

Required before RED:

- owner approves D15;
- requirements/examples contain no ambiguity;
- proposed matrix IDs are unique; the unchanged existing matrix is checker-green;
- exact/partial precedence and collision behavior are explicit;
- config expansion remains deferred.

Stop if the owner prefers a different flag vocabulary, automatic base creation,
or persistent config keys; those choices materially change the test plan.

### Gate WTD-G2 — pure behavior

Required before CLI integration:

- T-LOC-08..11 and T-LOC-14 green;
- all pre-existing G-LOC and G-NAM rows green;
- path traversal inventory green;
- no filesystem mutation in unit tests.

### Gate WTD-G3 — CLI and collision safety

Required before real pipeline tests:

- parser conflicts exit 2 before discovery;
- missing/non-directory base refuses before mutation;
- fixed explicit collisions make one attempt;
- derived collision suffix behavior and 1000 cap remain green;
- dry-run reports the exact effective path and stays local-only.

### Gate WTD-G4 — topology and downstream invariants

Required before documentation closure:

- all new F/C/U rows green;
- parent manifest and index remain unchanged;
- verification/rollback/race suites green;
- registry, output, launch templates, cleanup, and skill passthrough agree on
  the same final path;
- no orphan branch, worktree, registry entry, or created base directory remains.

### Gate WTD-G5 — final Phase E.5 gate

Run:

```bash
make check
just all
just check-matrix
just strict-collect
just clean-install
uv run pytest -vv
uv run pytest --collect-only -q
git diff --check
```

Then perform one disposable real-agent proof:

```bash
agent-fork fork display-name \
  --branch test/manual-branch \
  --worktree-base-dir <existing-temp-base> \
  --worktree-name manual-directory
```

Paste the emitted command, confirm the continued session runs from the exact
path, then clean up through `agent-fork cleanup`. Repeat for the other agent if
the skill or launch-command surface changed materially during implementation.

Final evidence must state:

- old invocations and paths remain compatible;
- every new row passes and no lifecycle skip was introduced;
- T-EXP-04 remains the only planned retired skip;
- no config or JSON schema expansion occurred;
- no release or publication work began;
- work stopped for owner review before Phase F.

## 7. Adversarial checklist

- Empty, whitespace-only, `.`, `..`, slash, backslash, and absolute leaf values.
- Base is missing, a file, a broken symlink, or a symlink to a directory.
- Leaf already exists as a directory, file, or symlink.
- Exact destination combined with each partial flag in both argument orders.
- Explicit branch collides while destination is free, and vice versa.
- Auto-name collision with derived path versus fixed explicit path.
- Spaces, quotes, `$`, `;`, Unicode, and leading dash in the leaf.
- Invocation from a nested cwd with a relative base.
- Linked-worktree mirror placement and bare-at-root placement.
- Template whose final component is literal versus placeholder-derived.
- Signal or verification failure after creation: rollback removes only the
  created worktree/branch and never the explicit base.
- Concurrent forks targeting the same composed destination: exactly one wins.

## 8. Completion evidence and post-implementation adversarial review

The completed diff was reviewed again from the parser, path-containment,
collision-provenance, rollback, output, and skill boundaries. One test-quality
finding was corrected: the original fixed-collision integration test supplied a
positional name and therefore did not exercise auto-name planning. It now uses
bare auto-name mode and proves both a fixed existing branch and a fixed exact
destination refuse immediately without a suffix. No unresolved implementation
finding remains.

WTD-G5 evidence:

- `flox activate -- just all`: green, 246 passed and only retired T-EXP-04 skipped;
- `just check-matrix`, `just strict-collect` (247 items), `just clean-install`,
  `git diff --check`: green;
- disposable real Codex fork created branch `test/phase-e5-manual` at the exact
  composed `/tmp/agent-fork-wtd-proof.LoQGae/manual-directory` and emitted
  `codex fork <parent-id> -C <that-path>`; force cleanup removed the worktree,
  branch, registry entry, and test-owned base, leaving an empty registry;
- old path derivation and `--worktree-dir` tests remain green; no lifecycle skip,
  config key, registry field, or JSON field was added;
- no release, publication, or Phase F work began.
- Cleanup invoked from outside and from inside the target; cwd guard remains.

## 8. Commit and review checkpoints

Suggested coherent commits, without intermediate PRs unless the owner requests
otherwise:

1. `docs: specify partial worktree destination controls`
2. `test: lock worktree destination composition`
3. `feat: compose worktree base and name overrides`
4. `test: lock explicit collision behavior`
5. `feat: make collision planning resource-aware`
6. `test: cover destination controls end to end`
7. `docs: close worktree destination conformance`

At each commit: inspect `git diff --check`, run the narrow proof, and keep the
worktree free of unrelated changes. Open at most one final implementation PR
after WTD-G5 if the owner authorizes execution and publication of the branch.

## 9. Definition of done

Phase E.5 is complete only when D15 is approved, the new matrix rows and all
existing rows are green, real path/branch/session independence is demonstrated,
the original defaults remain unchanged, the final evidence is recorded, and
work stops before Phase F release activity.
