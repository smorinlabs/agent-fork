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

From inside your Claude Code or Codex session:

```text
/agent-fork try-redis       # fork without leaving the conversation
```

Don't have the skill yet? One command installs it for both agents:

```bash
npx skills@latest add smorinlabs/agent-fork
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
/agent-fork try-redis       # explicit fork name
/agent-fork try-redis --now # fork immediately, no confirmation
/agent-fork                 # fork with context-aware naming
/agent-fork --session       # inspect this agent session
/agent-fork --session-only  # print only the native session-fork command
```

Codex invokes the same skill as `$agent-fork`; every form above is otherwise
identical.

The skill is a thin front end over the installed CLI — each form maps to one
CLI call:

| Skill form | CLI call | Result |
|---|---|---|
| The fork forms | `agent-fork fork ... --require-agent --json` | The branch, the worktree, and the paste command |
| `--session` | `agent-fork session --json` | The session inspection plus its native fork and resume commands |
| `--session-only` | `agent-fork session --json` | Only that native fork command |

The fork's name comes from one of three places:

- A name hint you typed is normalized to lowercase kebab-case
  (`"Review Auth"` becomes `review-auth`).
- With no hint on a topic branch — an ordinary feature branch — the CLI
  derives the name automatically (dated, with a suffix if it collides).
- With no hint on the default branch, a detached HEAD, or an unclassifiable
  branch, the skill proposes a name from the conversation.

Every fork is confirmed before it exists: the skill runs a dry run, shows you
the target branch, the destination worktree, and the files it would carry,
and creates the fork only after you approve. `--now` skips that confirmation;
the name is still chosen the same way.

When the `agent-fork` CLI is not installed, the skill walks you through the
fix step by step. It checks for `uv`: if `uv` is present it offers a one-off
`uvx` run or a permanent install, and if not it points at the `uv` installer
or a direct `pip` install. If it can confirm a local checkout of this
repository, it also offers — after asking — to run from that checkout with
`uv run --directory`.

Two limits are deliberate: the skill accepts no CLI flags beyond the forms
above (advanced flags are for direct CLI use), and the two inspection forms
always use the active session's directory (there is no directory option).

The skill ships as one copy: the Agent Skills artifact at
`.agents/skills/agent-fork` in this repository. Codex discovers it there as
`$agent-fork`; Claude Code discovers the same files through the repository's
`.claude/skills/agent-fork` symlink as `/agent-fork`. The user-level installs
above create the same two links under your home directory. The plugin manifests (`.claude-plugin/` for Claude
Code, `.codex-plugin/` for Codex) and the repo-root `skills/` directory all
point at that same artifact.

## Install

The skill installs with one command, for Claude Code and Codex at once:

```bash
npx skills@latest add smorinlabs/agent-fork
```

Claude Code can install it as a plugin instead — this repository is its own
marketplace:

```text
/plugin marketplace add smorinlabs/agent-fork
/plugin install agent-fork@agent-fork
```

### Optional: install the CLI

The skill runs the `agent-fork` CLI and helps you set it up on first use, so
installing the CLI yourself is optional. Doing so makes it available in any
terminal:

```bash
uv tool install git+https://github.com/smorinlabs/agent-fork
```

Or run it once without installing:

```bash
uvx --from git+https://github.com/smorinlabs/agent-fork agent-fork --version
```

> After PyPI publication the no-install command becomes simply
> `uvx agent-fork`.

**Requirements:** Python 3.11+ and Git 2.19+. Forking an agent session
additionally needs Claude Code 2.0.73+ or Codex 0.95+ (Codex's native `fork`
itself requires 0.81+). Run `agent-fork doctor` to check all of this at once.

### Alternative: local skill install

If you would rather not use the npx installer or the plugin, clone the
repository and symlink the canonical artifact into the user-level skill
directories for both agents:

```bash
git clone https://github.com/smorinlabs/agent-fork
cd agent-fork
mkdir -p ~/.claude/skills ~/.agents/skills
ln -sfn "$PWD/.agents/skills/agent-fork" ~/.claude/skills/agent-fork
ln -sfn "$PWD/.agents/skills/agent-fork" ~/.agents/skills/agent-fork
```

Claude Code then discovers it as `/agent-fork` and Codex as `$agent-fork`.

### Dev mode

Run these commands from the repository root. The editable `uv` tool install
keeps the command connected to this checkout; skill placement uses the same
two symlinks shown above.

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

### Uninstall

```bash
uv tool uninstall agent-fork
npx skills@latest remove agent-fork
```

