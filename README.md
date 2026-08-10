# agent-fork

`agent-fork` creates a Git branch and linked worktree carrying the current
staged, unstaged, and untracked state, verifies the copy, and prints the exact
command for continuing the current Claude Code or Codex conversation there.

The CLI is implemented for v0.1.0 but remains pre-release until the Phase F
release gate. It requires Python 3.11+, Git 2.19+, Claude Code 2.0.73+ or Codex
0.95+ (Codex native `fork` itself requires 0.81+).

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

Run inside the agent session whose conversation should be forked:

```bash
agent-fork fork review-auth
agent-fork fork review-auth --with-ignored
agent-fork fork --no-with-state --dry-run
agent-fork fork review-auth -o json
```

The agent and parent session are normally detected from
`CLAUDE_CODE_SESSION_ID` or `CODEX_THREAD_ID`. They can be supplied explicitly:

```bash
agent-fork fork review-auth \
  --agent claude --parent-session '<session-uuid>' \
  --branch review/auth --worktree-dir '../auth-review'
```

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
