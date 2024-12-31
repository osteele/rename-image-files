# Development commands for rename-image-files

# Default recipe to display available commands
default:
    @just --list

# Setup development environment
setup:
    uv pip install -e ".[dev]"

# Run all checks (linting, formatting, type checking)
check:
    hatch run format
    hatch run lint
    hatch run test

# Format code
format:
    hatch run format

# Fix linting and formatting issues, even in a dirty git workspace
fix:
    ruff check --fix-only .
    ruff format .

# Run tests
test:
    hatch run test

# Run tests with coverage
test-cov:
    hatch run test-cov

# Clean up temporary files
clean:
    rm -rf dist build *.egg-info .coverage .pytest_cache .mypy_cache .ruff_cache
    find . -type d -name __pycache__ -exec rm -rf {} +
