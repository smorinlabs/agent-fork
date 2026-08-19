# Version Consolidation (Option E) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `pyproject.toml` the only hand-edited version site: fix the one runtime bug, reword one README sentence out of the set, and machine-write the remaining 7 sites via a release-please-shaped `scripts/sync_versions.py` wired into `just bump` / `just version-check`.

**Architecture:** `pyproject.toml:3` stays the single source of truth; `uv.lock` and the two `importlib.metadata` readers already follow it. A new stdlib-only script, `scripts/sync_versions.py`, propagates that version to 4 JSON fields (addressed by explicit jsonpath, release-please's `json` updater convention) and 3 annotated text lines (marked `x-release-please-version`, release-please's `generic` updater convention), so P01-T20 later replaces the script with one `release-please-config.json` block without reformatting any target file. `just all` gains a `version-check` dependency, so CI inherits drift enforcement with zero workflow changes.

**Tech Stack:** Python 3.11+ stdlib (`tomllib`, `json`, `re`, `argparse`), pytest (untagged top-level infra tests), `uv` (`uv version` for the bump), `just`, ruff + ty (existing gates).

**Spec:** docs/superpowers/specs/2026-08-18-version-consolidation-design.md (§3.5, "Option E")

## Global Constraints

- **No version site outside `pyproject.toml` is ever hand-edited** for a normal bump — every other site is machine-written by `scripts/sync_versions.py` (interim) and by release-please after P01-T20.
- **Text-file markers must exactly match release-please's `x-release-please-version` convention** — the literal token on the same line as the semver it governs; any semver-shaped substring on an annotated line is rewritten regardless of its current value.
- **JSON sites must use explicit jsonpath addressing, never plain-string entries** — a plain-string `.json` entry defaults to `$.version` and silently no-ops on files like `marketplace.json` (spec §3.5.1 footgun).
- **Generated JSON output must round-trip through 2-space canonical `json.dumps` (`indent=2, ensure_ascii=False`, trailing newline) or the script must refuse to write it** — never silently reformat.
- **Stricter than release-please, on purpose:** a missing jsonpath, a wrong `x-release-please-version` annotation count, or an annotated line with no semver is a hard error (release-please silently skips; lost markers must fail loudly here).
- **Generated output is committed, not gitignored** — the manifests are read from the repo by marketplace machinery and `README.md` renders on GitHub; `--check` is what makes committed-and-generated safe.
- **Zero workflow-file changes** — CI's `matrix-and-tests` job runs `just all`, which inherits `version-check`.
- **No new `@pytest.mark.matrix` rows.** The new tests are tooling/infra tests placed at the top level of `tests/` (precedent: `tests/test_package.py`, `tests/test_check_matrix.py`). `scripts/check_matrix.py` maps only `tests/unit|pipeline|cli|live|fixtures` to tiers; an untagged test inside those directories fails CHECK1, and top-level `tests/*.py` files are out of its scope. Do not "tidy" a test into `tests/unit/` — it will break `just check-matrix`.
- **Version values change only in Task 5.** Tasks 1–4 must not alter any asserted version literal; Task 5's single script run is the repair.
- **Work in a dedicated git worktree branch** (repo discipline) — never on a live `main` checkout.
- Line numbers cited below are from worktree state at plan-writing time (`pyproject.toml` version `1.1.0`); re-verify them before editing if `main` has moved.

---

### Task 1: `codex_app_server.py` reads its handshake version from installed metadata

**Files:**
- Modify: `src/agent_fork/codex_app_server.py:10-12` (imports) and `:117-124` (the `initialize` send)
- Test: `tests/test_package.py` (append one test)

**Interfaces:**
- Consumes: nothing from other tasks (this site leaves the propagation set entirely).
- Produces: `codex_app_server.py` with no version literal; the `initialize` handshake's `clientInfo.version` always equals `importlib.metadata.version("agent-fork")`.

