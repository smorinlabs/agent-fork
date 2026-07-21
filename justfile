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

# Format, lint, typecheck, test
all: fmt lint typecheck test
