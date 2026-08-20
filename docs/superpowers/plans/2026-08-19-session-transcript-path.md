# Session transcript-path implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `agent-fork session` reports the absolute path and filename of the
active session's on-disk transcript — the Claude Code JSONL transcript or the
Codex rollout JSONL — as one additive `transcript` object, so the companion
skill can surface it.

**Architecture:** Both halves of the resolution already exist in the codebase
for other reasons and are currently discarded. `session.py`'s
`_claude_transcript()` derives the Claude path (used only to read the session
name); `agents.py`'s `codex_rollout_exists()` globs the Codex rollout file
(used only as a preflight boolean). This change promotes both into a
`SessionTranscript` value object hung off `SessionInspection`, exactly
mirroring how `resume_command` was added in PR #47. No new subcommand, no new
skill argument, no new dependency, no filesystem read of transcript contents.

**Tech Stack:** Python >=3.11, standard library only (`pathlib`, `re`,
`dataclasses`); `uv` for dependency and version management; `just` as the
command runner; `pytest` with a `matrix` marker cross-checked against
`docs/testing/TEST-MATRIX.md`; `ruff` for format and lint; `ty` for
typechecking.

**Spec:** `projects/P05-session-transcript-path.md` (written in Task 1 of this
plan; it is the scoped, owner-confirmed statement of the item). The design was
settled in conversation on 2026-08-19 with four explicit owner decisions,
recorded in the "Owner decisions" section below.
`docs/superpowers/plans/2026-08-14-session-fork-command.md` is the prior art
this change mirrors.

## Owner decisions (settled 2026-08-19 — do not relitigate)

| # | Question | Decision |
|---|---|---|
| 1 | What file is "the Codex transcript"? | The rollout JSONL: `<CODEX_HOME>/sessions/<YYYY>/<MM>/<DD>/rollout-<timestamp>-<thread-id>.jsonl` |
| 2 | Which output surfaces carry it? | `SessionInspection` only — the `--session` route's human text and JSON. `--session-only` is untouched. |
| 3 | What is emitted when the file is not on disk? | A `path` plus a boolean `exists` flag, not a status enum |
| 4 | How is the work investigated? | Done; this plan is its output |

## Global Constraints

- **Python floor:** `requires-python = ">=3.11"` (`pyproject.toml:11`). Standard
  library only — this change adds no dependency.
- **Worktree:** all work happens in the already-created worktree
  `/Users/stevemorin/c/agent-fork/.claude/worktrees/p05-session-transcript-path`
  on branch `worktree-p05-session-transcript-path`, branched from
  `origin/main`. Never commit to `main`. Never stage the pre-existing
  uncommitted changes that live in the main checkout.
- **One PR per item:** documentation, project-file flips, and implementation
  ship in a single pull request, merged only when the item is fully done.
- **Commit messages:** Conventional Commits.
- **Merge strategy:** merge commit (`gh pr merge <n> --merge`).
- **Verification gates:** `make check` verifies environment dependencies;
  `just all` runs `fmt lint typecheck version-check test`; `just check-matrix`
  is a separate CI gate that is **not** part of `just all` and must be run
  explicitly.
- **Test-row bookkeeping:** `scripts/check_matrix.py` enforces **exactly one**
  collected pytest item per live row in `docs/testing/TEST-MATRIX.md`. Adding a
  test with a `@pytest.mark.matrix("T-XXX-NN")` marker therefore requires
  adding exactly one matching row, and the file header's `Total rows:` count
  must be updated in the same change.
- **Terminal safety:** every session- or repository-controlled scalar printed
  to a terminal passes through `agent_fork.output.terminal_text()`. Session
  IDs that are not `[A-Za-z0-9-]+` never reach a filesystem path.
- **Version class:** an additive JSON field is a minor bump — the precedent
  `resume_command` set in PR #47. This plan bumps `1.1.0` to `1.2.0`.

## Result contract

Session JSON gains one additive object alongside `fork_command` and
`resume_command`:

```json
{"transcript": {"path": "/Users/dev/.claude/projects/-Users-dev-project/1111....jsonl", "exists": true}}
```

The invariant, exhaustively:

| Case | `path` | `exists` |
|---|---|---|
| Claude identity, transcript file present | absolute path string | `true` |
| Claude identity, transcript file not yet flushed | absolute path string | `false` |
| Claude or Codex identity whose ID is not `[A-Za-z0-9-]+` | `null` | `false` |
| Codex identity, rollout file matched | absolute path string | `true` |
| Codex identity, no rollout match | `null` | `false` |
| No identity (`not_detected`) or two identities (`ambiguous`) | `null` | `false` |

`path` is `null` whenever the transcript could not be located; `exists` is
`true` only when a file was observed on disk at that path. `path: null` with
`exists: true` is an illegal state and is rejected in `__post_init__`.

**Two asymmetries an implementer must not "fix":**

1. On Codex the path is *discovered* by globbing, because the rollout filename
   embeds a timestamp that cannot be predicted from the thread ID. So on Codex
   `exists` is always equivalent to `path is not None`. On Claude the path is
   *derived* from the session ID, so it can be non-null while `exists` is
   `false`. This follows from the two agents' storage layouts.
2. The Claude path is keyed on the directory `agent-fork` was invoked in.
   Invoking it outside the session's own working directory encodes the wrong
   directory and reports `exists: false`. This limitation is pre-existing —
   `_claude_name()` already resolves names the same way — and is documented in
   the README rather than fixed here. Fixing it is out of scope.

   **Empirically corrected 2026-08-19, after Task 8's live run.** An earlier
   draft of this plan claimed the failure case was "a session started in a main
   checkout and inspected from a linked worktree". That is wrong: Claude Code
   re-keys its transcript folder when the session's directory changes, so this
   very session — started in the main checkout, moved into
   `.claude/worktrees/p05-session-transcript-path` — resolved to an existing
   file under the *worktree's* encoded folder, with nothing left under the
   original. The real failure mode is invoking the CLI from an unrelated
   directory, verified by running it from the scratchpad and getting
   `(missing)`.

## Human output

`agent-fork session` gains one line, printed immediately after the existing
`resume command:` line:

