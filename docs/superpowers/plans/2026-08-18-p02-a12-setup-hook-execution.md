# P02-A12 — Repository setup-hook execution policy

This document defines `P02-T12`, the remediation for fault A12 in the P02
fault-remediation project. The intended reader is the engineer who implements
or reviews A12. The required action is to replace today's unconditional,
unbounded, invisible setup-hook execution with a disclosed, provenance-gated,
process-group-bounded one — without turning a `SHOULD`-tier convenience
(`REQ-24`) into a fatal fork step.

Terms used throughout:

- **setup hook** — `.agent-fork/worktree-setup.sh`, an executable script that
  lives in the *repository being forked*, not in agent-fork's own source.
  agent-fork owns the execution mechanism; the consuming repository supplies
  the content, exactly as `npm` owns `postinstall` and the package supplies it.
- **anchor** — `WorktreeCreation.anchor`, the commit SHA the new worktree was
  created at (`repository.create_worktree_at_anchor()`). The child's `HEAD`
  equals it; `verify_fork()` already asserts that.
- **eligible** — the hook is committed in the anchor's tree as a regular blob
  *and* the bytes on disk in the child are identical to that blob.
- **process group** — the POSIX group created by `start_new_session=True`, so
  `os.killpg()` reaches the hook and every process it spawned.

The CLI interface review below uses CLI Design Standard 1.4.14 at the existing
publishable tier. A12 adds flags, configuration keys, machine-output fields,
and a diagnostic row. It adds no commands, no network access, no streaming, no
plugins, and no interactive behavior.

| P02 gate | State |
|---|---|
| 1. Adversarial verification, including Codex | **CONFIRMED-WITH-CORRECTION** on 2026-08-17 (this document's Gate-1 evidence); independently reconfirmed **CONFIRMED-WITH-CORRECTIONS** on 2026-08-20 via a fresh live repro plus a Codex source-trace, committed at `30f5e76` on `worktree-p02-a12-ts12-reverify` |
| 2. Owner scope decision | **three constraints settled** at scoping time, recorded below. The plan's four open design questions are now **all settled** — see Owner decisions |
| 3. Design document | **this document** |
| 4. Implementation plan and adversarial review, including Codex | **no separate artifact** — "Test-driven implementation plan" below is the plan, and no plan-level review document exists under `docs/reviews/` (only the gate-1 re-verification, `2026-08-20-p02-a12-ts12-reverification.md`). Recorded as observed rather than inferred |
| 5. Test-driven implementation | **complete** — Steps 1–6 at `aa8948d`…`e88b915`, plus the gate-6 corrections below |
| 6. Adversarial implementation review, including Codex | **CONFIRMED-WITH-CORRECTIONS** on 2026-08-20 — two independent lenses (Claude, Codex) found corroborating defects in the shipped implementation; all are fixed, with five new matrix rows. See "Gate-6 corrections" |

---

## Outcome required

After A12, a fork that reaches the setup-hook step must satisfy all of the
following.

1. **Disclosed before it runs.** `fork --dry-run` states the hook path, whether
   it is present, whether it is eligible, whether it would run, and the
   timeout. `doctor` reports the same facts for the current worktree.
2. **Provenance-gated by default.** Only a hook committed at the anchor and
   byte-identical on disk runs. An untracked or modified hook is skipped with a
   named reason, and runs only under an explicit opt-in.
3. **Opt-out.** `--setup-hook-policy off` and a matching `[fork]` config key
   stop the step entirely, before any eligibility check or execution. (A12's
   register entry names `--no-setup-hook` as an example spelling; the owner
   chose a single three-way policy flag instead — see the Contracts section.)
4. **Bounded.** Execution has a timeout. The hook runs in its own process
   group, so a timeout kills the hook *and every child that stayed in that
   group*, not just the shell. A child that calls `setsid()` leaves the group
   and cannot be killed with it; waiting on it is bounded instead, and the
   result says so (see "Execution and reaping").
5. **Reaped on interruption.** `SIGINT`/`SIGTERM` to the CLI kills and reaps the
   whole hook process group before rollback removes the worktree.
6. **Correct interrupt exit code.** After rollback the CLI exits `130`
   (`SIGINT`) or `143` (`SIGTERM`) with a rendered error, not a traceback and
   exit `1`.
7. **Visible outcome.** Human output shows the hook running and whether it
   succeeded. Successful output is retained in a bounded form instead of being
   discarded.
8. **Structured for machines.** `--json` carries one `setup_hook` object with
   path, eligibility, ran/skipped plus reason, exit code, timed-out flag, and
   duration — and stdout stays exactly one JSON line, with no progress text.

Non-goals, stated so the reviewer does not expect them: hook failure stays
**non-fatal** (`REQ-24` is a `SHOULD`), and the pipeline order fixed by the
test-architecture spec (`docs/superpowers/specs/2026-08-08-test-architecture-design.md:105`)
is unchanged — the hook still runs after `.worktreeinclude` and before the
registry write.

---

## Gate-1 evidence

`P02-TS12` recorded **CONFIRMED-WITH-CORRECTION, 2026-08-17**. The executed
repro produced these facts:

| # | Observed | Mechanism in current code |
|---|---|---|
| 1 | A real fork executed an **index-untracked** hook | `include.py:97` tests only `hook.is_file()` |
| 2 | A `sleep 30` hook still had the CLI process, the hook shell, and the sleeper alive after **4.026 s** | `include.py:107-109` calls `subprocess.run(...)` with no `timeout=` |
| 3 | Successful stdout/stderr was swallowed | `include.py:112-113` returns `()` when `returncode == 0` |
| 4 | No dedicated opt-out existed | no flag, no `_FORK_KEYS` entry (`config.py:21-29`) |
| 5 | Neither `--dry-run` nor `doctor` disclosed the hook | `DryRunOutput` (`output.py:84-127`) and `run_doctor()` (`doctor.py:89-179`) have no hook field or check |
| 6 | Parent-only `SIGINT` removed the worktree and branch in **59.081 ms**, killed the direct hook shell, but **orphaned its sleeper under PID 1** | `subprocess.run()` kills only the direct child on exception, and the hook is not started with `start_new_session=True`, so descendants survive reparenting |
| 7 | The CLI exited **1 with a traceback** instead of **130** | `OperationInterrupted` (`rollback.py:19`) derives from `BaseException`; `main()` catches only `Exception` (`cli.py:1257`), so it escapes uncaught |

Fact 7 is a **conformance gap against text this repository already publishes**,
not a new requirement:

- `REQUIREMENTS.md:132` (`REQ-22`): "Signals mid-pipeline trigger the same
  rollback (exit 130/143)."
- `README.md:526-527`: "**Interrupts are handled.** SIGINT and SIGTERM exit 130
  and 143 after rollback where applicable."

The gap survived because the matrix rows that prove it — `T-RBK-03` and
`T-RBK-04` — assert at the *library* boundary. `tests/pipeline/test_rbk.py:133-143`
forks a worker that calls `run_with_rollback()` directly, catches
`OperationInterrupted`, and calls `os._exit(error.exit_code)` itself. Nothing
exercises `main()`'s exception handling under a signal, so `main()` never had
to translate the exception. A12 must add that missing CLI-level row.

---

## Settled owner constraints

These three are decided. The design accommodates them; it does not relitigate
them.

1. **A timeout cannot undo side effects.** A hook killed at 300 s may already
   have pushed a branch, written `~/.npmrc`, or mutated shared repository
   configuration. The timeout bounds *duration*, not *blast radius*, and every
   user-facing string must say so rather than implying a rollback of the hook's
   own work.
2. **Tracked proves provenance, not safety.** A committed hook is one a
   reviewer *could* have read; it is not one that is safe. The eligibility gate
   is a trust boundary against a *cloned repository silently running new code
   on the next fork*. It is not a sandbox and must never be described as one.
3. **Error messaging alone is insufficient.** The nonzero-exit notice path at
   `include.py:112-116` already exists and is not the fix. A12 must add
   controls — visibility, policy, bounded process-group execution and reaping,
   correct signal exit codes — not better prose.

A fourth boundary follows from `REQ-24`'s `SHOULD` tier and is asserted here as
a design decision rather than an owner ruling: **an ineligible hook is skipped,
not refused.** A refusal would make a `SHOULD`-tier step able to fail a fork,
which contradicts both `REQ-24` and `T-INC-04`. Skipping is loud (a notice, a
structured reason, a doctor row) and recoverable (commit the hook, or pass the
override).

---

## Scope boundary

In scope:

- `src/agent_fork/include.py` — eligibility, process-group execution, reaping,
  bounded output capture, the `SetupHookResult` type;
- `src/agent_fork/git.py` — promote the existing `_signal_process_group()`
  helper to a public name so include.py reuses it rather than copying it;
- `src/agent_fork/rollback.py` — `interrupt()` also terminates an active hook
  group;
- `src/agent_fork/pipeline.py` — thread the anchor, policy, and a progress
  callback in; carry `SetupHookResult` out on `ForkResult`;
- `src/agent_fork/cli.py` — flags, dry-run disclosure, progress line,
  `OperationInterrupted` handling;
- `src/agent_fork/config.py` — three new `[fork]` keys and their validation;
- `src/agent_fork/output.py` — the `setup_hook` document in `ForkOutput` and
  `DryRunOutput`;
- `src/agent_fork/doctor.py` — one additional check;
- `src/agent_fork/errors.py` — two interrupt error codes;
- tests and the documents listed under "Documentation and conformance".

Out of scope, with reasons:

- **Sandboxing or restricting the hook's environment.** A2 closed the
  environment-hardening item and explicitly left "the setup hook runs after
  verification with an inherited environment and can write shared repository
  configuration" as a *named, visible gap* (register lines 128-131 and
  142-146, issue #38). A12 does not reopen it; the eligibility gate is a
  disclosure and provenance control, not a confinement control.
- **The duplicate-notice defect.** `output.py:79` renders notices into stdout
  and `cli.py:624-625` reprints them on stderr. That is A13(a), now tracked as
  `P02-T13ABF`. A12 must not add the hook's *success* status to `notices` (it
  would double-print through the same defect) and must not fix the defect
  either.
