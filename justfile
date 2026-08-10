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

# Run tests
test:
    uv run pytest

# Validate TEST-MATRIX.md against the collected stub tree
check-matrix:
    uv run python scripts/check_matrix.py

# Fail on unknown markers, import errors, syntax errors, or other collection drift
strict-collect:
    uv run pytest --collect-only -q

# Build a wheel, install it into a disposable venv, and smoke-test the entry point
clean-install:
    bash scripts/check_clean_install.sh

# Format, lint, typecheck, test
all: fmt lint typecheck test
