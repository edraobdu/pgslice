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

![PgSlice Example](.github/pgslice-example.gif)

![PgSlice Example Wide](.github/pgslice-example-wide.gif)

## Overview

`pgslice` extracts a specific database record and **ALL** its related records by following foreign key relationships bidirectionally. Perfect for:

- Reproducing production bugs locally with real data
- Creating partial database dumps for specific users/entities
- Testing with realistic data subsets
- Debugging issues that only occur with specific data states

Extract only what you need while maintaining referential integrity.

## Features

- ✅ **CLI-first design**: Dumps always saved to files with visible progress (matches REPL behavior)
- ✅ **Bidirectional FK traversal**: Follows relationships in both directions (forward and reverse)
- ✅ **Circular relationship handling**: Prevents infinite loops with visited tracking
- ✅ **Multiple records**: Extract multiple records in one operation
- ✅ **Timeframe filtering**: Filter specific tables by date ranges
- ✅ **PK remapping**: Auto-remaps auto-generated primary keys for clean imports
- ✅ **DDL generation**: Optionally include CREATE DATABASE/SCHEMA/TABLE statements for self-contained dumps
- ✅ **Progress bar**: Visual progress indicator for dump operations
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

# check instalation
pgslice --version
# or
uv run pgslice --version
```

### From Docker Hub

```bash
# Pull the image
docker pull edraobdu/pgslice:latest

# Check instalation
docker run --rm -it \
  -v $(pwd)/dumps:/home/pgslice/.pgslice/dumps \
  -e PGPASSWORD=your_password \
  edraobdu/pgslice:latest \
  pgslice --version

# Pin to specific version
docker pull edraobdu/pgslice:0.1.1

# Use specific platform
docker pull --platform linux/amd64 edraobdu/pgslice:latest
```

#### Connecting to Localhost Database

When your PostgreSQL database runs on your host machine, use `--network host` (Linux) or `host.docker.internal` (Mac/Windows):

```bash
# Linux: Use host networking
docker run --rm -it \
  --network host \
  -v $(pwd)/dumps:/home/pgslice/.pgslice/dumps \
  -e PGPASSWORD=your_password \
  edraobdu/pgslice:latest \
  pgslice --host localhost --database your_db --dump users --pks 42

# Mac/Windows: Use special hostname
docker run --rm -it \
  -v $(pwd)/dumps:/home/pgslice/.pgslice/dumps \
  -e PGPASSWORD=your_password \
  edraobdu/pgslice:latest \
  pgslice --host host.docker.internal --database your_db --dump users --pks 42
```

See [DOCKER_USAGE.md](DOCKER_USAGE.md#connecting-to-localhost-database) for more connection options.

#### Docker Volume Permissions

The pgslice container runs as user `pgslice` (UID 1000) for security. When mounting local directories as volumes, you may encounter permission issues.

**The entrypoint script automatically fixes permissions** on mounted volumes. However, if you still encounter issues:

```bash
# Fix permissions on host before mounting
sudo chown -R 1000:1000 ./dumps

# Then run normally
docker run --rm -it \
  -v $(pwd)/dumps:/home/pgslice/.pgslice/dumps \
  edraobdu/pgslice:latest \
  pgslice --host your.db.host --database your_db --dump users --pks 42
```

**Alternative:** Run container as your user:
```bash
docker run --rm -it \
  -v $(pwd)/dumps:/home/pgslice/.pgslice/dumps \
  --user $(id -u):$(id -g) \
  edraobdu/pgslice:latest \
  pgslice --host your.db.host --database your_db --dump users --pks 42
```

### From Source (Development)

See [DEVELOPMENT.md](DEVELOPMENT.md) for detailed development setup instructions.

## Quick Start

### CLI Mode

Dumps are always saved to files with visible progress indicators (helpful for large datasets):

```bash
# Basic dump (auto-generates filename like: public_users_42_TIMESTAMP.sql)
PGPASSWORD=xxx pgslice --host localhost --database mydb --dump users --pks 42

# Multiple records
PGPASSWORD=xxx pgslice --host localhost --database mydb --dump users --pks 1,2,3

# Specify output file path
pgslice --host localhost --database mydb --dump users --pks 42 --output user_42.sql

# Dump by timeframe (instead of PKs) - filters main table by date range
pgslice --host localhost --database mydb --dump orders \
    --timeframe "created_at:2024-01-01:2024-12-31" --output orders_2024.sql

# Wide mode: follow all relationships including self-referencing FKs
# Be cautious - this can result in larger datasets
pgslice --host localhost --database mydb --dump customer --pks 42 --wide

# Keep original primary keys (no remapping)
pgslice --host localhost --database mydb --dump film --pks 1 --keep-pks

# Generate self-contained SQL with DDL statements
# Includes CREATE DATABASE/SCHEMA/TABLE statements
pgslice --host localhost --database mydb --dump film --pks 1 --create-schema

# Apply truncate filter to limit related tables by date range
pgslice --host localhost --database mydb --dump customer --pks 42 \
    --truncate "rental:rental_date:2024-01-01:2024-12-31"

# Enable debug logging (writes to stderr)
pgslice --host localhost --database mydb --dump users --pks 42 \
    --log-level DEBUG 2>debug.log
```

### Schema Exploration

```bash
# List all tables in the schema
pgslice --host localhost --database mydb --tables

# Describe table structure and relationships
pgslice --host localhost --database mydb --describe users
```

### Interactive REPL

```bash
# Start interactive REPL
PGPASSWORD=mypassword pgslice --host localhost --database mydb --user myuser --port 5432

pgslice> dump film 1 --output film_1.sql
pgslice> tables
pgslice> describe film
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
| `LOG_LEVEL` | Logging level (disabled by default unless specified) | disabled |
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
