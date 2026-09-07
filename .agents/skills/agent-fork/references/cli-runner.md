# Select an Agent Fork runner

Read this when the installed CLI is absent or incompatible, or the user has
requested a permanent installation or a local source checkout. The argument
gate in `SKILL.md` runs first. Keep the recorded invocation directory for
every command here.

Use the installed CLI when compatible. Otherwise, run the official-source
CLI through `uvx` and continue the requested operation. Do not ask for separate
confirmation merely because this fetches code over the network. Honor existing
user authorization and actual environment permissions. Use the environment's
approval mechanism when required; report an actual denial or missing
prerequisite rather than reserving execution for the user.

## Run from the official source

1. Probe `command -v uvx`. If absent, probe `command -v uv` and use
   `uv tool run`, which is equivalent. If both are absent, report that
   prerequisite and the [uv installation options](https://docs.astral.sh/uv/getting-started/installation/).
   Honor an existing installation request; otherwise offer setup choices.
2. Resolve the source once, before running the temporary CLI:

   ```bash
   git ls-remote https://github.com/smorinlabs/agent-fork.git refs/heads/main
   ```

   Require exit 0 and exactly one output record: a 40-character hexadecimal
   commit ID followed by `refs/heads/main`. Otherwise stop with the actual
   lookup error or `Invalid agent-fork source revision`. Never guess a revision
   or turn arbitrary lookup output into a shell command.
3. Replace `<commit>` below with that verified ID and retain the entire prefix
   through `agent-fork` as the selected runner:

   ```bash
   uvx --isolated --from 'git+https://github.com/smorinlabs/agent-fork@<commit>' agent-fork session --json
   ```

   With only `uv`, use:

   ```bash
   uv tool run --isolated --from 'git+https://github.com/smorinlabs/agent-fork@<commit>' agent-fork session --json
   ```

   These run locally in a cached tool environment. `--isolated` bypasses an
   older installed tool; the explicit commit prevents reuse of an older
   unpinned source and keeps the code stable for this operation. Do not resolve
   a new commit or refresh a moving branch between inspection and a fork.
4. Validate the session JSON and recorded directory using `SKILL.md`. If valid,
   reuse this inspection and the selected runner for the classified route.
   A version printout is not completion. Never return to the incompatible
   bare executable for subsequent preview, fork, or doctor commands.

Use the Git repository until a usable PyPI release is verified; the package
name currently resolves to a placeholder. This source lookup is the sole
direct Git command allowed by the skill. Repository inspection, worktree
operations, and mutation stay with the CLI.

Attempt automatic recovery once per operation, before any mutation. If the
selected source still lacks a required field, report the compatibility
diagnostic and source revision and stop. Malformed output, unknown status
values, and nonzero CLI refusals are not upgrade triggers. Never bootstrap or
retry after a real fork has been attempted.

## Perform an authorized permanent installation

When the user requests or has already authorized permanent installation or
upgrade, perform it instead of defaulting to a temporary runner. Probe `uv`
and resolve the official commit as above. For a new installation:

```bash
uv tool install 'git+https://github.com/smorinlabs/agent-fork@<commit>'
```

For an authorized replacement of an existing installation:

```bash
uv tool install --force 'git+https://github.com/smorinlabs/agent-fork@<commit>'
```

Locate the executable directory from the same `uv` that installed the tool:

```bash
uv tool dir --bin
```

Append `agent-fork` to that verified directory and select this installed
executable by its absolute, shell-quoted path. Resolve it and the result of
`command -v agent-fork` with `readlink -f` to compare targets. A different
PATH target is a conflict even if that other CLI has compatible output. Report
both paths, but use the explicitly selected installed executable to continue.
If PATH does not find it, report its absolute path rather than claiming the
bare command is available.

Run `session --json` through that installed executable and verify the required
fields and directory. Report success only after this check. An absent or
incompatible installed executable is an installation failure; do not silently
replace it with a temporary run. Do not repeat a question that the user's
installation request already answered.

## Use a confirmed source checkout

Use this alternative when the user selects a checkout, or offer it when the
temporary runner is unavailable. Discover an Agent Fork checkout in exactly
two places, in order:

1. The active directory: read its `pyproject.toml` and require
   `name = "agent-fork"`.
2. The skill's load directory: resolve it with `readlink -f`, strip the trailing
   `.agents/skills/agent-fork`, and verify the same declaration in the resulting
   directory's `pyproject.toml`. A development symlink can resolve to a
   checkout; a copied installation does not establish one.

Do not search the filesystem more widely or guess a checkout path. Name the
confirmed checkout and disclose that this runs its working tree, which may
be dirty or mid-refactor. Ask before using that source unless the user has
already selected or authorized it. On authorization, select this runner:

```bash
uv run --project '<checkout>' agent-fork session --json
```

Shell-quote the verified checkout as one argument. `--project` selects the
code environment while preserving the invocation directory. Validate that
directory in the returned JSON before accepting inspection or proceeding to
a fork. Keep the same runner for subsequent commands. If no checkout is
confirmed or the user declines it, report the remaining prerequisite or
execution failure; do not substitute hand-written Git for the CLI.