```text
transcript: /Users/dev/.claude/projects/-Users-dev-project/1111....jsonl (exists)
transcript: /Users/dev/.claude/projects/-Users-dev-project/1111....jsonl (missing)
transcript: unavailable
```

## File Structure

| File | Responsibility in this change |
|---|---|
| `src/agent_fork/agents.py` | Add `codex_rollout_path()` — the single Codex rollout glob. Existing `codex_rollout_exists()` delegates to it, preserving its behavior byte-for-byte. |
| `src/agent_fork/session.py` | Add the `SessionTranscript` value object, the `_session_transcript()` resolver, the required `transcript` field on `SessionInspection`, and its `document()` entry. |
| `src/agent_fork/cli.py` | Print the human `transcript:` line; update the `session` subcommand help. |
| `tests/unit/test_codex_resolution.py` | Prove `codex_rollout_path()` resolves the matching rollout deterministically. |
| `tests/unit/test_session.py` | Prove the resolution truth table and `document()` inclusion; update two direct `SessionInspection(...)` constructions for the new required field. |
| `tests/cli/test_session.py` | Prove the CLI human line and JSON object, including terminal escaping. |
| `tests/skill/test_companion_skill.py` | Prove the companion skill presents `transcript` and carries its upgrade path. |
| `.agents/skills/agent-fork/SKILL.md` | Present and validate `transcript` on the `--session` route only. |
| `.agents/skills/agent-fork/references/output-claude.md` | Claude `--session` example row. |
| `.agents/skills/agent-fork/references/output-codex.md` | Codex `--session` example row. |
| `docs/testing/TEST-MATRIX.md` | Four new `G-SES` rows plus the header recount. |
| `README.md` | Document the field, both storage layouts, and the directory-encoding caveat. |
| `projects/P05-session-transcript-path.md` | The item's own project file. |
| `PROJECTS.md` | Trunk row for P05. |
| `pyproject.toml`, `uv.lock`, `tests/cli/test_cli.py`, `scripts/check_clean_install.sh`, `README.md`, `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`, `.claude-plugin/marketplace.json` | Version `1.1.0` to `1.2.0`, all eight written by `just bump minor`. |

---

### Task 1: Register the project

Bookkeeping first, matching the P04 precedent where `PROJECTS.md` and the
project file landed in the feature's first commit. This task produces no code.

**Files:**
- Create: `projects/P05-session-transcript-path.md`
- Modify: `PROJECTS.md:50` (insert the new row directly after the P04 row)

**Interfaces:**
- Consumes: nothing.
- Produces: the task IDs `P05-TS01`..`P05-TS04` and `P05-T01`..`P05-T07` that
  later tasks tick off.

- [ ] **Step 1: Confirm you are in the worktree and on the right branch**

Run:

```bash
git rev-parse --show-toplevel && git branch --show-current
```

Expected: the toplevel ends in `.claude/worktrees/p05-session-transcript-path`
and the branch is `worktree-p05-session-transcript-path`. If not, stop — do not
create files in the main checkout.

- [ ] **Step 2: Write the project file**

Create `projects/P05-session-transcript-path.md` with exactly this content
(the outer `~~~` fence is not part of the file):

~~~markdown
# P05 — session transcript path

**References**
- **Trunk:** [PROJECTS.md](../PROJECTS.md)
- **Plan:** [2026-08-19-session-transcript-path.md](../docs/superpowers/plans/2026-08-19-session-transcript-path.md)
- **Prior art:** [P04 — session resume (rehydrate) command](P04-session-resume-command.md)
- **Discussion:** owner request 2026-08-19 — expose the active session's
  transcript file path through the companion skill, scoped and confirmed in
  conversation with four explicit decisions (Codex rollout file; `--session`
  surface only; `path` plus `exists` flag; investigation merged into one plan)

## [ ] Project P05: session transcript path (v1.2.0)
**Goal**: `agent-fork session` already reports the session's identity, its
repository context, and its fork and resume commands. Add the **transcript
path**: the absolute path and filename of the file where the active session's
conversation is stored on disk, so the companion skill can hand it to the user
or to a downstream tool.

- Claude Code: `<CLAUDE_CONFIG_DIR|~/.claude>/projects/<encoded-directory>/<session-id>.jsonl`,
  where `<encoded-directory>` is the resolved invocation directory with every
  non-alphanumeric character replaced by `-`
- Codex: `<CODEX_HOME|~/.codex>/sessions/<YYYY>/<MM>/<DD>/rollout-<timestamp>-<thread-id>.jsonl`,
  located by glob because the filename embeds a timestamp

New JSON field `transcript` (`path` plus `exists`), folded into the existing
`--session` route only — no new CLI subcommand, no new skill argument.

**Out of Scope**
- Reading, parsing, summarizing, copying, or truncating transcript contents.
  This item reports a location only.
- Correcting the directory-encoding limitation: a Claude session started in a
  main checkout and inspected from a linked worktree derives a path under the
  original directory's encoded folder and reports `exists: false`. This is
  pre-existing behavior shared with session-name resolution; it is documented,
  not changed.
- `--session-only`, which by design prints only `fork_command.command`.
- The generated `agents/openai.yaml` metadata, which is generator-managed.

### Tests & Tasks
- [ ] [P05-TS01] RED: `codex_rollout_path()` resolves the matching rollout file
      deterministically and stays consistent with `codex_rollout_exists()`
      (`tests/unit/test_codex_resolution.py`)
- [ ] [P05-TS02] RED: transcript resolution truth table — Claude derived path
      present and absent, Codex glob hit and miss, terminal-unsafe ID, and no
      ambient identity (`tests/unit/test_session.py`)
- [ ] [P05-TS03] RED: `document()` includes the additive `transcript` object
      (`tests/unit/test_session.py`)
- [ ] [P05-TS04] RED: CLI `session` human line and `--json` object, with
      terminal escaping (`tests/cli/test_session.py`)
- [ ] [P05-T01] GREEN: `codex_rollout_path()` in `agents.py`;
      `codex_rollout_exists()` delegates to it
- [ ] [P05-T02] GREEN: `SessionTranscript` dataclass, `_session_transcript()`
      resolver, and the `transcript` field wired through every
      `SessionInspection` construction site and `document()` in `session.py`
- [ ] [P05-T03] GREEN: `transcript: ...` CLI line and `session --help` epilog
      in `cli.py`
