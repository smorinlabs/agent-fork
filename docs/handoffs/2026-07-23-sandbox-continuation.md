# Session handoff — agent-fork implementation → Lima sandbox — 2026-07-23

## 🎯 Outcome
**Goal:** continue P01 (`agent-fork` v1) execution inside the curated Lima
sandbox — run **Phase B** (live experiments E1–E3), then **Phase C** (plan) and
**Phase D** (TDD build), honoring every phase gate in IMPLEMENTATION-PROMPT.md.
**Out of scope:** Phase E (release — needs host-bound 1Password/repo-secrets
and release plumbing) and Phase F (skill-create — writes to host harness
repos); both return to the Mac. No design re-litigation: D1–D14 are locked.
**Self-contained:** ✓ stands alone — spec essence inlined below; every
referenced doc is committed and pushed.

## ⚠ Portability & dependency preflight — read first
- **Uncommitted: none.** Working tree clean at handoff time.
- **Unpushed: none.** `main @ 9c9cd50` == `origin/main`. No stashes.
- **Referenced docs:** all ✓ committed · substantive (REQUIREMENTS.md ~196
  lines; RESEARCH.md ~266; DESIGN-DECISIONS.md ~100; CONFORMANCE.md;
  IMPLEMENTATION-PROMPT.md; projects/P01-agent-fork-v1.md).
- **Guest reality:** the sandbox mounts NO host paths. The repo reaches the
  guest only by `git clone` of the public origin. Anything not pushed does not
  exist there. The host agent-deck checkout (`~/c/agent-deck`) is likewise
  **absent in the guest** — by design this is fine, see REQ-37 note below.
- **Guest tool gap:** `sandboxctl prepare` installs Node, gh, Python, jq, rg,
  and the agent CLIs — **not `uv`, `just`, or `flox`**, which `make check`
  requires. The project setup command must install them (see plan §sandbox).

