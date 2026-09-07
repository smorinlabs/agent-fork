# Agent Fork skill recovery verification

Verified on 2026-09-06 against base commit
`8cc36b03bb8e16b876b0559d806155e83212275d`.

The owner approved automatic execution of the official-source CLI when the
installed CLI is missing or lacks a field needed by the requested route.
The assistant uses `uvx`, with `uv tool run` as its fallback, and retains one
source commit and runner through the operation. Permanent installation remains
available when requested or already authorized. Network fetching alone adds
no confirmation question. Actual environment permissions still apply.

The implementation updates the [skill](../../.agents/skills/agent-fork/SKILL.md),
its [runner procedure](../../.agents/skills/agent-fork/references/cli-runner.md),
[requirements](../../REQUIREMENTS.md), and [README](../../README.md).
REQ-02, REQ-05, REQ-49, and REQ-50 now agree on provisioning and recovery.
CLI runtime code and fork authorization rules are unchanged.

## Automated checks

Run from this checkout with the development dependencies installed:

```bash
uv run pytest tests/skill -o addopts= -q
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run python scripts/check_matrix.py
uv run python scripts/sync_versions.py --check
git diff --check
```

The skill suite passed all 31 tests. Ruff, formatting, type checking, test
matrix validation, version synchronization, and whitespace checks passed.
These are the checks relevant to the skill patch; the complete CLI runtime
suite was not rerun.

[test_runner_behavior.py](../../tests/skill/test_runner_behavior.py) executes
the documented commands with real `uv` and disposable, offline sources:

- The `uv run --project` example invokes the real session CLI from a separate
  checkout whose path contains spaces and an apostrophe. Both `directory`
  and `repository.root` identify the active repository.
- The original `--directory` command is an inverse control: it reports the
  code checkout instead. Against the original skill, the directory tests
  produced one failure and one pass. With the patch, all four runner tests
  pass. The test therefore detects the original defect.
- Both temporary runners receive inspection, preview, and fork arguments
  through the same selected source. The fallback test has no `uvx` on PATH.
  Installed and cached fixtures advertise the same version as the selected
  source, but omit `transcript`. The selected source supplies it, and installed
  tool and executable snapshots remain unchanged.

Temporary-runner tests substitute local wheels for the Git source. Their
recording CLI verifies process arguments, source selection, and directory
behavior; it does not create real forks. A separate audit probe successfully
ran `uvx --isolated --from` against the official Git source pinned to the base
commit above, returned the active directory and `transcript`, and left the
existing global CLI unchanged. That probe covers fetching and inspection,
not a real fork.

## Independent agent evaluations

Fresh agents received the changed skill, a user request, and a PATH containing
only recording fixtures plus standard system utilities. They did not receive
the expected result, audit, fixture implementation, or other agents' findings.
The supervisor inspected recorded commands and final responses afterward.

| Scenario | Observed result |
|---|---|
| Missing CLI, `--session` | Resolved the official commit and completed inspection through pinned `uvx`, without an installation or question. |
| CLI missing `transcript`, `--session` | Inspected the installed CLI once, recovered once through pinned `uvx`, and completed inspection. |
| Only `uv` available | Completed inspection through pinned `uv tool run`. |
| `--session-only`, no `transcript` | Used the installed CLI and returned only its exact fork command; no recovery. |
| Missing CLI, `demo --now` | Used the same pinned `uvx` prefix for inspection and the authorized mock fork; no dry run or extra question. |
| Authorized upgrade, compatible executable shadows installation | Installed the pinned source, found the managed executable through `uv tool dir --bin`, reported the PATH conflict, and inspected through the installed absolute path. |
| Invalid present command status plus missing `transcript` | Reported invalid JSON output without fetching or retrying. |
| Reported directory differs from invocation directory | Reported `Agent-fork invocation directory mismatch` and stopped before presenting session results or attempting a fork. |

All eight evaluations matched these expectations. They exercise agent
decisions and command selection through inert tools, not real installations,
forks, or environment approval denials. No evaluation claimed a blocked real
execution as a successful operation.

The reusable fixture factory is
[recovery_fixture.py](../../tests/skill/recovery_fixture.py). For example,
prepare an independent stale-CLI evaluation from the checkout root:

```bash
uv run python - <<'PY'
import runpy
import tempfile
from pathlib import Path

create_fixture = runpy.run_path('tests/skill/recovery_fixture.py')['create_fixture']
directory = Path(tempfile.mkdtemp(prefix='agent-fork-skill-eval-')) / 'stale'
active = create_fixture(directory, 'stale', Path.cwd() / '.agents/skills/agent-fork')
print(f'Working directory: {active}')
print(f'PATH: {directory / "bin"}:/usr/bin:/bin')
PY
```

Give a fresh evaluator the request `$agent-fork --session`, the printed working
directory, and the copied skill path. Require every shell call to use that
directory, the printed PATH, and `login=False`. Let it read only the skill and
referenced instructions. Keep fixture code, configuration, logs, and expected
answers hidden until it finishes. Then inspect the fixture directory's
`calls.jsonl` and the evaluator's answer. Installs and forks in this fixture
are recorded actions with no host installation or worktree mutation.

## Loader checks and limits

`skillsmith verify .agents/skills/agent-fork --deep --strict --json` was run
with Skillsmith 0.7.1. Its individual results were:

- Claude Code 2.1.263: static validation and deep skill loading passed.
- Codex adapter: static manifest validation passed, but its deep check
  returned `status: error`, `skipReason: exec-error`, and no verdict. The
  process exited 4 even though the top-level summary said `pass`. The same
  adapter error occurred against the unchanged base skill.

A separate native Codex 0.142.5 app-server probe completed `initialize` and
`skills/list` with the changed checkout in `cwds` and `forceReload: true`.
It returned exactly the changed `SKILL.md` as an enabled repository skill,
with no loader errors. It started no model turn. The shell sandbox prevented
app-server startup; the bounded probe succeeded through the environment's
approval mechanism, with temporary database and log directories. The
`sqlite_home` and `log_dir` overrides are documented in the
[Codex configuration reference](https://developers.openai.com/codex/config-reference/).

Native discovery establishes that Codex loads the changed artifact. It does
not turn the verifier adapter error into a pass or prove behavior for every
model. Plugin packaging migration, skill activation in the live checkout,
release/version changes, and the verifier adapter itself are outside this
patch.
