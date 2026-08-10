"""agent-fork command-line boundary."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
from importlib.metadata import version
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
    parser = argparse.ArgumentParser(prog="agent-fork", allow_abbrev=False)
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"agent-fork {version('agent-fork')}",
    )
    parser.add_argument("-v", "--verbose", action="count", default=0)
    parser.add_argument("-q", "--quiet", action="store_true")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--debug", action="store_true")
    commands = parser.add_subparsers(dest="command")
    fork = commands.add_parser("fork", allow_abbrev=False)
    fork.add_argument("name", nargs="?")
    fork.add_argument("--agent")
    fork.add_argument("--parent-session")
    fork.add_argument(
        "--with-state", action=argparse.BooleanOptionalAction, default=None
    )
    fork.add_argument(
        "--with-ignored", action=argparse.BooleanOptionalAction, default=None
    )
    fork.add_argument("--verify", action=argparse.BooleanOptionalAction, default=None)
    fork.add_argument("--force", action="store_true")
    fork.add_argument("--dry-run", action="store_true")
    fork.add_argument("--copy", action=argparse.BooleanOptionalAction, default=None)
    fork.add_argument("-o", "--output", choices=("text", "json"), default=None)
    fork.add_argument("--json", action="store_true")
    listing = commands.add_parser("list", allow_abbrev=False)
    listing.add_argument("-o", "--output", choices=("text", "json"), default="text")
    listing.add_argument("--json", action="store_true")
    cleanup = commands.add_parser("cleanup", allow_abbrev=False)
    cleanup.add_argument("target")
    cleanup.add_argument("--force", action="store_true")
    cleanup.add_argument("--keep-branch", action="store_true")
    cleanup.add_argument("--yes", action="store_true")
    cleanup.add_argument("--no-input", action="store_true")
    cleanup.add_argument("--dry-run", action="store_true")
    cleanup.add_argument("-o", "--output", choices=("text", "json"), default="text")
    cleanup.add_argument("--json", action="store_true")
    doctor = commands.add_parser("doctor", allow_abbrev=False)
    doctor.add_argument("-o", "--output", choices=("text", "json"), default="text")
    doctor.add_argument("--json", action="store_true")
    completion = commands.add_parser("completion", allow_abbrev=False)
    completion.add_argument("shell", choices=("bash", "zsh", "fish"))
    commands.add_parser("help", allow_abbrev=False)
    config = commands.add_parser("config", allow_abbrev=False)
    actions = config.add_subparsers(dest="config_action", required=True)
    setter = actions.add_parser("set", allow_abbrev=False)
    setter.add_argument("key")
    setter.add_argument("value")
    actions.add_parser("validate", allow_abbrev=False)
    viewer = actions.add_parser("view", allow_abbrev=False)
    viewer.add_argument("-o", "--output", choices=("text", "json"), default="text")
    viewer.add_argument("--json", action="store_true")
    getter = actions.add_parser("get", allow_abbrev=False)
    getter.add_argument("key")
    return parser


def _path_for_name(info, config, name, branch, environment):
    from agent_fork.location import derive_worktree_path

    root = info.worktree_root or info.common_dir
    data = Path(
        environment.get("XDG_DATA_HOME", Path(environment["HOME"]) / ".local/share")
    )
    return derive_worktree_path(
        root,
        branch,
        name,
        config.worktree_location,
        xdg_data_home=data,
        parent_path=info.parent_path,
        parent_is_linked=info.linked_worktree,
        bare_at_root=info.bare,
        location_explicit=config.worktree_location != "sibling",
    )


def _fork_cli(args, environment: dict[str, str]) -> int:
    from agent_fork.agents import (
        build_launch_command,
        detect_agent,
        preflight_agent,
        preflight_git,
    )
    from agent_fork.config import resolve_discovered_config
    from agent_fork.git import run_git
    from agent_fork.naming import (
        derive_auto_name,
        naming_plan,
        sanitize_name,
        unique_auto_name,
    )
    from agent_fork.output import DryRunOutput, ForkOutput, copy_to_clipboard
    from agent_fork.pipeline import ForkRequest, fork
    from agent_fork.repository import (
        inspect_repository,
        resolve_anchor,
        validate_fork_guards,
    )

    cwd = Path.cwd()
    flags = {
        key: value
        for key, value in {
            "with_state": args.with_state,
            "with_ignored": args.with_ignored,
            "verify": args.verify,
            "copy": args.copy,
            "output": "json" if args.json else args.output,
        }.items()
        if value is not None
    }
    config = resolve_discovered_config(
        cwd, environment, explicit_path=args.config, flags=flags
    )
    context = detect_agent(
        environment,
        explicit_agent=args.agent,
        explicit_parent_session=args.parent_session,
    )
    info = inspect_repository(cwd, env=environment)
    parent_path = info.worktree_root or info.parent_path
    if parent_path != info.parent_path:
        info = inspect_repository(parent_path, env=environment)
    symbolic = run_git(
        parent_path,
        ["symbolic-ref", "--quiet", "--short", "HEAD"],
        env=environment,
        check=False,
    )
    parent_branch = (
        symbolic.stdout.decode().strip() if symbolic.returncode == 0 else None
    )
    anchor = resolve_anchor(info.parent_path, env=environment)
    auto = derive_auto_name(parent_branch, detached_sha=anchor)

    def collides(candidate: str) -> bool:
        plan = naming_plan(candidate, branch_prefix=config.branch_prefix)
        destination = _path_for_name(info, config, candidate, plan.branch, environment)
        branch_exists = (
            run_git(
                parent_path,
                ["show-ref", "--verify", "--quiet", f"refs/heads/{plan.branch}"],
                env=environment,
                check=False,
            ).returncode
            == 0
        )
        return branch_exists or destination.exists() or destination.is_symlink()

    if args.name is None:
        name = unique_auto_name(auto, collides)
    else:
        name = sanitize_name(args.name)
    identity = naming_plan(name, branch_prefix=config.branch_prefix)
    destination = _path_for_name(info, config, name, identity.branch, environment)
    extra_args = (
        config.claude_extra_args
        if context.agent == "claude"
        else config.codex_extra_args
    )
    launch = build_launch_command(
        context, worktree=destination, name=name, extra_args=extra_args
    )
    output_kind = "json" if args.json else (args.output or config.output)

    if args.dry_run:
        preflight_agent(context, environment)
        git_version = subprocess.run(
            ["git", "--version"], env=environment, capture_output=True, text=True
        ).stdout
        preflight_git(git_version, force=args.force, verify=config.verify)
        validate_fork_guards(parent_path, identity.branch, destination, env=environment)

        def count(arguments):
            data = run_git(parent_path, arguments, env=environment).stdout
            return len([value for value in data.split(b"\0") if value])

        dry = DryRunOutput(
            identity.branch,
            destination,
            count(["diff", "--cached", "--name-only", "-z"]),
            count(["diff", "--name-only", "-z"]),
            count(["ls-files", "--others", "--exclude-standard", "-z"]),
            count(["ls-files", "--others", "--ignored", "--exclude-standard", "-z"])
            if config.with_ignored
            else 0,
            launch.command,
        )
        print(dry.render())
        return 0

    result = fork(
        ForkRequest(
            parent=parent_path,
            destination=destination,
            name=name,
            branch=identity.branch,
            agent=context,
            with_state=config.with_state,
            with_ignored=config.with_ignored,
            verify=config.verify,
            force=args.force,
            extra_args=extra_args,
            child_session_id=launch.child_session_id,
        ),
        env=environment,
    )
    notices = list(result.notices)
    if config.copy:
        notices.extend(copy_to_clipboard(result.launch.command))
    presented = ForkOutput(
        agent=context.agent,
        parent_session_id=context.parent_session_id,
        name=name,
        branch=identity.branch,
        worktree=result.creation.path,
        anchor_commit=result.creation.anchor,
        with_state=config.with_state,
        with_ignored=config.with_ignored,
        verification={"enabled": config.verify, "passed": config.verify},
        command=result.launch.command,
        notices=tuple(notices),
    )
    print(presented.render(output_kind))
    for notice in notices:
        print(notice, file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    args = _parser().parse_args(argv)
    environment = dict(os.environ)
    try:
        if args.command == "help":
            _parser().print_help()
            return 0
        if args.command == "completion":
            scripts = {
                "bash": (
                    "complete -W 'fork cleanup list doctor config completion help' "
                    "agent-fork"
                ),
                "zsh": "compdef '_arguments *::command:->cmds' agent-fork",
                "fish": (
                    "complete -c agent-fork -f -a "
                    "'fork cleanup list doctor config completion help'"
                ),
            }
            print(scripts[args.shell])
            return 0
        if args.command == "doctor":
            from agent_fork.doctor import run_doctor
            from agent_fork.output import json_line

            checks = run_doctor(Path.cwd(), environment)
            machine = args.json or args.output == "json"
            if machine:
                print(
                    json_line(
                        {
                            "checks": [
                                {
                                    "name": check.name,
                                    "ok": check.ok,
                                    "detail": check.detail,
                                }
                                for check in checks
                            ],
                            "ok": all(check.ok for check in checks),
                        }
                    )
                )
            else:
                for check in checks:
                    print(
                        f"{'ok' if check.ok else 'FAIL'} {check.name}: {check.detail}"
                    )
            return 0 if all(check.ok for check in checks) else 1
        if args.command == "fork":
            return _fork_cli(args, environment)
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
            machine = args.json or args.output == "json"
            if machine:
                from agent_fork.output import json_line

                print(
                    json_line(
                        {
                            "removed": result.removed,
                            "target": plan.entry.to_dict(),
                            "keep_branch": args.keep_branch,
                            "dry_run": args.dry_run,
                            "notices": list(result.notices),
                        }
                    )
                )
            else:
                prefix = "would " if args.dry_run else ""
                print(prefix + plan.render(keep_branch=args.keep_branch))
                for notice in result.notices:
                    print(notice)
            return 0
        if args.command == "list":
            from agent_fork.registry import read_registry

            entries = read_registry(env=environment)
            if args.json or args.output == "json":
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
            if args.config_action == "view":
                document = {
                    "with_state": resolved.with_state,
                    "with_ignored": resolved.with_ignored,
                    "branch_prefix": resolved.branch_prefix,
                    "worktree_location": resolved.worktree_location,
                    "verify": resolved.verify,
                    "copy": resolved.copy,
                    "output": resolved.output,
                    "agents": {
                        "claude": {"extra_args": list(resolved.claude_extra_args)},
                        "codex": {"extra_args": list(resolved.codex_extra_args)},
                    },
                }
                if args.json or args.output == "json":
                    from agent_fork.output import json_line

                    print(json_line(document))
                else:
                    for key, value in document.items():
                        print(f"{key} = {value}")
                return 0
            if args.config_action == "get":
                if not hasattr(resolved, args.key):
                    raise ConfigError(f"unknown config key: {args.key}")
                value = getattr(resolved, args.key)
                print(str(value).lower() if isinstance(value, bool) else value)
                return 0
    except ConfigError as error:
        machine = (
            bool(getattr(args, "json", False))
            or getattr(args, "output", None) == "json"
        )
        if machine:
            from agent_fork.output import render_error

            print(render_error(error, machine=True), file=sys.stderr)
        else:
            print(error, file=sys.stderr)
        return 2
    except Exception as error:
        from agent_fork.errors import AgentForkError
        from agent_fork.output import render_error

        machine = (
            bool(getattr(args, "json", False))
            or getattr(args, "output", None) == "json"
        )
        print(render_error(error, machine=machine), file=sys.stderr)
        return error.exit_code if isinstance(error, AgentForkError) else 1
    _parser().print_help()
    return 0


if __name__ == "__main__":  # pragma: no cover - console script is the public path
    raise SystemExit(main())