A symlink install is removed with
`rm ~/.claude/skills/agent-fork ~/.agents/skills/agent-fork`; a plugin install
with `/plugin uninstall agent-fork`.

## Quickstart

Inside a session, just type `/agent-fork` — the commands below are the
direct-CLI equivalents:

```bash
agent-fork doctor              # confirm Git, agent CLIs, config, and XDG paths
agent-fork fork try-redis      # create the fork, print the paste command
agent-fork session             # inspect context and print native fork/resume commands
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
5. **Verify** that the new worktree matches what was promised — Git-visible
   state, and the contents themselves: staged entries, file types, permissions,
   symlink targets, and a checksum of every carried file. The parent is
   snapshotted before the fork starts and rechecked afterwards, so a file that
   changes mid-fork fails rather than producing an ambiguous copy. A failed
   check rolls the fork back and reports exactly what to do.
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
| `agent-fork session [validate]` | Inspect session evidence, construct its native fork and resume commands, or assert expected identity and lineage |
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
```

Inspection reports sourced evidence, the resolved invocation directory,
nullable Git repository context, and two shell-quoted native commands for the
one detected agent identity:

- `fork_command` — creates a *new* session: a fresh session ID, a new Git
  branch and worktree, carrying a copy of the current file state forward. The
  original session keeps running untouched.
- `resume_command` — re-enters the *same* session in place: same session ID,
  same directory, same branch/worktree, continuing the same transcript. Use
  this to pick a session back up after setting it aside ("rehydrate" it) —
  nothing new is created.

```text
fork:   cd '<resolved-directory>' && claude --session-id '<fresh-child-uuid>' --resume '<current-session-id>' --fork-session
        codex fork '<current-thread-id>' -C '<resolved-directory>'
resume: cd '<resolved-directory>' && claude --resume '<current-session-id>'
        codex resume '<current-thread-id>' -C '<resolved-directory>'
```

JSON inspection also reports `agent_signal`, an additive object with
`status`, `present`, and `missing`. Its status is `absent`, `incomplete`,
`detected`, or `ambiguous`. The detail lists contain supported environment
variable names, never session or thread values. An incomplete Claude signal
remains observational in `session`: it reports no current session, retains
`lineage.status: not_detected`, `fork_command.status: not_detected`, and
`resume_command.status: not_detected`, and names the missing value in
`notices`.

Inspection never executes the returned command, mutates agent or repository
state, or makes a network call; in an ordinary terminal it succeeds with
`not_detected`. Validation asserts expected identity and lineage: optional
`--agent`, `--session-id`, `--parent-session-id`, and
`--has-parent`/`--no-parent` constraints compose with AND semantics.

Claude does not expose an authoritative historical parent ID for ordinary
forks; the explicit `agent-fork session claude-parent infer` analysis can infer
likely relationships from transcript structure and record them as local
evidence. The complete semantics — repository-context fields, availability
rules, parent-evidence caveats, and the inference commands, caching, and
evidence labels — are documented in
[docs/session-inspection.md](docs/session-inspection.md).

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
- **Verification is on by default, and it compares contents.** Matching
  `git status` output is not enough: the fork's carried files are compared by
  checksum, along with staged entries, file types, permissions, and symlink
  targets. Configuration that would silently rewrite content in transit — such
  as `apply.whitespace`, end-of-line conversion, or content filters — is
  therefore caught rather than reported as a successful copy. A failed check
  rolls the fork back and reports the exact manual recovery steps.
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
  collects no data ([details](#telemetry-and-networking)).

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
| 3 | Agent, session, assertion, or target not found | `agent_not_detected`, `agent_signal_incomplete`, `session_not_found`, `session_name_ambiguous`, `session_resolution_unavailable`, `session_validation_failed`, `cleanup_target_unknown` |
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

## Contributing

Contributions are welcome — the loop is short:

1. Fork the repository and create a topic branch. A Git worktree keeps your
   main checkout clean; `agent-fork fork` can create it for you.
2. Install [dev mode](#dev-mode) and run the gate before pushing: `make check`,
   then `flox activate` and `just all` (format, lint, typecheck, tests).
3. Write [Conventional Commits](https://www.conventionalcommits.org)
   (`feat:`, `fix:`, `docs:`, …).
4. Open a pull request; CI runs the same hermetic gate.

The design and evidence corpus — [DESIGN-DECISIONS.md](DESIGN-DECISIONS.md),
[REQUIREMENTS.md](REQUIREMENTS.md), [EXPERIMENTS.md](EXPERIMENTS.md), and
[CONFORMANCE.md](CONFORMANCE.md) — explains why things work the way they do;
check it before proposing behavior changes.

## License

MIT
