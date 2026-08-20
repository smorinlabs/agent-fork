# PRODUCT_GIT_MIN feature audit

**Date:** 2026-08-10
**Decision:** `PRODUCT_GIT_MIN = (2, 19, 0)`
**Scope:** production Git used by `agent-fork`; distinct from the test-only
`TEST_HARNESS_GIT_MIN = (2, 43)`.

## Method

The audit inventories the Git surface locked by REQ-19..25, REQ-31..32,
DESIGN-DECISIONS D5, and amendments A1..A4/A10. Feature availability was
checked against versioned upstream Git manuals and upstream release notes. The
original surface audit probed both Git implementations installed in the guest.
The Apple Git portability correction additionally ran its ITA regression gate
with both Git implementations on the macOS host:

```text
/usr/bin/git                                                    2.43.0
.flox/run/aarch64-linux.agent-fork-dev/bin/git                  2.54.0
/usr/bin/git (Apple Git-155, macOS 26.4)                        2.50.1
Flox aarch64-darwin git                                         2.54.0
```

All targets successfully reported the same linked-worktree topology through
`rev-parse` and the same path/ref records through `worktree list --porcelain`.
Apple Git 2.50.1 does not safely execute `apply --intent-to-add` against a
populated linked-worktree index: it replaces unrelated index entries. The
portable ITA sequence is plain `apply` followed by `add --intent-to-add`; its
regression gate passes with host Apple Git 2.50.1 and Flox GNU Git 2.54.0.

## Required production surface

| Area | Required command/flag | Earliest relevant availability | Audit disposition |
|---|---|---:|---|
| repository detection | `rev-parse --git-dir`, `--git-common-dir`, `--show-toplevel`, `--is-bare-repository`, `--verify HEAD^{commit}` | before 2.19 | supported |
| branch validation | `check-ref-format --branch`, `show-ref --verify`, `symbolic-ref`, `rev-parse --abbrev-ref` | before 2.19 | supported |
| worktree lifecycle | `worktree add -b`, `list --porcelain`, `remove --force`, `prune` | before 2.19 | supported |
| guard state | `ls-files -u -z`; operation sentinels resolved below the Git dir | before 2.19 | supported |
| staged transport | `diff --binary --no-color --cached --ita-invisible-in-index`; `apply --binary --index` | `--ita-invisible-in-index` documented by 2.17 | supported |
| ITA transport | `diff --ita-invisible-in-index`; plain `apply --binary`; `add --intent-to-add -- <path>`; `:(literal)<path>` and `:(exclude,literal)<path>` pathspecs | before 2.19 | supported; literal pathspecs prevent recorded filenames from being reinterpreted as patterns |
| unstaged transport | `diff --binary --no-color`; `apply --binary` | before 2.19 | supported |
| untracked/ignored transport | `ls-files --others -z --exclude-standard`; second pass with `--ignored` | before 2.19 | supported |
| verification/cleanup | `status --porcelain=v1 -z` (optionally `--ignored`), `worktree list --porcelain`, `branch -D` | before 2.19 | supported |
| unpushed cleanup guard | `rev-list`/`log` exclusions via `--remotes`; bounded `log -z --max-count` detail; read-only `git remote` configured-name probe | before 2.19 | supported |

## A13(e/f) floor evidence

The A13(e) operand correction uses only pathspec syntax documented at the
product floor. The versioned
[Git 2.19 glossary](https://git-scm.com/docs/gitglossary/2.19.0.html) defines
the long pathspec form as a comma-separated list of magic words. It defines
`literal` as treating wildcard characters literally and `exclude` as removing
matching paths after inclusion. Therefore `:(literal)<path>` and the combined
`:(exclude,literal)<path>` form are supported by Git 2.19.

The A13(f) guidance correction uses `git remote` without a subcommand only to
read configured remote names. The versioned
[Git 2.18 remote manual](https://git-scm.com/docs/git-remote/2.18.0) documents
that invocation and states that it lists existing remotes. The same manual's
version history reports no changes from Git 2.18.1 through 2.22.5, which
includes the Git 2.19 product floor. The probe reads local configuration; it
does not contact a remote.

The retained `T-MAT-12` cross-Git gate exercises the literal include and
exclude forms with overlapping pattern-shaped filenames and a filename
beginning `:(glob)`. It runs once with host Apple Git and once with the Flox
Git toolchain through `just test-git-matrix`. `T-CLN-18` and `T-CLN-24`
exercise configured and empty `git remote` results in the normal suite.

The implementation deliberately does not depend on newer conveniences such as
`git branch --show-current` (2.22), `rev-parse --path-format` (2.31), or
`worktree list --porcelain -z`. Avoiding them keeps the floor tied to the
audited command surface rather than incidental parsing choices.

## Floor disposition

The original audit selected Git 2.19 because that release added
`git apply --intent-to-add`. The Apple Git compatibility correction removes that
flag from production and therefore removes it as a valid floor justification.

`PRODUCT_GIT_MIN` remains 2.19.0 as a conservative supported floor. Lowering the
published floor would broaden the compatibility contract and requires a
dedicated full-suite audit on pre-2.19 Git; this repair does not make that
separate product decision. No audited production feature requires a version
newer than 2.19.

## Behavioral differences and mitigations

- Newer Git versions can add porcelain fields or conveniences. Production uses
  the stable, line-oriented `worktree list --porcelain` subset and ignores
  unknown fields.
- Git 2.36 fixed quoting details in worktree porcelain. `agent-fork` treats the
  `worktree ` path record as Git's path value and tests unusual paths on the
  supported runtime; it does not opt into a newer `-z` dependency.
- Git 2.28 changed default ITA diff presentation. The explicit
  `--ita-invisible-in-index` flag fixes the desired representation across the
  supported range.
- Apple Git 2.50.1 `apply --intent-to-add` can replace a linked worktree's
  populated index, leaving tracked files staged as deleted and simultaneously
  untracked. AgentFork applies the ITA patch to the working tree first, then
  marks only the intended path with `add --intent-to-add -- <path>`.
- Git 2.43 and 2.54 differ in unrelated behaviors such as remote-head defaults.
  The fixture and product contracts resolve explicit commits/refs and do not
  depend on those defaults.
- Every Git invocation resolves `git` through the current `PATH` (REQ-43/A10);
  no audit result authorizes caching an absolute executable path.

## Reproduction

Run the following with each target Git first on `PATH`:

```bash
git --version
git rev-parse --git-dir --git-common-dir --show-toplevel
git worktree list --porcelain
just test-git-matrix
```

On macOS, that target runs once with `/usr/bin/git` and once inside the Flox
environment. On Linux it runs with system Git and Flox Git. The Phase D fixture
suite exercises the full command surface and exact-copy semantics. Boundary
behavior for arbitrary installed versions is tested through injected
`git --version` output, so it does not require installing an obsolete Git
executable.
