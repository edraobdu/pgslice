.PHONY: help install dev-install test coverage lint format type-check clean docker-build docker-up docker-down docker-test all-checks test-fast coverage-minimal lint-fix format-check docker-shell docker-logs docker-clean run-repl run-dump generate-test-data watch-test

# Default target
.DEFAULT_GOAL := help

# Variables
DOCKER_COMPOSE := docker compose
DOCKER_RUN := $(DOCKER_COMPOSE) run --rm app

# Project paths
SRC_DIR := src/snippy
TESTS_DIR := src/tests

help:  ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

shell:  ## Open shell in Docker container
	$(DOCKER_RUN) /bin/bash

test:
	$(DOCKER_RUN) pytest -v

coverage:  ## Run tests with coverage report
	$(DOCKER_RUN) pytest --cov=$(SRC_DIR) --cov-report=html --cov-report=term-missing
	@echo "Coverage report generated in htmlcov/index.html"

lint:  ## Run ruff linter
	$(DOCKER_RUN) ruff check $(SRC_DIR) $(TESTS_DIR)

lint-fix:  ## Auto-fix linting issues
	$(DOCKER_RUN) ruff check --fix $(SRC_DIR) $(TESTS_DIR)

format:  ## Format code with ruff
	$(DOCKER_RUN) ruff format $(SRC_DIR) $(TESTS_DIR)

format-check:  ## Check code formatting
	$(DOCKER_RUN) ruff format --check $(SRC_DIR) $(TESTS_DIR)

type-check:  ## Run mypy type checker
	$(DOCKER_RUN) mypy $(SRC_DIR)

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

build:  ## Build Docker images
	$(DOCKER_COMPOSE) build

up:  ## Start Docker containers
	$(DOCKER_COMPOSE) up -d

down:  ## Stop Docker containers
	$(DOCKER_COMPOSE) down


run-repl:  ## Run interactive REPL (requires DATABASE_URL env var)
	snippy --repl

generate-test-data:  ## Generate large test dataset
	$(DOCKER_RUN) python $(TESTS_DIR)/test_data/generate_large_dataset.py > $(TESTS_DIR)/test_data/large_sample_data.sql
	@echo "Test data generated: $(TESTS_DIR)/test_data/large_sample_data.sql"

watch-test:  ## Watch for changes and run tests (requires pytest-watch)
	$(DOCKER_RUN) ptw -- -v