- [ ] [P05-T04] Version bump `1.1.0` to `1.2.0` via `just bump minor`
- [ ] [P05-T05] TEST-MATRIX.md: register `T-SES-39..42`, mark the four new
      tests, update the total-row count; `just check-matrix` clean
- [ ] [P05-T06] Companion skill: `--session` route presents and validates
      `transcript` with its own "predates the transcript contract" upgrade
      path; `--session-only` untouched; both
      `references/output-{claude,codex}.md` gained a transcript row
- [ ] [P05-T07] README: document the field, both storage layouts, and the
      directory-encoding caveat
- [ ] Regression Test Status: `just all` and `just check-matrix` green

### Deliverable
`agent-fork session` (human and `--json`) reports the active session's
transcript path alongside `fork_command` and `resume_command`.

### Automated Verification
- `make check` passes; `just all` green
- `just check-matrix` clean
- New tests pass; the only existing tests to change are the two direct
  `SessionInspection(...)` constructions that gain the new required argument

### Manual Verification
- Run `agent-fork session` inside a real Claude Code session and confirm the
  printed `transcript:` path is the session's actual JSONL file, verified with
  `ls -l` on the printed path.
~~~

- [ ] **Step 3: Add the trunk row**

In `PROJECTS.md`, immediately after the existing P04 row on line 50, add:

```markdown
- [ ] **P05** — [session transcript path](projects/P05-session-transcript-path.md)
```

- [ ] **Step 4: Verify the row renders and the link resolves**

Run:

```bash
grep -n "P05" PROJECTS.md && test -f projects/P05-session-transcript-path.md && echo LINK-OK
```

Expected: the row prints and `LINK-OK` appears.

- [ ] **Step 5: Commit**

```bash
git add PROJECTS.md projects/P05-session-transcript-path.md docs/superpowers/plans/2026-08-19-session-transcript-path.md
git commit -m "docs(p05): register the session transcript-path item and its plan"
```

---

### Task 2: Resolve the Codex rollout path

**Files:**
- Modify: `src/agent_fork/agents.py:277-279` (the existing `codex_rollout_exists`)
- Test: `tests/unit/test_codex_resolution.py`

**Interfaces:**
- Consumes: the existing `_codex_home(env: Mapping[str, str]) -> Path` at
  `src/agent_fork/agents.py:268` and the existing `AgentContext` dataclass,
  whose `parent_session_id` attribute carries the Codex thread ID.
- Produces: `codex_rollout_path(context: AgentContext, env: Mapping[str, str]) -> Path | None`
  — returns the newest matching rollout file, or `None` when nothing matches.
  Task 3 calls it. `codex_rollout_exists(context, env) -> bool` keeps its exact
  current signature and behavior; its existing caller (the preflight at
  `src/agent_fork/agents.py:403`) must not change.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_codex_resolution.py`. The module already defines
`UUID`, imports `Path`, and defines the `_world()` helper, which writes
`<world>/codex-home/sessions/2026/08/10/rollout-now-<UUID>.jsonl` and returns an
env with `CODEX_HOME` pointed at it — reuse all three.

```python
@pytest.mark.matrix("T-SES-42")
def test_codex_rollout_path_resolves_the_matching_rollout(repo_scenario):
    from agent_fork.agents import (
        AgentContext,
        codex_rollout_exists,
        codex_rollout_path,
    )

    _, env = _world(repo_scenario)
    context = AgentContext("codex", UUID)

    resolved = codex_rollout_path(context, env)
    assert resolved is not None
    assert resolved.name == f"rollout-now-{UUID}.jsonl"
    assert resolved.is_file()
    assert codex_rollout_exists(context, env) is True

    home = Path(env["CODEX_HOME"])
    newer = home / "sessions/2026/08/11" / f"rollout-later-{UUID}.jsonl"
    newer.parent.mkdir(parents=True)
    newer.write_text("{}\n")
    assert codex_rollout_path(context, env) == newer

    missing = AgentContext("codex", "019fed92-fa7e-7262-b93e-6bd73a38ac73")
    assert codex_rollout_path(missing, env) is None
    assert codex_rollout_exists(missing, env) is False
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
uv run pytest tests/unit/test_codex_resolution.py::test_codex_rollout_path_resolves_the_matching_rollout -v
```

Expected: FAIL with `ImportError: cannot import name 'codex_rollout_path'`.

- [ ] **Step 3: Write the implementation**

In `src/agent_fork/agents.py`, replace the existing three-line
`codex_rollout_exists` with:

```python
def codex_rollout_path(context: AgentContext, env: Mapping[str, str]) -> Path | None:
    """Locate one thread's rollout file; the newest match wins when several exist."""
    pattern = f"sessions/*/*/*/rollout-*-{context.parent_session_id}.jsonl"
    matches = sorted(_codex_home(env).glob(pattern))
    return matches[-1] if matches else None


def codex_rollout_exists(context: AgentContext, env: Mapping[str, str]) -> bool:
    return codex_rollout_path(context, env) is not None
