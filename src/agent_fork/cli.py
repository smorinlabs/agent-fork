"""agent-fork command-line boundary."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import traceback
from importlib.metadata import version
from pathlib import Path
from typing import cast

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
    parser = argparse.ArgumentParser(
        prog="agent-fork",
        allow_abbrev=False,
        description=(
            "Fork the active coding-agent session into a verified Git branch and "
            "worktree."
        ),
        epilog=(
            "Exit codes:\n"
            "  0 success\n"
            "  1 runtime or verification failure\n"
            "  2 usage error or required prompt disabled\n"
            "  3 agent/session/target not found\n"
            "  5 conflict or precondition refusal\n"
            "  130/143 interrupted by SIGINT/SIGTERM"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"agent-fork {version('agent-fork')}",
    )
    parser.add_argument(
        "-v", "--verbose", action="count", default=0, help="Increase diagnostics"
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="Suppress optional diagnostics"
    )
    parser.add_argument("--config", type=Path, help="Use exactly this TOML config")
    parser.add_argument(
        "--debug", action="store_true", help="Include debugging diagnostics"
    )
    commands = parser.add_subparsers(dest="command")
    fork = commands.add_parser(
        "fork",
        allow_abbrev=False,
        help="Create a verified branch and worktree",
        description="Create a verified branch and worktree carrying the current state.",
    )
    fork.add_argument(
        "name",
        nargs="?",
        metavar="NAME",
        help="Fork identity; derived from the current branch when omitted",
    )
    fork.add_argument(
        "--agent",
        metavar="{claude,codex}",
        help="Host agent (claude or codex); detected when omitted",
    )
    fork.add_argument(
        "--parent-session",
        metavar="ID",
        help="Parent session/thread ID; detected when omitted",
    )
    fork.add_argument("--branch", metavar="BRANCH", help="Explicit fork branch name")
    fork.add_argument(
        "--worktree-dir",
        type=Path,
        metavar="PATH",
        help="Use this exact worktree destination",
    )
    fork.add_argument(
        "--worktree-base-dir",
        type=Path,
        metavar="DIRECTORY",
        help="Replace only the derived worktree parent directory",
    )
    fork.add_argument(
        "--worktree-name",
        metavar="COMPONENT",
        help="Replace only the derived worktree directory name",
    )
    fork.add_argument(
        "--with-state",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Carry staged, unstaged, and untracked state (default: enabled)",
    )
    fork.add_argument(
        "--with-ignored",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Also carry ignored files (default: disabled)",
    )
    fork.add_argument(
        "--verify",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Verify the completed fork (default: enabled)",
    )
    fork.add_argument(
        "--force", action="store_true", help="Override only the Git-version floor"
    )
    fork.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview every planned local mutation without changing anything",
    )
    fork.add_argument(
        "--copy",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Copy the paste command to the clipboard",
    )
    fork.add_argument(
        "-o",
        "--output",
        choices=("table", "text", "json"),
        default=None,
        help="Select result format",
    )
    fork.add_argument("--json", action="store_true", help="Alias for --output json")
    listing = commands.add_parser(
        "list",
        allow_abbrev=False,
        help="List forks created by agent-fork",
        description="List registered forks in deterministic creation order.",
    )
    listing.add_argument(
        "-o",
        "--output",
        choices=("table", "text", "json"),
        default="table",
        help="Select result format",
    )
    listing.add_argument("--json", action="store_true", help="Alias for --output json")
    cleanup = commands.add_parser(
        "cleanup",
        allow_abbrev=False,
        help="Remove a registered fork",
        description="Remove a fork worktree and, by default, its branch.",
        epilog="Safety: Never remove the invoking working directory.",
    )
    cleanup.add_argument(
        "target", metavar="TARGET", help="Fork name, branch, or worktree path"
    )
    cleanup.add_argument(
        "--force",
        action="store_true",
        help="Allow unregistered, dirty, or unpushed targets",
    )
    cleanup.add_argument(
        "--keep-branch", action="store_true", help="Remove only the worktree"
    )
    cleanup.add_argument(
        "--yes", action="store_true", help="Confirm removal non-interactively"
    )
    cleanup.add_argument(
        "--no-input", action="store_true", help="Never prompt for confirmation"
    )
    cleanup.add_argument(
        "--dry-run", action="store_true", help="Print the removal plan only"
    )
    cleanup.add_argument(
        "-o",
        "--output",
        choices=("table", "text", "json"),
        default="table",
        help="Select result format",
    )
    cleanup.add_argument("--json", action="store_true", help="Alias for --output json")
    doctor = commands.add_parser(
        "doctor",
        allow_abbrev=False,
        help="Diagnose Git, agent, config, and XDG readiness",
    )
    doctor.add_argument(
        "-o",
        "--output",
        choices=("table", "text", "json"),
        default="table",
        help="Select result format",
    )
    doctor.add_argument("--json", action="store_true", help="Alias for --output json")
    completion = commands.add_parser(
        "completion", allow_abbrev=False, help="Generate shell completion"
    )
    completion.add_argument(
        "shell", choices=("bash", "zsh", "fish"), help="Shell syntax to generate"
    )
    help_command = commands.add_parser(
        "help", allow_abbrev=False, help="Show help for a command"
    )
    help_command.add_argument("topic", nargs="?", help="Command to explain")
    config = commands.add_parser(
        "config", allow_abbrev=False, help="Inspect or update configuration"
    )
    actions = config.add_subparsers(dest="config_action", required=True)
    viewer = actions.add_parser(
        "view", allow_abbrev=False, help="Show effective configuration"
    )
    viewer.add_argument(
        "-o",
        "--output",
        choices=("table", "text", "json"),
        default="table",
        help="Select result format",
    )
    viewer.add_argument("--json", action="store_true", help="Alias for --output json")
    getter = actions.add_parser(
        "get", allow_abbrev=False, help="Get one effective configuration value"
    )
    getter.add_argument("key", help="Configuration key")
    setter = actions.add_parser(
        "set", allow_abbrev=False, help="Set a user configuration value"
    )
    setter.add_argument("key", help="Configuration key")
    setter.add_argument("value", help="New value")
    actions.add_parser(
        "validate", allow_abbrev=False, help="Validate effective configuration"
    )
    return parser


def _path_for_name(info, config, name, branch, environment, args=None, cwd=None):
    from agent_fork.location import compose_worktree_destination, derive_worktree_path

    root = info.worktree_root or info.common_dir
    data = Path(
        environment.get("XDG_DATA_HOME", Path(environment["HOME"]) / ".local/share")
    )
    derived = derive_worktree_path(
        root,
        branch,
        name,
        config.worktree_location,
        xdg_data_home=data,
        parent_path=info.parent_path,
        parent_is_linked=info.linked_worktree,
        bare_at_root=info.bare,
        location_explicit=config.worktree_location_explicit,
    )
    if args is None or args.worktree_dir is not None:
        return derived
    return compose_worktree_destination(
        derived,
        invocation_cwd=cwd or Path.cwd(),
        base_dir=args.worktree_base_dir,
        worktree_name=args.worktree_name,
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

    def candidate_resources(candidate: str):
        plan = naming_plan(candidate, branch_prefix=config.branch_prefix)
        branch = args.branch or plan.branch
        destination = (
            args.worktree_dir.expanduser().resolve()
            if args.worktree_dir is not None
            else _path_for_name(
                info, config, candidate, branch, environment, args=args, cwd=cwd
            )
        )
        return branch, destination

    def collision_state(candidate: str):
        branch, destination = candidate_resources(candidate)
        branch_exists = (
            run_git(
                parent_path,
                ["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
                env=environment,
                check=False,
            ).returncode
            == 0
        )
        return branch_exists, destination.exists() or destination.is_symlink()

    if args.name is None:

        def collides(candidate: str) -> bool:
            branch_collision, path_collision = collision_state(candidate)
            if not (branch_collision or path_collision):
                return False
            next_name = f"{auto}-2" if candidate == auto else None
            if next_name is None:
                prefix = f"{auto}-"
                suffix = candidate.removeprefix(prefix)
                next_name = f"{auto}-{int(suffix) + 1}"
            branch, destination = candidate_resources(candidate)
            next_branch, next_destination = candidate_resources(next_name)
            from agent_fork.errors import PreconditionError

            if branch_collision and next_branch == branch:
                raise PreconditionError(
                    "conflict_branch_exists", f"branch already exists: {branch}"
                )
            if path_collision and next_destination == destination:
                raise PreconditionError(
                    "conflict_worktree_path",
                    f"worktree destination already exists: {destination}",
                )
            return True

        name = unique_auto_name(auto, collides)
    else:
        name = sanitize_name(args.name)
    identity = naming_plan(name, branch_prefix=config.branch_prefix)
    branch = args.branch or identity.branch
    if args.branch:
        valid = run_git(
            parent_path,
            ["check-ref-format", "--branch", branch],
            env=environment,
            check=False,
        )
        if valid.returncode != 0:
            from agent_fork.errors import PreconditionError

            raise PreconditionError("invalid_branch", f"invalid branch name: {branch}")
    destination = (
        args.worktree_dir.expanduser().resolve()
        if args.worktree_dir is not None
        else _path_for_name(info, config, name, branch, environment, args=args, cwd=cwd)
    )
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
        validate_fork_guards(parent_path, branch, destination, env=environment)

        def count(arguments):
            data = run_git(parent_path, arguments, env=environment).stdout
            return len([value for value in data.split(b"\0") if value])

        dry = DryRunOutput(
            branch,
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
            branch=branch,
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
        branch=branch,
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
    parser = _parser()
    args = parser.parse_args(argv)
    if (
        args.command == "fork"
        and args.worktree_dir is not None
        and (args.worktree_base_dir is not None or args.worktree_name is not None)
    ):
        parser.error(
            "--worktree-dir cannot be combined with --worktree-base-dir or "
            "--worktree-name"
        )
    environment = dict(os.environ)
    try:
        if args.verbose and not args.quiet:
            print(f"agent-fork: command={args.command or 'help'}", file=sys.stderr)
            if args.verbose > 1:
                print(f"agent-fork: cwd={Path.cwd()}", file=sys.stderr)
        if args.command == "help":
            parser = _parser()
            if args.topic is None:
                parser.print_help()
                return 0
            subparsers = next(
                action
                for action in parser._actions
                if isinstance(action, argparse._SubParsersAction)
            )
            selected = subparsers.choices.get(args.topic)
            if selected is None:
                parser.error(f"unknown help topic: {args.topic}")
            selected = cast(argparse.ArgumentParser, selected)
            selected.print_help()
            return 0
        if args.command == "completion":
            from agent_fork.completion import render_completion

            print(render_completion(args.shell), end="")
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
            if args.debug:
                traceback.print_exc()
            print(error, file=sys.stderr)
        return 2
    except Exception as error:
        from agent_fork.errors import AgentForkError
        from agent_fork.output import render_error

        machine = (
            bool(getattr(args, "json", False))
            or getattr(args, "output", None) == "json"
        )
        if args.debug and not machine:
            traceback.print_exc()
        print(render_error(error, machine=machine), file=sys.stderr)
        return error.exit_code if isinstance(error, AgentForkError) else 1
    _parser().print_help()
    return 0


if __name__ == "__main__":  # pragma: no cover - console script is the public path
    raise SystemExit(main())
