MAKEFLAGS += --no-print-directory --silent

.PHONY: help install dev-install test coverage lint format type-check clean build-dist install-local publish-test publish docker-build docker-up docker-down docker-test all-checks test-fast coverage-minimal lint-fix lint-fix-all format-check docker-shell docker-logs docker-clean run-repl run-dump generate-test-data watch-test uv-install sync lock test-compat setup imports

# Default target
.DEFAULT_GOAL := help

# Variables
DOCKER_COMPOSE := docker compose
DOCKER_RUN := $(DOCKER_COMPOSE) run --rm app

# Project paths
SRC_DIR := src/snippy

help:  ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

shell:  ## Open shell in Docker container
	$(DOCKER_RUN) /bin/bash

lint:  ## Run ruff linter
	uv run ruff check $(SRC_DIR)

lint-fix:  ## Auto-fix linting issues (safe fixes only)
	uv run ruff check --fix $(SRC_DIR)

lint-fix-all:  ## Auto-fix all linting issues including unsafe fixes
	uv run ruff check --fix --unsafe-fixes $(SRC_DIR)

imports:  ## Sort and organize imports with ruff
	@uv run ruff check --select I --fix $(SRC_DIR)

format:  ## Format code with ruff
	uv run ruff format $(SRC_DIR)

format-check:  ## Check code formatting
	uv run ruff format --check $(SRC_DIR)

type-check:  ## Run mypy type checker
	uv run mypy $(SRC_DIR)

all-checks:  ## Run all quality checks (tests, lint, format, type-check)
	echo "Running all checks..."
	$(MAKE) lint
	$(MAKE) format-check
	$(MAKE) type-check
	$(MAKE) imports
	echo "All checks passed!"

clean:  ## Remove build artifacts and cache
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

# Python package building and publishing
build-dist: clean  ## Build Python distribution packages (wheel + sdist)
	@echo "Building distribution packages..."
	uv build
	@echo "Build complete! Packages in dist/"
	@ls -lh dist/

install-local: build-dist  ## Install package locally from built wheel
	@echo "Installing from local build..."
	uv pip install dist/*.whl --force-reinstall
	@echo "Installation complete! Test with: snippy --version"

publish-test: build-dist  ## Publish to TestPyPI for testing
	@echo "Publishing to TestPyPI..."
	uv publish --publish-url https://test.pypi.org/legacy/
	@echo "Published to TestPyPI! Install with:"
	@echo "  pip install --index-url https://test.pypi.org/simple/ snippy"

publish: all-checks build-dist  ## Publish to production PyPI (requires confirmation)
	@echo "WARNING: This will publish to production PyPI!"
	@read -p "Version $$(grep '^version = ' pyproject.toml | cut -d'"' -f2) - Continue? [y/N] " confirm && \
	[ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ] || (echo "Aborted." && exit 1)
	@echo "Publishing to PyPI..."
	uv publish
	@echo "Published! Install with: pip install snippy"

build:  ## Build Docker images
	$(DOCKER_COMPOSE) build

up:  ## Start Docker containers
	$(DOCKER_COMPOSE) up -d

down:  ## Stop Docker containers
	$(DOCKER_COMPOSE) down


run-repl:  ## Run interactive REPL (requires DATABASE_URL env var)
	snippy --repl

# Local development with uv
uv-install:  ## Install uv (one-time setup)
	curl -LsSf https://astral.sh/uv/install.sh | sh

sync:  ## Sync dependencies with uv (local development)
	uv sync --all-extras

lock:  ## Update uv.lock file
	uv lock

test-compat:  ## Test compatibility across Python versions
	@echo "Testing Python 3.10..."
	@uv run --python 3.10 python --version || echo "Python 3.10 not available"
	@echo "Testing Python 3.13..."
	@uv run --python 3.13 python --version || echo "Python 3.13 not available"
	@echo "Testing Python 3.14..."
	@uv run --python 3.14 python --version || echo "Python 3.14 not available"

setup:  ## One-time local development setup
	@echo "Setting up local development environment..."
	@command -v uv >/dev/null 2>&1 || (echo "Installing uv..." && curl -LsSf https://astral.sh/uv/install.sh | sh)
	@echo "Installing Python 3.14..."
	uv python install 3.14
	@echo "Syncing dependencies..."
	uv sync --all-extras
	@echo "Installing pre-commit hooks..."
	uv run pre-commit install
	@echo "✓ Setup complete! Virtual environment ready at .venv/"
