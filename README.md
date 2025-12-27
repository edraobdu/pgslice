# PgSlice

<p align="center">
  <img src="assets/logo.png" alt="PgSlice Logo" width="200">
</p>

<p align="center">
  <em>Bump only what you need</em>
</p>

![PyPI](https://img.shields.io/pypi/v/pgslice?style=flat-square)
![Docker Image Version](https://img.shields.io/docker/v/edraobdu/pgslice?sort=semver&style=flat-square&logo=docker)
![Codecov](https://img.shields.io/codecov/c/gh/edraobdu/pgslice?logo=codecov&style=flat-square)
![PyPI - Wheel](https://img.shields.io/pypi/wheel/pgslice?style=flat-square)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/pgslice?logo=python&logoColor=blue&style=flat-square)
![PyPI - License](https://img.shields.io/pypi/l/pgslice?style=flat-square)



Python CLI tool for extracting PostgreSQL records with all related data via foreign key relationships.

## Overview

`pgslice` extracts a specific database record and **ALL** its related records by following foreign key relationships bidirectionally. Perfect for:

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
- ✅ **DDL generation**: Optionally include CREATE DATABASE/SCHEMA/TABLE statements for self-contained dumps
- ✅ **Interactive REPL**: User-friendly command-line interface
- ✅ **Schema caching**: SQLite-based caching for improved performance
- ✅ **Type-safe**: Full type hints with mypy strict mode
- ✅ **Secure**: SQL injection prevention, secure password handling

## Installation

### From PyPI (Recommended)

```bash
# Install with pipx (isolated environment, recommended)
pipx install pgslice

# Or with pip
pip install pgslice

# Or with uv
uv tool install pgslice
```

### From Docker Hub

```bash
# Pull the image
docker pull edraobdu/pgslice:latest

# Run pgslice
docker run --rm -it \
  -v $(pwd)/dumps:/home/pgslice/.pgslice/dumps \
  -e PGPASSWORD=your_password \
  edraobdu/pgslice:latest \
  pgslice --host your.db.host --port 5432 --user your_user --database your_db

# Pin to specific version
docker pull edraobdu/pgslice:0.1.1

# Use specific platform
docker pull --platform linux/amd64 edraobdu/pgslice:latest
```

### From Source (Development)

See [DEVELOPMENT.md](DEVELOPMENT.md) for detailed development setup instructions.

## Quick Start

```bash
# In REPL:
# This will dump all related records to the film with id 1
# The generated SQL file will be placed, by default, in ~/.pgslice/dumps
# The name will be a formated string with table name, id, and timestamp
pgslice> dump "film" 1

# You can overwrite the output path with:
pgslice> dump "film" 1 --output film_1.sql

# Extract multiple records
pgslice> dump "actor" 1,2,3 --output multiple_actors.sql

# Use wide mode to follow all relationships (including self-referencing FKs)
# Be cautions that this can result in larger datasets. So use with caution
pgslice> dump "customer" 42 --wide --output customer_42.sql

# Apply timeframe filter
pgslice> dump "customer" 42 --timeframe "rental:rental_date:2024-01-01:2024-12-31"

# List all tables
pgslice> tables

# Show table structure and relationships
pgslice> describe "film"

# Keep original primary key values (no remapping)
# By default, we will dinamically assign ids to the new generated records
# and handle conflicts gracefully. Meaninh, you can run the same file multiple times
# and no conflicts will arise.
# If you want to keep the original id's run:
pgslice> dump "film" 1 --keep-pks --output film_1.sql

# Generate self-contained SQL with DDL statements (NEW in v0.2.0)
# This creates a fully self-contained SQL file with:
# - CREATE DATABASE IF NOT EXISTS
# - CREATE SCHEMA IF NOT EXISTS
# - CREATE TABLE IF NOT EXISTS for all tables
# - All INSERT statements with data
pgslice> dump "film" 1 --create-schema --output film_1_complete.sql
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
| `PGSLICE_OUTPUT_DIR` | Output directory | `~/.pgslice/dumps` |

## Security

- ✅ **Parameterized queries**: All SQL uses proper parameterization
- ✅ **SQL injection prevention**: Identifier validation
- ✅ **Secure passwords**: Never logged or stored
- ✅ **Read-only enforcement**: Safe for production databases

## Contributing

Contributions are welcome! See [DEVELOPMENT.md](DEVELOPMENT.md) for comprehensive development documentation including:
- Local development setup
- Code quality standards and testing guidelines
- Version management and publishing workflow
- Architecture and design patterns

**Quick start for contributors:**
```bash
make setup        # One-time setup (installs dependencies, hooks)
make test         # Run all tests
git commit        # Pre-commit hooks run automatically (linting, formatting, type-checking)
```

For troubleshooting common development issues, see the [Troubleshooting section in DEVELOPMENT.md](DEVELOPMENT.md#troubleshooting).

## License

MIT
