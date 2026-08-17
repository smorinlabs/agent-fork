# agent-fork

**Forking a session is easy; forking your files isn't. This Claude Code /
Codex skill gives the forked session its own branch and worktree with every
uncommitted file copied and verified.**

[![CI](https://github.com/smorinlabs/agent-fork/actions/workflows/ci.yml/badge.svg)](https://github.com/smorinlabs/agent-fork/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](https://github.com/smorinlabs/agent-fork/blob/main/LICENSE)

You are deep in a Claude Code or Codex session. The agent has context you do not
want to rebuild, and your working tree is full of uncommitted work. Now you want
to try a *second* approach — without stashing, without losing the first one, and
without starting the conversation over.

The `agent-fork` skill does that without leaving the conversation. Type
`/agent-fork try-redis` (Claude Code) or `$agent-fork try-redis` (Codex) and it
creates a new branch and a linked Git worktree, copies your current staged,
unstaged, and untracked files into it, verifies the copy matched, and prints
the exact command that continues *this conversation* in that new worktree. Your
original worktree and session are never touched.

Underneath the skill is a standalone `agent-fork` CLI that does the same work
from any terminal. Outside an agent session it prints a `cd` command instead of
a session-continuation command, so the same tool covers plain Git workflows.

## Demo

From inside your agent session:

```text
/agent-fork try-redis       # Claude Code — fork without leaving the conversation
$agent-fork try-redis       # Codex — same skill, same behavior
```

The skill previews the fork — target branch, destination worktree, the files it
would carry — and asks for confirmation before creating anything. It drives the
CLI below, which works directly from a terminal too:

```console
$ agent-fork fork try-redis --dry-run
branch: create fork/try-redis
worktree: create /Users/you/code/myapp-fork-try-redis
files-to-carry: staged=3 unstaged=7 untracked=2 ignored=0
paste command: cd /Users/you/code/myapp-fork-try-redis && claude --session-id 9b74b9f2-f3d2-4060-b233-0121ac17ed7c --resume c854b79c-16b2-4863-a095-03d35d195ec9 --fork-session -n try-redis
validation: local-only; no mutation performed
```

Drop `--dry-run` and the fork is created. Paste the final line into a fresh
terminal and the agent picks up where it left off — same context, new branch,
your uncommitted work already there.

## The skill

The full set of skill invocations:

```text
/agent-fork try-redis       # Claude: explicit fork name
$agent-fork try-redis       # Codex: explicit fork name
/agent-fork try-redis --now  # Claude: fork immediately, no confirmation
$agent-fork try-redis --now  # Codex: fork immediately, no confirmation
/agent-fork                 # fork with context-aware naming
/agent-fork --session       # Claude: inspect this agent session
$agent-fork --session       # Codex: inspect this agent session
/agent-fork --session-only  # Claude: print only the native session-fork command
$agent-fork --session-only  # Codex: print only the native session-fork command
```

The skill calls the installed CLI directly. When that CLI is missing, it prints
the source install command and, if it can confirm a local checkout of this
repository, offers to run the same route from it under `uv run --directory`
after asking first. Both inspection forms use
`agent-fork session --json`; `--session` includes the returned native fork
command with the inspection, while `--session-only` prints only that exact
command. Forking uses
`agent-fork fork ... --require-agent --json`. An explicit name hint is
normalized to lowercase kebab case. With no
name, a topic branch uses the CLI's date-bearing automatic name and collision
suffixes, and a default, detached, or unclassified branch gets a name proposed
from the conversation. Every fork is then confirmed against a dry run — showing
the target branch, the destination worktree, and the files it would carry —
before anything is created. `--now` skips that confirmation without changing
how the name is chosen. Advanced CLI flags are intentionally direct-CLI use
cases rather than skill arguments. The two inspection forms infer the base
directory from the active agent session; they do not accept a directory option.

The skill lives at one canonical Agent Skills artifact,
`.agents/skills/agent-fork`. Codex discovers it there as `$agent-fork`; Claude
Code discovers the same artifact through `.claude/skills/agent-fork` as
`/agent-fork`.

## Install

Install the CLI:

```bash
uv tool install git+https://github.com/smorinlabs/agent-fork
```

Or run it without installing:

```bash
uvx --from git+https://github.com/smorinlabs/agent-fork agent-fork --version
```

> PyPI and Homebrew releases land with v1.0.0.

**Requirements:** Python 3.11+ and Git 2.19+. Forking an agent session
additionally needs Claude Code 2.0.73+ or Codex 0.95+ (Codex's native `fork`
itself requires 0.81+). Run `agent-fork doctor` to check all of this at once.

### Install the skill

The skill ships in this repository. Clone it, then symlink the canonical
artifact into the user-level skill directories for both agents:

```bash
git clone https://github.com/smorinlabs/agent-fork
cd agent-fork
mkdir -p ~/.claude/skills ~/.agents/skills
ln -sfn "$PWD/.agents/skills/agent-fork" ~/.claude/skills/agent-fork
ln -sfn "$PWD/.agents/skills/agent-fork" ~/.agents/skills/agent-fork
```

Claude Code then discovers it as `/agent-fork` and Codex as `$agent-fork`.

### Local development installation

Run these commands from the repository root before registry publication. The
editable `uv` tool install keeps the command connected to this checkout; skill
placement uses the same two symlinks shown above.

```bash
uv tool install --editable --force .
mkdir -p ~/.claude/skills ~/.agents/skills
ln -sfn "$PWD/.agents/skills/agent-fork" ~/.claude/skills/agent-fork
ln -sfn "$PWD/.agents/skills/agent-fork" ~/.agents/skills/agent-fork
```

Verify the installed version and both placements:

```bash
agent-fork --version
readlink ~/.claude/skills/agent-fork ~/.agents/skills/agent-fork
```

The version command must print `agent-fork 1.0.0`. Both symlinks must resolve
to this repository's `.agents/skills/agent-fork` directory.

## Quickstart

```bash
agent-fork doctor              # confirm Git, agent CLIs, config, and XDG paths
agent-fork fork try-redis      # create the fork, print the paste command
agent-fork session             # inspect context and print a native fork command
agent-fork list                # see the forks you have created
agent-fork cleanup try-redis --yes   # remove one when you are done
```

## How it works

1. **Detect** the agent and parent session from `CLAUDE_CODE_SESSION_ID` or
   `CODEX_THREAD_ID` — or accept both explicitly as flags.
2. **Anchor** to the parent's current commit and create the fork branch.
3. **Create** a linked Git worktree at the destination.
4. **Copy** staged, then unstaged, then untracked files into it, preserving
   symlinks and the executable bit.
5. **Verify** that the new worktree's Git-visible state matches what was
   promised. A failed check rolls the fork back and reports exactly what to do.
6. **Emit** the launch command for the detected agent, and record the fork in a
   local registry so `list` and `cleanup` can find it later.

Why not just `git worktree add`? That gives you an empty worktree at `HEAD`.
`agent-fork` carries your uncommitted work across, proves the copy is faithful,
rolls back cleanly when it is not, and continues the agent conversation rather
than starting a new one.

## Command reference

| Command | Purpose |
|---|---|
| `agent-fork fork [NAME]` | Create a verified branch and worktree; print the paste command |
| `agent-fork session [validate]` | Inspect session evidence, construct its native fork command, or assert expected identity and lineage |
| `agent-fork list` | List forks created by `agent-fork` |
| `agent-fork cleanup <name\|branch\|worktree> --yes` | Remove a registered fork |
| `agent-fork doctor` | Diagnose Git, agent, config, and XDG readiness |
| `agent-fork config view\|get\|set\|validate` | Inspect or update configuration |
| `agent-fork completion bash\|zsh\|fish` | Generate a shell completion script |
| `agent-fork help [command]` | Show help for a command |

Global options: `-V/--version`, `-v/--verbose`, `-q/--quiet`, `--debug`, and
`--config PATH`. Commands that emit formatted results (`fork`, `list`,
`session`, `cleanup`, `doctor`, and `config view`) accept
`-o/--output {table,text,json}`; `--json` is an alias for `-o json`.

`cleanup` is registry-scoped unless `--force` is used. It always inspects the
target for uncommitted changes and commits that are not reachable from a remote.
Without the matching override, it refuses and lists up to 10 at-risk paths or
commits before reporting how many additional entries were omitted. Untracked
paths are grouped separately from modified paths.

`--force` keeps its 1.x behavior: it extends targeting beyond registered forks
and overrides both Git safety guards. `--allow-dirty` and `--allow-unpushed`
override only their named guard. None of these flags replaces consent via
`--yes`, and none overrides the refusal to remove the invoking working
directory. Agent-owned session files are never removed.

## Session inspection and validation

Use the same interface inside Claude Code or Codex:

```bash
agent-fork session
agent-fork session -o json
agent-fork session validate --agent codex --has-parent
agent-fork session validate \
  --session-id "$EXPECTED_CHILD" \
  --parent-session-id "$EXPECTED_PARENT" -o json
```

Inspection reports sourced evidence, the resolved invocation directory, and
nullable Git repository context. Repository context includes the worktree root,
branch or detached state, remote/default-branch candidates, default membership,
linked/bare topology, and clean/staged/unstaged/untracked/unmerged/operation
status. A bare repository has null working-tree status. Outside Git—or when Git
context is unavailable—the session evidence remains usable and `repository` is
null. Inspection also reports `fork_command`: one detected Claude Code or Codex
identity produces a shell-quoted native command using the resolved invocation
directory. Claude receives a fresh, single-use child UUID. No identity,
ambiguous identity, or terminal-unsafe identity/path data produces an explicit
unavailable status and a null command. Inspection succeeds with `not_detected`
in an ordinary terminal.

The native session commands have these shapes:

```text
cd '<resolved-directory>' && claude --session-id '<fresh-child-uuid>' --resume '<current-session-id>' --fork-session
codex fork '<current-thread-id>' -C '<resolved-directory>'
```

`available` means the command was constructible from ambient identity; it does
not run native CLI preflight. Use `agent-fork fork` when you need the supported
version and Codex-rollout checks before repository mutation. The ordinary
session command and both skill inspection forms never execute the returned
command, create a branch or worktree, copy files, write registry or lineage
state, or touch the clipboard. There is no direct CLI `--session-only` flag;
that spelling is a companion-skill presentation shortcut over the JSON field.

Validation without constraints requires any unambiguous supported current
session. Optional `--agent`, `--session-id`, `--parent-session-id`, and
`--has-parent`/`--no-parent` assertions compose with AND semantics.

Parent means parent evidence, not proof that a transcript still exists. Codex
name and parent evidence comes from its bounded local app-server. Agent
Fork-created Claude children retain a prompt-free XDG provenance claim because
Claude transcripts do not preserve the source session UUID. Missing evidence
is not proof that a session was never forked. Inspection makes no network calls
and does not modify agent or repository state.

### Claude parent inference

Claude does not expose an authoritative historical parent ID for ordinary
forks. An explicit, potentially expensive structural analysis can infer likely
relationships from copied message UUID/`parentUuid` ancestry:

```bash
agent-fork session claude-parent infer --current
agent-fork session claude-parent infer --session-id UUID -o json
agent-fork session claude-parent infer --session-id UUID --record
agent-fork session claude-parent infer --all
agent-fork session claude-parent infer --all --record-all
agent-fork session claude-parent list
agent-fork session claude-parent show --session-id UUID
agent-fork session claude-parent delete --session-id UUID --source inferred --yes
```

Exactly one of `--current`, `--session-id`, or `--all` is required. Preview is
read-only. `--record` is single-target only; bulk persistence requires the
deliberate `--record-all` spelling. Delete removes only Agent Fork metadata,
never Claude transcripts, history, sessions, Git branches, or worktrees. It
prompts only in interactive human mode; use `--yes` for automation, while
`--no-input` makes missing consent fail immediately. Bulk JSON remains one
document and uses bounded per-target candidate projections.

Analysis uses a bounded manifest, superficial streaming UUID screens, exact
candidate parsing, and bounded graph comparison. Cache shards live under
`$XDG_CACHE_HOME/agent-fork/claude-lineage-index-v2/`; unchanged unrelated
transcripts are not reread on warm lookup. Inferred records live separately at
`$XDG_STATE_HOME/agent-fork/session-lineage-inferences.json`. Neither cache nor
state stores prompt/response content, although session IDs and UUID correlation
remain sensitive local metadata.

`inferred` and `strongly_inferred` are evidence labels, not proof of immediate
parentage. Same-boundary siblings remain ambiguous regardless of timestamps.
Recorded freshness means `current_at_last_analysis`: the analyzed source files,
algorithm version, index generation, and target-specific candidate-universe
digest are retained, but ordinary `session`, `list`, and `show` never rescan the
Claude corpus and therefore do not claim global currentness. A later explicit
inference refresh can detect relevant candidate-universe changes. Stale records
remain manageable with `list`/`show` but are not used as parent evidence. This
heuristic relies on observed Claude transcript structure, not a documented
Anthropic lineage API.

## `cleanup` options

| Flag | Effect |
|---|---|
| `TARGET` | Select a fork by registered name, branch, or worktree path |
| `--force` | Allow an unregistered target and override both the dirty and unpushed guards |
| `--allow-dirty` | Override only the guard against uncommitted changes |
| `--allow-unpushed` | Override only the guard against commits absent from every remote |
| `--keep-branch` | Remove the worktree but preserve its branch |
| `--yes` | Supply non-interactive consent; it does not override safety guards |
| `--no-input` | Never prompt; fail unless required consent was supplied with `--yes` |
| `--dry-run` | Run the full safety inspection and preview removal without mutating |
| `-o/--output {table,text,json}` | Select the result format |
| `--json` | Alias for `--output json` |

Examples:

```bash
agent-fork cleanup review-auth --dry-run
agent-fork cleanup review-auth --allow-dirty --yes
agent-fork cleanup ../unregistered-worktree --force --dry-run
agent-fork cleanup review-auth --force --dry-run --json
```

A human forced preview writes its removal plan to stdout and its at-risk warning
to stderr. A JSON guard refusal places `details` inside the stderr error object;
a JSON dry-run result places the same object at the top level on stdout:

```json
{
  "dirty": [
    {"status": " M", "path": "tracked.txt"},
    {"status": "??", "path": "important_untracked.txt"}
  ],
  "dirty_count": 2,
  "dirty_truncated": false,
  "unpushed": [
    {"sha": "a1b2c3d", "subject": "wip: parser rewrite"}
  ],
  "unpushed_count": 1,
  "unpushed_truncated": false
}
```

Each array contains at most 10 entries. Its `*_count` field reports the complete
count, and its `*_truncated` field is `true` when additional entries were
omitted. Human diagnostics render backslashes, terminal control characters, and
undecodable path bytes as visible C-style escapes such as `\\x1b`; structured
JSON retains the underlying string values. Dry runs that find overridden risk
still exit `0`; a dirty or unpushed guard refusal exits `5`.

## `fork` options

| Flag | Effect |
|---|---|
| `NAME` | Fork identity; derived from the current branch when omitted |
| `--agent {claude,codex}` | Host agent; detected when omitted |
| `--parent-session ID_OR_NAME` | Parent session/thread UUID, or a renamed Codex session name |
| `--require-agent` | Refuse unless a single usable agent session is available |
| `--no-agent` | Ignore agent signals; create only the branch and worktree |
| `--branch BRANCH` | Explicit fork branch name |
| `--worktree-dir PATH` | Use this exact worktree destination |
| `--worktree-base-dir DIR` | Replace only the derived parent directory |
| `--worktree-name COMPONENT` | Replace only the derived directory name |
| `--with-state` / `--no-with-state` | Carry staged, unstaged, and untracked state (default: enabled) |
| `--with-ignored` / `--no-with-ignored` | Also carry ignored files (default: disabled) |
| `--verify` / `--no-verify` | Verify the completed fork (default: enabled) |
| `--codex-session-name-resolution` / `--no-codex-session-name-resolution` | Resolve renamed Codex sessions (default: enabled) |
| `--force` | Override only the Git-version floor |
| `--dry-run` | Preview every planned mutation without changing anything |
| `--copy` / `--no-copy` | Copy the paste command to the clipboard |

Examples:

```bash
agent-fork fork review-auth                 # auto-detect agent or Git-only
agent-fork fork terminal-copy --no-agent    # explicitly Git-only
agent-fork fork session-copy --require-agent
agent-fork fork review-auth --with-ignored
agent-fork fork --no-with-state --dry-run
agent-fork fork --no-with-state --dry-run -o json
agent-fork fork review-auth -o json
agent-fork fork experiment --branch review/manual \
  --worktree-base-dir /work/forks --worktree-name 'Manual Worktree'
```

Dry-run JSON is a preview schema rather than a completed-fork result. It sets
`dry_run: true` and reports the planned branch and worktree creates, staged,
unstaged, untracked, and ignored file counts, the paste command, notices,
local validation status, and `mutation_performed: false`.

The default `auto` mode detects the agent and parent session from
`CLAUDE_CODE_SESSION_ID` or `CODEX_THREAD_ID`. They can be supplied explicitly:

```bash
agent-fork fork review-auth \
  --agent claude --parent-session '<session-uuid>' \
  --branch review/auth --worktree-dir '../auth-review'

# A renamed Codex thread can be supplied instead of its UUID.
agent-fork fork review-auth \
  --agent codex --parent-session 'hello-codex' --dry-run
```

`--agent` with an explicit `--parent-session` works without either environment
variable and implies strict agent behavior. `--require-agent` refuses unless a
single usable session is available; `--no-agent` ignores agent signals. Set the
default with `[fork] agent_mode = "auto" | "strict" | "git-only"` or
`AGENT_FORK_AGENT_MODE`.

### Choosing where the worktree lands

`--worktree-dir` selects one exact destination. Alternatively,
`--worktree-base-dir` and `--worktree-name` independently replace the parent and
leaf of the configured/default destination and may be combined. An explicit base
must already exist. The exact-path flag cannot be mixed with either partial
override.

### Renamed Codex sessions

Codex stores a rename separately from the rollout filename, so a name such as
`hello-codex` cannot be used directly with `codex fork`. When an explicit Codex
parent is not a UUID, `agent-fork` asks the installed local Codex app-server for
exact name matches, replaces the name with the canonical thread UUID, verifies
that UUID's rollout is present, and emits the normal
`codex fork <uuid> -C <worktree>` command. UUID input bypasses this lookup. The
lookup is local and bounded; `agent-fork` never reads Codex's internal SQLite
database directly.

Name resolution is enabled by default. Disable it for a strict UUID-only path
with `--no-codex-session-name-resolution`, or persist that choice:

```toml
[agents.codex]
session_name_resolution = false
```

The corresponding config key is `agents.codex.session_name_resolution`. With
resolution disabled, a non-UUID Codex parent is rejected before repository
mutation. Missing and duplicate names are also rejected; duplicate diagnostics
list the candidate UUIDs. This option is intentionally Codex-specific. If
another agent later needs the same facility, a future design may add a generic
option while retaining this name as a compatible alias.

## Configuration

Configuration is TOML, discovered per the XDG/project precedence documented in
[REQUIREMENTS.md](https://github.com/smorinlabs/agent-fork/blob/main/REQUIREMENTS.md).
`--config PATH` replaces discovery entirely. State — the fork registry backing
`list` and `cleanup` — lives under `$XDG_STATE_HOME/agent-fork`.

| `[fork]` key | Default | Environment variable | Notes |
|---|---|---|---|
| `with_state` | `true` | — | Carry staged, unstaged, and untracked files |
| `with_ignored` | `false` | — | Also carry ignored files; implies `with_state` |
| `branch_prefix` | `"fork/"` | — | Whitespace falls back to the default |
| `worktree_location` | `"sibling"` | — | `sibling`, `central` (XDG data), `subdirectory`, or a path template |
| `agent_mode` | `"auto"` | `AGENT_FORK_AGENT_MODE` | `auto`, `strict`, or `git-only` |
| `verify` | `true` | — | Run the verification ladder |
| `copy` | `false` | — | Copy the paste command to the clipboard |
| `output` | `"table"` | `AGENT_FORK_OUTPUT` | `table`, `text`, or `json` |

Per-agent tables append arguments to the emitted command, each element
individually shell-quoted:

```toml
[agents.claude]
extra_args = []

[agents.codex]
extra_args = []
session_name_resolution = true
```

`AGENT_FORK_CONFIG` selects a config file, equivalent to `--config`.

An explicit flag beats config **and** suppresses dependent config settings — a
config `with_ignored = true` combined with `--no-with-state` carries no state.

### Repository hooks

`.worktreeinclude` may list ignored files to copy after verification. An
optional `.agent-fork/worktree-setup.sh` runs non-fatally in the new worktree
with `REPO_ROOT` and `WORKTREE_PATH` set.

## Safety and guarantees

- **Your parent worktree and session transcript are never modified.** The fork
  is additive.
- **Verification is on by default.** A failed check rolls the fork back and
  reports the exact manual recovery steps.
- **Ignored files stay put unless you ask.** `--with-ignored` may copy
  secret-bearing files such as `.env` between working trees, which is precisely
  why it is off by default.
- **`cleanup` is deliberately hard to misuse.** It is registry-scoped and
  refuses dirty or unpushed worktrees unless `--force` or the matching granular
  override is supplied. It always refuses to delete the directory you are
  standing in and requires separate consent through `--yes`. Agent-owned
  session files are never removed.
- **Interrupts are handled.** SIGINT and SIGTERM exit 130 and 143 after rollback
  where applicable.
- **No network, no telemetry.** `agent-fork` makes no runtime network calls and
  collects no data. Git operations against already-configured local repository
  metadata remain local; package managers own installation and updates.

## Compatibility policy

The v1 JSON result schema is open and stable within major version 1 as documented
in
[REQUIREMENTS.md](https://github.com/smorinlabs/agent-fork/blob/main/REQUIREMENTS.md).
Incompatible CLI or schema changes require a major version change; compatible
additions may appear in a minor release. Deprecated interfaces will be
documented before removal.

## Exit codes and error catalog

Under any machine format, a failure prints a single error object on stderr:

```json
{"error":{"code":"config_error","message":"cannot discover project config: /tmp/notrepo is not a worktree"}}
```

Codes are stable compatibility identifiers; messages may gain detail without
changing their meaning. Error objects may add a documented `details` object;
cleanup guard refusals use the cleanup schema shown above.

| Exit | Meaning | Codes |
|---|---|---|
| 0 | Success | — |
| 1 | Runtime or verification failure | `runtime_error`, `verify_failed`, `registry_busy` |
| 2 | Usage error or required prompt disabled | `config_error` |
| 3 | Agent, session, assertion, or target not found | `agent_not_detected`, `session_not_found`, `session_name_ambiguous`, `session_resolution_unavailable`, `session_validation_failed`, `cleanup_target_unknown` |
| 5 | Conflict or precondition refusal | `conflict_branch_exists`, `conflict_branch_worktree`, `conflict_worktree_path`, `parent_mid_operation`, `repo_no_commits`, `unmerged_index`, `not_git_repository`, `git_version_unsupported`, `invalid_branch`, `invalid_worktree_base`, `invalid_worktree_name`, `cleanup_target_is_cwd`, `cleanup_dirty_worktree`, `cleanup_unpushed_commits` |
| 130 / 143 | Interrupted by SIGINT / SIGTERM | — |

Exit 4 remains reserved because this local tool has no authentication failure
class.

## Development

The default gate is hermetic: it excludes authenticated real-agent tests and
the two process-group signal tests that require an unrestricted runner.

```bash
make check         # environment and dependency preflight
flox activate
just all
just check-matrix
just strict-collect
just clean-install
just test-git-matrix
```

`just test-git-matrix` runs the intent-to-add compatibility gate with macOS
Apple Git and the GNU Git pinned by Flox. Linux runs use the system Git and the
same Flox Git.

Flox owns the reproducible Python, Git, and test toolchain. Claude Code and
Codex remain host-managed prerequisites because their release cadence and
platform availability differ from the four-system Flox environment, including
Intel macOS. Install and update those CLIs with their native package managers.

Run the external-capability gates explicitly:

```bash
just test-live       # real Claude and Codex calls; may consume account quota
just test-signals    # unrestricted process-group signaling; Linux CI owns this
```

`just test-live` first prints the selected path, resolved path, and version for
both host CLIs. It stops before pytest unless both are installed and
authenticated, `~/.claude` and `~/.codex` are writable, and the Anthropic and
ChatGPT endpoints are reachable. A failed real-agent command includes its
captured stdout and stderr. Override only the network probe hosts with
`AGENT_FORK_LIVE_NETWORK_HOSTS=host1,host2` when an approved provider or proxy
uses different endpoints.

The design and evidence corpus is in [DESIGN-DECISIONS.md](DESIGN-DECISIONS.md),
[REQUIREMENTS.md](REQUIREMENTS.md), [EXPERIMENTS.md](EXPERIMENTS.md), and
[CONFORMANCE.md](CONFORMANCE.md).

## Telemetry and networking

None. `agent-fork` makes no runtime network calls and collects no data. Git
operations against already configured local repository metadata remain local;
package managers own installation and updates. The explicit `just test-live`
development gate is separate from the product runtime and calls the installed
Claude and Codex CLIs after its network/authentication preflight.

## License

MIT
