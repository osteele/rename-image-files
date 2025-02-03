# Development commands for rename-image-files

# Default recipe to display available commands
default:
    @just --list

# Setup development environment
install:
    uv sync

# Run all checks (linting, formatting, type checking)
# Run all validation steps in order:
# 1. Fix formatting and lint issues (format)
# 2. Check for remaining lint errors and type issues (lint)
# 3. Run tests to verify nothing was broken (test)
check: fix lint test

# Fix issues without failing on remaining ones (useful during development)
format:
    uv run --dev ruff format .              # Format code first
    uv run --dev ruff check --fix-only .    # Fix remaining auto-fixable lint issues

# Like format, but also shows unfixable issues that need manual attention
fix:
    uv run --dev ruff format .              # Format code first
    uv run --dev ruff check --fix .         # Then apply fixes without failing on remaining issues

# Verify code quality without modifying files
lint:
    uv run --dev ruff format --check .      # Verify formatting without making changes
    uv run --dev ruff check .               # Check for lint issues
    uv run --dev pyright .                  # Run static type checking

# Run tests
test:
    uv run --dev pytest

# Clean up temporary files
clean:
    rm -rf dist build *.egg-info .coverage .pytest_cache .mypy_cache .ruff_cache
    find . -type d -name __pycache__ -exec rm -rf {} +
