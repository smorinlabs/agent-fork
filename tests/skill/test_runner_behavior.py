"""Execute skill runner examples with real uv and offline, disposable sources.

These checks validate the commands' process behavior. They do not simulate an
assistant deciding when to recover or claim to validate fetching from GitHub.
"""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

from conftest import sealed_env

ROOT = Path(__file__).parents[2]
SKILL = ROOT / ".agents/skills/agent-fork/SKILL.md"


def _executable(name: str) -> str:
    executable = shutil.which(name)
    assert executable is not None, f"runner behavior checks require real {name}"
    return executable


def _run(argv: list[str], *, cwd: Path, env: dict[str, str]) -> str:
    result = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, (
        f"{shlex.join(argv)} exited {result.returncode}\n{result.stderr}"
    )
    return result.stdout


@pytest.fixture
def runner_env(tmp_path: Path) -> dict[str, str]:
    return sealed_env(
        {
            "HOME": str(tmp_path / "home"),
            "UV_CACHE_DIR": str(tmp_path / "cache"),
            "UV_TOOL_DIR": str(tmp_path / "tools"),
            "UV_TOOL_BIN_DIR": str(tmp_path / "bin"),
            "UV_PYTHON": sys.executable,
            "UV_PYTHON_DOWNLOADS": "never",
            "UV_OFFLINE": "1",
            "UV_NO_CONFIG": "1",
        }
    )


def _wheel(directory: Path, version: str, files: dict[str, bytes]) -> Path:
    """Supply a local distribution without build dependencies or registry access."""
    directory.mkdir(parents=True)
    wheel = directory / f"agent_fork-{version}-py3-none-any.whl"
    info = f"agent_fork-{version}.dist-info"
    contents = {
        **files,
        f"{info}/METADATA": (
            f"Metadata-Version: 2.1\nName: agent-fork\nVersion: {version}\n"
        ).encode(),
        f"{info}/WHEEL": (
            b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
        ),
        f"{info}/entry_points.txt": (
            b"[console_scripts]\nagent-fork = agent_fork.cli:main\n"
        ),
    }
    with ZipFile(wheel, "w") as archive:
        for name, content in contents.items():
            archive.writestr(name, content)
        archive.writestr(
            f"{info}/RECORD",
            "".join(f"{name},,\n" for name in [*contents, f"{info}/RECORD"]),
        )
    return wheel


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    """Package the real session CLI with a stdlib-only fixture build backend.

    Session inspection uses no third-party imports. This fixture intentionally
    tests that route without resolving the production packaging dependencies.
    """
    directory = tmp_path / "Agent Fork checkout's tree"
    directory.mkdir()
    wheel = _wheel(
        directory / "wheel",
        "1.2.0",
        {
            str(path.relative_to(ROOT / "src")): path.read_bytes()
            for path in (ROOT / "src/agent_fork").rglob("*.py")
        },
    )
    (directory / "pyproject.toml").write_text(
        '[project]\nname = "agent-fork"\nversion = "1.2.0"\n'
        'requires-python = ">=3.11"\n'
        "[build-system]\nrequires = []\n"
        'build-backend = "fixture_backend"\nbackend-path = ["."]\n'
    )
    (directory / "fixture_backend.py").write_text(
        "from pathlib import Path\nimport shutil\n"
        "def build_wheel(wheel_directory, config_settings=None, "
        "metadata_directory=None):\n"
        f"    source = Path(__file__).parent / 'wheel' / {wheel.name!r}\n"
        "    shutil.copyfile(source, Path(wheel_directory) / source.name)\n"
        "    return source.name\n"
        "build_editable = build_wheel\n"
    )
    return directory


def _checkout_command(checkout: Path) -> list[str]:
    commands = [
        line
        for line in map(str.strip, _runner_instructions().splitlines())
        if line.startswith("uv run ")
        and "'<checkout>'" in line
        and line.endswith("agent-fork session --json")
    ]
    assert len(commands) == 1, "expected one executable checkout example"
    argv = shlex.split(commands[0].replace("'<checkout>'", shlex.quote(str(checkout))))
    argv[0] = _executable("uv")
    return argv


def _runner_instructions() -> str:
    text = SKILL.read_text()
    reference = "references/cli-runner.md"
    if f"]({reference})" in text:
        text += "\n" + (SKILL.parent / reference).read_text()
    return text


@pytest.fixture
def active_repository(tmp_path: Path, runner_env: dict[str, str]) -> Path:
    directory = tmp_path / "active repository"
    directory.mkdir()
    git = _executable("git")
    _run([git, "init", "--initial-branch=main"], cwd=directory, env=runner_env)
    _run(
        [git, "commit", "--allow-empty", "-m", "fixture"], cwd=directory, env=runner_env
    )
    return directory


def test_documented_checkout_command_preserves_active_directory(
    active_repository: Path, runner_env: dict[str, str], checkout: Path
) -> None:
    document = json.loads(
        _run(_checkout_command(checkout), cwd=active_repository, env=runner_env)
    )
    assert document["directory"] == str(active_repository.resolve())
    assert document["repository"]["root"] == str(active_repository.resolve())
    assert "transcript" in document