- **Streaming the hook's output live.** Deferred; see "Known limits".
- **Making hook failure fatal.** Contradicts `REQ-24`.

---

## Design options

Three axes carry real choices. Each is presented with its options, then one
recommended combination.

### Axis A — process ownership and reaping

**A1 — mirror `run_git`, with a local active-process slot. (recommended)**

Replace `subprocess.run()` with `subprocess.Popen(..., start_new_session=True)`
and reuse the escalation ladder that `git.py:106-130` already runs for Git.
Add a module-local `_ACTIVE = threading.local()` slot and
`terminate_active_setup_hook()` in `include.py`, exactly parallel to
`git.py:14` and `git.py:73-78`. `rollback.interrupt()` calls both terminators.

Promote `git.py:_signal_process_group()` to the public
`signal_process_group()`, unchanged. Its docstring encodes hard-won behavior —
macOS can report `EPERM` after another signal killed the group leader but
before `Popen` reaped it, so it re-polls before falling back to a direct-child
signal. `T-RBK-07` exists solely to pin that. Copying the function would
duplicate a regression the repository has already paid for once.

- Cost: one rename, one new module-local slot, one extra call in `interrupt()`.
- Benefit: identical shape to the only other subprocess primitive in the
  codebase, so a reviewer verifies it by comparison.

**A2 — a shared active-child registry module.**

Introduce `process.py` owning `signal_process_group()`, an active-process
registry, and the reap ladder; `git.py` and `include.py` both register into it,
and `interrupt()` sweeps the registry.

- Cost: a new module and a refactor of the Git path, which A1 leaves untouched.
- Benefit: a third subprocess site (the Codex app-server, the agent version
  probes) would get reaping for free.
- Rejected for now: the repository's scope rules say do not build an
  abstraction for what is currently two call sites. A2 is the right shape *if*
  a later item needs the third; A12 should not pre-pay for it.

**A3 — `subprocess.run(timeout=...)` plus `os.setsid` and a `killpg` on timeout.**

The minimal patch: keep `run()`, add `timeout=`, add
`preexec_fn=os.setsid`, and `killpg` in the `TimeoutExpired` handler.

- Rejected: it closes the timeout orphan but **not** the signal orphan, which
  is the actual Gate-1 finding (fact 6). `subprocess.run()` kills only the
  direct child when an exception unwinds through it, and
  `OperationInterrupted` is raised from a signal handler *inside* the wait, so
  the group is never signalled. `preexec_fn` is also documented as unsafe in
  the presence of threads, where `start_new_session=True` is the supported
  spelling of the same thing.

### Axis B — the eligibility check

**B1 — two Git plumbing calls compared by digest. (recommended)**

Evaluated **in the child, immediately before execution**:

1. `git -C <child> ls-tree -z <anchor> -- .agent-fork/worktree-setup.sh`
   → zero entries means `untracked`; a mode of `120000` (symlink) or `160000`
   (gitlink) means `not_a_regular_blob`; otherwise keep the blob OID.
2. `git -C <child> cat-file blob <oid>` → the committed bytes.
3. `Path.lstat()` on the child's hook → a symlink or non-regular file means
   `not_a_regular_blob`.
4. `hashlib.sha256` of the committed bytes versus `sha256` of the child's
   on-disk bytes → unequal means `modified`; equal means `eligible`.

Why the *child* and not the parent: `materialize()` carries the parent's
staged, unstaged, and untracked state into the new worktree. A parent-side-only
check would pass on the committed copy while the child executes a modified
one. Checking the file that is about to be executed is the only version of this
check that means anything.

Why digest comparison and not `git hash-object`: `hash-object` on a path
applies the path's clean filter and text conversion, so a repository with a
filter on `.agent-fork/**` could make differing bytes hash equal. Comparing raw
committed bytes to raw on-disk bytes has no such escape.

Why not `100755`-only eligibility: a committed-but-non-executable hook is
already covered by `T-INC-04`, which asserts the `setup hook failed to start`
notice. Folding executability into eligibility would silently change that row's
meaning. Mode is reported in the structured result; it does not gate.

**B2 — reuse `content.py`'s `capture_state()` / `compare_states()` on the single hook path.**

- Rejected: `content.py` is inventory-shaped. `collect_inventory()` runs five
  Git commands to build the *set of carried paths*, and `capture_state()`
  walks the index and manifest for all of them. Restricting it to one path
  means constructing a synthetic `Inventory` and discarding almost all of the
  result. It also compares parent-to-child, which is not the question A12
  asks — A12 compares child-to-*anchor*.

**B3 — `git status --porcelain -- <hook>` emptiness as the clean test.**

- Rejected on this repository's own evidence. A1 (`P02-TS01`, CONFIRMED
  2026-08-16) demonstrated *status-preserving content divergence*: with
  `apply.whitespace=fix`, child bytes diverged while porcelain status stayed
  identical and verification reported `passed: true`. Using status as a
  byte-equality oracle is the exact mistake A1 exists to have corrected.

### Axis C — surfacing successful hook output

**C1 — bounded tails always in the structured result; human echo on failure, timeout, or `--debug`. (recommended)**

- Capture stdout and stderr separately (they already are separate pipes).
- Bound each to its **last 4096 bytes** before decoding, then run
  `escape_terminal_text()` (`text.py:23`) over the result. The hook's output is
  repository-controlled and directly attacker-chosen — that is the premise of
  `T-INC-07` — so the success path needs the same escaping the failure path
  already has.
- Record `stdout_bytes` / `stderr_bytes` totals and a `truncated` flag so a
  consumer can see that a bound was applied rather than inferring it.
- Human mode prints a one-line status always; it echoes the tails to stderr
  only when the hook failed, timed out, or `--debug` is set.
- 4096 bytes is chosen as large enough for a realistic dependency-install
  failure and small enough to keep a single JSON line manageable. The existing
  house precedent for bounded detail is `verify.DETAIL_LIMIT = 5`, which bounds
  *items*; bytes are the right unit for a free-form stream.

**C2 — a new `--verbose` flag gating the echo in both modes.**

- Rejected: a machine consumer cannot be expected to pass an extra flag to get
  a field it needs, and a bounded field costs nothing when the hook is quiet.
  `--debug` already exists (`cli.py:67`) and already means "include debugging
  diagnostics", so C1 reuses it rather than adding a near-synonym.

**C3 — spool full output to a file under `XDG_STATE_HOME` and print the path.**

- Rejected for v1: it creates a new artifact class with no lifecycle, no
  cleanup path, and a new leak surface (a hook that prints a token would write
  it to disk). Worth reconsidering only if a real hook's output routinely
  exceeds the bound.

### Recommended combination

| Axis | Choice | One-line rationale |
|---|---|---|
| A | **A1** | Same shape as `run_git`; closes both the timeout orphan and the signal orphan; smallest diff that is actually correct |
| B | **B1** | Compares the bytes that will execute against the bytes that were committed, immune to filters and to the status oracle A1 disproved |
| C | **C1** | Output is never discarded, never unbounded, always escaped, and needs no new flag |

---

## Contracts

### Policy resolution

```
mode    := resolved.setup_hook_policy   # "tracked" | "any" | "off"
timeout := resolved.setup_hook_timeout  # seconds, > 0
```

| `setup_hook_policy` | Hook present | Eligible | Outcome |
|---|---|---|---|
| `off` | any | any | `status="disabled"`, never executed, eligibility not evaluated |
| `tracked` or `any` | no | — | `status="absent"` |
| `tracked` or `any` | yes | yes | `status="ran"` |
| `tracked` | yes | no | `status="skipped"`, `reason` names the eligibility failure |
| `any` | yes | no | `status="ran"`, eligibility reported as observed |

`off` dominates: disabled means disabled. Under `any`, eligibility is still
*reported* even though the hook runs, so the structured result never hides
that unreviewed code ran.

**Owner decision (2026-08-20):** the plan originally proposed two paired
boolean flags (`--setup-hook`/`--no-setup-hook` and
`--allow-unreviewed-setup-hook`), following this repository's `--verify`/
`--no-verify` convention. The owner chose the single three-way enum below
instead. One consequence: the literal `--no-setup-hook` spelling named in
A12's original register entry (`projects/P02-agent-fork-fault-remediation.md:326-334`)
no longer exists as its own flag — the equivalent is
`--setup-hook-policy off`. `REQUIREMENTS.md`/`README.md` updates in Step 6
must use the enum spelling, not the register's original literal text.

