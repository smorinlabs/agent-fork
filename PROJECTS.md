# Projects

Index of every project in this repo. Per-project files live in
`projects/`. Skills in the `project-harness` plugin operate on this
file plus those.

## Status legend

| Glyph | Meaning                | File state                              |
|-------|------------------------|-----------------------------------------|
| `[?]` | Idea / exploratory     | stub file, trailing-hyphen filename     |
| `[ ]` | Scoped, not started    | full scope + tasks                      |
| `[~]` | In progress            | full + some `[x]` tasks                 |
| `[x]` | Completed              | all tasks `[x]`                         |
| `[-]` | Decided not to do      | reason at top of file                   |
| `[>]` | Proceeded to successor | redirects to successor's file           |

## Conventions

- Filename: `projects/P<NN>-<kebab-slug>.md` for scoped/active/done;
  `projects/P<NN>-<roughName>-.md` (trailing hyphen) for ideas.
- Trunk row: `- [<glyph>] **P<NN>** — [<title>](projects/<filename>)`.
  The title is a standard markdown link to the per-project file —
  external tools (markdown linters, doc generators, AI agents
  reading the repo without project-harness loaded) can parse the
  schema without prior knowledge of the conventions.
- Every non-`[?]` per-project file has a `**References**` block at
  the top whose first bullet is `- **Trunk:** [PROJECTS.md](../PROJECTS.md)`,
  the back-pointer to this file. Bidirectional schema.
- One trunk row per file; one file per trunk row.
- Status glyph mirrors the rolled-up state of the per-project file.
- Flip task checkboxes immediately as each task lands (no batching).
- TDD bias: every project has at least one `TS` task before its first
  `T` task. Opt out with `**TDD: not applicable**` in the body.

### Project workflow skills (plugin: project-harness)

- `using-project-harness` — bootstrap: when to use which skill below
- `project-next` — orient: what's in progress, what's next, what's recently touched
- `project-add` — capture an idea (≤4 questions, reserves the ID with a commit)
- `project-refine` — flesh out / scope / decompose an existing project
- `project-audit` — verify state matches conventions; fix per finding

## Project index

<!-- One row per project. Scoped / in-progress / done first; ideas last. -->