```

The rollout filename embeds an ISO-8601-ordered timestamp, so lexical `sorted()`
is chronological ordering and `matches[-1]` is the newest. Keeping
`codex_rollout_exists` as a delegating wrapper leaves the preflight caller
untouched and leaves exactly one glob in the codebase.

- [ ] **Step 4: Run the test to verify it passes**

Run:

```bash
uv run pytest tests/unit/test_codex_resolution.py -v
```

Expected: PASS, including every pre-existing test in the file — the preflight
tests exercise `codex_rollout_exists` and so prove the delegation is
behavior-neutral.

**Expect `just check-matrix` to fail from here until Task 6.** From this commit
onward the tree carries `matrix` markers whose rows do not exist yet, so the
gate reports `CHECK1: <item> cites unknown matrix ID`. That is the designed
intermediate state — Task 6 registers the rows. Do not "fix" it by deleting a
marker.

- [ ] **Step 5: Commit**

```bash
git add src/agent_fork/agents.py tests/unit/test_codex_resolution.py
git commit -m "feat(agents): resolve the Codex rollout path, not just its existence"
```

---

### Task 3: Add the transcript field to session inspection

**Files:**
- Modify: `src/agent_fork/session.py` — the import block (lines 13-20), the
  constants near line 30, `_claude_name` (line 192), a new resolver after
  `_claude_transcript` (line 189), the dataclass block after
  `SessionResumeCommand` (ends line 137), `SessionInspection` (lines 139-177),
  and the construction sites at lines 279, 294, and the `_inspection` closure
  at line 331
- Test: `tests/unit/test_session.py`

**Interfaces:**
- Consumes: `codex_rollout_path()` from Task 2; the existing
  `_claude_transcript(env, cwd, session_id) -> Path` at
  `src/agent_fork/session.py:186`.
- Produces: `SessionTranscript(path: Path | None, exists: bool)` with a
  `document() -> dict[str, object]` method returning
  `{"path": str | None, "exists": bool}`; a required
  `transcript: SessionTranscript` field on `SessionInspection`; and the
  `"transcript"` key in `SessionInspection.document()`. Task 4 reads
  `inspection.transcript`.

- [ ] **Step 1: Write the first failing test — the resolution truth table**

Append to `tests/unit/test_session.py`. `repo_scenario` seals `HOME` to
`<world>/home`, so the derived Claude path lands under a temporary directory.

```python
@pytest.mark.matrix("T-SES-39")
def test_transcript_resolution_uses_identity_and_disk_state(repo_scenario, monkeypatch):
    import agent_fork.session as session_module

    world = repo_scenario()

    no_identity = session_module.inspect_session(world.env, cwd=world.parent_path)
    assert no_identity.transcript.path is None
    assert no_identity.transcript.exists is False

    claude_env = {
        **world.env,
        "CLAUDECODE": "1",
        "CLAUDE_CODE_SESSION_ID": "claude-child",
    }
    absent = session_module.inspect_session(claude_env, cwd=world.parent_path)
    expected = session_module._claude_transcript(
        claude_env, world.parent_path, "claude-child"
    )
    assert absent.transcript.path == expected
    assert absent.transcript.exists is False

    expected.parent.mkdir(parents=True)
    expected.write_text("{}\n")
    present = session_module.inspect_session(claude_env, cwd=world.parent_path)
    assert present.transcript.path == expected
    assert present.transcript.exists is True

    ambiguous = session_module.inspect_session(
        {**claude_env, "CODEX_THREAD_ID": "codex-thread"}, cwd=world.parent_path
    )
    assert ambiguous.transcript.path is None
    assert ambiguous.transcript.exists is False

    unsafe = session_module.inspect_session(
        {
            **world.env,
            "CLAUDECODE": "1",
            "CLAUDE_CODE_SESSION_ID": "unsafe\x1b]52;c;Zm9v\x07",
        },
        cwd=world.parent_path,
    )
    assert unsafe.transcript.path is None
    assert unsafe.transcript.exists is False

    original_which = session_module.shutil.which
    monkeypatch.setattr(
        session_module.shutil,
        "which",
        lambda name, path=None: (
            None if name == "codex" else original_which(name, path=path)
        ),
    )
    codex_home = world.parent_path.parent / "codex-home"
    rollout = codex_home / "sessions/2026/08/19" / "rollout-now-codex-thread.jsonl"
    rollout.parent.mkdir(parents=True)
    rollout.write_text("{}\n")
    codex_env = {
        **world.env,
        "CODEX_THREAD_ID": "codex-thread",
        "CODEX_HOME": str(codex_home),
    }
    codex = session_module.inspect_session(codex_env, cwd=world.parent_path)
    assert codex.transcript.path == rollout
    assert codex.transcript.exists is True

    codex_missing = session_module.inspect_session(
        {
            **world.env,
            "CODEX_THREAD_ID": "absent-thread",
            "CODEX_HOME": str(codex_home),
        },
        cwd=world.parent_path,
    )
    assert codex_missing.transcript.path is None
    assert codex_missing.transcript.exists is False

    with pytest.raises(ValueError, match="cannot exist"):
        session_module.SessionTranscript(None, True)
```

The `monkeypatch` of `shutil.which` makes the Codex CLI look absent, which
routes `inspect_session` through its "Codex CLI is unavailable" branch. That
branch still returns through the shared `_inspection()` closure, so the
transcript is populated without needing a live Codex app-server.

- [ ] **Step 2: Write the second failing test — the document entry**

Append to `tests/unit/test_session.py`:

```python
@pytest.mark.matrix("T-SES-40")
def test_document_includes_transcript(repo_scenario):
    from agent_fork.session import inspect_session

    world = repo_scenario()
    claude_env = {
        **world.env,
        "CLAUDECODE": "1",
        "CLAUDE_CODE_SESSION_ID": "claude-child",
    }
    result = inspect_session(claude_env, cwd=world.parent_path)
    document = result.document()
    assert result.transcript.path is not None
    assert document["transcript"] == {
        "path": str(result.transcript.path),
        "exists": False,
    }
```

- [ ] **Step 3: Run both tests to verify they fail**

Run:

```bash
uv run pytest tests/unit/test_session.py -k "transcript_resolution or includes_transcript" -v
```

Expected: FAIL with
`AttributeError: module 'agent_fork.session' has no attribute 'SessionTranscript'`.

- [ ] **Step 4: Import the resolver and add the shared ID guard**

In `src/agent_fork/session.py`, add `codex_rollout_path` to the existing
`from agent_fork.agents import (...)` block:

```python
from agent_fork.agents import (
    AgentContext,
    AgentSignalAssessment,
    UnsafeCommandInputError,
    assess_agent_signals,
    build_session_fork_command,
    build_session_resume_command,
    codex_rollout_path,
)
```

Then, next to the existing limits near line 30, add the shared guard:

```python
CLAUDE_TRANSCRIPT_LIMIT = 1_048_576
CLAUDE_RECORD_LIMIT = 10_000
SAFE_SESSION_ID = re.compile(r"[A-Za-z0-9-]+")
SessionForkStatus = Literal["available", "not_detected", "ambiguous", "unsafe_input"]
```

And in `_claude_name` (line 192), replace the inline literal so the guard has
one definition:

```python
    if SAFE_SESSION_ID.fullmatch(session_id) is None:
        return None, "not_found"