### Flags and configuration keys

| Flag | argparse form | `[fork]` key | Type | Default |
|---|---|---|---|---|
| `--setup-hook-policy {tracked,any,off}` | `choices=[...]`, `default=None` | `setup_hook_policy` | str enum | `tracked` |
| `--setup-hook-timeout SECONDS` | `type=int`, `default=None` | `setup_hook_timeout` | int (seconds) | `300` |

Config plumbing:

- `setup_hook_policy` joins `_FORK_KEYS` and needs a new
  `_ENUM_KEYS = {"setup_hook_policy": ("tracked", "any", "off")}`, validated
  by membership. A value outside the three literals raises `ConfigError`
  (exit 2) — same A11-guard reasoning as the timeout key below: a key that
  passes `config validate` and later crashes `fork` is exactly the A11
  pattern this design must not repeat.
- `setup_hook_timeout` joins `_FORK_KEYS` and needs a new
  `_INT_KEYS = {"setup_hook_timeout"}` validated as a positive `int` — note
  that `isinstance(True, int)` is true in Python, so the check must reject
  `bool` explicitly. A value `<= 0` raises `ConfigError` (exit 2). There is
  deliberately **no** "no timeout" sentinel: an unbounded hook is the fault
  A12 exists to close.
- `ConfigValues` and `ResolvedConfig` (`models.py`) gain the two fields;
  `resolve_config()` gains two assignment blocks.
- `set_user_value()` gains int coercion so `config set setup_hook_timeout 300`
  round-trips, and enum-membership validation so
  `config set setup_hook_policy tracked` round-trips while
  `config set setup_hook_policy nonsense` fails at validate time, not at
  `fork` time.

### `SetupHookResult`

```python
@dataclass(frozen=True)
class SetupHookResult:
    path: str                    # always ".agent-fork/worktree-setup.sh"
    present: bool
    policy: str                  # "tracked" | "any" | "off" — the resolved policy in effect
    eligibility: str             # "eligible" | "untracked" | "modified"
                                 #  | "not_a_regular_blob" | "absent" | "unchecked"
    status: str                  # "ran" | "skipped" | "disabled" | "absent"
                                 #  | "failed_to_start"
    reason: str | None           # populated for "skipped" and "failed_to_start"
    exit_code: int | None        # None unless status == "ran"
    timed_out: bool
    descendants_cleared: bool    # False when the hook outlived itself
    duration_seconds: float | None
    timeout_seconds: int
    stdout_tail: str             # escaped, bounded
    stderr_tail: str             # escaped, bounded
    stdout_bytes: int            # pre-bound totals
    stderr_bytes: int
    truncated: bool
    notices: tuple[str, ...]
```

`eligibility == "unchecked"` occurs only when the override is on *and* the Git
plumbing could not answer (no anchor, or the path is not inside a worktree). It
is a reporting state, never a way to run a hook that policy would skip.

### Function signature

```python
def run_setup_hook(
    repo_root: Path,
    child: Path,
    *,
    anchor: str,
    policy: SetupHookPolicy,
    env: Mapping[str, str] | None = None,
) -> SetupHookResult:
```

The two positional parameters are unchanged so the diff at the call sites stays
readable. The return type changes from `tuple[str, ...]` to
`SetupHookResult`; the failure-notice strings inside `.notices` stay
**byte-identical** so `T-INC-04`'s assertion
(`"setup hook failed (exit 17): deliberate"`) and `T-INC-07`'s escaping
assertion survive with only a `.notices` attribute access added.

`pipeline.fork()` passes `anchor=creation.anchor`, builds `SetupHookPolicy`
from the resolved config, and carries the result out on a new
`ForkResult.setup_hook` field. The normative pipeline order is unchanged.

### Execution and reaping

```python
process = subprocess.Popen(
    [str(hook)],
    cwd=child,
    env=environment,
    stdin=subprocess.DEVNULL,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    start_new_session=True,
)
```

`stdin=subprocess.DEVNULL` is a deliberate behavior change, and it follows from
`start_new_session=True`: a new session has no controlling terminal, so a hook
that reads the inherited TTY would block or take a `SIGTTIN` rather than fail
cleanly. `DEVNULL` gives it a defined EOF instead. This is recorded in
"Known limits" as a compatibility note.

**Amended 2026-08-20 (gate-6 review, both lenses).** The ladder and the timeout
path below are the corrected versions. What the first implementation shipped —
and what an earlier revision of this section specified — decided cleanup from
*the leader's exit status*, and two independent reviews falsified that premise
from opposite ends. The rule the corrected code follows is: **a process group
can still hold live members after its leader is gone, so every decision is made
about the group, never about the leader.**

**Amended 2026-08-21 (gate-6 round 3).** Every signalling path now goes through
one `_HookGroup` record — the `Popen` plus an `emptied` latch — instead of
through the bare `Popen`. `_group_is_empty()` sets the latch the first time the
group answers `ESRCH`, reads it before probing, and `_signal_hook_group()`
returns without signalling whenever it is set. Emptiness is therefore terminal:
once observed, that PID is never signalled again by anything.

Reap ladder, used identically on the timeout path and the signal path:

1. `_signal_hook_group(group, SIGTERM)` — probes first, so an already-empty
   group is never signalled
2. probe the group for up to 1 s — a live leader is "not empty" with no syscall
   at all, and once it has been reaped `killpg(pgid, 0)` answering `ESRCH`
   means empty and latches `group.emptied`
3. still populated: `_signal_hook_group(group, SIGKILL)`
4. probe again for up to 1 s
5. still populated: give up and append a notice naming the PID — cleanup stays
   best-effort so the original interruption remains observable.

Two deliberate divergences from `git.py:117-127`, both required:

- **The escalation is gated on the group being empty, not on
  `process.wait()`.** `wait()` returns the moment the hook's own shell exits,
  which skipped the SIGKILL its surviving children still needed.
- **`include` has its own `_signal_hook_group()` rather than reusing
  `git.signal_process_group()`.** The Git helper returns *before* `killpg`
  whenever `process.poll()` shows the leader exited. That gate is right for
  Git, whose children do not outlive it, and wrong for a hook, where the
  survivors are the entire point. Addressing the group by the leader's pid is
  safe after the leader has been reaped *for as long as the group holds a
  member* — the kernel reserves the pid as the group id for exactly that long.
  It is **not** safe afterwards: an emptied group's pid is free for the kernel
  to hand to an unrelated process, which is why emptiness latches and no
  further signal is issued once it has (`T-INC-18`). A live leader does not
  shortcut the `killpg(pgid, 0)` probe either — round 4 tried that and it was
  wrong (see the round-5 correction below); `T-INC-21` now pins the probe
  running unconditionally, live leader or not. The latch and the always-run
  probe do not make the check-and-signal pair one atomic step; Known limit 9
  states what is left. `git.py` is unchanged, and `T-RBK-07` still pins its
  behavior.

Execution path — two bounds, because a pipe outlives its writer's parent:

```python
stdout, stderr, outcome = _collect_output(
    process,
    leader_deadline=started + policy.timeout_seconds,
    drain_seconds=SETUP_HOOK_DRAIN_SECONDS,   # 2.0
)
if outcome == "timed_out":
    timed_out = True
    reap_notices = _reap(group)
    stdout, stderr, outcome = _collect_output(   # bounded drain, never open-ended
        process, leader_deadline=time.monotonic(), drain_seconds=SETUP_HOOK_DRAIN_SECONDS
    )
if outcome == "detached":
    _abandon_pipes(process)
descendants_cleared = outcome != "detached" and _group_is_empty(group)
```

`leader_deadline` bounds how long the hook's own process may run;
`drain_seconds` separately bounds how long its pipes may stay open *after* that
process exits. `_collect_output()` re-calls `communicate(timeout=...)` in short
slices — the documented retry pattern, where the buffers accumulate across calls
and `TimeoutExpired` carries what has been read so far — and reports one of
three outcomes:

| Outcome | Meaning | Result |
|---|---|---|
| `completed` | both pipes reached EOF | the hook's own exit code decides ok/failed |
| `timed_out` | the hook itself was still running at `leader_deadline` | `timed_out=True`, group reaped, then a bounded drain |
| `detached` | the hook exited but its output stayed open past `drain_seconds` | pipes released, `descendants_cleared=False` |

Keeping the two bounds separate is what fixes two defects the single
`communicate(timeout=...)` produced. A hook that backgrounds a daemon and exits
in milliseconds was reported `timed_out: true` — measured at 121 s of wall clock
for a hook whose shell exited immediately — because "the pipes are still open"
was read as "the hook is still running". And the follow-up drain was
unbounded on the false premise quoted above: *"the second `communicate()` cannot
hang: every process that could still hold the pipe write end was in the group
and has been `SIGKILL`ed."* A process that calls `setsid()` is no longer in the
group, was never signalled, and holds the write end for as long as it likes, so
that drain hung forever.

**The honest limit, stated rather than papered over.** A descendant that leaves
the process group cannot be killed with it — that is Unix, not a defect, and no
amount of ladder fixes it. What A12 owes is a bound and a true report, so:
agent-fork stops waiting, releases the pipes, reports the hook's own exit code,
and sets `descendants_cleared=False` with a notice. It does **not** kill
leftovers on the success path; a hook that deliberately starts a background
process is a legitimate pattern, and the timeout is the only place this step is
licensed to kill anything.

