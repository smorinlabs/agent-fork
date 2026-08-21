# P02-TS12 — A12 adversarial re-verification (executed 2026-08-20)

**Purpose.** Re-execute, live and black-box, the adversarial verification of
register item **A12 — Repository setup hook: no timeout, no opt-out,
unreviewed execution** (`projects/P02-agent-fork-fault-remediation.md`,
register lines ~326-334; task pair `P02-TS12` / `P02-T12`, lines ~394-397).
The 2026-08-17 execution of this verification was never committed and its
findings are gone; this run reproduces the work independently.

**Overall verdict: CONFIRMED-WITH-CORRECTIONS.** All five claimed behaviors
reproduced exactly as A12 describes them. Two findings go beyond the register
text and are new material for `P02-T12`:

1. Interrupting a fork exits **1 with an uncaught Python traceback**, not the
   `130` that `agent-fork --help` documents for SIGINT. No handler for
   `OperationInterrupted` exists anywhere in the CLI.
2. The hook's **grandchild** process (`sleep`) is orphaned and reparented to
   PID 1 while the hook's own shell is killed — so "the worktree is deleted
   around the still-running hook" is literally true, and the survivor is a
   process the CLI never had a handle on.

## Method

- **Binary under test:** `/Users/stevemorin/c/agent-fork/.claude/worktrees/p02-a12-ts12-reverify/.venv/bin/agent-fork`
  (the real console script, invoked as a subprocess — no library calls).
- **Source under test:** `src/agent_fork/include.py:90-116` (`run_setup_hook`),
  called from `src/agent_fork/pipeline.py:150-153`, wrapped by
  `src/agent_fork/rollback.py:33` (`run_with_rollback`).
- **Isolation:** one fresh scratch world per scenario under
  `…/scratchpad/a12/s{0..4}`, each a real `git init -b main` repository with a
  real seed commit. Every CLI and `git` invocation ran under `env -i` with only
  `PATH`, plus scratch `HOME`, `TMPDIR`, `GIT_CONFIG_GLOBAL`, and all four
  `XDG_*` variables pointed inside the scenario directory, so the machine's
  real fork registry and config were never touched and no agent-detection
  environment variables leaked in.
- **Invocation shape:** `agent-fork fork --no-agent --worktree-dir <scratch>
  <name>` — git-only mode, explicit destination, all other defaults
  (`--with-state` on, `--verify` on).
- **Scenario 0 (control):** a fork with no hook present succeeded, exit 0.

## 1. Untracked hook executes anyway — CONFIRMED

Parent repo: seed commit only. `.agent-fork/worktree-setup.sh` written to the
working tree, `chmod 755`, never `git add`-ed.

```console
$ git status --porcelain
?? .agent-fork/
$ git ls-files -- .agent-fork
(no output — the hook is untracked)

$ agent-fork fork --no-agent --worktree-dir …/s1/child1 untracked
mode: git-only
fork: untracked
branch: fork/untracked
worktree: …/s1/child1
EXIT=0

$ cat …/s1/sentinel-untracked
untracked hook ran at 1787266209
```

The hook reached the child through the default `--with-state` materialization
of untracked files, kept its executable bit, and ran. `run_setup_hook`'s only
gate is `hook.is_file()` (`include.py:95`) — there is no `git ls-files` /
tracked check.

Two details worth carrying into the fix:

- The sentinel was written **outside** the new worktree (into the scenario
  root), so the hook is unconstrained arbitrary code execution, not
  worktree-scoped setup.
- The successful run printed **no notice at all** that a hook had been found or
  executed. Nothing in the user-visible output distinguishes it from scenario 0.

## 2. Modified-but-uncommitted hook is the version that runs — CONFIRMED

Parent repo: hook v1 committed (writes `sentinel-committed`), then overwritten
on disk with v2 (writes `sentinel-modified`) and left uncommitted.