```

This single-source-of-truth move is deliberate: T-SES-21 ("a hostile Claude
session ID cannot escape the bounded transcript path") already depends on this
guard, and the new resolver must enforce exactly the same rule rather than a
second copy that could drift.

- [ ] **Step 5: Add the value object**

In `src/agent_fork/session.py`, immediately after `SessionResumeCommand` ends
(line 137) and before `SessionInspection`:

```python
@dataclass(frozen=True)
class SessionTranscript:
    path: Path | None
    exists: bool

    def __post_init__(self) -> None:
        if self.path is None and self.exists:
            raise ValueError("an unlocated transcript cannot exist")

    def document(self) -> dict[str, object]:
        return {
            "path": str(self.path) if self.path is not None else None,
            "exists": self.exists,
        }
```

- [ ] **Step 6: Add the resolver**

In `src/agent_fork/session.py`, immediately after `_claude_transcript` (line 189):

```python
def _session_transcript(
    agent: str, session_id: str, env: Mapping[str, str], directory: Path
) -> SessionTranscript:
    """Locate the session's on-disk transcript without reading its contents."""
    if SAFE_SESSION_ID.fullmatch(session_id) is None:
        return SessionTranscript(None, False)
    if agent == "claude":
        path = _claude_transcript(env, directory, session_id)
        return SessionTranscript(path, path.is_file())
    rollout = codex_rollout_path(AgentContext("codex", session_id), env)
    return SessionTranscript(rollout, rollout is not None)
```

The ID guard runs before the Codex glob, so the glob pattern can only ever
contain `[A-Za-z0-9-]` — no glob metacharacters and no path separators reach it.
`Path.is_file()` returns `False` rather than raising on an unreadable or
malformed path, so no exception handling is needed.

- [ ] **Step 7: Add the field and the document entry**

In `SessionInspection`, add `transcript` after `resume_command`. It must have
**no default value** — commit `9a7c992`'s message records the reason: a
defaulted field lets a future construction site omit it with no type error.
Required fields must precede the defaulted `notices` field:

```python
@dataclass(frozen=True)
class SessionInspection:
    agent: str | None
    current_session: SessionEvidence | None
    parent_session: SessionEvidence | None
    lineage_status: str
    directory: Path
    repository: SessionRepository | None
    fork_command: SessionForkCommand
    resume_command: SessionResumeCommand
    transcript: SessionTranscript
    notices: tuple[str, ...] = ()
```

And in `SessionInspection.document()`, after the `"resume_command"` entry:

```python
            "resume_command": self.resume_command.document(),
            "transcript": self.transcript.document(),
```

- [ ] **Step 8: Wire every construction site**

There are exactly three sites in `inspect_session`. The two early returns get a
literal empty transcript.

At the `ambiguous` early return (line 279), after `resume_command=...`:

```python
            resume_command=SessionResumeCommand("ambiguous", None),
            transcript=SessionTranscript(None, False),
```

At the `absent`/`incomplete` early return (line 294), after `resume_command=...`:

```python
            resume_command=SessionResumeCommand("not_detected", None),
            transcript=SessionTranscript(None, False),
```

The remaining five return sites all flow through the `_inspection()` closure.
Compute the transcript once, immediately after the `resume_command` try/except
block ends (line 329) and before `def _inspection(`:

```python
    transcript = _session_transcript(agent, current_id, env, directory)

    def _inspection(
```

and inside that closure's `SessionInspection(...)` call, after
`resume_command=resume_command,`:

```python
            resume_command=resume_command,
            transcript=transcript,
```

- [ ] **Step 9: Update the two direct constructions in existing tests**

`tests/unit/test_session.py` builds `SessionInspection` by hand in two places.
Both now need the new required argument.

At line 132, add `SessionTranscript` to the import list, and after the
`resume_command=...` argument at line 148:

```python
        resume_command=SessionResumeCommand(
            status="available", command="codex resume child -C /tmp"
        ),
        transcript=SessionTranscript(None, False),
    )
```

At line 176, add `SessionTranscript` to that import list too, and after the
`resume_command=...` argument at line 191:

```python
                resume_command=SessionResumeCommand(
                    status="not_detected", command=None
                ),
                transcript=SessionTranscript(None, False),
            ),
```

- [ ] **Step 10: Run the tests to verify they pass**

Run:

```bash
uv run pytest tests/unit/test_session.py -v
```

Expected: PASS, all tests in the file.

- [ ] **Step 11: Commit**

```bash
git add src/agent_fork/session.py tests/unit/test_session.py
git commit -m "feat(session): report the active session's transcript path"
```

---

### Task 4: Print the transcript in CLI output

**Files:**
- Modify: `src/agent_fork/cli.py:176-190` (the `session` subparser description
  and epilog) and `src/agent_fork/cli.py:1101-1107` (immediately after the
  `resume command:` block)
- Test: `tests/cli/test_session.py`

**Interfaces:**
- Consumes: `inspection.transcript` from Task 3 and the existing
  `agent_fork.output.terminal_text()`, already imported in this code path.
- Produces: nothing later tasks import — this is the terminal surface.

- [ ] **Step 1: Write the failing test**

Append to `tests/cli/test_session.py`. The module already imports `json`, `re`,
and `pytest`, and `run_cli` is imported from `conftest` inside each test. If
`from pathlib import Path` is not already at the top of the file, add it.

```python
@pytest.mark.matrix("T-SES-41")
def test_session_outputs_transcript_path_or_unavailable(repo_scenario):
    from conftest import run_cli

    world = repo_scenario()
    env = {
        **world.env,
        "CLAUDECODE": "1",
        "CLAUDE_CODE_SESSION_ID": "claude-child",
    }
    machine = run_cli(["session", "--json"], env, world.parent_path)
    document = json.loads(machine.stdout)
    transcript = document["transcript"]
    assert transcript["exists"] is False
    assert transcript["path"].endswith("/claude-child.jsonl")
    assert "/projects/" in transcript["path"]

    human = run_cli(["session"], env, world.parent_path)
    assert f"transcript: {transcript['path']} (missing)".encode() in human.stdout

    written = Path(transcript["path"])
    written.parent.mkdir(parents=True, exist_ok=True)
    written.write_text("{}\n")
    present = run_cli(["session"], env, world.parent_path)
    assert f"transcript: {transcript['path']} (exists)".encode() in present.stdout

    absent = run_cli(["session"], world.env, world.parent_path)
    assert b"transcript: unavailable" in absent.stdout
    absent_document = json.loads(
        run_cli(["session", "--json"], world.env, world.parent_path).stdout
    )
    assert absent_document["transcript"] == {"path": None, "exists": False}

    unsafe_env = {
        **world.env,
        "CLAUDECODE": "1",
        "CLAUDE_CODE_SESSION_ID": "unsafe\x1b]52;c;Zm9v\x07\nnext\u202e",
    }
    unsafe = run_cli(["session"], unsafe_env, world.parent_path)
    assert b"\x1b" not in unsafe.stdout and b"\x07" not in unsafe.stdout
    assert b"transcript: unavailable" in unsafe.stdout
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
uv run pytest tests/cli/test_session.py::test_session_outputs_transcript_path_or_unavailable -v
```

Expected: FAIL — `KeyError: 'transcript'` on the first JSON lookup.

- [ ] **Step 3: Print the line**

In `src/agent_fork/cli.py`, directly after the `resume command:` block (which
ends with `print(f"resume command: unavailable ({resume_command.status})")`) and
before `return 0`:

```python
            transcript = inspection.transcript
            if transcript.path is None:
                print("transcript: unavailable")
            else:
                state = "exists" if transcript.exists else "missing"
                print(f"transcript: {terminal_text(transcript.path)} ({state})")
