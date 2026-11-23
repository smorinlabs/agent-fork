# P10 — CI macOS compatibility job speedup

**References**
- **Trunk:** [PROJECTS.md](../PROJECTS.md)
- **Discussion:** https://github.com/smorinlabs/agent-fork/pull/85 (this project's PR)
- **Prior art:** [P02 — fault remediation](P02-agent-fork-fault-remediation.md) (A6b step 7 added the clone-cost benchmark to `scripts/check_git_matrix.sh`)

## [~] Project P10: CI macOS compatibility job speedup (CI only, no release)
**Goal**: cut pull-request CI wall-clock from ~4.5 min to ~2.5 min without
dropping intent-to-add (ITA) compatibility coverage.

Evidence (run 43570573784 on `main`, 2026-11-14): the macOS job "Apple Git and
Flox Git compatibility" was the critical path at 5.6 min. Its 279 s step was
~41 s of ITA compatibility tests and ~238 s of the A6b clone-cost benchmark
(`measure_clone_cost`): ~98 s building a 50,000-file submodule fixture, ~88 s
for the measured fork, and ~50 s of teardown. The benchmark has no pass/fail
threshold.

- Keep `just test-git-matrix` (Apple Git and Flox Git ITA tests) on every PR.
- Move the benchmark to `just measure-clone-cost` and its own workflow,
  `clone-cost.yml`: push to `main`, nightly, on demand, and PRs that touch the
  clone/submodule-carry path.

**Out of Scope**
- Shrinking the benchmark fixture (it would invalidate the recorded baseline).
- Changing the ubuntu jobs.

**TDD: not applicable** — CI configuration only; verified by CI timings.

### Tests & Tasks
- [x] [P10-T01] Split `measure_clone_cost` out of `scripts/check_git_matrix.sh` into `scripts/measure_clone_cost.sh` plus a `measure-clone-cost` just recipe
- [x] [P10-T02] Add `.github/workflows/clone-cost.yml` (path-filtered PRs, push to `main`, nightly, `workflow_dispatch`)
- [x] [P10-T03] Update the `ci.yml` runtime comment and the README development section
- [x] [P10-TS01] PR CI: `ci.yml` wall-clock about 2.5 min, compat job under ~2.5 min, and the clone-cost job green
      PR #85 run 45114824093: `ci.yml` 2m34s (was ~4.5 min avg); compat job 1m34s (was 5.6 min); critical path is now the ubuntu matrix job at 2m31s. Clone-cost run 45114824310 green in 3m31s (`with-submodule=55s without-submodule=1s delta=54s`).
- [ ] [P10-T04] Close P10 after PR #85 merges
