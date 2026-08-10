# agent-fork

`agent-fork` creates a Git branch and linked worktree carrying the current
staged, unstaged, and untracked state, verifies the copy, and prints the exact
command for continuing the current Claude Code or Codex conversation there. In
a normal terminal it creates the same verified branch/worktree and prints a
`cd` command without requiring an agent CLI.

The CLI is implemented for v0.1.0 but remains pre-release until the Phase F
release gate. It requires Python 3.11+ and Git 2.19+. Managed session forks
additionally require Claude Code 2.0.73+ or Codex 0.95+ (Codex native `fork`
itself requires 0.81+).

## Companion skill

The repository includes one canonical Agent Skills artifact at
`.agents/skills/agent-fork`. Codex discovers it there as `$agent-fork`; Claude
Code discovers the same artifact through `.claude/skills/agent-fork` as
`/agent-fork`.

From an active agent session, invoke it with an optional fork name:

```text
$agent-fork my-experiment   # Codex
/agent-fork my-experiment   # Claude Code
```

The skill requires `agent-fork` on `PATH`, delegates all repository mechanics
to `agent-fork fork --json`, and returns a command to paste into a fresh
terminal. Until Phase F publishes v0.1.0, use the CLI from a source checkout.

## Usage

Run inside an agent session or an ordinary terminal:

```bash
agent-fork fork review-auth                 # auto-detect agent or Git-only
agent-fork fork terminal-copy --no-agent    # explicitly Git-only
agent-fork fork session-copy --require-agent
agent-fork fork review-auth --with-ignored
agent-fork fork --no-with-state --dry-run
agent-fork fork review-auth -o json
agent-fork fork experiment --branch review/manual \
  --worktree-base-dir /work/forks --worktree-name 'Manual Worktree'
```

The default `auto` mode detects the agent and parent session from
`CLAUDE_CODE_SESSION_ID` or `CODEX_THREAD_ID`. They can be supplied explicitly:

```bash
agent-fork fork review-auth \
  --agent claude --parent-session '<session-uuid>' \
  --branch review/auth --worktree-dir '../auth-review'
```

`--agent` with an explicit `--parent-session` works without either environment
variable and implies strict agent behavior. `--require-agent` refuses unless a
single usable session is available; `--no-agent` ignores agent signals. Set the
default with `[fork] agent_mode = "auto" | "strict" | "git-only"` or
`AGENT_FORK_AGENT_MODE`.

`--worktree-dir` selects one exact destination. Alternatively,
`--worktree-base-dir` and `--worktree-name` independently replace the parent
and leaf of the configured/default destination and may be combined. An explicit
base must already exist. The exact-path flag cannot be mixed with either partial
override.

Other commands:

```bash
agent-fork list [-o json]
agent-fork cleanup <name|branch|worktree> --yes
agent-fork doctor [-o json]
agent-fork config view|get|set|validate
agent-fork completion bash|zsh|fish
agent-fork help [command]
```

`cleanup` is registry-scoped unless `--force` is used. It refuses dirty or
unpushed worktrees without `--force`, always refuses to remove the invoking
working directory, and requires separate consent via `--yes`. Agent-owned
session files are never removed.

## State and repository behavior

Exact-copy mode is the default. `--no-with-state` creates a clean worktree at
the parent commit. `--with-ignored` additionally copies ignored files and may
therefore copy secret-bearing files such as `.env`; it is deliberately off by
default. The parent worktree and session transcript remain untouched.

`.worktreeinclude` may list ignored files to copy after verification. An
optional `.agent-fork/worktree-setup.sh` runs non-fatally in the new worktree
with `REPO_ROOT` and `WORKTREE_PATH` set.

State is stored under `$XDG_STATE_HOME/agent-fork`; configuration follows the
XDG/project precedence documented in [REQUIREMENTS.md](REQUIREMENTS.md).

## Compatibility policy

The v1 JSON result schema is open and stable within major version 0/1 as
documented in [REQUIREMENTS.md](REQUIREMENTS.md). Incompatible CLI or schema
changes require a major version change; compatible additions may appear in a
minor release. Deprecated interfaces will be documented before removal.

## Error catalog

Machine-format failures use `{"error":{"code","message"}}` on stderr. Codes
are stable compatibility identifiers; messages may gain detail without changing
their meaning.

| Exit | Codes |
|---|---|
| 1 | `runtime_error`, `verify_failed`, `registry_busy` |
| 2 | `config_error` |
| 3 | `agent_not_detected`, `session_not_found`, `cleanup_target_unknown` |
| 5 | `conflict_branch_exists`, `conflict_branch_worktree`, `conflict_worktree_path`, `parent_mid_operation`, `repo_no_commits`, `unmerged_index`, `not_git_repository`, `git_version_unsupported`, `invalid_branch`, `invalid_worktree_base`, `invalid_worktree_name`, `cleanup_target_is_cwd`, `cleanup_dirty_worktree`, `cleanup_unpushed_commits` |

Exit 4 remains reserved because this local tool has no authentication failure
class. SIGINT and SIGTERM exit 130 and 143 after rollback where applicable.

## Development

```bash
make check
flox activate
just all
just check-matrix
just clean-install
```

The design and evidence corpus is in [DESIGN-DECISIONS.md](DESIGN-DECISIONS.md),
[REQUIREMENTS.md](REQUIREMENTS.md), [EXPERIMENTS.md](EXPERIMENTS.md), and
[CONFORMANCE.md](CONFORMANCE.md).

## Telemetry and networking

None. `agent-fork` makes no runtime network calls and collects no data. Git
operations against already configured local repository metadata remain local;
package managers own installation and updates.

## License

MIT