```

`terminal_text()` is required here for the same reason the neighbouring
`directory:` line uses it: the path embeds the resolved invocation directory,
which is repository-controlled and may carry terminal control characters.

- [ ] **Step 4: Update the subcommand help**

In `_parser()`, replace the `session` subparser's existing `description` and
`epilog` values with:

```python
        description=(
            "Report agent-neutral current-session evidence, locate its transcript "
            "file, and construct its native fork command and resume (rehydrate) "
            "command without executing either."
        ),
        epilog=(
            "Examples:\n"
            "  agent-fork session          # human inspection, transcript, commands\n"
            "  agent-fork session --json   # exact commands in fork_command.command "
            "and resume_command.command; transcript file in transcript.path\n\n"
            "Command availability means constructible, not preflighted.\n"
            "A transcript path is reported even when the file is not yet on disk; "
            "transcript.exists says which."
        ),
```

- [ ] **Step 5: Run the tests to verify they pass**

Run:

```bash
uv run pytest tests/cli/test_session.py -v
```

Expected: PASS. T-SES-32 asserts the help text's content — if it fails, read its
assertion and reconcile the epilog wording with it rather than weakening the
test.

- [ ] **Step 6: Commit**

```bash
git add src/agent_fork/cli.py tests/cli/test_session.py
git commit -m "feat(cli): print the session transcript path and its on-disk state"
```

---

### Task 5: Bump the version

An additive JSON field is a minor bump, the same contract class as
`resume_command`. `scripts/sync_versions.py` propagates the number to every
pinned site — including `tests/cli/test_cli.py` and
`scripts/check_clean_install.sh`, the file whose hand-missed pin failed CI on
PR #47 — and `just version-check` runs inside `just all`, so drift cannot
survive.

**Files:**
- Modify: `pyproject.toml:3`, `uv.lock`, `tests/cli/test_cli.py:43`,
  `scripts/check_clean_install.sh:12`, `README.md`,
  `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`, and
  `.claude-plugin/marketplace.json` — **eight** sites, all written by the
  command below. (Corrected after the live run: an earlier draft listed only
  the first four. `scripts/sync_versions.py` also syncs both plugin manifests,
  the marketplace listing, and a README version string. Stage all eight or
  `just version-check` fails.)

**Interfaces:**
- Consumes: nothing.
- Produces: version `1.2.0`, cited by the project file written in Task 1.

- [ ] **Step 1: Bump**

Run:

```bash
just bump minor
```

Expected: `git diff --stat` prints changes to `pyproject.toml`, `uv.lock`,
`tests/cli/test_cli.py`, and `scripts/check_clean_install.sh`.

- [ ] **Step 2: Verify every site agrees**

Run:

```bash
just version-check && grep -n 'version = "1.2.0"' pyproject.toml
```

Expected: the check passes and the grep prints line 3.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock tests/cli/test_cli.py scripts/check_clean_install.sh
git commit -m "chore(release): bump 1.1.0 -> 1.2.0 for the additive transcript field"
```

---

### Task 6: Register the test-matrix rows

`scripts/check_matrix.py` requires exactly one collected pytest item per live
row, so the four markers written in Tasks 2-4 need exactly four new rows. The
header's total-row count is part of the gate.

**Files:**
- Modify: `docs/testing/TEST-MATRIX.md:14` (the total) and line 563 (the end of
  the G-SES table)

**Interfaces:**
- Consumes: the marker IDs `T-SES-39`, `T-SES-40`, `T-SES-41`, and `T-SES-42`
  written in Tasks 2, 3, and 4.
- Produces: a clean `just check-matrix`.

- [ ] **Step 1: Add the four rows**

In `docs/testing/TEST-MATRIX.md`, immediately after the `T-SES-38` row on line
563, add:

```markdown
| T-SES-39 | transcript resolution derives the Claude path from identity and directory, discovers the Codex rollout by glob, and reports no path for an unsafe ID or absent identity | baseline | U | live | P05; REQ-47; REQ-50 |
| T-SES-40 | `document()` includes the additive `transcript` object alongside `fork_command` and `resume_command` | agent=claude | U | live | P05; REQ-47; REQ-50 |
| T-SES-41 | JSON reports the additive transcript path/exists object and human output prints an escaped path with its on-disk state or an explicit unavailable line | baseline | C | live | P05; REQ-47; REQ-50; CLI R7.2 |
| T-SES-42 | Codex rollout resolution returns the newest matching rollout file and stays consistent with the existence probe | agent=codex | U | live | P05; REQ-46; REQ-50 |
```

- [ ] **Step 2: Update the total**

On line 14, change `Total rows: 404` to `Total rows: 408`. The rest of that line
is unchanged.

- [ ] **Step 3: Run the gate**

Run:

```bash
just check-matrix
```

Expected: exit 0 with no `CHECK1`/`CHECK2`/`CHECK6`/`CHECK7` complaints. A
`CHECK1: T-SES-NN has 0 collected items` error means a marker string does not
match its row ID exactly.