**Placement rationale (do not relocate):** the existing handshake tests live in `tests/unit/test_codex_resolution.py` and every test there carries a `@pytest.mark.matrix("T-…")` product row. This new test is version-plumbing infra, not a product-matrix row, so it goes in the top-level `tests/test_package.py` ("the package … exposes its metadata"), which `scripts/check_matrix.py` does not tier-scope. An untagged test added to `tests/unit/` would fail `just check-matrix` (CHECK1).

- [ ] **Step 1: Write the failing test**

In `tests/test_package.py`, change the import block from:

```python
import tomllib
from importlib.metadata import version
from pathlib import Path
```

to:

```python
import json
import tomllib
from importlib.metadata import version
from pathlib import Path
```

and append at the end of the file (the fake `codex` script pattern mirrors `_server()` in `tests/unit/test_codex_resolution.py`, extended to record every request it receives):

```python
def test_app_server_handshake_reports_installed_version(tmp_path) -> None:
    from agent_fork.codex_app_server import list_named_threads

    recorded = tmp_path / "requests.jsonl"
    server = tmp_path / "codex"
    server.write_text(
        "#!/usr/bin/env python3\n"
        "import json,sys\n"
        f"log=open({str(recorded)!r},'a')\n"
        "for line in sys.stdin:\n"
        " log.write(line); log.flush()\n"
        " request=json.loads(line)\n"
        " if 'id' not in request: continue\n"
        " result={} if request['id']==1 else {'data':[]}\n"
        " print(json.dumps({'id':request['id'],'result':result}),flush=True)\n"
    )
    server.chmod(0o755)
    assert list_named_threads(str(server), "hello", {}) == ()
    requests = [json.loads(line) for line in recorded.read_text().splitlines()]
    initialize = next(r for r in requests if r.get("method") == "initialize")
    assert initialize["params"]["clientInfo"] == {
        "name": "agent-fork",
        "version": version("agent-fork"),
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_package.py -q`