```console
$ git show HEAD:.agent-fork/worktree-setup.sh
#!/bin/sh
echo "COMMITTED version ran" > "…/s2/sentinel-committed"
$ git status --porcelain
 M .agent-fork/worktree-setup.sh

$ agent-fork fork --no-agent --worktree-dir …/s2/child2 modified
EXIT=0

$ cat …/s2/sentinel-committed
cat: …/s2/sentinel-committed: No such file or directory
$ cat …/s2/sentinel-modified
MODIFIED-UNCOMMITTED version ran
```

The child's checkout supplies v1; state materialization overlays v2; the hook
that runs is v2. The absence of `sentinel-committed` is the proof. A
tracked-in-git requirement alone would therefore not close this angle — the
check has to be against the *content that will run*, not merely against path
tracking.

## 3. No timeout; SIGINT during the hook — CONFIRMED-WITH-CORRECTIONS

Parent repo: hook committed, body `echo $$ > hook.pid; sleep 25; echo "hook
completed" > hook-completed`. The CLI was launched with Python
`subprocess.Popen(..., start_new_session=True)` and signalled with
`os.kill(cli_pid, SIGINT)` — a pid-targeted SIGINT that models
`kill -INT <cli-pid>`. (A terminal Ctrl-C signals the whole foreground process
group and would additionally hit the hook directly; the pid-targeted form is
the stricter test and is what the task prescribes.)

Process tree while the hook was running, before the signal:

```text
   PID   PPID  PGID STAT ELAPSED ARGS
 72758  72519 72519 S     00:03  /bin/sh …/s3/child3/.agent-fork/worktree-setup.sh
 72806  72758 72519 S     00:02  sleep 25
   (72519 = the agent-fork CLI)
```

SIGINT was delivered at t+6.63s after launch (~3.1s into the hook).

| Observation | Value |
|---|---|
| Time from SIGINT to CLI process exit | **0.576 s** |
| `Popen.returncode` | **1** (a normal exit, not death-by-signal `-2`) |
| CLI stdout | empty |
| CLI stderr | Python traceback ending `agent_fork.rollback.OperationInterrupted: 2` |
| Hook shell (pid 72758) survival past CLI exit | **0.0 s** — already dead |
| `sleep` grandchild (pid 72806) survival past CLI exit | **21.7 s**, reparented to **PID 1** |
| `hook-completed` sentinel | **absent** — the hook body never finished |
| Worktree `…/s3/child3` after exit | **removed** |
| `fork/hang` branch after exit | **absent** (`git branch --list` shows only `main`) |
| Fork registry under `XDG_STATE_HOME` | empty — no entry written |

The traceback's frames are the mechanism, verbatim from stderr:

```text
  File "…/src/agent_fork/pipeline.py", line 152, in finish
    hook_notices = run_setup_hook(request.parent, creation.path, env=env)
  File "…/src/agent_fork/include.py", line 107, in run_setup_hook
    completed = subprocess.run(
        [str(hook)], cwd=child, env=environment, capture_output=True, text=True
    )
  …
  File "…/src/agent_fork/rollback.py", line 33, in interrupt
    raise OperationInterrupted(signum)
agent_fork.rollback.OperationInterrupted: 2
```

Readings:

- **No timeout is real.** `subprocess.run` blocked in `communicate()` for as
  long as the hook chose to run. Nothing bounded it; the CLI only moved because
  an external signal arrived.
- **Exit-code contract violated.** `src/agent_fork/cli.py:44` documents
  `130/143 interrupted by SIGINT/SIGTERM`, but a grep of `src/agent_fork/`
  finds `OperationInterrupted` only where it is *defined*
  (`rollback.py:19`) and *raised* (`rollback.py:33`) — never caught. It is a
  `BaseException`, so it escapes `main()` and the interpreter exits 1 after
  printing the traceback. This is not hook-specific: any interrupt inside
  `run_with_rollback` takes the same path. Recommend `P02-T12` (or the A11
  exit-contract work) add the missing handler; the fix is not covered by
  "add `timeout=`".
- **Rollback works; process cleanup does not.** The interrupted CLI correctly
  removed the branch, the worktree, and left no registry entry — while an
  orphaned `sleep` whose working directory was inside the just-deleted worktree
  kept running for another 21.7 s under PID 1. CPython's `subprocess.run` kills
  its *direct* child on exception, which is why the hook shell died instantly;
  it has no knowledge of the shell's own children. A fix that only adds
  `timeout=` inherits the same defect, because `subprocess.run`'s timeout path
  also kills just the direct child. Closing this needs a process group
  (`start_new_session=True` on the hook plus `os.killpg`).

