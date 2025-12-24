# snippy

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

Python CLI tool for extracting PostgreSQL records with all related data via foreign key relationships.

## Overview

`snippy` extracts a specific database record and **ALL** its related records by following foreign key relationships bidirectionally. Perfect for:

- Reproducing production bugs locally with real data
- Creating partial database dumps for specific users/entities
- Testing with realistic data subsets
- Debugging issues that only occur with specific data states

Extract only what you need while maintaining referential integrity.

## Features

- ✅ **Bidirectional FK traversal**: Follows relationships in both directions (forward and reverse)
- ✅ **Circular relationship handling**: Prevents infinite loops with visited tracking
- ✅ **Multiple records**: Extract multiple records in one operation
- ✅ **Timeframe filtering**: Filter specific tables by date ranges
- ✅ **PK remapping**: Auto-remaps auto-generated primary keys for clean imports
- ✅ **Interactive REPL**: User-friendly command-line interface
- ✅ **Schema caching**: SQLite-based caching for improved performance
- ✅ **Type-safe**: Full type hints with mypy strict mode
- ✅ **Secure**: SQL injection prevention, secure password handling

## Development Setup

> **Note:** This guide is for developers contributing to snippy. End-user installation instructions will be added when published to PyPI and Docker Hub.

### Prerequisites

- Python 3.10+ (development uses 3.13/3.14)
- PostgreSQL database for testing
- Git

### Local Development Setup

```bash
# One-time setup (installs uv, Python 3.14, dependencies, pre-commit hooks)
make setup
```

#### Option A: Using .env file (Recommended)

```bash
# Configure database connection
cp .env.example .env
# Edit .env with your database credentials

# Run snippy (Makefile loads .env automatically)
make run-repl

# Or override specific variables
make run-repl DB_NAME=other_database
```

#### Option B: Pass credentials directly to CLI

```bash
# Set password as environment variable (not stored)
export PGPASSWORD=your_password

# Run snippy with all parameters
uv run snippy --host localhost --port 5432 --user postgres --database test_db
```

### Docker Development Setup

For isolated testing without affecting your local environment:

```bash
# Build development image
make docker-build
```

#### Option A: Using .env file (Recommended)

```bash
# Configure .env file first
cp .env.example .env
# Edit .env, set DB_HOST=host.docker.internal for Mac/Windows

# Run snippy (Makefile loads .env automatically)
# Generated files appear in ./dumps/
make docker-run

# Open shell in container for debugging
make docker-shell
```

#### Option B: Pass credentials directly

```bash
# Run with manual parameters
docker run --rm -it \
  --user $(id -u):$(id -g) \
  -v $(pwd)/dumps:/home/snippy/.snippy/dumps \
  -e PGPASSWORD=your_password \
  snippy:latest \
  snippy --host host.docker.internal --port 5432 --user postgres --database test_db
```

## Usage Examples

Quick examples for testing during development:

```bash
# In REPL:
# This will dump all related records to the film with id 1
# The generated SQL file will be placed, by default, in ~/.snippy/dumps
snippy> dump "film" 1

# You can overwrite the output path with:
snippy> dump "film" 1 --output film_1.sql

# Extract multiple records
snippy> dump "actor" 1,2,3 --output multiple_actors.sql

# Use wide mode to follow all relationships (including self-referencing FKs)
# Be cautions that this can result in larger datasets. So use with caution
snippy> dump "customer" 42 --wide --output customer_42.sql

# Apply timeframe filter
snippy> dump "customer" 42 --timeframe "rental:rental_date:2024-01-01:2024-12-31"

# List all tables
snippy> tables

# Show table structure and relationships
snippy> describe "film"

# Keep original primary key values (no remapping)
# By default, we will dinamically assign ids to the new generated records
# and handle conflicts gracefully. Meaninh, you can run the same file multiple times
# and no conflicts will arise.
# If you want to keep the original id's run:
snippy> dump "film" 1 --keep-pks --output film_1.sql
```

## Configuration

Key environment variables (see `.env.example` for full reference):

| Variable | Description | Default |
|----------|-------------|---------|
| `DB_HOST` | Database host | `localhost` |
| `DB_PORT` | Database port | `5432` |
| `DB_NAME` | Database name | - |
| `DB_USER` | Database user | - |
| `DB_SCHEMA` | Schema to use | `public` |
| `PGPASSWORD` | Database password (env var only) | - |
| `CACHE_ENABLED` | Enable schema caching | `true` |
| `CACHE_TTL_HOURS` | Cache time-to-live | `24` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `SNIPPY_OUTPUT_DIR` | Output directory | `~/.snippy/dumps` |

## Development Workflow

### Running Code Quality Checks

```bash
make all-checks      # Run all quality checks (lint, format, type-check)
make lint            # Check code style with ruff
make lint-fix        # Auto-fix safe linting issues
make lint-fix-all    # Auto-fix all linting issues (including unsafe)
make format          # Format code with ruff
make format-check    # Check formatting without changes
make type-check      # Run mypy type checking
make imports         # Sort and organize imports
```

### Building & Publishing

```bash
make build-dist      # Build distribution packages
make install-local   # Install locally for testing
make publish-test    # Publish to TestPyPI
make publish         # Publish to production PyPI (requires confirmation)
```

### Available Make Commands

Run `make help` to see all available commands.

### Detailed Development Guide

For comprehensive development documentation including:
- Code quality standards and mypy configuration
- Type checking and Python 3.10+ compatibility
- Module organization and architecture
- Common patterns and adding new features
- FK remapping implementation details

## Security

- ✅ **Parameterized queries**: All SQL uses proper parameterization
- ✅ **SQL injection prevention**: Identifier validation
- ✅ **Secure passwords**: Never logged or stored
- ✅ **Read-only enforcement**: Safe for production databases

## Troubleshooting

### Common Issues

1. **Permission denied on output files (Docker)**
   - Make sure you're using `--user $(id -u):$(id -g)` with docker run
   - The Makefile commands handle this automatically

2. **Cannot connect to database from Docker**
   - Mac/Windows: Use `host.docker.internal` as DB_HOST
   - Linux: Use `host.docker.internal` or `--network host`

3. **Schema cache issues**
   - Clear cache: `snippy --no-cache`
   - Or delete cache directory: `rm -rf ~/.cache/snippy`

4. **Import errors after installation**
   - Ensure virtual environment is activated: `source .venv/bin/activate`
   - Or use `uv run snippy` which handles venv automatically

## Contributing

Contributions welcome! Please ensure:
- Code passes all checks: `make all-checks`
- Type checking passes (mypy strict mode)
- Code is formatted with ruff
- Pre-commit hooks are installed: `uv run pre-commit install`

## License

MIT
