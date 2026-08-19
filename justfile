# agent-fork dev tasks — `make check` verifies environment deps first.

default:
    @just --list

# Format code
fmt:
    uv run ruff format

# Check formatting without modifying
fmt-check:
    uv run ruff format --check

# Lint
lint:
    uv run ruff check

# Lint with autofix
lint-fix:
    uv run ruff check --fix

# Typecheck
typecheck:
    uv run ty check

# Run hermetic tests; real-agent and unrestricted signal gates are explicit
test:
    uv run pytest -m "not requires_real_cli and not requires_process_group_signals"

# Run host-managed real-agent tests after identity, auth, state, and network preflights
test-live:
    uv run python scripts/check_live_tests.py
    uv run pytest -m requires_real_cli

# Run ITA compatibility coverage with system Git and Flox GNU Git
test-git-matrix:
    bash scripts/check_git_matrix.sh

# Run rollback signal tests in an unrestricted process environment
test-signals:
    uv run pytest -m requires_process_group_signals

# Validate TEST-MATRIX.md against the collected stub tree
check-matrix:
    uv run python scripts/check_matrix.py

# Fail on unknown markers, import errors, syntax errors, or other collection drift
strict-collect:
    uv run pytest --collect-only -q

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