No cleanup debt: the orphan self-exited at its natural 25 s, and a post-run
`ps -eo pid,ppid,args | grep -E "worktree-setup|sleep 25"` found nothing.

## 4. Successful hook output is swallowed — CONFIRMED

Hook committed with `echo "SENTINEL_STDOUT_MARKER_9f3a"`,
`echo "SENTINEL_STDERR_MARKER_9f3a" >&2`, `exit 0`.

```console
$ agent-fork fork --no-agent --worktree-dir …/s4/child4 chatty
mode: git-only
fork: chatty
branch: fork/chatty
worktree: …/s4/child4

cd …/s4/child4
EXIT=0
$ grep -c SENTINEL_ST fork.out fork.err
fork.out:0
fork.err:0
```

`-o json` is equally silent — `"notices":[]`, and `grep -c SENTINEL_ST` on the
JSON returns 0. Neither stream nor the machine surface carries a single byte of
a successful hook's output.

**Contrast run (not in the original claim, worth recording):** the same hook
changed to `exit 3` produced

```text
EXIT=0
--- stderr ---
setup hook failed (exit 3): SENTINEL_STDERR_MARKER_9f3a
```

So a *failing* hook surfaces only its stderr (stdout is still dropped, per
`include.py:113`'s `stderr or stdout` preference) as a notice — and the fork
itself still reports success with exit code 0.

## 5. Dry-run and doctor disclose nothing about the hook — CONFIRMED

All four surfaces ran against the same repo with the hook committed and
present.

| Surface | Command | `grep -ic hook` |
|---|---|---|
| Dry-run, text | `agent-fork fork --no-agent --dry-run …` | 0 (stdout and stderr) |
| Dry-run, JSON | `agent-fork fork --no-agent --dry-run -o json …` | 0 |
| Doctor, text | `agent-fork doctor` | 0 (stdout and stderr) |
| Doctor, JSON | `agent-fork doctor -o json` | 0 |

The dry-run plan enumerates branch, worktree, `files-to-carry`, the paste
command, and `validation: local-only; no mutation performed` — the one planned
mutation it omits is the arbitrary code the fork will execute. Doctor's seven
checks (git floor, Claude CLI, Codex CLI, agent recipe flags, environment
signals, config validity, XDG paths) include nothing about hooks.

Two supporting reads, both zero-match:

- `agent-fork fork --help` and `agent-fork doctor --help` never mention a hook —
  there is no `--no-hooks` flag.
- `grep -rn "hook" src/agent_fork/config.py src/agent_fork/cli.py` returns
  nothing, and `_FORK_KEYS` (`config.py:21-29`) is
  `{with_state, with_ignored, branch_prefix, worktree_location, agent_mode,
  verify, copy}` — no hook opt-out key exists at any config layer.

## Recommended additions to P02-T12 beyond the register's proposed direction

The register proposes: timeout, opt-out, surface in dry-run plan, require the
hook be tracked. This run supports all four and adds:

1. **Catch `OperationInterrupted` and exit 130/143** — the documented contract
   is currently a lie for every interrupted fork, hook or not.
2. **Run the hook in its own process group and kill the group**, on both the
   timeout path and the interrupt path; killing the direct child alone
   demonstrably leaves orphans reparented to PID 1.
3. **Gate on hook content, not path tracking** — a tracked hook modified in the
   working tree runs in its modified form (scenario 2).
4. **Announce the hook on the success path**, at least as a notice naming the
   hook that ran; today a successful hook is invisible on every surface.
5. **Decide whether a nonzero hook should still yield exit 0** — today it does,
   with only a stderr notice.

## Reproduction assets

Scenario drivers (scratch, not part of the repository):
`…/scratchpad/a12/{setup.sh,env.sh,s0.sh,s1.sh,s2.sh,s3.py,s4.sh}`.