A timeout yields `status="ran"`, `timed_out=True`, and a non-fatal notice —
**the fork still succeeds**, because a timeout is a hook problem, not a
worktree problem, and the settled constraints say the timeout cannot undo what
the hook already did.

Signal path: `rollback.interrupt()` fires inside `communicate()`, calls both
`terminate_active_git()` and `terminate_active_setup_hook()`, and raises
`OperationInterrupted`. `run_setup_hook()` wraps `communicate()` in
`except BaseException: _reap(group); raise` with a `finally` that clears the
active slot — again the `run_git` shape. `terminate_active_setup_hook()` is
load-bearing on its own, not merely the early half of the ladder: when the
hook's own shell has already exited, `run_setup_hook()` can be past its ladder
while group members it left behind are still running, and this call is what
reaches them (`T-RBK-10`).

**The `Popen`-to-registration window is closed by blocking the handled
signals** (amended 2026-08-21, gate-6 round 3). `process = Popen(...)`
evaluates the spawn before binding the name, and CPython runs signal handlers
between bytecodes, so a handler firing in that gap finds a running hook
registered nowhere — reachable by neither `rollback.interrupt()` nor the reap
ladder. An earlier revision of this section claimed that enclosing the gap in
the reap-protected `try` closed it and that "no OS-level signal blocking is
involved"; both were wrong. Enclosure does not help, because the `except
BaseException` handler reaps the local `process`, which is exactly the name
that is not yet bound.

What closes it:

```python
restore_mask = signal.pthread_sigmask(signal.SIG_BLOCK, _HANDLED_SIGNALS)
try:
    process = subprocess.Popen(..., preexec_fn=<restore the child's mask>)
    ...
    _ACTIVE.group = _HookGroup(process)
finally:
    signal.pthread_sigmask(signal.SIG_SETMASK, restore_mask)
```

`_HANDLED_SIGNALS` is exactly `{SIGINT, SIGTERM}`, the pair
`run_with_rollback()` handles. A signal arriving anywhere in the critical
section stays pending until `SIG_SETMASK` restores the caller's own mask — one
bytecode after the registration, and still inside the `except BaseException`
block, so the deferred delivery lands on the reap path with the group
registered. `SIG_SETMASK` with the saved mask rather than `SIG_UNBLOCK`: a
caller who already had these signals blocked gets them back blocked.
`pthread_sigmask` is available on both supported platforms (macOS, Linux).

The `preexec_fn` is required, not decorative: a signal mask is inherited across
fork and survives exec (verified on CPython 3.13, macOS), so without it the
hook would run with SIGINT and SIGTERM blocked — the reap ladder's SIGTERM
would never be deliverable and only the SIGKILL escalation would work
(`T-INC-20`). Its documented hazard is other threads holding locks at fork
time, and hooks are spawned from a single-threaded CLI. `git.py` has the
unprotected shape; that is pre-existing and out of scope for A12.
`run_with_rollback()` then rolls back
and re-raises. Because the group is reaped *before* rollback, nothing is still
writing into the directory being removed, which is precisely the ordering that
produced the PID-1 orphan in Gate-1 fact 6.

### Interrupt exit codes

Three ways to give `main()` a `130`/`143` path were considered. The constraint
that decides it is `T-OUT-14`
(`tests/cli/test_out.py:455-482`), which parses every `src/agent_fork/*.py`
file and asserts that the set of `code = "<literal>"` class attributes equals
`set(ERROR_CATALOG)` exactly. A catalog entry without a class fails it, and a
class without an entry fails it.

| Option | Shape | Verdict |
|---|---|---|
| **I-a** | One catalog code `interrupted` at `ErrorSpec(130, ...)`, one class, and a per-instance `exit_code` of `143` for `SIGTERM` | Rejected: silently breaks the catalog's one-code-one-exit-code invariant |
| **I-b** | No catalog change; an ad-hoc `render_interrupt()` emitting a non-catalog `interrupted` code | Rejected: publishes a machine code that `STABLE_ERROR_CODES` does not list, so consumers cannot enumerate it |
| **I-c** | Two codes, two classes, strict 1:1 | **Recommended** |

I-c, concretely:

```python
# errors.py
"interrupted_sigint":  ErrorSpec(130, "interrupted by SIGINT after rollback"),
"interrupted_sigterm": ErrorSpec(143, "interrupted by SIGTERM after rollback"),
```

with two `AgentForkError` subclasses carrying those codes. `main()` gains, ahead
of the existing `except Exception` clause:

```python
except OperationInterrupted as error:
    translated = INTERRUPT_ERRORS[error.signum]("interrupted after rollback")
    print(render_error(translated, machine=machine), file=sys.stderr)
    return translated.exit_code
```

`OperationInterrupted` itself stays a `BaseException` so pipeline-internal
`except Exception` handlers (`pipeline.py:181`) still cannot swallow it.

For completeness outside the `run_with_rollback()` window — during preflight,
naming, or dry-run, where no worktree exists to roll back — `main()` also
catches `KeyboardInterrupt` and returns `130` without a traceback. `SIGTERM`
there retains its default disposition, which already yields `143` at the shell.

README's exit-code table gains the two codes on its existing `130 / 143` row,
which currently reads `—`.

### `fork` output

Human (`text` and `table`), on **stderr**, so stdout stays the paste-command
surface:

```
setup hook: running .agent-fork/worktree-setup.sh (timeout 300s)
setup hook: ok in 0.42s
```

and the other terminal lines:

```
setup hook: failed (exit 17) in 0.31s; fork kept
setup hook: timed out after 300s; process group terminated. Changes it already made are not undone
setup hook: skipped — present but not committed at the fork anchor (run it anyway with --setup-hook-policy any)
setup hook: skipped — present but modified since the fork anchor (run it anyway with --setup-hook-policy any)
setup hook: disabled (--setup-hook-policy off)
```

The running line is emitted through a new optional
`ForkRequest.progress: Callable[[str], None] | None = None`. `_fork_cli()`
supplies a closure writing to `sys.stderr`; library callers get silence by
default. Rendering stays in the CLI layer, which is why the callback is
preferred over printing from `include.py`.

**In `--json` mode the progress line is suppressed entirely.** In machine mode
stderr is reserved for exactly one JSON error object
(`README.md:542`, `render_error(machine=True)`); interleaving plain progress
text would break a consumer that parses stderr as JSON.

The success status is **not** appended to `ForkResult.notices`. Notices are
rendered into stdout by `output.py:79` *and* reprinted on stderr by
`cli.py:624-625` — the A13(a) duplicate-notice defect, tracked as
`P02-T13ABF`. Adding a success notice would double-print through it. Failure,
timeout, and skip reasons stay in `notices` for backward compatibility.

`ForkOutput.document()` gains one additive top-level key, always present:

```json
"setup_hook": {
  "path": ".agent-fork/worktree-setup.sh",
  "present": true,
  "policy": "tracked",
  "eligibility": "eligible",
  "status": "ran",
  "reason": null,
  "exit_code": 0,
  "timed_out": false,
  "descendants_cleared": true,
  "duration_seconds": 0.418,
  "timeout_seconds": 300,
  "output": {
    "stdout": "installed 42 packages\n",
    "stderr": "",
    "stdout_bytes": 22,
    "stderr_bytes": 0,
    "truncated": false
  }
}
```

Absent hook:

```json
"setup_hook": {"path": ".agent-fork/worktree-setup.sh", "present": false,
               "policy": "tracked", "eligibility": "absent", "status": "absent",
               "reason": null, "exit_code": null, "timed_out": false,
               "descendants_cleared": true,
               "duration_seconds": null, "timeout_seconds": 300,
               "output": {"stdout": "", "stderr": "", "stdout_bytes": 0,
                          "stderr_bytes": 0, "truncated": false}}
```

Emitting the object unconditionally gives consumers one stable shape, matching
A9's additive-object precedent for `agent_signal`. `json_line()` sorts keys, so
field order is automatic.

### `fork --dry-run` disclosure

Dry-run evaluates the same predicate **parent-side**, against the anchor that
`resolve_anchor()` returns and the parent's working-tree copy. That is a
*prediction* of the child state, because `materialize()` has not run yet; the
document says so with a `prediction: true` field rather than implying certainty.

Human, one line added to `DryRunOutput.render()`:

```
setup-hook: .agent-fork/worktree-setup.sh; eligible at anchor; would run; timeout 300s
setup-hook: .agent-fork/worktree-setup.sh; not committed at anchor; would skip; override --setup-hook-policy any
setup-hook: none
setup-hook: disabled (--setup-hook-policy off)
```

JSON, nested under the existing `plan` object so the dry-run schema keeps its
shape:

```json
"plan": {
  "branch": {"...": "unchanged"},
  "worktree": {"...": "unchanged"},
  "files_to_carry": {"...": "unchanged"},
  "setup_hook": {
    "path": ".agent-fork/worktree-setup.sh",
    "present": true,
    "policy": "tracked",
    "eligibility": "eligible",
    "would_run": true,
    "reason": null,
    "timeout_seconds": 300,
    "prediction": true
  }
}
```

`mutation_performed: false` still holds: eligibility runs `ls-tree` and
`cat-file`, both read-only plumbing.

### `doctor` disclosure

One additional `DoctorCheck`, which needs no JSON schema change because
`doctor` already emits `checks[]` of `{name, ok, detail}` (`cli.py:710-724`):

```
ok    repository setup hook: .agent-fork/worktree-setup.sh present, eligible at HEAD, policy=tracked, timeout=300s
FAIL  repository setup hook: .agent-fork/worktree-setup.sh present, modified since HEAD (blocked under policy=tracked; override --setup-hook-policy any)
ok    repository setup hook: .agent-fork/worktree-setup.sh present, modified since HEAD (allowed to run under policy=any)
ok    repository setup hook: none in /path/to/repo
ok    repository setup hook: disabled by config
```

**Owner decision (2026-08-20): the check fails.** The plan originally
recommended an informational-only check (`ok` always `true`), reasoning that
every existing `doctor` failure is *machine readiness*, not a repository's
working-tree state, and that failing here would make `doctor` exit nonzero in
any worktree where someone is mid-edit on the hook. The owner chose to treat
a present-but-ineligible hook as a hard failure instead. This changes what
`doctor`'s exit code has meant so far — it now also signals a
repository-content problem, not only a machine-readiness one — so this
distinction must be called out explicitly in `README.md`'s `doctor`
documentation (Step 6) rather than left implicit.

`ok` is `false` **only** when `setup_hook_policy` is `tracked` (the default)
and a present hook fails the eligibility check — the same condition that
makes `fork` skip the hook. It stays `true` when the hook is eligible, when
`setup_hook_policy` is `any` (an ineligible hook is explicitly allowed to run,
so it is not a failure), when `setup_hook_policy` is `off` (the hook is not
evaluated), and when no hook is present at all.

`doctor` evaluates against `HEAD` in the cwd's worktree, and the detail says
`HEAD` explicitly, because `fork` resolves its own anchor
(`repository.resolve_anchor()`) which can differ — notably on a detached HEAD.

### CLI Design Standard 1.4.14 review scope

| Rule | A12 requirement |
|---|---|
| R5.x flags | `--setup-hook-policy` uses `choices=[...]` with `default=None`, so an unset flag falls through to config/default rather than forcing a value; the integer `--setup-hook-timeout` flag names its unit (seconds) in `--help` |
| R6.1 | `130` / `143` become reachable process exit codes from `main()`; `config_error` (2) covers an invalid timeout |
| R7.1, R7.6 | Progress and hook diagnostics on stderr; the fork result and the JSON line on stdout |
| R7.2, R9.3 | `setup_hook` is additive; no existing field changes meaning |
| R7.8 | Machine failures, including interrupts, remain exactly one JSON error object on stderr |
| R7.12 | `interrupted_sigint` and `interrupted_sigterm` are published stable codes |
| R8.6 | `--dry-run` performs no mutation while disclosing the hook |
| R9.10 | `doctor` names the exact reason a hook would not run and the exact override |
| R9.14 | Every new behavior gets a permanent matrix row |

Groups not affected and therefore N/A for this scoped review: command structure
and vocabulary, configuration *precedence* (unchanged — new keys ride the
existing chain), destructive-action confirmation, networked behavior,
streaming, plugins, and interactive setup.

---

## Test-driven implementation plan

Every production change follows a demonstrated failing test. New IDs are added
to `docs/testing/TEST-MATRIX.md` with tier and requirement source, and the
matrix's "Total rows" line is updated after the rows exist.

Numbering, per the matrix's own convention that IDs are never renumbered:
`T-INC-06` was never issued and the gap stays — new include rows start at
**`T-INC-08`**. `T-RBK-07` is taken, so new rollback rows start at
**`T-RBK-08`**. New CLI rows start at **`T-CLI-32`**, new output-contract rows
at **`T-OUT-23`**, and new config rows at **`T-CFG-18`**.

### Step 1 — RED: eligibility and policy, `tests/pipeline/test_inc.py`

Tier F (a real repository fixture is required — this is Git plumbing).

| Test ID | Required proof |
|---|---|
| `T-INC-08` | A hook committed at the anchor and unchanged on disk runs; `SetupHookResult.eligibility == "eligible"`, `status == "ran"`, `exit_code == 0` |
| `T-INC-09` | An **untracked** hook carried into the child is skipped by default: the hook's sentinel file does not exist, `eligibility == "untracked"`, `status == "skipped"`, and the notice names the override flag. This is the direct Gate-1 fact-1 regression |
| `T-INC-10` | A committed hook **modified** in the parent working tree is carried into the child and skipped: `eligibility == "modified"`. Asserted by byte comparison, not by `git status`, per Axis B |
| `T-INC-11` | With `policy="any"`, both the untracked and the modified hook run, and `eligibility` still reports `"untracked"` / `"modified"` rather than being masked |
| `T-INC-12` | A hook recorded in the anchor tree as a symlink (`120000`), and separately a hook that is a symlink on disk, are both `not_a_regular_blob` and are skipped |
| `T-INC-13` | Policy disabled: eligibility is never evaluated, no process is spawned (assert the sentinel is absent), `status == "disabled"` |
| `T-INC-14` | Successful stdout and stderr reach `stdout_tail` / `stderr_tail`; a hook printing more than the bound sets `truncated: true` and the byte totals exceed the tail lengths. This is Gate-1 fact 3 |
| `T-INC-15` | Success-path output is escaped: a hook printing `ESC[2J` on **stdout with exit 0** renders safely, extending `T-INC-07`'s guarantee from the failure path to the success path |

`T-INC-04` and `T-INC-07` change mechanically only: `T-INC-04` reads
`result.setup_hook.notices` instead of scanning `result.notices` (the notice
strings themselves are unchanged, which is the point of the assertion), and
`T-INC-07` passes `policy=SetupHookPolicy(mode="any", timeout_seconds=300)` so its bare
`tmp_path` child needs no anchor. Its escaping assertion is untouched.
`T-INC-03` and `T-INC-05` need the hook committed, which `_commit_support()`
(`tests/pipeline/test_inc.py:17-26`) already does, so they stay green
unmodified — worth confirming explicitly in the RED run.

### Step 2 — GREEN: `include.py`, `git.py`, `rollback.py`, `pipeline.py`

1. `git.py`: rename `_signal_process_group` → `signal_process_group`, docstring
   unchanged; update the two internal call sites.
2. `include.py`: add `SetupHookPolicy`, `SetupHookResult`, `_ACTIVE`,
   `terminate_active_setup_hook()`, `_eligibility()`, the reap ladder, and the
   new `run_setup_hook()` body.
3. `rollback.py`: `interrupt()` calls both terminators.
4. `pipeline.py`: pass `anchor`, `policy`, and `progress`; carry
   `SetupHookResult` on `ForkResult`.

### Step 3 — RED then GREEN: timeout and signal reaping

Tier F, marked `requires_process_group_signals`, so they run under
`just test-signals` and are excluded from `just all` — the same gate
`T-RBK-03`/`T-RBK-04` use.

| Test ID | File | Required proof |
|---|---|---|
| `T-INC-16` | `tests/pipeline/test_inc.py` | A hook that sleeps past a short configured timeout is killed; the fork **succeeds**; `timed_out: true`; and the hook's own long-lived grandchild is gone. Prove the grandchild by having the hook write its background child's PID to a file and asserting the PID is unkillable afterwards. This is Gate-1 fact 2 |
| `T-RBK-08` | `tests/pipeline/test_rbk.py` | `SIGINT` delivered while the hook is running exits `130`, rolls the worktree back, and leaves **no** surviving process from the hook's group. This is Gate-1 fact 6, the PID-1 orphan |
| `T-RBK-09` | `tests/pipeline/test_rbk.py` | Same for `SIGTERM` → `143` |

`T-RBK-08`/`T-RBK-09` use `T-RBK-03`'s harness shape
(`tests/pipeline/test_rbk.py:133-163`): `os.fork()` a worker, wait for a
readiness sentinel the hook writes, signal the worker, `waitpid`, and assert
`os.waitstatus_to_exitcode(status)`. The orphan assertion is the new part —
read the grandchild PID from the sentinel file and assert it no longer exists.

### Step 4 — RED then GREEN: CLI exit codes, dry-run, doctor, JSON

| Test ID | File | Required proof |
|---|---|---|
| `T-CLI-32` | `tests/cli/test_cli.py` | `fork --dry-run` human and JSON disclose the hook for all four states (eligible, ineligible, absent, disabled), the JSON carries `prediction: true`, `mutation_performed` stays `false`, and no branch or worktree is created |
| `T-CLI-33` | `tests/cli/test_cli.py` | `doctor` human and JSON carry the `repository setup hook` row for all five states (eligible, ineligible-under-`tracked`, ineligible-but-allowed-under-`any`, absent, disabled); the row's `ok` is `false` only for the ineligible-under-`tracked` state, and `doctor`'s overall exit code goes nonzero in that state alone |
| `T-OUT-23` | `tests/cli/test_out.py` | `fork --json` stdout is exactly one parseable line containing the full `setup_hook` object with **no** progress text; the same fork in `text` mode prints the running and result lines to stderr and leaves stdout byte-identical to today's |
| `T-CLI-34` | `tests/cli/test_cli.py` | `main()` under a real `SIGINT` during the hook returns `130` and prints a rendered error, not a traceback; the `--json` variant prints exactly one JSON error object on stderr with code `interrupted_sigint`. Marked `requires_process_group_signals`. This is Gate-1 fact 7 and the missing CLI-boundary row |
| `T-OUT-24` | `tests/cli/test_out.py` | `interrupted_sigint` and `interrupted_sigterm` satisfy the existing catalog-exactness and JSON round-trip invariants (`T-OUT-14`, `T-OUT-15` stay green unmodified) |

### Step 5 — RED then GREEN: configuration

| Test ID | File | Required proof |
|---|---|---|
| `T-CFG-18` | `tests/unit/test_cfg.py` | The two keys default to `tracked` / `300`; an explicit `--setup-hook-policy` flag beats a config value; `--setup-hook-policy off` dominates every other setting |
| `T-CFG-19` | `tests/cli/test_cfg.py` | `config set` / `config get` round-trip both keys, including integer coercion for `setup_hook_timeout` and enum-membership validation for `setup_hook_policy` |
| `T-CFG-20` | `tests/unit/test_cfg.py` | `setup_hook_timeout = 0`, a negative value, a string, and a boolean each raise `ConfigError`; `setup_hook_policy` set to a value outside `{tracked, any, off}` also raises `ConfigError`; the CLI exits `2` in every case. Directly guards against repeating the A11 pattern of a key that validates clean and crashes at use |

### Step 6 — Documentation and conformance

Proposed edits, all outside this document and none of them made by it:

- `README.md` — three rows in the `fork` flag table, three rows in the
  `[fork]` config table, the two interrupt codes on the existing `130 / 143`
  row, and a rewrite of the two-sentence "Repository hooks" section
  (`README.md:502-506`) covering the eligibility rule, the timeout, and the
  explicit statement that a timeout does not undo the hook's side effects;
- `REQUIREMENTS.md` — amend `REQ-24` to record that the hook is
  provenance-gated, bounded, and opt-outable while remaining non-fatal;
  `REQ-22` needs no change, since A12 implements what it already says;
- `CONFORMANCE.md` — refresh the `REQ-24` evidence row and add one CLI
  Standard 1.4.14 review-history row; no new waiver expected;
- `DESIGN-DECISIONS.md` — a new `D22 — Repository setup-hook execution policy`
  (next free number after `D21`) recording the default-tracked rule, the
  skip-not-refuse choice, and the timeout default, since those are policy
  decisions a future reader will otherwise have to re-derive. Proposed here;
  written only if the owner approves;
- `docs/testing/TEST-MATRIX.md` — all nineteen new rows (`T-INC-08` through
  `T-INC-16`, `T-RBK-08`, `T-RBK-09`, `T-CLI-32` through `T-CLI-34`,
  `T-OUT-23`, `T-OUT-24`, and `T-CFG-18` through `T-CFG-20`), plus the
  `Total rows:` count, which moves from 404 to 423.

### Step 7 — Gates and review

```bash
just all
just test-signals      # T-RBK-08, T-RBK-09, T-INC-16, T-CLI-34
just check-matrix
just strict-collect
just clean-install
```

Then an adversarial implementation review and an independent Codex second lens
against the complete A12 diff. Absorb only findings this design promises or
A12 introduces; route the rest under P02 Gate 6.

---

## Known limits

Stated so no reviewer mistakes them for oversights.

1. **A timeout does not undo the hook's work.** Settled constraint 1. The
   timeout message says this in words.
2. **Tracked is not safe.** Settled constraint 2. A malicious committed hook
   runs exactly as before. The gate stops *new, unreviewed* code from executing
   on the next fork; it does not evaluate what the code does.
3. **The eligibility check is read-then-execute.** A racing writer could swap
   the file between the digest comparison and `Popen`. The window is inside a
   directory agent-fork created moments earlier, and closing it would need an
   `O_EXEC`-style handle Python does not portably expose. This belongs to the
   A8 TOCTOU family and should be reconciled there, not solved here.
4. **The hook's environment is still inherited.** Out of scope, per A2's named
   gap (issue #38).
5. **Output is buffered whole before it is bounded.** `communicate()` holds the
   full stream in memory; the 4096-byte bound is applied afterwards. A hook
   printing gigabytes can still exhaust memory. This is true of the current
   code as well, so A12 does not regress it, but it is a real ceiling that a
   streaming reader would remove.
6. **`stdin` becomes `/dev/null`.** A hook that today prompts interactively
   will now read EOF instead of the user's terminal. This follows from running
   in a new session and is the correct behavior for an unattended post-fork
   step, but it is a behavior change worth a README line.
7. **`doctor` reads `HEAD`, `fork` resolves its own anchor.** On a detached
   HEAD the two can differ. The doctor detail names `HEAD` so the user is not
   misled.
8. **A descendant that leaves the process group cannot be terminated with it.**
   `start_new_session=True` bounds everything the hook starts *and keeps in its
   group*; a child that calls `setsid()` is in a different group, and `killpg`
   by construction cannot reach it. Nothing agent-fork can do changes that —
   the same shape of limit as "a timeout cannot undo side effects". What A12
   guarantees instead is that such a process cannot make the fork hang: waiting
   for the hook's output is bounded, the pipes are released, and
   `descendants_cleared: false` plus a notice reports what was left behind.
   Added 2026-08-20 from the gate-6 review.
9. **Signalling a process group by pid is not atomic with checking that the pid
   is still the hook's.** Four rounds of review narrowed this; none closed it,
   and round 4's attempt to narrow it further was itself wrong and was reverted
   in round 5 (below) rather than shipped. What holds today: `_group_is_empty()`
   always issues a `killpg(pgid, 0)` probe — including when the leader is still
   alive — because that probe is the function's only actual source of proof.
   Round 4 tried skipping it whenever `Popen.poll()` returned `None`, reasoning
   that a session leader cannot leave its own group, so an unreaped child
   provably pins its pid. That reasoning missed a second, CPython-documented
   meaning of `poll() is None`: status unknown because a concurrent `waitpid`
   already holds the process's internal lock, which a signal handler
   re-entering this same process during another `communicate()`/`poll()` call
   can genuinely produce. Treating every `None` as "leader confirmed alive" was
   therefore a false safety claim, not a narrower race, and round 5 reverted it
   — `_group_is_empty()` now matches round 3's shape. What remains, honestly:
   while the group holds any member the kernel keeps its leader's pid reserved
   as the group id, so the probe's answer is trustworthy; and once the group
   has been *seen* empty, the latch retires the pid and no path signals it
   again (`T-INC-18`). Between those two states — after `process.poll()` has
   reaped the leader and released its pid, and before the probe's answer is
   acted on — `_group_is_empty()`'s `killpg(pgid, 0)` probe and the eventual
   `killpg(pgid, signum)` that acts on its answer are two separate syscalls
   with no atomicity between them. If the group empties in that span *and* the
   kernel recycles the pid *and* the new owner installs it as a process group
   id — all within a couple of adjacent syscalls — the signal reaches a
   stranger. Closing it needs a handle that names the process rather than its
   number: Linux has had `pidfd_open`/`pidfd_send_signal` since kernel 5.3 for
   signalling a single process, but process-group scope
   (`PIDFD_SIGNAL_PROCESS_GROUP`) did not arrive until kernel 6.9, and a pidfd
   opened against an already-reaped leader answers `ESRCH` regardless — so the
   5.3 primitive is not by itself a stable handle for the surviving-group case
   this limit describes. macOS has no equivalent at any kernel version, and
   agent-fork supports both platforms and depends only on `platformdirs`.
   Adding a dependency, or a Linux-only path gated to a kernel new enough to
   carry `PIDFD_SIGNAL_PROCESS_GROUP`, buys a narrower race on one platform at
   the cost of two code paths to reason about — the trade round 1 made and
   round 3 had to undo, and round 4 remade in a different, subtler form. Stated
   rather than claimed shut. Added 2026-08-21 from the gate-6 round-4 review;
   corrected 2026-08-21 in round 5 after an independent review found round 4's
   narrowing itself unsound.

---

## Owner decisions

Four items needed an owner decision. All four are now settled (2026-08-20).

1. **Timeout default — DECIDED: 300 seconds.** The plan had proposed 120 s;
   the owner chose 300 s, favoring tolerance for heavy dependency installs
   over catching a hang faster. Every `120` value in this document (contracts,
   examples, test rows) has been updated to `300`.
2. **Override flag shape — DECIDED: a single enum.** The plan had proposed
   paired booleans (`--allow-unreviewed-setup-hook` alongside
   `--setup-hook`/`--no-setup-hook`), matching this CLI's `--verify`/
   `--no-verify` convention. The owner chose the alternative instead: one flag,
   `--setup-hook-policy {tracked,any,off}`, with `[fork] setup_hook_policy`
   as its config-key twin. Consequence: the literal `--no-setup-hook` spelling
   A12's register entry names no longer exists as its own flag; the
   equivalent is `--setup-hook-policy off`. The Contracts section, `doctor`
   disclosure section, and Step 4/5 test rows have been updated to the enum
   shape throughout.
3. **Whether the success output tail is always in the JSON — DECIDED: yes.**
   The owner confirmed the plan's own recommendation: the bounded tail
   (4096 bytes per stream, option C1) is always present, so a machine
   consumer never needs to pass a flag to see a field it needs. No contract
   change follows from this decision — `SetupHookResult`, the `fork --json`
   examples, and `T-OUT-23` already reflect it as written.
4. **Whether `doctor` may fail on a present-but-ineligible hook — DECIDED:
   yes.** The plan had recommended informational-only (`ok` always `true`),
   reasoning that every existing `doctor` failure is machine readiness, not
   repository working-tree state, and that failing here would flag any
   worktree where someone is mid-edit on the hook. The owner chose to treat it
   as a hard failure instead. `ok` is `false` only when `setup_hook_policy` is
   `tracked` (the default) and a present hook is ineligible — the same
   condition that makes `fork` skip it; it is unaffected under `any` (the
   hook is explicitly allowed to run) or `off` (the hook is not evaluated).
   `README.md`'s `doctor` documentation (Step 6) must now note explicitly that
   `doctor`'s exit code can also signal a repository-content problem, not
   only a machine-readiness one.

---

## References

- Register entry: `projects/P02-agent-fork-fault-remediation.md` — A12 at lines
  326-334, `P02-TS12` verdict and `P02-T12` at lines 394-395
- Gate-1 handoff: `docs/handoffs/2026-08-17-p02-a7-a13-validation.md`
- Pipeline order: `docs/superpowers/specs/2026-08-08-test-architecture-design.md:105`
- Prior-art design docs followed for structure:
  `docs/superpowers/plans/2026-08-18-p02-a09-shared-agent-signal-assessment.md`,
  `docs/superpowers/plans/2026-08-17-p02-a4-recipe-flag-probe.md`
- Current implementation: `src/agent_fork/include.py:90-116`,
  `src/agent_fork/pipeline.py:150-153`, `src/agent_fork/rollback.py:19-42`,
  `src/agent_fork/git.py:50-78`, `src/agent_fork/cli.py:1257-1268`
- Contract text A12 closes: `REQUIREMENTS.md:132` (`REQ-22`),
  `REQUIREMENTS.md:134` (`REQ-24`), `README.md:526-527`

---

## Reevaluation against `origin/main` (2026-08-20)

This branch was rebased onto `origin/main` (`46201c1`, the `refactor/src-
duplication` merge, PR #53) — 31 commits landed since this plan's baseline.
The rebase applied cleanly with zero conflicts. This section is the result of
re-checking every load-bearing claim above against the post-rebase code and
docs; it revises citations and numbering only. **No finding below changes the
recommendation, the contracts, or the test plan's content.**

**The fault surface this plan targets is untouched.** The refactor's own
commit message lists its touched files (`agents.py`, `claude_lineage_
inference.py`, `cleanup.py`, `cli.py`, `completion.py`, `config.py`,
`lineage.py`, `lineage_inference_store.py`, `materialize.py`, `output.py`,
`registry.py`, `repository.py`) — `include.py` is not among them, and its
`run_setup_hook()` is byte-identical to the version this plan was written
against. `git.py`'s `_signal_process_group()` / `run_git()` process-group
pattern (the reuse target for Axis A) is unchanged. `rollback.py:19`'s
`OperationInterrupted(BaseException)` is unchanged. `cli.py`'s `main()` still
catches only `Exception`, so `OperationInterrupted` still escapes uncaught —
Gate-1 fact 7 (the REQ-22 130/143 conformance gap) is still real and still
open. A new regression test, `T-RBK-07`, landed in the interim for a related
but distinct mechanism (macOS `EPERM` on an already-exited process during
Git's own interrupted cleanup) — it does not cover the CLI-boundary gap this
plan closes, and its presence confirms the reused process-group pattern is
itself already trusted enough to have a dedicated regression test.

**Citation drift (cosmetic, not substantive).** A few line numbers moved with
the surrounding file's growth; the referenced code is unchanged in every case:
`cli.py`'s `except Exception` clause is now at line **1229** (was 1257);
`README.md`'s "Interrupts are handled" line is now **553** (was 526-527);
`output.py`'s `DryRunOutput` is now at line **97** (was ~84); `config.py`'s
`_FORK_KEYS` is now at line **22** (was ~21). These will self-correct during
Step 1's RED pass against current `HEAD` and are not worth a standalone edit
before then.

**Test-matrix ID collisions (mechanical, must fix before Step 1).** The matrix
grew from 404 rows at this plan's baseline to **441** today — other P02/P05
work (A13(b)'s output/completion-parity rows, the bidi-escaping regression,
the shared XDG resolver rows) claimed IDs in the ranges this plan reserved.
Confirmed by direct check of `docs/testing/TEST-MATRIX.md`:

| Prefix | Plan reserved | Now taken by unrelated rows | Actual next-free |
|---|---|---|---|
| `T-INC` | 08-16 | — (still free) | **08-16, unchanged** |
| `T-RBK` | 08-09 | — (still free) | **08-09, unchanged** |
| `T-CLI` | 32-34 | `T-CLI-32/33/34` (A13(b), completion parity) | **36-38** |
| `T-OUT` | 23-24 | `T-OUT-23` (bidi-escaping regression) | **24-25** |
| `T-CFG` | 18-20 | `T-CFG-18/19/20` (A13(b), XDG resolver) | **24-26** |

Renumber `T-CLI-32/33/34 → 36/37/38`, `T-OUT-23/24 → 24/25`, and
`T-CFG-18/19/20 → 24/25/26` when Step 1 actually adds rows to the matrix; the
`T-INC` and `T-RBK` reservations need no change. This is expected churn from
six P02 items having worktrees in flight concurrently, not a defect in this
plan.

**Finding outside this plan's scope, flagged for the owner.** The `P02-TS12`
CONFIRMED-WITH-CORRECTION verdict this plan's Gate-1 evidence section
reproduces verbatim was never committed to any branch —
`git log --all -S "P02-TS12" -- projects/P02-agent-fork-fault-remediation.md`
returns only the register's original creation commit. It existed solely as an
uncommitted edit in the live main checkout as of 2026-08-18 (along with the
supporting handoff doc, `docs/handoffs/2026-08-17-p02-a7-a13-validation.md`,
which no commit on any branch has ever added). Neither is present in the live
main checkout as of this reevaluation; the committed register still reads
`- [ ] [P02-TS12] A12 adversarial verification (incl. Codex): hang/interrupt
and untracked-hook execution repros`, pre-verdict. This design document is
now the only durable, committed record of that verdict's substance. This is a
register-file / process concern for the owner to resolve — out of scope for
this planning worktree, which was instructed not to touch
`projects/P02-agent-fork-fault-remediation.md`.

**Conclusion.** The design, its recommendation, and its contracts stand
unchanged. Before Step 1 begins: renumber the five collided test IDs per the
table above, and separately decide how the TS12 verdict gets a durable
committed home.

---

## Second reevaluation against `origin/main` (2026-08-20, later same day)

This branch was rebased a second time, onto `origin/main` at `f7b5a98` (up
from `46201c1` above) — 20 more commits, all of it two more P02 items landing
in full: `A10` (Claude inferred-parent freshness, PR #63) and `A6`, split
into `A6a` (dirty submodules, PR #58) and a still-open `A6b`. The rebase
applied cleanly, zero conflicts.

**The fault surface is still untouched.** Diffing `46201c1..f7b5a98` directly
by file: `include.py`, `git.py`, `rollback.py`, `config.py`, `doctor.py`, and
`output.py` — every file this plan's contracts touch — have zero changes.
`cli.py` grew by roughly 200 lines and `pipeline.py` picked up 8 lines, but
neither touches what this plan depends on: `pipeline.py`'s change adds a
`with_state` parameter to `validate_fork_guards()` for A6a's submodule fix,
nowhere near the `run_setup_hook()` call site; `cli.py`'s top-level
`except Exception as error:` is still present, still does not catch
`OperationInterrupted` (a `BaseException` subclass), just at a new line
(**1413**, was 1229). The REQ-22 130/143 conformance gap this plan closes is
still real.

**A second test-ID collision, on the IDs the first reevaluation had already
renumbered to.** `A6a`'s own gate-6 pass independently claimed
`T-CLI-36/37/38` — confirmed by its merge commit's own message
(`1f9dcff`, "resolve T-CLI ID collision"), which describes resolving a
concurrent claim on those same three IDs against `A10`'s branch and shifting
`A10`'s rows to `T-CLI-39..50`. Those are precisely the IDs this plan's first
reevaluation reserved for A12 after the previous collision. Checked directly
against the live matrix:

| Prefix | This plan's current reservation | Now taken by unrelated rows | Actual next-free |
|---|---|---|---|
| `T-INC` | 08-16 | — (still free) | **08-16, unchanged** |
| `T-RBK` | 08-09 | — (still free) | **08-09, unchanged** |
| `T-CLI` | 36-38 | `T-CLI-36/37/38` (A6a) | **51-53** |
| `T-OUT` | 24-25 | — (still free) | **24-25, unchanged** |
| `T-CFG` | 24-26 | — (still free) | **24-26, unchanged** |

Only `T-CLI` moved again; renumber `T-CLI-36/37/38 → 51/52/53` when Step 1
adds rows. This is the second time in three days that concurrent P02 work has
claimed IDs this plan reserved — worth the owner knowing this project
currently has enough parallel worktrees in flight that test-ID reservations
should be treated as provisional until the moment a PR actually lands, not
locked in during planning.

**The TS12 provenance gap from the first reevaluation is unchanged.** Still
absent from `origin/main`; still durably recorded only in this document and
in the separate `30f5e76` commit on `worktree-p02-a12-ts12-reverify` (see the
header gate table above).

**Conclusion.** No design change. Renumber `T-CLI` a second time before
Step 1; the four other prefixes need no further change.

---

## Gate-6 corrections (2026-08-20)

Two independent adversarial reviews of the shipped implementation — one Claude,
one Codex — found corroborating defects. All are fixed on this branch. The
table is the record of what changed *after* Step 5, so a later reader does not
have to diff the branch to find out which parts of this document describe the
plan and which describe the product.

| # | Defect | Correction | Rows |
|---|---|---|---|
| 1 | Reaping decided from the leader's exit status, not the group. Timeout path: a hook that backgrounded a process and exited was reported `timed_out: true` after 121 s, and the post-reap drain was unbounded. Interrupt path: `signal_process_group()` returned before `killpg` when the leader had already exited, so a surviving group member ignoring SIGTERM never got SIGKILL | `_signal_hook_group()` (unconditional `killpg`), group-emptiness probing in `_reap()`, and `_collect_output()`'s two separate bounds; `descendants_cleared` reports what is left. "Execution and reaping" and "Known limits" above are rewritten to match | `T-INC-17`, `T-RBK-10` |
| 2 | An interrupt between `Popen()` and the `_ACTIVE` registration leaked the process group | Spawn and registration moved inside the reap-protected region, registration in a `finally`. **Insufficient — see round 3, item 1: enclosure narrows the window, it does not close it** | covered by 1's rows |
| 3 | `main()`'s interrupt boundary chose JSON-versus-human from the raw arguments, not the resolved output mode | `_fork_cli()` publishes the resolved mode; `_machine()` prefers it. Note for the record: `output` is not a `[fork]` config key — `AGENT_FORK_OUTPUT` is the whole non-flag route. **Partial — see round 3, item 3: publication happened too late in `_fork_cli()`** | `T-CLI-54` |
| 4 | Axis C1's human-mode tail echo was never implemented — `stdout_tail`/`stderr_tail` appeared nowhere in `cli.py` | Echoed to stderr for failed, timed-out, and `--debug`, reusing the already-bounded, already-escaped fields | `T-OUT-26`, `T-OUT-27` |
| 5 | `CONFORMANCE.md` overclaimed machine-mode stderr purity: the hook's skip and failure notices still land there as plain text | Claim corrected, not the behavior — the notice path is A13(a) / `P02-T13ABF`, out of scope and deliberately preserved | `T-OUT-24` extended |

Three nitpicks were taken as well: a digits-only pre-check on
`setup_hook_timeout` (`int("1_000")` silently became 1000), a fallback so a
reason-less eligibility cannot render the literal `None` in dry-run text, and
`T-INC-14`'s missing exact-bound case (output of exactly 4096 bytes), which
passed as written. Matrix rows move from 532 to 537.

### Round 3 (2026-08-21)

An independent Codex confirmation pass over the round-2 fixes found rows 1 and
4-5 genuinely closed, row 2 still open, row 3 only partly closed, and one new
hazard introduced by row 1's own fix. All three are fixed here.

| # | Defect | Correction | Rows |
|---|---|---|---|
| 1 | The `Popen()`-to-registration window was **not** closed by round 2. `process = Popen(...)` spawns before it binds the name, so a handler firing in the gap has nothing to reap (the local is unbound) and nothing to signal (`_ACTIVE` is unwritten) — enclosure in the protected block cannot help | `{SIGINT, SIGTERM}` blocked with `signal.pthread_sigmask` across the spawn and registration, restored with `SIG_SETMASK` inside the protected block; `preexec_fn` restores the child's inherited mask so the hook can still receive the ladder's SIGTERM. "Signal path" above is rewritten to match | `T-INC-19`, `T-INC-20` |
| 2 | New hazard from round 1's fix: a PID is reserved as its group's id only while the group is non-empty, so the unconditional `killpg` could signal an unrelated process group after the hook's own had emptied and the PID had been reused — worse than the orphan A12 exists to prevent | Emptiness latched on a `_HookGroup` record read by every signalling path; `_signal_hook_group()` probes and returns rather than signalling once latched. The reap-ladder section's "can never name an unrelated process" claim is corrected. **Tightened further in round 4, item 2; what the latch leaves is Known limit 9, not a closed hazard** | `T-INC-18` |
| 3 | Round 2's resolved-output publication sat immediately before the hook step, leaving agent-mode resolution, repository inspection, the anchor and branch Git calls, naming, and destination calculation inside the window it was meant to close | Published immediately after configuration resolution, the first point the mode is knowable. **Partial — see round 4, item 1: moving the publication narrows the window, it does not close it** | `T-CLI-55` |

Matrix rows move from 537 to 541.

### Round 4 (2026-08-21)

A second independent Codex pass confirmed round 3's item 1 genuinely closed and
found the remaining two items short of their claims: item 3 narrowed a window
it could not close by position alone, and item 2's latch stops repeated
signalling but leaves a sub-syscall race the primitives on both supported
platforms cannot remove. The first is fixed; the second is tightened as far as
it goes and then disclosed as Known limit 9 rather than claimed closed.

| # | Defect | Correction | Rows |
|---|---|---|---|
| 1 | The resolve-to-publish window was **not** closed by round 3. `resolve_discovered_config()`, the `output_kind` computation, and the `args._resolved_machine` assignment are three statements, and CPython runs signal handlers between bytecodes, so a signal landing between the return and the assignment still unwound with the mode unpublished and rendered a human error under `AGENT_FORK_OUTPUT=json` | `{SIGINT, SIGTERM}` blocked with `signal.pthread_sigmask` across all three statements in `_fork_cli()`, restored with `SIG_SETMASK` in a `finally` — the same technique round 3 used for the spawn, and simpler here because no child process is involved. A `ConfigError` from resolution still leaves the mode unpublished, which is correct: none exists yet | `T-CLI-56` |
| 2 | Round 3's emptiness latch stops a *repeated* signal once emptiness has been observed, but the check and the signal are still two syscalls, and `process.poll()` can itself reap the leader and release its pid before the probe even runs | Tried: skip the `killpg(pgid, 0)` probe on a live leader (`Popen.poll() is None`), reasoning that a session leader cannot leave its own group. **Wrong — see round 5: `poll() is None` does not only mean "confirmed alive."** Disclosed as Known limit 9 rather than claimed shut | `T-INC-21` (rewritten in round 5) |

Matrix rows move from 537 to 541.

### Round 5 (2026-08-21)

A third independent Codex pass, checking round 4's item 2 tightening
specifically, found it introduced a false safety claim rather than a narrower
race: `Popen.poll()` returning `None` does not only mean "leader confirmed
still running." CPython also returns `None` when a concurrent `waitpid` call
already holds the process's internal lock and no status could be observed —
which a signal handler re-entering this same single-threaded process during
another `communicate()`/`poll()` call can genuinely trigger. Round 4's
skip-the-probe optimization treated that "unknown" case as "known alive," so
it could skip the `killpg(pgid, 0)` probe and go straight to signalling a pid
that had, in fact, already been reaped and could have been recycled — the
exact hazard Known limit 9 exists to disclose, now silently reintroduced by
the code that was supposed to be tightening it.

| # | Defect | Correction | Rows |
|---|---|---|---|
| 1 | Round 4's skip-the-probe optimization in `_group_is_empty()` produced a false safety claim: it treated every `Popen.poll() is None` as proof of a live, unreaped leader, when CPython also returns `None` for "status unknown, lock contended," a state a re-entrant signal handler can produce | Reverted `_group_is_empty()` to round 3's shape verbatim: `poll()` is still called first (it is what makes the probe honest against zombies), but the function always follows with the `killpg(pgid, 0)` probe — no shortcut, live leader or not. The probe is the function's only actual source of proof | `T-INC-21` (rewritten to pin the always-probe behavior) |
| 2 | Known limit 9's text, and the `_signal_hook_group()`/`_group_is_empty()` docstrings, asserted the skipped-probe path was "provably safe" and that a live leader was "answered with no probe at all" | Both corrected to describe the always-probe behavior and the honest residual (the reaped-leader adjacent-syscall race) with no overclaim | — |
| 3 | Known limit 9 cited `pidfd_open`/`pidfd_send_signal` (Linux 5.3+) as the closing primitive without noting they signal a single process, not a group — `PIDFD_SIGNAL_PROCESS_GROUP` did not arrive until kernel 6.9, and a pidfd on an already-reaped leader answers `ESRCH` regardless | Corrected; the point stands (no primitive here is a stable handle for the surviving-group case on both supported platforms without new complexity), stated precisely rather than approximately | — |

This round removes mechanism rather than adding it — the revert restores code
an earlier round already reviewed and whose residual (Known limit 9's
adjacent-syscall race) that round characterized correctly. Matrix rows stay
at 543; only `T-INC-21`'s row text and matrix-row description changed, no new
row was added.

Matrix rows move from 541 to 543.
