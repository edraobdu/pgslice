MAKEFLAGS += --no-print-directory --silent

# Load .env file if it exists (makes variables available to make and subprocesses)
-include .env
export

.PHONY: help install dev-install test test-unit test-parallel test-cov test-ci test-fast test-integration coverage lint format type-check clean build-dist install-local publish-test publish docker-build docker-run docker-shell all-checks lint-fix lint-fix-all format-check uv-install sync lock test-compat setup imports run run-repl show-version bump-patch bump-minor bump-major

# Default target
.DEFAULT_GOAL := help

# Project paths
SRC_DIR := src/pgslice
DOCKER_IMAGE := pgslice:latest

help:  ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' Makefile | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

## Run pgslice REPL (loads .env automatically)
run:
	@if [ ! -f .env ]; then \
		echo "Error: .env file not found. Run 'cp .env.example .env' and configure it."; \
		exit 1; \
	fi
	uv run pgslice --host $(DB_HOST) --port $(DB_PORT) --user $(DB_USER) --database $(DB_NAME)

# Testing commands
test:  ## Run all tests with coverage
	uv run pytest

test-parallel:  ## Run tests in parallel (faster)
	uv run pytest -n auto

test-cov:  ## Run tests with HTML coverage report
	uv run pytest --cov-report=html --cov-report=term-missing
	@echo "Coverage report: htmlcov/index.html"


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

# Version management
show-version:  ## Show current version from pyproject.toml
	@uv version

bump-patch:  ## Bump patch version (0.1.1 -> 0.1.2)
	@uv version --bump patch

bump-minor:  ## Bump minor version (0.1.1 -> 0.2.0)
	@uv version --bump minor

bump-major:  ## Bump major version (0.1.1 -> 1.0.0)
	@uv version --bump major

# Python package building and publishing
build-dist: clean  ## Build Python distribution packages (wheel + sdist)
	@echo "Building distribution packages..."
	uv build
	@echo "Build complete! Packages in dist/"
	@ls -lh dist/

install-local: build-dist  ## Install package locally from built wheel
	@echo "Installing from local build..."
	uv pip install dist/*.whl --force-reinstall
	@echo "Installation complete! Test with: pgslice --version"

publish-test: build-dist  ## Publish to TestPyPI for testing
	@echo "Publishing to TestPyPI..."
	uv publish --publish-url https://test.pypi.org/legacy/
	@echo "Published to TestPyPI! Install with:"
	@echo "  pip install --index-url https://test.pypi.org/simple/ pgslice"

publish: all-checks build-dist  ## Publish to production PyPI (requires confirmation)
	@echo "WARNING: This will publish to production PyPI!"
	@read -p "Version $$(grep '^version = ' pyproject.toml | cut -d'"' -f2) - Continue? [y/N] " confirm && \
	[ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ] || (echo "Aborted." && exit 1)
	@echo "Publishing to PyPI..."
	uv publish
	@echo "Published! Install with: pip install pgslice"

# Docker commands
docker-build:  ## Build Docker image
	docker build -t $(DOCKER_IMAGE) .

docker-run:  ## Run pgslice in Docker (loads .env automatically)
	@if [ ! -f .env ]; then \
		echo "Error: .env file not found. Run 'cp .env.example .env' and configure it."; \
		exit 1; \
	fi
	docker run --rm -it \
		--user $$(id -u):$$(id -g) \
		-v $(PWD)/dumps:/home/pgslice/.pgslice/dumps \
		--env-file .env \
		$(DOCKER_IMAGE) \
		pgslice

docker-shell:  ## Open shell in Docker container (with .env loaded)
	@if [ ! -f .env ]; then \
		echo "Warning: .env file not found. Some features may not work."; \
	fi
	docker run --rm -it \
		--user $$(id -u):$$(id -g) \
		-v $(PWD)/dumps:/home/pgslice/.pgslice/dumps \
		--env-file .env \
		$(DOCKER_IMAGE) \
		bash

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
	@echo "Copying env file..."
	cp .env.template .env
	@echo "Setting up local development environment..."
	@command -v uv >/dev/null 2>&1 || (echo "Installing uv..." && curl -LsSf https://astral.sh/uv/install.sh | sh)
	@echo "Installing Python 3.14..."
	uv python install 3.14
	@echo "Syncing dependencies..."
	uv sync --all-extras
	@echo "Installing pre-commit hooks..."
	uv run pre-commit install
	@echo "✓ Setup complete! Virtual environment ready at .venv/"