## 🧭 Where you are
- Repo: **agent-fork** · origin `https://github.com/smorinlabs/agent-fork.git` · default `main`
- Branch: `main @ 9c9cd50` (merge of PR #2, attribution removal)
- Repo root (host Mac, convenience): `/Users/stevemorin/c/agent-fork` — guest path will be the clone target instead
- Build/verify: `make check` (env deps) then `just all` (format, lint, typecheck, test) — green at handoff

## 📎 Artifacts & sources of truth (precedence order)
| What | Repo-relative path | Status |
|---|---|---|
| Decisions D1–D14 + final config schema (precedence 1) | `DESIGN-DECISIONS.md` | ✓ committed, substantive |
| REQ-01..42, CLI Standard v1.4.14, exit codes, §9 test plan (precedence 2) | `REQUIREMENTS.md` | ✓ (REQ-37 amended 2026-07-22) |
| Port source map, §2.2 materialization sequence, §2.3 detection matrix, §7 experiments | `RESEARCH.md` | ✓ |
| Applicability map + R2.1 `cleanup` waiver | `CONFORMANCE.md` | ✓ |
| Per-agent fork recipes + version gates | `research/reference/agent-session-fork-cli-recipes-2026-07-21.md` | ✓ |
| Method brief: phases A–F, gates, guardrails | `IMPLEMENTATION-PROMPT.md` | ✓ (amended 2026-07-22) |
| Tracking: trunk + P01 tasks mapped to REQ IDs | `PROJECTS.md`, `projects/P01-agent-fork-v1.md` | ✓ |
| PRs merged | [#1](https://github.com/smorinlabs/agent-fork/pull/1) scaffold · [#2](https://github.com/smorinlabs/agent-fork/pull/2) attribution removal | merged |

## 📋 Plan · inlined skeleton (carries the essence; docs above are depth)
- **Phase A — DONE** (gate cleared by owner directing continuation): repo live
  public under org ruleset (merge/rebase only); uv scaffold (console script
  `agent-fork`, `requires-python >=3.11`, dep `platformdirs`); ruff+ty+pytest;
  `just all` + `make check`; Flox tiered manifest (`agents` pkg-group:
  claude-code 2.1.201, codex 0.142.3 — above the REQ-27 matrix); MIT LICENSE;
  P01 tracking; welcome announcement.
- **Phase B — NEXT**: three experiments as pytest integration tests marked
  `requires_real_cli` (marker already registered in pyproject), run once for
  real, results recorded in a new `EXPERIMENTS.md` + folded into REQ-28,
  RESEARCH §7, and the recipes leaf. Gate: STOP for owner review.
  - **E1 (Claude):** `--resume <id> --fork-session --session-id <pinned> -n <name>`
    in one non-interactive invocation — does any flag no-op? Decides `-n` in the template.
  - **E2 (Codex):** explicit-UUID `codex fork` from a foreign cwd (bypasses cwd
    filter?); `-C <worktree>` behavior; does the TUI cwd-change prompt fire with
    `-C`? Decides the Codex template + emitted-output documentation.
  - **E3 (Claude E2E):** full paste command in a real worktree — full context
    recall, fresh UUID, parent transcript untouched.
  - Old E4/E6 are moot (D14 refusal posture); E5 is Phase D's core TDD.
- **Phase C**: implementation plan via superpowers:writing-plans, sized for
  subagent dispatch, dependency order: config resolver (REQ-13 tri-state +
  implication rule) → git detection matrix → guards/anchor/worktree-create →
  materialize (§2.2 sequence) → verify ladder + rollback → registry (locked
  XDG state) → per-agent detection/preflight/templates (+ extra_args quoting) →
  `fork` → `cleanup`/`list`/`doctor`/`config`/`completion` → machine output +
  error catalog → conformance fixtures (R9.14). Each task names its
  failing-test-first. Gate: plan review.
- **Phase D**: execute with subagent-driven development + TDD; `just all` green
  at every merge; CI from the start; quoting tests on every emitted command;
  phase-end fable + codex reviews. Gate: build review.
- **Phase E/F (host, later)**: cli-standards audit → release-please/trusted
  publishing → v0.1.0 (PEP 541: the PyPI `0.0.0.dev0` placeholder should become
  real reasonably soon) → companion skill via skill-create.

## 🏖 Sandbox execution plan (host-side bring-up, then guest session)
Skills: `sandbox-lima` → `sandbox-prepare` → `sandbox-project` (wrapper:
`sandboxctl` in the sandbox-lima skill's `scripts/`). Ubuntu 24.04 ARM64, VZ,
no host mounts.
1. `sandboxctl setup` then `sandboxctl check` (idempotent VM create + isolation check).
2. `sandboxctl prepare` (toolchain + agent CLIs) → `sandboxctl auth` —
   **interactive, owner does**: Codex ChatGPT device auth, Claude Pro/Max
   login, `gh auth login --web` (+ `gh auth setup-git`) → `sandboxctl auth-check`
   must pass for codex, claude, gh. Recommend `sandboxctl import-skills` (yes —
   the guest session needs superpowers/project-harness/cli-standards et al.).
3. `sandbox-project`: project id **agent-fork**, repo
   `https://github.com/smorinlabs/agent-fork.git`, branch `main`; setup command
   installs the missing toolchain — recommended: install **flox** (repo's
   `.flox` covers `aarch64-linux`; provides pinned python/uv/just/make and the
   `agents` group) — lean fallback: `uv` installer + `just` via apt; check
   command: `make check && just all`. Render per the skill's
   `references/project-definition.md`, `sandboxctl project import agent-fork <file>`,
   `project sync`, `project check`, finish with `project commands`.
4. Launch the continuation session in the guest (terminal:
   `sandboxctl shell` → `cd <clone>` → `claude`), paste the First-action prompt.
   (`project goal` launches Codex instead; pick ONE session.)
- **Guest agent versions must still pass the REQ-27 matrix** (Claude pinned-ID
  fork ≥2.0.73, worktree-scoped resume ≥~2.1.1xx; Codex fork ≥0.81.0,
  `CODEX_THREAD_ID` ≥0.95.0, `fork --last` ≥0.129.0) — verify with
  `claude --version` / `codex --version` before Phase B; refuse-and-upgrade if below.

## 🔧 State to resume
- Done: Phase A tasks P01-T01..T05 all `[x]` in `projects/P01-agent-fork-v1.md`.
- In flight: nothing mid-edit; no failing tests; 2 smoke tests green.
- Next unchecked tasks: P01-TS01..TS03 + P01-T06 (Phase B).

## 🧠 Critical context that won't survive a fresh window
- **REQ-37 amended 2026-07-22 (owner): agent-deck attribution REMOVED.**
  No NOTICE, no headers. Consequence: agent-deck is a behavioral reference
  only — implement from RESEARCH.md's documented semantics; **never translate
  agent-deck Go source** (also moot in the guest: the checkout isn't there).
  "Port verbatim" in older wording means verbatim *semantics*, not code.
- **D14 (owner override):** preflight failure ⇒ refuse with diagnosis; nothing
  created. No fallback ladder in v1. **D11 (owner override):** `[agents.<name>]
  extra_args` ships, each element individually shell-quoted; template tests
  assert fixed prefix byte-for-byte + quoted-suffix property.
- **Worktree discipline continues in the guest:** never commit to main; every
  change via worktree → PR → `--merge` merge → `pull --ff-only` → branch
  cleanup. On the host Mac, `gh` GraphQL rate-limits constantly — REST
  (`gh api repos/...`) proved reliable; keep the ≥20s poll floor anywhere.
- **TDD is non-negotiable** (superpowers:test-driven-development), subagent
  model matrix: haiku=mechanical · sonnet=standard · opus=tricky/mutating ·
  codex=adversarial second lens · fable=planning/gates.
- Owner flagged at the Phase A gate (still open, cosmetic): welcome-announcement
  wording in `.claude/settings.json` is Claude-authored — owner may tweak.
- Rejected/decided along the way: repo is public (matches org pattern);
  pyproject `version = "0.1.0"` until release-please takes over (Phase E).

## 👉 First action (paste in the guest session)
> Read `docs/handoffs/2026-07-23-sandbox-continuation.md` and
> `IMPLEMENTATION-PROMPT.md` at the repo root, verify `make check` and
> `just all` are green, confirm `claude --version` / `codex --version` pass the
> REQ-27 matrix, then start Phase B (experiments E1–E3) per the brief. STOP at
> the Phase B gate.

## ℹ How this was made
digest: ok (240 turns, 2026-07-21 → 2026-07-23) · gathered 2026-07-23 ·
machine: host Mac (darwin) · self-contained: ✓
