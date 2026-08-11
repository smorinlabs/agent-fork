"""Deterministic shell completion renderers for the static CLI grammar."""

from __future__ import annotations

COMMANDS = (
    "fork",
    "session",
    "cleanup",
    "list",
    "doctor",
    "config",
    "completion",
    "help",
)
GLOBAL_OPTIONS = (
    "-h",
    "--help",
    "-V",
    "--version",
    "-v",
    "--verbose",
    "-q",
    "--quiet",
    "--config",
    "--debug",
)
CONFIG_ACTIONS = ("view", "get", "set", "validate")
OUTPUTS = ("table", "text", "json")
AGENTS = ("claude", "codex")
SHELLS = ("bash", "zsh", "fish")

FORK_OPTIONS = (
    "--agent",
    "--parent-session",
    "--codex-session-name-resolution",
    "--no-codex-session-name-resolution",
    "--require-agent",
    "--no-agent",
    "--branch",
    "--worktree-dir",
    "--worktree-base-dir",
    "--worktree-name",
    "--with-state",
    "--no-with-state",
    "--with-ignored",
    "--no-with-ignored",
    "--verify",
    "--no-verify",
    "--force",
    "--dry-run",
    "--copy",
    "--no-copy",
    "--output",
    "--json",
)
CLEANUP_OPTIONS = (
    "--force",
    "--allow-dirty",
    "--allow-unpushed",
    "--keep-branch",
    "--yes",
    "--no-input",
    "--dry-run",
    "--output",
    "--json",
)
SESSION_OPTIONS = (
    "validate",
    "--agent",
    "--session-id",
    "--parent-session-id",
    "--has-parent",
    "--no-parent",
    "--output",
    "--json",
)


def _words(values: tuple[str, ...]) -> str:
    return " ".join(values)


def _bash() -> str:
    return f"""_agent_fork_complete() {{
    local cur command words
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    command="${{COMP_WORDS[1]}}"
    if (( COMP_CWORD == 1 )); then
        words="{_words(COMMANDS)} {_words(GLOBAL_OPTIONS)}"
    else
        case "$command" in
            fork) words="{_words(FORK_OPTIONS)} {_words(AGENTS)} {_words(OUTPUTS)}" ;;
            session) words="{_words(SESSION_OPTIONS)} {_words(AGENTS)} \
{_words(OUTPUTS)}" ;;
            cleanup) words="{_words(CLEANUP_OPTIONS)} {_words(OUTPUTS)}" ;;
            list|doctor) words="--output --json {_words(OUTPUTS)}" ;;
            config) words="{_words(CONFIG_ACTIONS)} --output --json \
{_words(OUTPUTS)}" ;;
            completion) words="{_words(SHELLS)}" ;;
            help) words="{_words(COMMANDS)}" ;;
            *) words="" ;;
        esac
    fi
    COMPREPLY=( $(compgen -W "$words" -- "$cur") )
}}
complete -F _agent_fork_complete agent-fork
"""


def _zsh() -> str:
    return f"""#compdef agent-fork
_agent_fork() {{
  local -a commands choices
  commands=({_words(COMMANDS)} {_words(GLOBAL_OPTIONS)})
  if (( CURRENT == 2 )); then
    _describe 'command' commands
    return
  fi
  case $words[2] in
    fork) choices=({_words(FORK_OPTIONS)} {_words(AGENTS)} {_words(OUTPUTS)}) ;;
    session) choices=({_words(SESSION_OPTIONS)} {_words(AGENTS)} {_words(OUTPUTS)}) ;;
    cleanup) choices=({_words(CLEANUP_OPTIONS)} {_words(OUTPUTS)}) ;;
    list|doctor) choices=(--output --json {_words(OUTPUTS)}) ;;
    config) choices=({_words(CONFIG_ACTIONS)} --output --json {_words(OUTPUTS)}) ;;
    completion) choices=({_words(SHELLS)}) ;;
    help) choices=({_words(COMMANDS)}) ;;
  esac
  _describe 'argument' choices
}}
compdef _agent_fork agent-fork
"""


def _fish() -> str:
    lines = ["complete -c agent-fork -f"]
    for option in GLOBAL_OPTIONS:
        if option.startswith("--"):
            lines.append(f"complete -c agent-fork -l '{option.removeprefix('--')}'")
        elif len(option) == 2:
            lines.append(f"complete -c agent-fork -s '{option[1:]}'")
    for command in COMMANDS:
        lines.append(
            f"complete -c agent-fork -n '__fish_use_subcommand' -a '{command}'"
        )
    for action in CONFIG_ACTIONS:
        lines.append(
            "complete -c agent-fork -n '__fish_seen_subcommand_from config' "
            f"-a '{action}'"
        )
    for option in FORK_OPTIONS:
        lines.append(
            "complete -c agent-fork -n '__fish_seen_subcommand_from fork' "
            f"-l '{option.removeprefix('--')}'"
        )
    for option in SESSION_OPTIONS:
        if option.startswith("--"):
            lines.append(
                "complete -c agent-fork -n '__fish_seen_subcommand_from session' "
                f"-l '{option.removeprefix('--')}'"
            )
    for option in CLEANUP_OPTIONS:
        lines.append(
            "complete -c agent-fork -n '__fish_seen_subcommand_from cleanup' "
            f"-l '{option.removeprefix('--')}'"
        )
    lines.extend(
        (
            "complete -c agent-fork -n '__fish_seen_subcommand_from fork' "
            f"-a '{_words(AGENTS)} {_words(OUTPUTS)}'",
            "complete -c agent-fork -n "
            "'__fish_seen_subcommand_from list doctor config' "
            f"-a '{_words(OUTPUTS)}'",
            "complete -c agent-fork -n '__fish_seen_subcommand_from completion' "
            f"-a '{_words(SHELLS)}'",
        )
    )
    return "\n".join(lines) + "\n"


def render_completion(shell: str) -> str:
    """Render completion source for one parser-approved shell."""
    return {"bash": _bash, "zsh": _zsh, "fish": _fish}[shell]()
