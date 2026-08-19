"""agent-fork command-line boundary."""

from __future__ import annotations

import argparse
import json
import os
import shlex
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
            "Create a verified Git branch and worktree, with adaptive coding-agent "
            "session integration."
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
        metavar="ID_OR_NAME",
        help=(
            "Parent session/thread UUID or renamed Codex session name; "
            "detected when omitted"
        ),
    )
    agent_mode = fork.add_mutually_exclusive_group()
    agent_mode.add_argument(
        "--require-agent",
        action="store_true",
        help="Require an unambiguous supported agent session",
    )
    agent_mode.add_argument(
        "--no-agent",
        action="store_true",
        help="Create only the Git branch and worktree",
    )
    fork.add_argument(
        "--codex-session-name-resolution",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Resolve renamed Codex sessions through the local app-server "
            "(default: enabled; UUIDs bypass it)"
        ),
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
    session = commands.add_parser(
        "session",
        allow_abbrev=False,
        help="Inspect or validate the current agent session",
        description=(
            "Report agent-neutral current-session evidence and construct its native "
            "fork command and resume (rehydrate) command without executing either."
        ),
        epilog=(
            "Examples:\n"
            "  agent-fork session          # human inspection, fork/resume commands\n"
            "  agent-fork session --json   # exact commands in fork_command.command "
            "and resume_command.command\n\n"
            "Command availability means constructible, not preflighted."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    session.add_argument(
        "-o",
        "--output",
        choices=("table", "text", "json"),
        default="table",
        help="Select result format",
    )
    session.add_argument("--json", action="store_true", help="Alias for --output json")
    session_actions = session.add_subparsers(dest="session_action")
    session_validate = session_actions.add_parser(
        "validate", allow_abbrev=False, help="Assert detected session facts"
    )
    session_validate.add_argument("--agent", choices=("claude", "codex"))
    session_validate.add_argument("--session-id", metavar="ID")
    session_validate.add_argument("--parent-session-id", metavar="ID")
    parent_assertion = session_validate.add_mutually_exclusive_group()
    parent_assertion.add_argument("--has-parent", action="store_true")
    parent_assertion.add_argument("--no-parent", action="store_true")
    session_validate.add_argument(
        "-o",
        "--output",
        choices=("table", "text", "json"),
        default="table",
        help="Select result format",
    )
    session_validate.add_argument(
        "--json", action="store_true", help="Alias for --output json"
    )
    claude_parent = session_actions.add_parser(
        "claude-parent", allow_abbrev=False, help="Manage Claude parent evidence"
    )
    parent_actions = claude_parent.add_subparsers(
        dest="claude_parent_action", required=True
    )

    def parent_output(action):
        action.add_argument(
            "-o", "--output", choices=("table", "text", "json"), default="table"
        )
        action.add_argument(
            "--json", action="store_true", help="Alias for --output json"
        )

    parent_list = parent_actions.add_parser("list", allow_abbrev=False)
    parent_list.add_argument(
        "--source", choices=("planned", "inferred", "all"), default="all"
    )
    parent_output(parent_list)
    parent_show = parent_actions.add_parser("show", allow_abbrev=False)
    parent_show.add_argument("--session-id", required=True, metavar="ID")
    parent_show.add_argument("--source", choices=("planned", "inferred"))
    parent_output(parent_show)
    parent_infer = parent_actions.add_parser("infer", allow_abbrev=False)
    target = parent_infer.add_mutually_exclusive_group(required=True)
    target.add_argument("--current", action="store_true")
    target.add_argument("--session-id", metavar="ID")
    target.add_argument("--all", action="store_true")
    parent_infer.add_argument("--record", action="store_true")
    parent_infer.add_argument("--record-all", action="store_true")
    parent_output(parent_infer)
    parent_delete = parent_actions.add_parser("delete", allow_abbrev=False)
    parent_delete.add_argument("--session-id", required=True, metavar="ID")
    parent_delete.add_argument("--source", choices=("planned", "inferred"))
    parent_delete.add_argument("--yes", action="store_true")
    parent_delete.add_argument("--no-input", action="store_true")
    parent_output(parent_delete)
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
        help="Allow unregistered targets and override dirty/unpushed guards",
    )
    cleanup.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Override only the guard against uncommitted changes",
    )
    cleanup.add_argument(
        "--allow-unpushed",
        action="store_true",
        help="Override only the guard against unpushed commits",
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
        "--dry-run",
        action="store_true",
        help="Inspect safety and print the removal plan without changing anything",
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
    doctor_mode = doctor.add_mutually_exclusive_group()
    doctor_mode.add_argument("--require-agent", action="store_true")
    doctor_mode.add_argument("--no-agent", action="store_true")
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
        LaunchCommand,
        build_launch_command,
        preflight_agent,
        preflight_git,
        resolve_agent_mode,
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
        count_paths,
        current_branch,
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
            "agent_mode": (
                "strict"
                if args.require_agent
                or args.agent is not None
                or args.parent_session is not None
                else "git-only"
                if args.no_agent
                else None
            ),
            "codex_session_name_resolution": args.codex_session_name_resolution,
        }.items()
        if value is not None
    }
    config = resolve_discovered_config(
        cwd, environment, explicit_path=args.config, flags=flags
    )
    context = resolve_agent_mode(
        config.agent_mode,
        environment,
        explicit_agent=args.agent,
        explicit_parent_session=args.parent_session,
    )
    info = inspect_repository(cwd, env=environment)
    parent_path = info.worktree_root or info.parent_path
    if parent_path != info.parent_path:
        info = inspect_repository(parent_path, env=environment)
    parent_branch = current_branch(parent_path, env=environment)
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
        if context is not None and context.agent == "claude"
        else config.codex_extra_args
        if context is not None
        else ()
    )
    output_kind = "json" if args.json else (args.output or config.output)

    if args.dry_run:
        if context is not None:
            agent_check = preflight_agent(
                context,
                environment,
                codex_session_name_resolution=config.codex_session_name_resolution,
            )
            context = agent_check.context or context
            launch = build_launch_command(
                context, worktree=destination, name=name, extra_args=extra_args
            )
        else:
            launch = LaunchCommand(f"cd {shlex.quote(str(destination))}", None, ())
        git_version = subprocess.run(
            ["git", "--version"], env=environment, capture_output=True, text=True
        ).stdout
        preflight_git(git_version, force=args.force, verify=config.verify)
        validate_fork_guards(parent_path, branch, destination, env=environment)

        def count(arguments):
            return count_paths(parent_path, arguments, env=environment)

        dry = DryRunOutput(
            branch,
            destination,
            count(["diff", "--cached", "--name-only", "-z", "--no-renames"])
            if config.with_state
            else 0,
            count(["diff", "--name-only", "-z", "--no-renames"])
            if config.with_state
            else 0,
            count(["ls-files", "--others", "--exclude-standard", "-z"])
            if config.with_state
            else 0,
            count(["ls-files", "--others", "--ignored", "--exclude-standard", "-z"])
            if config.with_state and config.with_ignored
            else 0,
            launch.command,
            agent_check.notices if context is not None else (),
        )
        print(dry.render(output_kind))
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
            codex_session_name_resolution=config.codex_session_name_resolution,
        ),
        env=environment,
    )
    notices = list(result.notices)
    if config.copy:
        notices.extend(copy_to_clipboard(result.launch.command))
    presented = ForkOutput(
        agent=result.agent.agent if result.agent is not None else None,
        parent_session_id=(
            result.agent.parent_session_id if result.agent is not None else None
        ),
        parent_session_name=result.parent_session_name,
        mode="agent" if context is not None else "git-only",
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
    if (
        args.command == "fork"
        and args.no_agent
        and (args.agent is not None or args.parent_session is not None)
    ):
        parser.error("--no-agent cannot be combined with --agent or --parent-session")
    if (
        args.command == "session"
        and args.session_action == "validate"
        and args.no_parent
        and args.parent_session_id is not None
    ):
        parser.error("--no-parent cannot be combined with --parent-session-id")
    if (
        args.command == "session"
        and args.session_action == "claude-parent"
        and args.claude_parent_action == "infer"
    ):
        if args.record and args.record_all:
            parser.error("--record and --record-all are mutually exclusive")
        if args.all and args.record:
            parser.error("--all requires --record-all for bulk recording")
        if not args.all and args.record_all:
            parser.error("--record-all requires --all")
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

            doctor_mode = (
                "strict"
                if args.require_agent
                else "git-only"
                if args.no_agent
                else None
            )
            checks = run_doctor(Path.cwd(), environment, agent_mode=doctor_mode)
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
        if args.command == "session":
            from agent_fork.output import json_line, terminal_text
            from agent_fork.session import (
                SessionAssertions,
                inspect_session,
                validate_session,
            )

            if args.session_action == "claude-parent":
                from agent_fork.claude_lineage_inference import (
                    ClaudeLineageCorpus,
                    to_record,
                )
                from agent_fork.errors import (
                    AgentSignalIncompleteError,
                    ClaudeParentError,
                    ClaudeParentNotRecordableError,
                    ClaudeParentPartialRecordError,
                )
                from agent_fork.lineage import (
                    find_lineage,
                    read_lineage,
                    remove_lineage,
                )
                from agent_fork.lineage_inference_store import (
                    add_inference,
                    read_inferences,
                    remove_inference,
                )

                action = args.claude_parent_action
                machine = args.json or args.output == "json"

                def emit(document):
                    if machine:
                        print(json_line(document))
                    else:
                        if isinstance(document, list):
                            for item in document:
                                fields = (
                                    item["child_session_id"],
                                    item["parent_session_id"],
                                    item["source"],
                                    item["status"],
                                )
                                print("  ".join(str(value) for value in fields))
                        else:
                            for key, value in document.items():
                                print(f"{key}: {terminal_text(value)}")

                def records():
                    values = []
                    if getattr(args, "source", "all") in ("planned", "all"):
                        values += [
                            {**x.__dict__, "source": "planned", "status": "claimed"}
                            for x in read_lineage(env=environment)
                            if x.agent == "claude"
                        ]
                    if getattr(args, "source", "all") in ("inferred", "all"):
                        values += [
                            {**x.document(), "source": "inferred"}
                            for x in read_inferences(env=environment)
                        ]
                    return sorted(
                        values, key=lambda x: (x["child_session_id"], x["source"])
                    )

                if action == "list":
                    emit(records())
                    return 0
                if action == "show":
                    found = [
                        x for x in records() if x["child_session_id"] == args.session_id
                    ]
                    if len(found) != 1:
                        raise ClaudeParentError(
                            "Claude parent record not found or source is ambiguous"
                        )
                    emit(found[0])
                    return 0
                if action == "delete":
                    found = [
                        x for x in records() if x["child_session_id"] == args.session_id
                    ]
                    if len(found) != 1:
                        raise ClaudeParentError(
                            "Claude parent record not found or source is ambiguous"
                        )
                    if not args.yes:
                        if (
                            machine
                            or args.no_input
                            or not sys.stdin.isatty()
                            or not sys.stderr.isatty()
                        ):
                            raise ConfigError(
                                "Claude parent delete requires --yes when prompting "
                                "is unavailable"
                            )
                        selected = found[0]
                        print("Delete Claude parent metadata?", file=sys.stderr)
                        print(
                            f"child: {terminal_text(selected['child_session_id'])}",
                            file=sys.stderr,
                        )
                        print(
                            f"parent: {terminal_text(selected['parent_session_id'])}",
                            file=sys.stderr,
                        )
                        print(
                            f"source: {terminal_text(selected['source'])}",
                            file=sys.stderr,
                        )
                        print(
                            "This does not delete Claude transcripts or Git resources.",
                            file=sys.stderr,
                        )
                        if selected["source"] == "planned":
                            print(
                                "Warning: this removes Agent Fork's strongest local "
                                "parent evidence.",
                                file=sys.stderr,
                            )
                        print("Continue? [y/N] ", end="", file=sys.stderr, flush=True)
                        if sys.stdin.readline().strip().lower() not in {"y", "yes"}:
                            print("Claude parent delete cancelled", file=sys.stderr)
                            return 2
                    if found[0]["source"] == "planned":
                        remove_lineage("claude", args.session_id, env=environment)
                    else:
                        remove_inference(args.session_id, env=environment)
                    emit(
                        {
                            "deleted": True,
                            "session_id": args.session_id,
                            "source": found[0]["source"],
                        }
                    )
                    return 0
                ids = []
                if args.current:
                    from agent_fork.agents import assess_agent_signals

                    assessment = assess_agent_signals(environment)
                    if assessment.status == "incomplete":
                        raise AgentSignalIncompleteError(
                            assessment.present, assessment.missing
                        )
                    if assessment.status == "ambiguous":
                        raise ClaudeParentError(
                            "current agent signals are ambiguous: "
                            f"{assessment.diagnosis()}",
                            details=assessment.document(),
                        )
                    if (
                        assessment.context is None
                        or assessment.context.agent != "claude"
                    ):
                        raise ClaudeParentError("no current Claude session detected")
                    ids = [assessment.context.parent_session_id]
                elif args.session_id:
                    ids = [args.session_id]
                corpus = ClaudeLineageCorpus(environment)
                if args.all:
                    ids = [
                        p.stem
                        for p in corpus.paths
                        if find_lineage("claude", p.stem, env=environment) is None
                    ]
                documents = []
                failures = 0
                recorded_count = 0
                bulk_spool = None
                if args.all:
                    from agent_fork.bulk_output import BulkSpool

                    bulk_spool = BulkSpool()
                for sid in ids:
                    try:
                        result = corpus.infer_one(sid)
                        recorded = False
                        if args.record or args.record_all:
                            if not result.recordable:
                                failures += 1
                            elif not corpus.evidence_stable(result):
                                failures += 1
                            else:
                                add_inference(to_record(result), env=environment)
                                recorded = True
                                recorded_count += 1
                        document = {**result.document(), "recorded": recorded}
                        if bulk_spool is None:
                            documents.append(document)
                        else:
                            bulk_spool.append(document)
                    except Exception as error:
                        failures += 1
                        document = {
                            "agent": "claude",
                            "session_id": sid,
                            "relationship": {"status": "unavailable"},
                            "error": str(error),
                            "recorded": False,
                        }
                        if bulk_spool is None:
                            documents.append(document)
                        else:
                            bulk_spool.append(document)
                if bulk_spool is not None:
                    summary = {
                        "total": bulk_spool.count,
                        "recorded": recorded_count,
                        "failed": failures,
                    }
                    if failures:
                        if machine:
                            bulk_spool.render_json(
                                sys.stderr,
                                summary,
                                error_code=(
                                    "claude_parent_partial_record"
                                    if args.record_all
                                    else "claude_parent_unavailable"
                                ),
                                error_message=(
                                    "one or more Claude parent results were not "
                                    "recordable"
                                    if args.record_all
                                    else "one or more Claude parent analyses were "
                                    "unavailable"
                                ),
                            )
                        else:
                            bulk_spool.render_human(sys.stderr, summary)
                        bulk_spool.close()
                        return 3
                    if machine:
                        bulk_spool.render_json(sys.stdout, summary)
                    else:
                        bulk_spool.render_human(sys.stdout, summary)
                    bulk_spool.close()
                    return 0
                analysis = (
                    documents[0]
                    if len(documents) == 1
                    else {
                        "results": documents,
                        "summary": {"total": len(documents), "failed": failures},
                    }
                )
                if failures and (args.record or args.record_all):
                    record_error = (
                        ClaudeParentNotRecordableError
                        if len(documents) == 1
                        else ClaudeParentPartialRecordError
                    )
                    raise record_error(
                        "one or more Claude parent results were not recordable",
                        details={"analysis": analysis},
                        human_message=(
                            "Claude parent analysis completed, but the result is not "
                            "recordable"
                        ),
                    )
                if failures:
                    raise ClaudeParentError(
                        "one or more Claude parent analyses were unavailable",
                        details={"analysis": analysis},
                    )
                emit(analysis)
                return 0
            inspection = inspect_session(environment, cwd=Path.cwd())
            machine = args.json or args.output == "json"
            if args.session_action == "validate":
                has_parent = (
                    True
                    if args.has_parent or args.parent_session_id is not None
                    else False
                    if args.no_parent
                    else None
                )
                document = validate_session(
                    inspection,
                    SessionAssertions(
                        agent=args.agent,
                        session_id=args.session_id,
                        parent_session_id=args.parent_session_id,
                        has_parent=has_parent,
                    ),
                )
                if machine:
                    print(json_line(document))
                else:
                    print("session valid")
                return 0
            if machine:
                print(json_line(inspection.document()))
                return 0
            if inspection.current_session is None:
                if inspection.agent_signal.status == "incomplete":
                    print("agent signal: incomplete")
                print(f"session: {inspection.lineage_status}")
            else:
                current = inspection.current_session
                print(f"agent: {terminal_text(inspection.agent)}")
                print(f"current session: {terminal_text(current.id)}")
                print(
                    "current name: "
                    + (terminal_text(current.name) if current.name is not None else "-")
                )
                if inspection.parent_session is None:
                    print("parent session: -")
                else:
                    print(
                        "parent session: " + terminal_text(inspection.parent_session.id)
                    )
                    print(
                        "parent name: "
                        + (
                            terminal_text(inspection.parent_session.name)
                            if inspection.parent_session.name is not None
                            else "-"
                        )
                    )
                print(f"lineage: {terminal_text(inspection.lineage_status)}")
            for notice in inspection.notices:
                print(f"notice: {terminal_text(notice)}")
            print(f"directory: {terminal_text(inspection.directory)}")
            repository = inspection.repository
            if repository is None:
                print("repository: -")
            else:
                print(f"repository: {terminal_text(repository.root)}")
                print(
                    "branch: "
                    + (
                        terminal_text(repository.branch)
                        if repository.branch is not None
                        else "(detached)"
                    )
                )
                print(
                    "worktree: "
                    f"linked={'yes' if repository.linked_worktree else 'no'} "
                    f"bare={'yes' if repository.bare else 'no'}"
                )
                status = repository.status
                if status is None:
                    print("status: unavailable")
                elif status.clean:
                    print("status: clean")
                else:
                    operation = (
                        terminal_text(status.operation)
                        if status.operation is not None
                        else "-"
                    )
                    print(
                        "status: "
                        f"staged={status.staged} unstaged={status.unstaged} "
                        f"untracked={status.untracked} unmerged={status.unmerged} "
                        f"operation={operation}"
                    )
            fork_command = inspection.fork_command
            if fork_command.status == "available":
                assert fork_command.command is not None
                print(f"fork command: {fork_command.command}")
            else:
                print(f"fork command: unavailable ({fork_command.status})")
            resume_command = inspection.resume_command
            if resume_command.status == "available":
                assert resume_command.command is not None
                print(f"resume command: {resume_command.command}")
            else:
                print(f"resume command: unavailable ({resume_command.status})")
            return 0
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
                allow_dirty=args.allow_dirty,
                allow_unpushed=args.allow_unpushed,
                keep_branch=args.keep_branch,
                dry_run=args.dry_run,
            )
            machine = args.json or args.output == "json"
            if machine:
                from agent_fork.output import json_line

                document = {
                    "removed": result.removed,
                    "target": plan.entry.to_dict(),
                    "keep_branch": args.keep_branch,
                    "dry_run": args.dry_run,
                    "notices": list(result.notices),
                }
                if args.dry_run:
                    document["details"] = result.details.document()
                print(json_line(document))
            else:
                prefix = "would " if args.dry_run else ""
                print(prefix + plan.render(keep_branch=args.keep_branch))
                if args.dry_run and result.details.has_risk:
                    print(result.details.render_preview(plan.branch), file=sys.stderr)
                if args.dry_run:
                    print("nothing was removed")
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
                        f"{item.agent or item.mode}\t{exists}"
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
                    "agent_mode": resolved.agent_mode,
                    "verify": resolved.verify,
                    "copy": resolved.copy,
                    "output": resolved.output,
                    "agents": {
                        "claude": {"extra_args": list(resolved.claude_extra_args)},
                        "codex": {
                            "extra_args": list(resolved.codex_extra_args),
                            "session_name_resolution": (
                                resolved.codex_session_name_resolution
                            ),
                        },
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
                aliases = {
                    "agents.codex.session_name_resolution": (
                        resolved.codex_session_name_resolution
                    )
                }
                if args.key in aliases:
                    value = aliases[args.key]
                elif hasattr(resolved, args.key):
                    value = getattr(resolved, args.key)
                else:
                    raise ConfigError(f"unknown config key: {args.key}")
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
