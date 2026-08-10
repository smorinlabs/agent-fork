"""agent-fork command-line boundary."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from agent_fork.config import (
    XDG_RELATIVE_PATH,
    ConfigError,
    resolve_discovered_config,
    set_user_value,
)


def _user_config_path(environment: dict[str, str]) -> Path:
    base = Path(
        environment.get(
            "XDG_CONFIG_HOME", Path(environment.get("HOME", "~")) / ".config"
        )
    ).expanduser()
    return base / XDG_RELATIVE_PATH


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-fork")
    parser.add_argument("--config", type=Path)
    commands = parser.add_subparsers(dest="command")
    listing = commands.add_parser("list")
    listing.add_argument("-o", "--output", choices=("text", "json"), default="text")
    cleanup = commands.add_parser("cleanup")
    cleanup.add_argument("target")
    cleanup.add_argument("--force", action="store_true")
    cleanup.add_argument("--keep-branch", action="store_true")
    cleanup.add_argument("--yes", action="store_true")
    cleanup.add_argument("--no-input", action="store_true")
    cleanup.add_argument("--dry-run", action="store_true")
    config = commands.add_parser("config")
    actions = config.add_subparsers(dest="config_action", required=True)
    setter = actions.add_parser("set")
    setter.add_argument("key")
    setter.add_argument("value")
    actions.add_parser("validate")
    getter = actions.add_parser("get")
    getter.add_argument("key")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    environment = dict(os.environ)
    try:
        if args.command == "cleanup":
            from agent_fork.cleanup import cleanup, resolve_cleanup_target

            plan = resolve_cleanup_target(
                args.target, cwd=Path.cwd(), env=environment, force=args.force
            )
            if not args.dry_run and not args.yes:
                if args.no_input:
                    print(
                        "cleanup requires --yes when --no-input is set", file=sys.stderr
                    )
                    return 2
                print(
                    f"Remove {plan.render(keep_branch=args.keep_branch)}? [y/N] ",
                    end="",
                    file=sys.stderr,
                    flush=True,
                )
                answer = sys.stdin.readline().strip().lower()
                if answer not in {"y", "yes"}:
                    print("cleanup cancelled", file=sys.stderr)
                    return 2
            result = cleanup(
                plan,
                cwd=Path.cwd(),
                env=environment,
                force=args.force,
                keep_branch=args.keep_branch,
                dry_run=args.dry_run,
            )
            prefix = "would " if args.dry_run else ""
            print(prefix + plan.render(keep_branch=args.keep_branch))
            for notice in result.notices:
                print(notice)
            return 0
        if args.command == "list":
            from agent_fork.registry import read_registry

            entries = read_registry(env=environment)
            if args.output == "json":
                print(
                    json.dumps(
                        {
                            "version": 1,
                            "forks": [
                                item.to_dict(include_exists=True) for item in entries
                            ],
                        },
                        sort_keys=True,
                    )
                )
            else:
                for item in entries:
                    exists = "yes" if Path(item.worktree).exists() else "no"
                    print(
                        f"{item.name}\t{item.branch}\t{item.worktree}\t"
                        f"{item.agent}\t{exists}"
                    )
            return 0
        if args.command == "config" and args.config_action == "set":
            path = args.config or _user_config_path(environment)
            set_user_value(path, args.key, args.value)
            return 0
        if args.command == "config":
            resolved = resolve_discovered_config(
                Path.cwd(), environment, explicit_path=args.config
            )
            if args.config_action == "validate":
                print("config valid")
                return 0
            if args.config_action == "get":
                if not hasattr(resolved, args.key):
                    raise ConfigError(f"unknown config key: {args.key}")
                value = getattr(resolved, args.key)
                print(str(value).lower() if isinstance(value, bool) else value)
                return 0
    except ConfigError as error:
        print(error, file=sys.stderr)
        return 2
    except Exception as error:
        from agent_fork.errors import AgentForkError

        print(error, file=sys.stderr)
        return error.exit_code if isinstance(error, AgentForkError) else 1
    _parser().print_help()
    return 0


if __name__ == "__main__":  # pragma: no cover - console script is the public path
    raise SystemExit(main())