- [ ] **Step 4: Commit**

```bash
git add docs/testing/TEST-MATRIX.md
git commit -m "docs(testing): register T-SES-39..42 for the transcript path"
```

---

### Task 7: Surface the transcript in the companion skill

**Critical constraint from PR #47's review:** the shared "Validate and present
CLI results" contract block is used by **both** the `--session` and
`--session-only` routes. Requiring a new key there would make `--session-only`
refuse against an older CLI that emits a perfectly valid `fork_command`. That
exact bug shipped and was fixed in `4b215d8`. Scope the `transcript`
requirement to the `--session` route only.

**Files:**
- Modify: `.agents/skills/agent-fork/SKILL.md` — the `--session` route section
  (lines 122-142), the upgrade-path paragraph (lines 333-341), and the route
  field list (lines 355-361)
- Modify: `.agents/skills/agent-fork/references/output-claude.md` — the
  `--session` inspection table and the prose after it
- Modify: `.agents/skills/agent-fork/references/output-codex.md` — same
- Test: `tests/skill/test_companion_skill.py`

**Interfaces:**
- Consumes: the JSON contract from Task 3.
- Produces: no code interface. Skill tests are prose assertions and carry no
  matrix marker, matching how the `resume_command` skill test was added.

- [ ] **Step 1: Write the failing test**

Append to `tests/skill/test_companion_skill.py`, next to
`test_skill_session_route_also_presents_the_resume_command`:

```python
def test_skill_session_route_also_presents_the_transcript_path() -> None:
    text = _text()
    assert "`transcript`" in text
    assert "predates the transcript" in text and "contract" in text
    assert "transcript.path" in text
    assert "transcript.exists" in text
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
uv run pytest tests/skill/test_companion_skill.py::test_skill_session_route_also_presents_the_transcript_path -v
```

Expected: FAIL on the first assertion.

- [ ] **Step 3: Extend the `--session` route section**

In `.agents/skills/agent-fork/SKILL.md`, change the route heading on line 122 to:

```markdown
### Inspect the current agent session and include its transcript, fork, and resume commands
```

Then, after the paragraph ending "report the exact status and null command for
each." (line 142), add:

```markdown
Also present `transcript`: the absolute path of the file where this session's
conversation is stored on disk — a Claude Code JSONL transcript or a Codex
rollout JSONL. When `transcript.path` is a string, show it verbatim under a
clear label and state whether `transcript.exists` is `true` or `false`; a
`false` value means the path is where the transcript belongs but no file is
there yet, which is normal early in a session and also happens when the session
began in a different directory. When `transcript.path` is `null`, report that
the transcript could not be located and do not guess a path. Never read,
summarize, copy, or quote the file's contents — this field is a location only.
```

- [ ] **Step 4: Add the upgrade path**

In the paragraph beginning "If session JSON is otherwise valid but contains no
`fork_command` key" (line 333), replace the sentence

```markdown
Report `Installed agent-fork predates the fork_command contract` (missing
`fork_command`) or `Installed agent-fork predates the resume_command contract`
(missing `resume_command`, `--session` route only), show the upgrade command,
and stop:
```

with

```markdown
Report `Installed agent-fork predates the fork_command contract` (missing
`fork_command`), `Installed agent-fork predates the resume_command contract`
(missing `resume_command`, `--session` route only), or `Installed agent-fork
predates the transcript contract` (missing `transcript`, `--session` route
only), show the upgrade command, and stop:
```

- [ ] **Step 5: Extend the route field list**

In the "Treat exit 0 as success only when" list, replace the Session bullet with:

```markdown
- Session: `agent`, `current_session`, `parent_session`, `lineage`, `notices`,
  `directory`, and `repository` (which may be null), plus `fork_command`; the
  `--session` route additionally requires `resume_command` and `transcript`.
  Each of `fork_command` and `resume_command` must be an object whose `status`
  is exactly `available`, `not_detected`, `ambiguous`, or `unsafe_input`.
  `available` requires a non-empty string `command`; every other status
  requires a null `command`. `transcript` must be an object whose `path` is a
  non-empty string or null and whose `exists` is a boolean; `path: null` with
  `exists: true` is invalid output.
```

- [ ] **Step 6: Add the Claude reference row**

In `.agents/skills/agent-fork/references/output-claude.md`, add a row to the
`--session` inspection table, after the `Status` row:

```markdown
| Transcript | `/Users/dev/.claude/projects/-Users-dev-project/11111111-1111-4111-8111-111111111111.jsonl` (on disk) |
```

And after the resume-command block, before the "Row variants" paragraph, add:

```markdown
The Transcript row is `transcript.path` verbatim; `(on disk)` renders
`transcript.exists: true` and `(not yet written)` renders `false`. When
`transcript.path` is null the row reads `not located`.
```

- [ ] **Step 7: Add the Codex reference row**

In `.agents/skills/agent-fork/references/output-codex.md`, add the equivalent
row to its `--session` inspection table, after the `Status` row:

```markdown
| Transcript | `/Users/dev/.codex/sessions/2026/08/19/rollout-2026-08-19T09-14-02-019fed92-fa7e-7262-b93e-6bd73a38ac72.jsonl` (on disk) |
```

And the same explanatory paragraph, with the Codex-specific caveat:

```markdown
The Transcript row is `transcript.path` verbatim; `(on disk)` renders
`transcript.exists: true` and `(not yet written)` renders `false`. Codex
rollout files are located by search rather than derived, so a Codex
`transcript.path` is never non-null with `exists: false`; an unlocatable
rollout reads `not located`.
```

- [ ] **Step 8: Run the skill tests to verify they pass**

Run:

```bash
uv run pytest tests/skill/ -v
```

Expected: PASS, all tests — including the pre-existing
`test_skill_locks_session_and_fork_command_routes`, which guards the
`--session-only` route's fork-only contract.

- [ ] **Step 9: Commit**

```bash
git add .agents/skills/agent-fork/SKILL.md .agents/skills/agent-fork/references/output-claude.md .agents/skills/agent-fork/references/output-codex.md tests/skill/test_companion_skill.py
git commit -m "docs(skill): present the transcript path on the --session route"
```

---

### Task 8: Document, verify, and close

