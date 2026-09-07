"""Hermetic command fixtures for independent agent evaluations of the skill.

Each fixture exposes recorded tool responses, not real installs or forks.
The evaluating agent receives the skill and a request, without an answer key.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

REVISION = "8cc36b03bb8e16b876b0559d806155e83212275d"

_TOOL = r"""
import json
import os
import shlex
import sys
from pathlib import Path

base = Path(__file__).resolve().parent
config = json.loads((base / "fixture.json").read_text())
tool = Path(sys.argv[0]).name
args = sys.argv[1:]
with (base / "calls.jsonl").open("a") as output:
    output.write(json.dumps({
        "tool": tool, "argv": args, "cwd": os.getcwd(),
        "executable": str(Path(sys.argv[0]).absolute()),
    }) + "\n")

def fail(message):
    print(message, file=sys.stderr)
    raise SystemExit(64)

if tool == "git":
    if args != ["ls-remote", "https://github.com/smorinlabs/agent-fork.git",
                "refs/heads/main"]:
        fail("fixture: unsupported git operation")
    print(config["revision"] + "\trefs/heads/main")
    raise SystemExit(0)

installed = tool == "agent-fork"
if tool == "uv" and args == ["tool", "dir", "--bin"]:
    print(base / "installed-bin")
    raise SystemExit(0)
if tool == "uv" and args[:2] == ["tool", "install"]:
    (base / "installed").touch()
    managed = base / "installed-bin/agent-fork"
    managed.parent.mkdir(exist_ok=True)
    code = (base / "tool.py").read_text().replace(
        "base = Path(__file__).resolve().parent", f"base = Path({str(base)!r})", 1)
    managed.write_text(code)
    managed.chmod(0o755)
    executable = base / "bin/agent-fork"
    if config["scenario"] != "install_shadow":
        if executable.is_symlink():
            executable.unlink()
        executable.symlink_to(managed)
    raise SystemExit(0)
if tool == "uv":
    if args[:2] != ["tool", "run"]:
        fail("fixture: unsupported uv operation")
    args = args[2:]
if tool in ("uv", "uvx"):
    source = "git+https://github.com/smorinlabs/agent-fork@" + config["revision"]
    if args[:4] != ["--isolated", "--from", source, "agent-fork"]:
        fail("fixture: unexpected temporary runner arguments")
    args = args[4:]
if tool not in ("agent-fork", "uv", "uvx"):
    fail("fixture: unsupported executable")
if args == ["--version"]:
    print("agent-fork 1.2.0")
    raise SystemExit(0)

active = str(base / "active")
identity = "11111111-1111-4111-8111-111111111111"
command = "codex fork " + identity + " -C " + shlex.quote(active)
document = {
    "agent": "codex",
    "current_session": {"id": identity, "source": "CODEX_THREAD_ID", "name": "fixture"},
    "parent_session": None,
    "lineage": {"status": "not_found"},
    "notices": [],
    "directory": active,
    "repository": {
        "root": active, "branch": "feature/fixture", "detached": False,
        "on_default_branch": False,
        "status": {"clean": True, "staged": 0, "unstaged": 0, "untracked": 0},
    },
    "fork_command": {"status": "available", "command": command},
    "resume_command": {
        "status": "available", "command": command.replace("fork", "resume", 1)},
    "transcript": {"path": None, "exists": False},
}
if args == ["session", "--json"]:
    if installed and not (base / "installed").exists():
        if config["scenario"] in ("stale", "session_only", "install", "malformed"):
            del document["transcript"]
        if config["scenario"] == "malformed":
            document["fork_command"]["status"] = "future-status"
        if config["scenario"] == "wrong_directory":
            document["directory"] = str(base / "wrong")
    print(json.dumps(document))
elif args and args[0] == "fork":
    name = args[1] if len(args) > 1 and not args[1].startswith("-") else "fixture"
    worktree = str(base / ("fork-" + name))
    if "--dry-run" in args:
        print(json.dumps({"dry_run": True, "mutation_performed": False, "plan": {
            "branch": {"name": "worktree-" + name},
            "worktree": {"path": worktree},
            "files_to_carry": {
                "staged": 0, "unstaged": 0, "untracked": 0, "ignored": 0},
        }}))
    else:
        print(json.dumps({"command": command.replace(active, worktree), "fork": {
            "name": name, "branch": "worktree-" + name, "worktree": worktree,
        }}))
else:
    fail("fixture: unsupported Agent Fork operation")
"""


def create_fixture(directory: Path, scenario: str, skill: Path) -> Path:
    """Return an active directory with copied instructions and fake tool PATH.

    Set PATH to <directory>/bin:/usr/bin:/bin in every evaluation shell, with
    login=False. Do not expose the host's real uv or agent-fork executables.
    """
    directory.mkdir(parents=True)
    active = directory / "active"
    active.mkdir()
    shutil.copytree(skill, active / ".agents/skills/agent-fork")
    (active / "pyproject.toml").write_text(
        '[project]\nname = "fixture-active-repository"\nversion = "0.0.0"\n'
    )
    (directory / "fixture.json").write_text(
        json.dumps({"scenario": scenario, "revision": REVISION}) + "\n"
    )
    script = directory / "tool.py"
    script.write_text(f"#!{sys.executable}\n" + _TOOL)
    script.chmod(0o755)
    command_bin = directory / "bin"
    command_bin.mkdir()
    tools = ["git", "uv"]
    if scenario != "uv_only":
        tools.append("uvx")
    if scenario in (
        "stale",
        "session_only",
        "install",
        "install_shadow",
        "malformed",
        "wrong_directory",
    ):
        tools.append("agent-fork")
    for tool in tools:
        (command_bin / tool).symlink_to(script)
    return active