Expected: FAIL with `AssertionError: assert {'name': 'age...ion': '1.0.0'} == {'name': 'age...ion': '1.1.0'}` — the hardcoded `1.0.0` handshake vs. the installed metadata version (currently `1.1.0`; the right side always tracks `pyproject.toml`'s built metadata). Validated: this exact failure was reproduced against the current code.

- [ ] **Step 3: Write minimal implementation**

In `src/agent_fork/codex_app_server.py`, change the import block (lines 10–12):

```python
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast
```

to:

```python
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.metadata import version
from typing import cast
```

and change the `initialize` send (lines 117–124):

```python
    try:
        send(
            {
                "id": 1,
                "method": "initialize",
                "params": {"clientInfo": {"name": "agent-fork", "version": "1.0.0"}},
            }
        )
```

to:

```python
    try:
        send(
            {
                "id": 1,
                "method": "initialize",
                "params": {
                    "clientInfo": {
                        "name": "agent-fork",
                        "version": version("agent-fork"),
                    }
                },
            }
        )
```

(This matches `cli.py:13`/`__init__.py:3`'s `from importlib.metadata import version` pattern, and is already ruff-format-stable and ty-clean — validated.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_package.py tests/unit/test_codex_resolution.py -q`

Expected: PASS (all tests; the existing resolution tests prove no handshake regression).

- [ ] **Step 5: Commit**

```bash
git add src/agent_fork/codex_app_server.py tests/test_package.py
git commit -m "fix(codex): read the app-server handshake version from installed metadata"
```

---

### Task 2: Reword `README.md:147` out of the propagation set

**Files:**
- Modify: `README.md:147-148`

**Interfaces:**
- Consumes: nothing.
- Produces: a README whose only remaining version literal is line 190 (annotated in Task 3, machine-written from Task 5 on) — a precondition for `GENERIC_SITES["README.md"] == 1` in Task 4.

- [ ] **Step 1: Make the edit**

Change lines 147–148:

```markdown
> PyPI and Homebrew releases land with v1.0.0; after PyPI publication the
> no-install command becomes simply `uvx agent-fork`.
```

to:

```markdown
> After PyPI publication the no-install command becomes simply
> `uvx agent-fork`.
```

(The old sentence described a v1.0.0 release that never shipped to PyPI — the placeholder there is `0.0.0.dev0`. The reword drops the version claim entirely, per spec §3.5.2; nothing is left to track.)

- [ ] **Step 2: Verify the edit**

Run: `grep -c "land with v" README.md; grep -nE "1\.0\.0|1\.1\.0" README.md`

Expected: first command prints `0`; second prints exactly one line — line 190's `agent-fork 1.0.0` (still stale on purpose until Task 5). Do **not** grep for all `\d+.\d+.\d+` shapes — lines 150–152 legitimately mention tool versions (`2.0.73`, `0.95`, `2.19`) that are not version sites.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(readme): drop the stale version literal from the PyPI availability note"
```

---

### Task 3: Annotate the three text-file sites with `x-release-please-version`

**Files:**
- Modify: `tests/cli/test_cli.py:43`
- Modify: `scripts/check_clean_install.sh:12`
- Modify: `README.md:190-191`

**Interfaces:**
- Consumes: Task 2 (README has no other version literal, so the file's annotation count is exactly 1).
- Produces: the three `GENERIC_SITES` entries Task 4's script expects, each with annotation count 1. Asserted values are **not** changed here (`1.1.0` in the two tripwires is already correct; README's `1.0.0` stays stale until Task 5).

- [ ] **Step 1: Annotate `tests/cli/test_cli.py:43`**

Change:

```python
        assert completed.stdout == b"agent-fork 1.1.0\n"
```

to:

```python
        assert completed.stdout == b"agent-fork 1.1.0\n"  # x-release-please-version
```

(84 columns — inside ruff's 88 limit; validated format-stable.)

- [ ] **Step 2: Annotate `scripts/check_clean_install.sh:12`**

Change:

```bash
test "$version_output" = "agent-fork 1.1.0"
```

to:

```bash
test "$version_output" = "agent-fork 1.1.0" # x-release-please-version
```

- [ ] **Step 3: Annotate `README.md:190-191`**

Change:

```markdown
The version command must print `agent-fork 1.0.0`. Both symlinks must resolve
to this repository's `.agents/skills/agent-fork` directory.
```

to:

```markdown
The version command must print `agent-fork 1.0.0`. <!-- x-release-please-version -->
Both symlinks must resolve to this repository's `.agents/skills/agent-fork`
directory.
```

(The HTML comment renders as nothing on GitHub; it must sit on the same line as the semver — the `generic` updater rewrites semver tokens only on annotated lines. The value stays `1.0.0` here; Task 5 repairs it.)

- [ ] **Step 4: Verify counts and that nothing broke**

Run:

```bash
grep -c "x-release-please-version" tests/cli/test_cli.py scripts/check_clean_install.sh README.md
uv run ruff format --check tests/cli/test_cli.py
bash -n scripts/check_clean_install.sh
uv run pytest tests/cli/test_cli.py -q
```

Expected: the grep prints `tests/cli/test_cli.py:1`, `scripts/check_clean_install.sh:1`, `README.md:1`; ruff reports the file already formatted; `bash -n` is silent; the CLI tests PASS (values were untouched).

- [ ] **Step 5: Commit**

```bash
git add tests/cli/test_cli.py scripts/check_clean_install.sh README.md
git commit -m "chore(release): annotate version tripwires with x-release-please-version markers"
```

---

### Task 4: Build `scripts/sync_versions.py` (TDD)

**Files:**
- Create: `scripts/sync_versions.py`
- Test: `tests/test_sync_versions.py`

**Interfaces:**
- Consumes: Task 3's annotations (the real-repo site tables reference them, though the tests here never touch real repo files — `ROOT`, `JSON_SITES`, and `GENERIC_SITES` are monkeypatched to `tmp_path` fixtures).
- Produces: `render_json(path, dotted_paths, version)`, `render_generic(path, expected_count, version)`, `main()` (write mode + `--check`), and the module constants `ROOT`, `SEMVER`, `ANNOTATION`, `JSON_SITES`, `GENERIC_SITES` — consumed by Tasks 5 and 6 via `uv run python scripts/sync_versions.py [--check]`.

Do **not** run the script against the real repo in this task — that is Task 5's mutation.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_sync_versions.py` (top-level `tests/`, untagged — see Global Constraints; `from scripts import …` works via pytest's `pythonpath = ["."]`, same as `tests/test_check_matrix.py`):

```python
"""Tooling tests: scripts/sync_versions.py propagation, guards, and check mode."""

import json
import sys

import pytest
from scripts import sync_versions
from scripts.sync_versions import render_generic, render_json


def _canonical(data):
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _fake_repo(tmp_path, project_version, json_version, text_version):
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname = "demo"\nversion = "{project_version}"\n'
    )
    (tmp_path / "plugin.json").write_text(
        _canonical({"name": "demo", "version": json_version})
    )
    (tmp_path / "notes.md").write_text(
        f"prints `demo {text_version}`. <!-- x-release-please-version -->\n"
    )
    return tmp_path


def _point_script_at(monkeypatch, root):
    monkeypatch.setattr(sync_versions, "ROOT", root)
    monkeypatch.setattr(sync_versions, "JSON_SITES", {"plugin.json": ["version"]})
    monkeypatch.setattr(sync_versions, "GENERIC_SITES", {"notes.md": 1})


def test_render_json_rewrites_only_the_addressed_field(tmp_path):
    path = tmp_path / "plugin.json"
    path.write_text(_canonical({"name": "demo", "version": "1.0.0"}))
    assert render_json(path, ["version"], "2.0.0") == _canonical(
        {"name": "demo", "version": "2.0.0"}
    )


def test_render_json_handles_nested_and_list_jsonpaths(tmp_path):
    path = tmp_path / "marketplace.json"
    data = {
        "metadata": {"version": "1.0.0"},
        "plugins": [{"name": "demo", "version": "1.0.0"}],
    }
    path.write_text(_canonical(data))
    rendered = render_json(path, ["metadata.version", "plugins.0.version"], "2.0.0")
    assert json.loads(rendered) == {
        "metadata": {"version": "2.0.0"},
        "plugins": [{"name": "demo", "version": "2.0.0"}],
    }


def test_render_json_refuses_non_canonical_form(tmp_path):
    path = tmp_path / "plugin.json"
    path.write_text('{"name": "demo", "version": "1.0.0"}\n')  # one line, not 2-space
    with pytest.raises(SystemExit, match="not in canonical 2-space JSON form"):
        render_json(path, ["version"], "2.0.0")


def test_render_json_missing_jsonpath_is_a_hard_error(tmp_path):
    path = tmp_path / "plugin.json"
    path.write_text(_canonical({"name": "demo"}))
    with pytest.raises(KeyError, match="version"):
        render_json(path, ["version"], "2.0.0")


def test_render_generic_rewrites_semver_on_annotated_lines_only(tmp_path):
    path = tmp_path / "notes.md"
    path.write_text(
        "unrelated 0.9.9 stays\n"
        "prints `demo 1.0.0`. <!-- x-release-please-version -->\n"
    )
    assert render_generic(path, 1, "2.0.0") == (
        "unrelated 0.9.9 stays\n"
        "prints `demo 2.0.0`. <!-- x-release-please-version -->\n"
    )


def test_render_generic_wrong_annotation_count_is_a_hard_error(tmp_path):
    path = tmp_path / "notes.md"
    path.write_text("no annotation here 1.0.0\n")
    with pytest.raises(SystemExit, match="expected 1 'x-release-please-version'"):
        render_generic(path, 1, "2.0.0")


def test_render_generic_annotated_line_without_semver_is_a_hard_error(tmp_path):
    path = tmp_path / "notes.md"
    path.write_text("stale marker, no version <!-- x-release-please-version -->\n")
    with pytest.raises(SystemExit, match="line 1 has no semver"):
        render_generic(path, 1, "2.0.0")


def test_write_mode_repairs_stale_sites_idempotently(tmp_path, monkeypatch, capsys):
    root = _fake_repo(tmp_path, "2.0.0", "1.0.0", "1.5.0")
    _point_script_at(monkeypatch, root)
    monkeypatch.setattr(sys, "argv", ["sync_versions.py"])
    sync_versions.main()
    assert json.loads((root / "plugin.json").read_text())["version"] == "2.0.0"
    assert "`demo 2.0.0`" in (root / "notes.md").read_text()
    out = capsys.readouterr().out
    assert "synced plugin.json" in out and "synced notes.md" in out
    sync_versions.main()  # second run converges: nothing left to sync
    assert "synced" not in capsys.readouterr().out


def test_check_mode_with_no_drift_exits_zero_and_writes_nothing(tmp_path, monkeypatch):
    root = _fake_repo(tmp_path, "2.0.0", "2.0.0", "2.0.0")
    _point_script_at(monkeypatch, root)
    monkeypatch.setattr(sys, "argv", ["sync_versions.py", "--check"])
    before = {p.name: p.read_text() for p in root.iterdir()}
    sync_versions.main()  # returning without SystemExit is exit code 0
    assert {p.name: p.read_text() for p in root.iterdir()} == before


def test_check_mode_with_drift_exits_nonzero_names_files_writes_nothing(
    tmp_path, monkeypatch
):
    root = _fake_repo(tmp_path, "2.0.0", "1.0.0", "2.0.0")
    _point_script_at(monkeypatch, root)
    monkeypatch.setattr(sys, "argv", ["sync_versions.py", "--check"])
    before = {p.name: p.read_text() for p in root.iterdir()}
    with pytest.raises(SystemExit, match="version drift.*plugin.json") as excinfo:
        sync_versions.main()
    assert excinfo.value.code != 0
    assert {p.name: p.read_text() for p in root.iterdir()} == before
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_sync_versions.py -q`

Expected: FAIL at collection with `ImportError: cannot import name 'sync_versions' from 'scripts'` (validated verbatim).

- [ ] **Step 3: Write the implementation**

Create `scripts/sync_versions.py` — this is spec §3.5.3's script with only two mechanical changes for the repo's ruff gates (imports split one-per-line for E401; two lines wrapped for E501/format). Logic is byte-for-byte the spec's:

```python
#!/usr/bin/env python3
"""Propagate pyproject.toml's version to every declared site.

Interim stand-in for release-please extra-files (P01-T20). Addressing
conventions are release-please's own, so migration = add
release-please-config.json mirroring the tables below, delete this script.
  - JSON sites: jsonpath addressing (release-please `json` updater).
  - Text sites: `x-release-please-version` inline annotations
    (release-please `generic` updater) -- any semver on an annotated
    line is rewritten, regardless of its current value.
Deliberately stricter than release-please: a missing jsonpath, a missing
annotation, or an annotated line with no semver is a hard error here
(release-please silently skips) -- lost markers must fail loudly.
"""

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# release-please's own semver pattern
SEMVER = re.compile(r"\d+\.\d+\.\d+(?:-[\w.]+)?(?:\+[-\w.]+)?")
ANNOTATION = "x-release-please-version"

# Mirror of the future release-please-config.json `extra-files` entries.
JSON_SITES = {  # path -> list of dotted paths ($.-less jsonpath)
    ".claude-plugin/plugin.json": ["version"],
    ".codex-plugin/plugin.json": ["version"],
    ".claude-plugin/marketplace.json": ["metadata.version", "plugins.0.version"],
}
GENERIC_SITES = {  # path -> expected annotation count
    "tests/cli/test_cli.py": 1,
    "scripts/check_clean_install.sh": 1,
    "README.md": 1,
}


def _set(obj, dotted, value):
    *parents, leaf = dotted.split(".")
    for key in parents:
        obj = obj[int(key)] if isinstance(obj, list) else obj[key]
    if leaf not in obj:
        raise KeyError(dotted)
    obj[leaf] = value


def render_json(path, dotted_paths, version):
    raw = path.read_text()
    data = json.loads(raw)
    canonical = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if canonical != raw:  # round-trip guard: never silently reformat
        sys.exit(f"{path}: not in canonical 2-space JSON form; refusing to rewrite")
    for dotted in dotted_paths:
        _set(data, dotted, version)
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def render_generic(path, expected_count, version):
    lines, hits = path.read_text().splitlines(keepends=True), 0
    for i, line in enumerate(lines):
        if ANNOTATION in line:
            if not SEMVER.search(line):
                sys.exit(f"{path}: annotated line {i + 1} has no semver to replace")
            lines[i] = SEMVER.sub(version, line)
            hits += 1
    if hits != expected_count:  # a deleted marker shrinks coverage loudly
        sys.exit(
            f"{path}: expected {expected_count} '{ANNOTATION}' line(s), found {hits}"
        )
    return "".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check", action="store_true", help="exit 1 on drift instead of writing"
    )
    args = parser.parse_args()
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    drift = []
    for rel, spec in list(JSON_SITES.items()) + list(GENERIC_SITES.items()):
        path = ROOT / rel
        desired = (
            render_json(path, spec, version)
            if rel in JSON_SITES
            else render_generic(path, spec, version)
        )
        if desired != path.read_text():
            drift.append(rel)
            if not args.check:
                path.write_text(desired)
                print(f"synced {rel}")
    if args.check and drift:
        sys.exit(
            "version drift vs pyproject.toml (run `just bump` or "
            "`uv run python scripts/sync_versions.py`): " + ", ".join(drift)
        )


if __name__ == "__main__":
    main()
```

Then: `chmod +x scripts/sync_versions.py`

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_sync_versions.py -q && uv run ruff format --check scripts/sync_versions.py tests/test_sync_versions.py && uv run ruff check scripts/sync_versions.py tests/test_sync_versions.py && uv run ty check scripts/sync_versions.py tests/test_sync_versions.py`

Expected: `10 passed`; both files "already formatted"; ruff and ty "All checks passed!" (all four validated against these exact file contents).

- [ ] **Step 5: Commit**

```bash
git add scripts/sync_versions.py tests/test_sync_versions.py
git commit -m "feat(release): add sync_versions.py single-source version propagation"
```

---

### Task 5: Run the script for real — repair the stale sites

**Files:**
- Modify (via the script, not by hand): `.claude-plugin/plugin.json:3`, `.codex-plugin/plugin.json:3`, `.claude-plugin/marketplace.json:9` and `:16`, `README.md:190`

**Interfaces:**
- Consumes: Task 4's `scripts/sync_versions.py` (write mode) and Tasks 2–3's site preparation.
- Produces: every declared site equal to `pyproject.toml`'s version — the precondition for Task 6's `version-check` passing.

This is a real repo mutation. The spec counted "7 stale sites"; Tasks 1 (code fix) and 2 (reword) already removed two of them, so this run repairs the remaining **5 sites across 4 files**.

- [ ] **Step 1: Re-read current values before running**

`main` may have moved since this plan was written — do not assume the `1.1.0`/`1.0.0` values cited below. Run:

```bash
grep -n '^version' pyproject.toml
grep -n '"version"' .claude-plugin/plugin.json .codex-plugin/plugin.json .claude-plugin/marketplace.json
grep -n 'x-release-please-version' tests/cli/test_cli.py scripts/check_clean_install.sh README.md
```

Expected (at plan-writing time): `pyproject.toml` says `1.1.0`; the four JSON fields say `1.0.0`; the three annotated lines say `1.1.0`, `1.1.0`, `1.0.0` respectively. If `pyproject.toml` shows a different version, every "1.1.0" in the steps below means *that* version instead.

- [ ] **Step 2: Run the repair**

Run: `uv run python scripts/sync_versions.py`

Expected stdout, exactly these four lines in this order (table order; the two already-correct tripwires print nothing):

```
synced .claude-plugin/plugin.json
synced .codex-plugin/plugin.json
synced .claude-plugin/marketplace.json
synced README.md
```

- [ ] **Step 3: Verify the diff and convergence**

Run: `git diff --stat && git diff && uv run python scripts/sync_versions.py --check; echo "check exit: $?"`

Expected: 4 files changed; the only hunks are version-string lines — `"version": "1.0.0"` → `"1.1.0"` in both `plugin.json` files, `metadata.version` and `plugins[0].version` in `marketplace.json`, and README line 190's `agent-fork 1.0.0` → `agent-fork 1.1.0` (the `<!-- x-release-please-version -->` comment untouched). No whitespace or key-order churn anywhere (the JSON files were verified canonical). `--check` prints nothing and `check exit: 0`. A second write-mode run would print nothing (idempotent).

- [ ] **Step 4: Confirm the tripwires still hold**

Run: `uv run pytest tests/cli/test_cli.py -q && bash scripts/check_clean_install.sh && echo CLEAN-INSTALL-OK`

Expected: CLI tests PASS; the clean-install smoke test builds a wheel, installs it into a throwaway venv, and its `test "$version_output" = "agent-fork 1.1.0"` line passes; `CLEAN-INSTALL-OK` prints.

- [ ] **Step 5: Commit**

```bash
git add .claude-plugin/plugin.json .codex-plugin/plugin.json .claude-plugin/marketplace.json README.md
git commit -m "fix(release): sync stale version sites to pyproject.toml via sync_versions"
```

---

### Task 6: `justfile` — `bump` and `version-check` recipes, wired into `all`

**Files:**
- Modify: `justfile:51-56` (insert two recipes after the `clean-install` recipe; rewrite the `all` line)

**Interfaces:**
- Consumes: Task 4's script (`--check` and write modes), Task 5's converged state.
- Produces: `just bump <part>`, `just version-check`, and `all: fmt lint typecheck version-check test` — CI inherits `version-check` because the `matrix-and-tests` job already runs `just all` (verified in `.github/workflows/ci.yml:33`).

- [ ] **Step 1: Edit the justfile**

The file currently ends (lines 51–56):

```make
# Build a wheel, install it into a disposable venv, and smoke-test the entry point
clean-install:
    bash scripts/check_clean_install.sh

# Format, lint, typecheck, and hermetic tests
all: fmt lint typecheck test
```

Replace those lines with:

```make
# Build a wheel, install it into a disposable venv, and smoke-test the entry point
clean-install:
    bash scripts/check_clean_install.sh

# Bump the version everywhere: part = major | minor | patch | an explicit X.Y.Z
bump part:
    #!/usr/bin/env bash
    set -euo pipefail
    case "{{part}}" in
      major|minor|patch) uv version --bump "{{part}}" ;;
      *)                 uv version "{{part}}" ;;
    esac
    uv run python scripts/sync_versions.py
    git diff --stat

# Verify every version site matches pyproject.toml
version-check:
    uv run python scripts/sync_versions.py --check

# Format, lint, typecheck, version sync, and hermetic tests
all: fmt lint typecheck version-check test
```

(`uv version` re-locks `uv.lock` itself by default, so no separate `uv lock` step; the recipe comments are the interim "bumping the version" documentation until `RELEASING.md`/P01-T20 exists — spec §3.5.8 item 6.)

- [ ] **Step 2: Verify `version-check` passes, then fails loudly on injected drift**

Run:

```bash
just version-check && echo VERSION-CHECK-OK
sed -i '' 's/"version": "1.1.0"/"version": "9.9.9"/' .codex-plugin/plugin.json
just version-check; echo "drift exit: $?"
git checkout -- .codex-plugin/plugin.json
just version-check && echo RESTORED-OK
```

Expected: first line prints `VERSION-CHECK-OK`. After the deliberate break, `just version-check` exits non-zero printing `version drift vs pyproject.toml (run `just bump` or `uv run python scripts/sync_versions.py`): .codex-plugin/plugin.json` and `drift exit: 1`. After restore, `RESTORED-OK`. (Use the version Step 1 of Task 5 found, if not `1.1.0`.)

- [ ] **Step 3: Commit**

```bash
git add justfile
git commit -m "feat(release): wire bump and version-check recipes into just all"
```

- [ ] **Step 4: Post-commit end-to-end `bump` proof (non-destructive, same-version)**

Run: `just bump 1.1.0` (substitute the current `pyproject.toml` version — bumping to the version already set is a proven byte-identical no-op for both `pyproject.toml` and `uv.lock`; validated empirically on this exact repo state).

Expected: uv prints `agent-fork 1.1.0 => 1.1.0`; the sync script prints no `synced` lines; `git diff --stat` shows no version-site files (and `git status --porcelain` shows nothing new). This exercises the full recipe — `uv version` → `sync_versions.py` → diff report — without changing anything.

---

### Task 7: Final integration check

**Files:**
- None (verification only).

**Interfaces:**
- Consumes: everything above.
- Produces: green local equivalents of both CI jobs.

- [ ] **Step 1: Run the CI-equivalent gate chain**

Run: `just check-matrix && just strict-collect && just all`

Expected: all green — `check-matrix` still passes (the two new test files are top-level, outside its tier scope; no matrix rows were added), `strict-collect` finds no marker or collection drift, and `all` now runs `fmt lint typecheck version-check test` in that order, with `version-check` silent and the hermetic test suite passing (including `tests/test_sync_versions.py` and the new handshake test).

- [ ] **Step 2: Run the conformance-job equivalent**

Run: `just clean-install && echo CONFORMANCE-OK`

Expected: wheel build + disposable-venv install succeed and the machine-written `agent-fork 1.1.0` tripwire passes end to end; `CONFORMANCE-OK` prints.

- [ ] **Step 3: Confirm the branch is clean and complete**

Run: `git status --porcelain && git log --oneline origin/main..HEAD`

Expected: no uncommitted changes of yours (pre-existing dirt in the checkout, if any, is reported, never staged); six commits — Tasks 1 through 6. Open the PR per repo convention (merge-commit strategy).

---

## Self-review: spec §3.5.8 checklist coverage

| §3.5.8 deliverable | Task |
|---|---|
| 1. `codex_app_server.py` → `importlib.metadata.version("agent-fork")` | Task 1 |
| 2. `README.md:147` reworded to drop the version literal | Task 2 |
| 3. `x-release-please-version` annotations on `tests/cli/test_cli.py:43`, `scripts/check_clean_install.sh:12`, `README.md:190` | Task 3 |
| 4. New `scripts/sync_versions.py` per §3.5.3; run once to repair the stale sites | Tasks 4 (build) + 5 (run) |
| 5. `justfile` `bump` + `version-check`, `version-check` in `all`, CI inherits via `just all` | Task 6 |
| 6. "Bumping the version" note | Carried by the `bump`/`version-check` recipe comments in Task 6 — the spec itself designates the justfile comments as the interim home until `RELEASING.md`/P01-T20 exists. No separate doc file is created. |
| 7. P01-T20 inherits §3.5.6's `release-please-config.json` block verbatim | Migration-time deliverable — no repo change now. The script's `JSON_SITES`/`GENERIC_SITES` tables and docstring are its transcription source. |

**Validation status of the code blocks in this plan** (all run against the live worktree before writing): the Task 1 test fails against current code with exactly the quoted assertion and passes with the Task 1 fix; Task 4's script + 10 tests pass pytest, `ruff format --check`, `ruff check`, and `ty check` byte-for-byte as printed; all three JSON manifests round-trip the canonical-form guard today; `uv version <same-version>` is byte-identical for `pyproject.toml` and `uv.lock`; the Task 4 Step 2 ImportError message is verbatim from a real run.
