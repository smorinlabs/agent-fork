# agent-fork

Fork a running coding-agent session: one command creates a new git branch +
worktree carrying your current file state (staged, unstaged, untracked —
gitignored opt-in), verifies the copy against the parent, and prints the
exact paste command to continue the conversation in a forked session of the
same agent in a new terminal.

**Status: pre-release scaffold — no working CLI yet.** The design is locked
(see the design corpus below); implementation is in progress. v1 agents:
**Claude Code** and **Codex**.

## Design corpus

| Doc | Role |
|---|---|
| [DESIGN-DECISIONS.md](DESIGN-DECISIONS.md) | All 14 decisions (D1–D14), final config schema, v1 surface |
| [REQUIREMENTS.md](REQUIREMENTS.md) | REQ-01..42 — full CLI spec, pinned to CLI Design Standard v1.4.14 |
| [RESEARCH.md](RESEARCH.md) | agent-deck port source map, materialization sequence, launch recipes |
| [CONFORMANCE.md](CONFORMANCE.md) | Standard applicability map + waivers |

## Development

Requires `git`, `uv`, `just`, and `flox` (agent CLIs for integration tests
come from the Flox `agents` pkg-group).

```bash
make check       # verify environment dependencies
flox activate    # reproducible toolchain (optional outside CI)
just all         # format, lint, typecheck, test
```

## Telemetry

None. `agent-fork` makes zero network calls at runtime and collects no data.

## License

MIT