def test_directory_inverse_control_detects_original_checkout_bug(
    active_repository: Path, runner_env: dict[str, str], checkout: Path
) -> None:
    document = json.loads(
        _run(
            [
                _executable("uv"),
                "run",
                "--directory",
                str(checkout),
                "agent-fork",
                "session",
                "--json",
            ],
            cwd=active_repository,
            env=runner_env,
        )
    )
    assert document["directory"] == str(checkout.resolve())
    assert document["directory"] != str(active_repository.resolve())
    assert document["repository"] is None


def _probe_wheel(directory: Path, source: str, *, transcript: bool) -> Path:
    """Record runner provenance/argv; this fixture does not implement real forks."""
    code = (
        "import json, os, sys\n"
        "def main():\n"
        "    if sys.argv[1:] == ['--version']:\n"
        "        print('agent-fork 1.2.0')\n"
        "        return\n"
        "    document = {'directory': os.getcwd(), 'argv': sys.argv[1:], "
        f"'source': {source!r}, 'environment': sys.prefix}}\n"
        f"    if {transcript!r}:\n"
        "        document['transcript'] = {'path': None, 'exists': False}\n"
        "    print(json.dumps(document))\n"
    )
    return _wheel(
        directory,
        "1.2.0",
        {"agent_fork/__init__.py": b"", "agent_fork/cli.py": code.encode()},
    )


def _documented_tool_prefix(
    runner: str, source: Path, env: dict[str, str]
) -> list[str]:
    candidates = [
        shlex.split(line)
        for line in map(str.strip, _runner_instructions().splitlines())
        if line.startswith(f"{runner} ")
        and "--from " in line
        and line.endswith("agent-fork session --json")
    ]
    assert len(candidates) == 1, f"expected one executable {runner} session example"
    argv = candidates[0]
    argv[argv.index("--from") + 1] = str(source)
    executable = shutil.which(argv[0], path=env["PATH"])
    assert executable is not None, f"{runner} is unavailable in the fixture PATH"
    argv[0] = executable
    return argv[:-2]


def _file_snapshot(directory: Path) -> dict[str, str]:
    return {
        str(path.relative_to(directory)): (
            f"symlink:{path.readlink()}"
            if path.is_symlink()
            else hashlib.sha256(path.read_bytes()).hexdigest()
        )
        for path in directory.rglob("*")
        if path.is_file() or path.is_symlink()
    }


@pytest.mark.parametrize("runner", ["uvx", "uv tool run"])
def test_temporary_runner_retains_source_and_preserves_installed_tool(
    tmp_path: Path, runner_env: dict[str, str], runner: str
) -> None:
    active = tmp_path / "active repository"
    active.mkdir()
    command_bin = tmp_path / "command-bin"
    command_bin.mkdir()
    # uv's relocatable cached entry points use these standard shell utilities.
    # Expose them without exposing the host's uvx in the fallback scenario.
    for executable in ("uv", "dirname", "realpath"):
        (command_bin / executable).symlink_to(_executable(executable))
    if runner == "uvx":
        (command_bin / "uvx").symlink_to(_executable("uvx"))
    env = {
        **runner_env,
        "PATH": os.pathsep.join([str(command_bin), runner_env["UV_TOOL_BIN_DIR"]]),
    }
    if runner == "uv tool run":
        assert shutil.which("uvx", path=env["PATH"]) is None

    stale = _probe_wheel(tmp_path / "stale", "stale", transcript=False)
    selected = _probe_wheel(tmp_path / "selected", "selected", transcript=True)
    _run(
        [str(command_bin / "uv"), "tool", "install", str(stale)],
        cwd=active,
        env=env,
    )
    installed = str(Path(env["UV_TOOL_BIN_DIR"]) / "agent-fork")
    installed_document = json.loads(
        _run([installed, "session", "--json"], cwd=active, env=env)
    )
    assert installed_document["source"] == "stale"
    assert "transcript" not in installed_document
    before_tools = _file_snapshot(Path(env["UV_TOOL_DIR"]))
    before_bin = _file_snapshot(Path(env["UV_TOOL_BIN_DIR"]))

    # Prime a stale temporary environment too. Both fixture sources deliberately
    # advertise the same version; a version check cannot select the right code.
    stale_prefix = _documented_tool_prefix(runner, stale, env)
    stale_cached = json.loads(
        _run([*stale_prefix, "session", "--json"], cwd=active, env=env)
    )
    assert stale_cached["source"] == "stale"
    prefix = _documented_tool_prefix(runner, selected, env)
    assert _run([*prefix, "--version"], cwd=active, env=env) == _run(
        [installed, "--version"], cwd=active, env=env
    )

    for arguments in (
        ["session", "--json"],
        ["fork", "review-auth", "--dry-run", "--require-agent", "--json"],
        ["fork", "review-auth", "--require-agent", "--json"],
    ):
        document = json.loads(_run([*prefix, *arguments], cwd=active, env=env))
        assert document["source"] == "selected"
        assert document["argv"] == arguments
        assert document["directory"] == str(active.resolve())
        assert document["transcript"] == {"path": None, "exists": False}
        assert Path(document["environment"]).is_relative_to(Path(env["UV_CACHE_DIR"]))

    assert _file_snapshot(Path(env["UV_TOOL_DIR"])) == before_tools
    assert _file_snapshot(Path(env["UV_TOOL_BIN_DIR"])) == before_bin
    assert json.loads(_run([installed, "session", "--json"], cwd=active, env=env)) == (
        installed_document
    )
