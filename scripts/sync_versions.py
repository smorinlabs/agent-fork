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
    try:
        for key in parents:
            obj = obj[int(key)] if isinstance(obj, list) else obj[key]
        if leaf not in obj:
            raise KeyError(dotted)
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise KeyError(dotted) from error
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