**Files:**
- Modify: `README.md` — the "Session inspection and validation" section
  (lines 269-305) and the skill-routes table row for `--session`
- Modify: `projects/P05-session-transcript-path.md` — flip every task checkbox
- Modify: `PROJECTS.md` — flip the P05 row glyph to `[x]`

**Interfaces:**
- Consumes: everything from Tasks 1-7.
- Produces: the finished item.

- [ ] **Step 1: Document the field in the README**

In `README.md`, after the `resume_command` bullet and the command-shapes code
block (ending line 296), insert this text (the outer `~~~` fence is not part of
the file):

~~~markdown
Inspection also reports `transcript`: where this session's conversation is
stored on disk.

```text
claude: <CLAUDE_CONFIG_DIR|~/.claude>/projects/<encoded-directory>/<session-id>.jsonl
codex:  <CODEX_HOME|~/.codex>/sessions/<YYYY>/<MM>/<DD>/rollout-<timestamp>-<thread-id>.jsonl
```

`transcript.path` is the absolute path and `transcript.exists` says whether a
file is there right now. The two agents store transcripts differently, and the
difference is visible in the field. The Claude path is *derived* from the
session ID and the resolved invocation directory — every non-alphanumeric
character of that directory becomes `-` — so it can be reported before the file
is flushed, and a session that began in a different directory (a main checkout
inspected from a linked worktree, for example) derives a path under that
original directory and reports `exists: false`. The Codex path is *discovered*
by search, because the rollout filename embeds a timestamp, so a Codex
`transcript.path` is null whenever no rollout matches. A session ID that is not
`[A-Za-z0-9-]+` never reaches the filesystem and reports a null path.
Inspection reports the location only; it never reads the transcript.
~~~

- [ ] **Step 2: Sync the skill-routes table**

In `README.md`, find the skill-routes table row describing `--session` (last
touched in commit `e098408` to mention the resume command) and extend its
description to name the transcript path alongside the fork and resume commands.

- [ ] **Step 3: Run the full gate**

Run:

```bash
make check && just all && just check-matrix
```

Expected: all green. `just all` covers `fmt`, `lint`, `typecheck`,
`version-check`, and the hermetic test suite; the suite should report **five**
more passing tests than before this plan — the four matrix-marked tests plus
the unmarked skill-contract test from Task 7. (Corrected after the live run:
an earlier draft said four, having overlooked that skill tests carry no matrix
marker. Observed: 479 passed, 1 skipped, 9 deselected.)

Also run the wheel-build conformance check, which is neither in `just all` nor
in CI's matrix gate and is what actually failed CI on PR #47:

```bash
just clean-install
```

Expected: exit 0, having built `agent_fork-1.2.0` and smoke-tested the entry
point in a disposable venv.

- [ ] **Step 4: Verify the feature by hand against a real session**

This step needs a real Claude Code session's environment, so it is the owner's
to run — an automated test cannot prove the derived path matches the file the
live agent is actually writing.

Run, from the worktree:

```bash
uv run agent-fork session | grep '^transcript:'
uv run agent-fork session --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["transcript"]["path"])' | xargs ls -l
```

Expected: the printed path ends in `.jsonl`, the `ls -l` succeeds, and the human
line reports `(exists)`. Record the observed path in the project file's Manual
Verification section.

- [ ] **Step 5: Flip the project state**

In `projects/P05-session-transcript-path.md`, change every `- [ ]` task line to
`- [x]`, change the project heading from `## [ ] Project P05:` to
`## [x] Project P05:`, and replace the Manual Verification bullet with what was
actually observed in Step 4. In `PROJECTS.md`, change the P05 row's `- [ ]` to
`- [x]`.

- [ ] **Step 6: Commit and open the pull request**

```bash
git add README.md PROJECTS.md projects/P05-session-transcript-path.md
git commit -m "docs(p05): document the transcript path and close the item"
git push -u origin worktree-p05-session-transcript-path
gh pr create --title "feat(session): report the active session's transcript path" --body "Adds one additive transcript object to agent-fork session — the absolute path and filename of the active session's on-disk transcript, for both Claude Code and Codex — surfaced through the companion skill's --session route.

Both halves of the resolution already existed and were being discarded: _claude_transcript() derived the Claude path to read the session name, and codex_rollout_exists() globbed the Codex rollout as a preflight boolean. This promotes both into a reported value.

--session-only is deliberately untouched, and the new key is required only on the --session route; re-tripping the older-CLI refusal fixed in 4b215d8 would otherwise be the failure mode.

Bumps 1.1.0 -> 1.2.0 (additive JSON field)."
```

---

## Self-Review

**1. Spec coverage.** Every row of the result-contract table maps to an
assertion in the T-SES-39 test (Task 3, Step 1): Claude present, Claude absent,
unsafe ID, Codex hit, Codex miss, no identity, and ambiguous. The human-output
forms map to T-SES-41 (Task 4, Step 1). Owner decision 1 (Codex rollout file) is
Task 2; decision 2 (`--session` only) is Task 7's scoping constraint plus the
untouched `--session-only` route; decision 3 (`path` plus `exists`) is the
`SessionTranscript` shape in Task 3, Step 5; decision 4 produced this plan. Both
documented asymmetries appear in the README (Task 8, Step 1) and in the Codex
reference file (Task 7, Step 7).

**2. Placeholder scan.** No `TBD`, `TODO`, "similar to Task N", or "add error
handling" appears. Every code step carries the literal code. The one step whose
output cannot be predicted — the manual verification against a live session —
states the exact commands and what to record.

**3. Type consistency.**
`codex_rollout_path(context: AgentContext, env: Mapping[str, str]) -> Path | None`
is defined in Task 2 and called with exactly that signature in Task 3, Step 6.
`SessionTranscript(path: Path | None, exists: bool)` is defined in Task 3,
Step 5 and constructed positionally as `SessionTranscript(None, False)` in
Task 3, Steps 8 and 9, and in the tests in Steps 1 and 2. `document()` returns
`{"path": str | None, "exists": bool}` in Step 5 and is asserted in exactly that
shape in Step 2's test and in Task 4's CLI test. `SAFE_SESSION_ID` is defined
once in Step 4 and used in Steps 4 and 6. The field name is `transcript`
everywhere — never `transcript_path`.
