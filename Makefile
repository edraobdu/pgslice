.PHONY: help install dev-install test coverage lint format type-check clean docker-build docker-up docker-down docker-test all-checks test-fast coverage-minimal lint-fix format-check docker-shell docker-logs docker-clean run-repl run-dump generate-test-data watch-test

# Default target
.DEFAULT_GOAL := help

# Variables
PYTHON := python3
PYTEST := pytest
MYPY := mypy
RUFF := ruff
COVERAGE := coverage
DOCKER_COMPOSE := docker compose

# Project paths
SRC_DIR := src/snippy
TESTS_DIR := tests

help:  ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:  ## Install production dependencies
	$(PYTHON) -m pip install -e .

dev-install:  ## Install development dependencies
	$(PYTHON) -m pip install -e ".[dev]"
	@echo "Development environment ready!"

test:  ## Run all tests
	$(PYTEST) -v

test-fast:  ## Run tests in parallel
	$(PYTEST) -v -n auto

coverage:  ## Run tests with coverage report
	$(PYTEST) --cov=$(SRC_DIR) --cov-report=html --cov-report=term
	@echo "Coverage report generated in htmlcov/index.html"

coverage-minimal:  ## Show coverage summary only
	$(PYTEST) --cov=$(SRC_DIR) --cov-report=term-missing

lint:  ## Run ruff linter
	$(RUFF) check $(SRC_DIR) $(TESTS_DIR)

lint-fix:  ## Auto-fix linting issues
	$(RUFF) check --fix $(SRC_DIR) $(TESTS_DIR)

format:  ## Format code with ruff
	$(RUFF) format $(SRC_DIR) $(TESTS_DIR)

format-check:  ## Check code formatting
	$(RUFF) format --check $(SRC_DIR) $(TESTS_DIR)

type-check:  ## Run mypy type checker
	$(MYPY) $(SRC_DIR)

all-checks:  ## Run all quality checks (tests, lint, format, type-check)
	@echo "Running all checks..."
	@$(MAKE) test
	@$(MAKE) lint
	@$(MAKE) format-check
	@$(MAKE) type-check
	@echo "All checks passed!"

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

docker-build:  ## Build Docker images
	$(DOCKER_COMPOSE) build

docker-up:  ## Start Docker containers
	$(DOCKER_COMPOSE) up -d

docker-down:  ## Stop Docker containers
	$(DOCKER_COMPOSE) down

docker-test:  ## Run tests in Docker container
	$(DOCKER_COMPOSE) run --rm app $(PYTEST) -v

docker-shell:  ## Open shell in Docker container
	$(DOCKER_COMPOSE) run --rm app /bin/bash

docker-logs:  ## View Docker container logs
	$(DOCKER_COMPOSE) logs -f

docker-clean:  ## Remove Docker containers and volumes
	$(DOCKER_COMPOSE) down -v

run-repl:  ## Run interactive REPL (requires DATABASE_URL env var)
	snippy --repl

run-dump:  ## Example: dump user with id 1 (customize as needed)
	snippy --table users --pk-values 1 --output output/user_1.sql

generate-test-data:  ## Generate large test dataset
	$(PYTHON) tests/test_data/generate_large_dataset.py > tests/test_data/large_sample_data.sql
	@echo "Test data generated: tests/test_data/large_sample_data.sql"

watch-test:  ## Watch for changes and run tests (requires pytest-watch)
	ptw -- -v
