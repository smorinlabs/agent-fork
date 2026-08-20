"""Deterministic shell completion renderers derived from the live CLI parser."""

from __future__ import annotations

import argparse
from functools import lru_cache
from typing import cast


@lru_cache(maxsize=1)
def _vocabulary() -> dict[str, tuple[str, ...]]:
    from agent_fork.cli import _parser

    root = _parser()
    commands = _subparser_choices(root)
    config_actions = _subparser_choices(commands["config"])
    completion_parser = commands["completion"]
    shells = _choice_values(completion_parser, "shell")
    outputs = _collect_choice_values(root, "output") or ("text", "json")
    agents = _collect_choice_values(root, "agent") or ("claude", "codex")
    return {
        "commands": tuple(sorted(commands)),
        "global_options": _option_strings(root),
        "config_actions": tuple(sorted(config_actions)),
        "fork_options": _parser_words(commands["fork"], include_choices=False),
        "cleanup_options": _parser_words(commands["cleanup"], include_choices=False),
        "session_options": _parser_words(commands["session"], include_choices=False),
        "list_options": _parser_words(commands["list"], include_choices=False),
        "doctor_options": _parser_words(commands["doctor"], include_choices=False),
        "config_options": _parser_words(commands["config"], include_choices=False),
        "outputs": outputs,
        "agents": agents,
        "shells": shells,
    }


def _subparser_choices(
    parser: argparse.ArgumentParser,
) -> dict[str, argparse.ArgumentParser]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return cast(dict[str, argparse.ArgumentParser], dict(action.choices))
    return {}


def _option_strings(parser: argparse.ArgumentParser) -> tuple[str, ...]:
    values: set[str] = set()
    for action in parser._actions:
        values.update(action.option_strings)
    return tuple(sorted(values, key=lambda item: (not item.startswith("--"), item)))


def _choice_values(parser: argparse.ArgumentParser, dest: str) -> tuple[str, ...]:
    for action in parser._actions:
        if action.dest == dest and action.choices is not None:
            return tuple(str(value) for value in action.choices)
    return ()


def _collect_choice_values(
    parser: argparse.ArgumentParser, dest: str
) -> tuple[str, ...]:
    values: set[str] = set(_choice_values(parser, dest))
    for subparser in _subparser_choices(parser).values():
        values.update(_collect_choice_values(subparser, dest))
    return tuple(sorted(values))


def _parser_words(
    parser: argparse.ArgumentParser,
    *,
    include_choices: bool,
) -> tuple[str, ...]:
    words: set[str] = set(_option_strings(parser))
    for action in parser._actions:
        if include_choices and action.choices is not None:
            words.update(str(value) for value in action.choices)
    for name, subparser in _subparser_choices(parser).items():
        words.add(name)
        words.update(_parser_words(subparser, include_choices=include_choices))
    return tuple(sorted(words, key=lambda item: (not item.startswith("-"), item)))


def _words(values: tuple[str, ...]) -> str:
    return " ".join(values)


def _joined(*parts: tuple[str, ...]) -> str:
    return " ".join(_words(part) for part in parts)


def _bash() -> str:
    words = _vocabulary()
    top_level = _joined(words["commands"], words["global_options"])
    fork_words = _joined(words["fork_options"], words["agents"], words["outputs"])
    session_words = _joined(words["session_options"], words["agents"], words["outputs"])
    cleanup_words = _joined(words["cleanup_options"], words["outputs"])
    list_words = _joined(words["list_options"], words["outputs"])
    doctor_words = _joined(words["doctor_options"], words["outputs"])
    config_words = _joined(
        words["config_actions"], words["config_options"], words["outputs"]
    )
    return f"""_agent_fork_complete() {{
    local cur command words
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    command="${{COMP_WORDS[1]}}"
    if (( COMP_CWORD == 1 )); then
        words="{top_level}"
    else
        case "$command" in
            fork) words="{fork_words}" ;;
            session) words="{session_words}" ;;
            cleanup) words="{cleanup_words}" ;;
            list) words="{list_words}" ;;
            doctor) words="{doctor_words}" ;;
            config) words="{config_words}" ;;
            completion) words="{_words(words["shells"])}" ;;
            help) words="{_words(words["commands"])}" ;;
            *) words="" ;;
        esac
    fi
    COMPREPLY=( $(compgen -W "$words" -- "$cur") )
}}
complete -F _agent_fork_complete agent-fork
"""


