---
type: terminal
status: current
created: 2026-07-21
updated: 2026-08-09
library_version: claude-code 2.1.220 / codex-cli 0.147.0 (pi 0.80.6, opencode 1.18.3, kilo 7.4.11 noted)
confidence: high
confidence_basis: official docs cross-checked against changelogs, upstream PRs, binary help/strings, and live scoping tests on local binaries; 3-vote adversarial verification (23 confirmed, 2 refuted, 0 unverified); Q5/Q6 gaps stated explicitly rather than papered over
verified_example: true   # Phase B E1-E3 live-verified in the isolated guest; see EXPERIMENTS.md
assumptions: single-user local terminal, macOS/Linux, default CLAUDE_CONFIG_DIR/CODEX_HOME
sources: [https://code.claude.com/docs/en/sessions, https://code.claude.com/docs/en/cli-reference, https://platform.claude.com/docs/en/agent-sdk/sessions, https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md, https://github.com/openai/codex/pull/10096, https://github.com/openai/codex/pull/8994, https://developers.openai.com/codex/cli/reference, https://github.com/asheshgoplani/agent-deck]
origin_prompt: ../topics/01-session-fork-resume-cli-mechanics/prompts/00-fork-resume-mechanics.prompt.md
---

# Agent session-fork CLI recipes (Claude Code + Codex, v1 targets)

## The specific knowledge

### Claude Code — the emit command

```bash
cd '<worktree>' && claude --session-id '<pre-generated-uuid>' --resume '<parent-session-id>' --fork-session -n '<derived-name>'
```

- Works cross-directory **because** the worktree belongs to the same repo: `--resume <id>`
  lookup is officially scoped to the current project directory *and its git worktrees*.
  No session-file copying. Unrelated dirs fail ("No conversation found…").
- `--fork-session` = full-history copy under a new ID; parent untouched; both resumable.
- `--session-id` pinning valid **only with** `--fork-session` (+`--resume`/`--continue`); ≥ v2.0.73.
- Pre-generate the UUID host-side (agent-deck does; avoids `uuidgen` availability issues
  and makes the fork's ID known before launch).
- Self-ID from inside a session: `$CLAUDE_CODE_SESSION_ID` (child-process env).
  Host detection: `CLAUDECODE=1`, `AI_AGENT=claude-code_<ver>_agent` (version parseable).
- Storage: `${CLAUDE_CONFIG_DIR:-~/.claude}/projects/<cwd with [^a-zA-Z0-9]→'-'>/<id>.jsonl` —
  format vendor-declared unstable; never parse/copy except as guarded last resort.
- Min versions: fork+pinned-ID ≥2.0.73; worktree-scoped resume reliable ≥~2.1.1xx (#48835
  failed older); `/add-dir`-based discovery ≥2.1.118.

### Codex — the emit command

```bash
codex fork '<parent-thread-id>' -C '<worktree>'
```

- `codex fork <uuid>` = documented Stable; transcript copied, parent preserved.
- Self-ID from inside a session: `$CODEX_THREAD_ID` (≥ rust-v0.95.0, PR #10096).
  Pre-0.95.0 fallback: newest `~/.codex/sessions/YYYY/MM/DD/rollout-*-<uuid>.jsonl`, or
  probe the codex process's open fds (walk up own process tree → `lsof -p`/`/proc/<pid>/fd`,
  agent-deck's method).
- Phase B E2 verified that an explicit SESSION_ID bypasses cwd filtering. A foreign-cwd
  launch without `-C` fires the session/current-directory chooser; `-C <worktree>` both
  selects the worktree and suppresses that chooser, so it is mandatory in the v1 template.
- Min versions: fork ≥0.81.0; `CODEX_THREAD_ID` ≥0.95.0; trustworthy `fork --last` ≥0.129.0.
  Preflight the installed binary (agent-deck instead emits-and-lets-it-fail; a
  print-for-human CLI should check first).
- Session enumeration (if ever needed): App Server JSON API (`thread/list` …), the
  officially recommended tool-builder surface.

### v2 targets (local-binary evidence only; web pass produced nothing verified)

- **Pi 0.80.6**: `pi --fork <path|id> --session-dir <dir> -n <name>`; also `--session-id`
  (create-if-missing). agent-deck forks by newest-jsonl file path.
- **OpenCode 1.18.3**: `opencode --session <id> --fork` (or `-c --fork`); export/import
  round-trip is the older mechanism agent-deck scripts.
- **Kilo 7.4.11**: OpenCode-lineage twin (`--fork`, `--session`, `--cloud-fork`); not in
  agent-deck at all — greenfield.

## Minimal example

The Claude command and Codex `-C` variant were run end-to-end in Phase B; see
`EXPERIMENTS.md` for the versions, procedure, and assertions.

## Gotchas

- Claude: session-scoped permission approvals do NOT carry into a fork; resuming without
  `--fork-session` in a second terminal interleaves two writers into one transcript.
- Claude: `--session-id` without `--fork-session` on a resume = hard error.
- Codex: rollout files flush asynchronously — verify the rollout exists
  (`sessions/*/*/*/rollout-*-<id>.jsonl`) before emitting fork (agent-deck #756).
- Both: quote every interpolated value (agent-deck has two unquoted-interpolation warts —
  Claude workDir, Codex resume id — do not replicate).

## Live experiments

E1-E3 are resolved in `EXPERIMENTS.md`. The `.jsonl` fallback experiment is retired
until v1.1 (A8/D14); state fidelity is core pipeline TDD rather than a live experiment.

## Currency notes

Claude docs annotated through 2.1.211 (local: 2.1.216). agent-deck Codex path verified
against 0.137.0 (local: 0.144.6). developers.openai.com → learn.chatgpt.com redirects.
