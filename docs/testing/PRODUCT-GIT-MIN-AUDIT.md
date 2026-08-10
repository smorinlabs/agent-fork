# PRODUCT_GIT_MIN feature audit

**Date:** 2026-08-10
**Decision:** `PRODUCT_GIT_MIN = (2, 19, 0)`
**Scope:** production Git used by `agent-fork`; distinct from the test-only
`TEST_HARNESS_GIT_MIN = (2, 43)`.

## Method

The audit inventories the Git surface locked by REQ-19..25, REQ-31..32,
DESIGN-DECISIONS D5, and amendments A1..A4/A10. Feature availability was
checked against versioned upstream Git manuals and upstream release notes. The
surface was then probed with both Git implementations installed in the guest:

```text
/usr/bin/git                                                    2.43.0
.flox/run/aarch64-linux.agent-fork-dev/bin/git                  2.54.0
```

Both targets successfully reported the same linked-worktree topology through
`rev-parse` and the same path/ref records through `worktree list --porcelain`.
Both advertise and execute the limiting `apply --intent-to-add` behavior.

## Required production surface

| Area | Required command/flag | Earliest relevant availability | Audit disposition |
|---|---|---:|---|
| repository detection | `rev-parse --git-dir`, `--git-common-dir`, `--show-toplevel`, `--is-bare-repository`, `--verify HEAD^{commit}` | before 2.19 | supported |
| branch validation | `check-ref-format --branch`, `show-ref --verify`, `symbolic-ref`, `rev-parse --abbrev-ref` | before 2.19 | supported |
| worktree lifecycle | `worktree add -b`, `list --porcelain`, `remove --force`, `prune` | before 2.19 | supported |
| guard state | `ls-files -u -z`; operation sentinels resolved below the Git dir | before 2.19 | supported |
| staged transport | `diff --binary --no-color --cached --ita-invisible-in-index`; `apply --binary --index` | `--ita-invisible-in-index` documented by 2.17 | supported |
| ITA transport | `apply --intent-to-add` | **2.19.0** | limiting feature |
| unstaged transport | `diff --binary --no-color`; `apply --binary` | before 2.19 | supported |
| untracked/ignored transport | `ls-files --others -z --exclude-standard`; second pass with `--ignored` | before 2.19 | supported |
| verification/cleanup | `status --porcelain=v1 -z` (optionally `--ignored`), `worktree list --porcelain`, `branch -D` | before 2.19 | supported |
| unpushed cleanup guard | `rev-list`/`log` against configured upstream refs | before 2.19 | supported |

The implementation deliberately does not depend on newer conveniences such as
`git branch --show-current` (2.22), `rev-parse --path-format` (2.31), or
`worktree list --porcelain -z`. Avoiding them keeps the floor tied to the actual
ITA preservation requirement rather than incidental parsing choices.

## Limiting evidence

The upstream Git 2.18 `git-apply` synopsis has no `--intent-to-add` option. The
Git 2.19 manual adds `--intent-to-add`, and the Git 2.19 release notes explicitly
identify it as newly learned behavior. Since REQ-21/A3 requires preservation of
intent-to-add entries, 2.18 and older cannot implement the locked contract
without changing semantics. Git 2.19 is therefore necessary.

No audited production feature requires a version newer than 2.19. The product
floor is consequently 2.19.0—not the guest version and not the higher harness
floor.

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
- Git 2.43 and 2.54 differ in unrelated behaviors such as remote-head defaults.
  The fixture and product contracts resolve explicit commits/refs and do not
  depend on those defaults.
- Every Git invocation resolves `git` through the current `PATH` (REQ-43/A10);
  no audit result authorizes caching an absolute executable path.

## Reproduction

Run the following with each target Git first on `PATH`:

```bash
git --version
git apply -h
git rev-parse --git-dir --git-common-dir --show-toplevel
git worktree list --porcelain
```

The Phase D fixture suite will exercise the full command surface and exact-copy
semantics against the guest Git. Boundary behavior for arbitrary installed
versions is tested through injected `git --version` output, so it does not
require installing an obsolete Git executable.