def _zsh() -> str:
    words = _vocabulary()
    top_level = _joined(words["commands"], words["global_options"])
    fork_choices = _joined(words["fork_options"], words["agents"], words["outputs"])
    session_choices = _joined(
        words["session_options"], words["agents"], words["outputs"]
    )
    cleanup_choices = _joined(words["cleanup_options"], words["outputs"])
    list_choices = _joined(words["list_options"], words["outputs"])
    doctor_choices = _joined(words["doctor_options"], words["outputs"])
    config_choices = _joined(
        words["config_actions"], words["config_options"], words["outputs"]
    )
    return f"""#compdef agent-fork
_agent_fork() {{
  local -a commands choices
  commands=({top_level})
  if (( CURRENT == 2 )); then
    _describe 'command' commands
    return
  fi
  case $words[2] in
    fork) choices=({fork_choices}) ;;
    session) choices=({session_choices}) ;;
    cleanup) choices=({cleanup_choices}) ;;
    list) choices=({list_choices}) ;;
    doctor) choices=({doctor_choices}) ;;
    config) choices=({config_choices}) ;;
    completion) choices=({_words(words["shells"])}) ;;
    help) choices=({_words(words["commands"])}) ;;
  esac
  _describe 'argument' choices
}}
compdef _agent_fork agent-fork
"""


def _fish_option_lines(command: str, options: tuple[str, ...]) -> list[str]:
    lines: list[str] = []
    condition = f"__fish_seen_subcommand_from {command}"
    for option in options:
        if option.startswith("--"):
            lines.append(
                f"complete -c agent-fork -n '{condition}' "
                f"-l '{option.removeprefix('--')}'"
            )
        elif len(option) == 2 and option.startswith("-"):
            lines.append(f"complete -c agent-fork -n '{condition}' -s '{option[1:]}'")
    return lines


def _fish() -> str:
    words = _vocabulary()
    lines = ["complete -c agent-fork -f"]
    for option in words["global_options"]:
        if option.startswith("--"):
            lines.append(f"complete -c agent-fork -l '{option.removeprefix('--')}'")
        elif len(option) == 2:
            lines.append(f"complete -c agent-fork -s '{option[1:]}'")
    for command in words["commands"]:
        lines.append(
            f"complete -c agent-fork -n '__fish_use_subcommand' -a '{command}'"
        )
    for action in words["config_actions"]:
        lines.append(
            "complete -c agent-fork -n '__fish_seen_subcommand_from config' "
            f"-a '{action}'"
        )
    for command, options in (
        ("fork", words["fork_options"]),
        ("session", words["session_options"]),
        ("cleanup", words["cleanup_options"]),
        ("list", words["list_options"]),
        ("doctor", words["doctor_options"]),
        ("config", words["config_options"]),
    ):
        lines.extend(_fish_option_lines(command, options))
    lines.extend(
        (
            "complete -c agent-fork -n '__fish_seen_subcommand_from fork' "
            f"-a '{_words(words['agents'])} {_words(words['outputs'])}'",
            "complete -c agent-fork -n "
            "'__fish_seen_subcommand_from list doctor config' "
            f"-a '{_words(words['outputs'])}'",
            "complete -c agent-fork -n '__fish_seen_subcommand_from completion' "
            f"-a '{_words(words['shells'])}'",
        )
    )
    return "\n".join(lines) + "\n"


def render_completion(shell: str) -> str:
    """Render completion source for one parser-approved shell."""
    return {"bash": _bash, "zsh": _zsh, "fish": _fish}[shell]()
