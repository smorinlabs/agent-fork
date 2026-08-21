"""Locale-independent human and machine result rendering."""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from agent_fork.errors import ERROR_CATALOG, AgentForkError

STABLE_ERROR_CODES = tuple(ERROR_CATALOG)


def json_line(value: object) -> str:
    """Render one machine-readable line with every non-ASCII codepoint escaped.

    ``ensure_ascii=True`` is a safety property here, not a formatting
    preference. Repository-controlled strings reach this function — branch
    names, paths, session names — and JSON escapes only the C0 controls on its
    own. Without this, C1 controls and bidi overrides such as U+202E would
    reach the terminal verbatim and reorder the text a reader sees.
    """
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def terminal_text(value: object) -> str:
    """Render one untrusted scalar without terminal control characters.

    Intentionally separate from ``text.escape_terminal_text``: this path is
    ASCII-only via a ``json.dumps`` trick and serves compact CLI table output,
    while ``escape_terminal_text`` is surrogate-aware for repository-controlled
    strings elsewhere.
    """
    return json.dumps(str(value), ensure_ascii=True)[1:-1]


@dataclass(frozen=True)
class ForkOutput:
    agent: str | None
    parent_session_id: str | None
    mode: str
    name: str
    branch: str
    worktree: Path
    anchor_commit: str
    with_state: bool
    with_ignored: bool
    verification: dict[str, bool]
    command: str
    notices: tuple[str, ...] = ()
    parent_session_name: str | None = None
    # `SetupHookResult.document()` output, supplied by every real fork. `None`
    # renders as `null` rather than omitting the key, so the shape a consumer
    # parses is the same whether or not a hook step was evaluated.
    setup_hook: dict[str, object] | None = None

    def document(self) -> dict[str, object]:
        result: dict[str, object] = {
            "setup_hook": self.setup_hook,
            "mode": self.mode,
            "fork": {
                "name": self.name,
                "branch": self.branch,
                "worktree": str(self.worktree),
                "anchor_commit": self.anchor_commit,
                "mode": {
                    "with_state": self.with_state,
                    "with_ignored": self.with_ignored,
                },
            },
            "verification": self.verification,
            "command": self.command,
            "notices": list(self.notices),
        }
        if self.agent is not None:
            result["agent"] = self.agent
            result["parent_session_id"] = self.parent_session_id
            if self.parent_session_name is not None:
                result["parent_session_name"] = self.parent_session_name
        if self.agent == "codex":
            result["cwd_prompt_expected"] = False
        return result

    def render(self, output: str = "text") -> str:
        if output == "json":
            return json_line(self.document())
        lines = [
            f"fork: {self.name}",
            f"branch: {self.branch}",
            f"worktree: {self.worktree}",
        ]
        if self.mode == "git-only":
            lines.insert(0, "mode: git-only")
        lines.extend(("", self.command))
        return "\n".join(lines)


def setup_hook_plan_line(hook: dict[str, object] | None) -> str | None:
    """Render one dry-run disclosure line from a predicted setup-hook plan."""
    if hook is None:
        return None
    if hook["policy"] == "off":
        return "setup-hook: disabled (--setup-hook-policy off)"
    if not hook["present"]:
        return "setup-hook: none"
    state = (
        "eligible at the fork anchor"
        if hook["eligibility"] == "eligible"
        # Every reason-less eligibility is handled above today; the fallback
        # keeps a future one from rendering the literal string "None" at a user.
        else hook["reason"] or f"eligibility {hook['eligibility']}"
    )
    if hook["would_run"]:
        return (
            f"setup-hook: {hook['path']}; {state}; would run; "
            f"timeout {hook['timeout_seconds']}s"
        )
    return (
        f"setup-hook: {hook['path']}; {state}; would skip; "
        "override --setup-hook-policy any"
    )


@dataclass(frozen=True)
class DryRunOutput:
    branch: str
    worktree: Path
    staged: int
    unstaged: int
    untracked: int
    ignored: int
    command: str
    notices: tuple[str, ...] = ()
    # Predicted parent-side, since `materialize()` has not run: the document
    # says `prediction: true` rather than implying certainty about the child.
    setup_hook: dict[str, object] | None = None

    def document(self) -> dict[str, object]:
        return {
            "dry_run": True,
            "plan": {
                "branch": {"action": "create", "name": self.branch},
                "worktree": {"action": "create", "path": str(self.worktree)},
                "files_to_carry": {
                    "staged": self.staged,
                    "unstaged": self.unstaged,
                    "untracked": self.untracked,
                    "ignored": self.ignored,
                },
                "setup_hook": self.setup_hook,
            },
            "command": self.command,
            "notices": list(self.notices),
            "validation": {"scope": "local", "passed": True},
            "mutation_performed": False,
        }

    def render(self, output: str = "text") -> str:
        if output == "json":
            return json_line(self.document())
        lines = [
            f"branch: create {self.branch}",
            f"worktree: create {self.worktree}",
            f"files-to-carry: staged={self.staged} unstaged={self.unstaged} "
            f"untracked={self.untracked} ignored={self.ignored}",
        ]
        hook_line = setup_hook_plan_line(self.setup_hook)
        if hook_line is not None:
            lines.append(hook_line)
        if self.notices:
            lines.append("notices: " + "; ".join(self.notices))
        lines.extend(
            (
                f"paste command: {self.command}",
                "validation: local-only; no mutation performed",
            )
        )
        return "\n".join(lines)


def render_error(error: BaseException, *, machine: bool = False) -> str:
    code = error.code if isinstance(error, AgentForkError) else "runtime_error"
    if machine:
        document: dict[str, object] = {"code": code, "message": str(error)}
        details = getattr(error, "details", None)
        if details is not None:
            document["details"] = details
        return json_line({"error": document})
    message = getattr(error, "human_message", None) or str(error)
    return f"{code}: {message}"


def copy_to_clipboard(command: str) -> tuple[str, ...]:
    """Try OSC52, then platform helpers; failure remains notice-only."""
    try:
        import sys

        if sys.stderr.isatty():
            payload = base64.b64encode(command.encode()).decode()
            sys.stderr.write(f"\033]52;c;{payload}\a")
            sys.stderr.flush()
            return ()
    except OSError:
        pass
    candidates = (
        ("pbcopy",),
        ("xclip", "-selection", "clipboard"),
        ("wl-copy",),
    )
    for candidate in candidates:
        executable = shutil.which(candidate[0])
        if executable is None:
            continue
        completed = subprocess.run(
            [executable, *candidate[1:]], input=command.encode(), capture_output=True
        )
        if completed.returncode == 0:
            return ()
    return ("clipboard copy failed; paste command remains available on stdout",)
