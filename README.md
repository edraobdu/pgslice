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

- ✅ **CLI-first design**: Stream SQL to stdout for easy piping and scripting
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

### CLI Mode

The CLI mode streams SQL to stdout by default, making it easy to pipe or redirect output:

```bash
# Basic dump to stdout (pipe to file)
PGPASSWORD=xxx pgslice --host localhost --database mydb --table users --pks 42 > user_42.sql

# Multiple records
PGPASSWORD=xxx pgslice --host localhost --database mydb --table users --pks 1,2,3 > users.sql

# Output directly to file with --output flag
pgslice --host localhost --database mydb --table users --pks 42 --output user_42.sql

# Dump by timeframe (instead of PKs) - filters main table by date range
pgslice --host localhost --database mydb --table orders \
    --timeframe "created_at:2024-01-01:2024-12-31" > orders_2024.sql

# Wide mode: follow all relationships including self-referencing FKs
# Be cautious - this can result in larger datasets
pgslice --host localhost --database mydb --table customer --pks 42 --wide > customer.sql

# Keep original primary keys (no remapping)
pgslice --host localhost --database mydb --table film --pks 1 --keep-pks > film.sql

# Generate self-contained SQL with DDL statements
# Includes CREATE DATABASE/SCHEMA/TABLE statements
pgslice --host localhost --database mydb --table film --pks 1 --create-schema > film_complete.sql

# Apply truncate filter to limit related tables by date range
pgslice --host localhost --database mydb --table customer --pks 42 \
    --truncate "rental:rental_date:2024-01-01:2024-12-31" > customer.sql

# Enable debug logging (writes to stderr)
pgslice --host localhost --database mydb --table users --pks 42 \
    --log-level DEBUG 2>debug.log > output.sql
```

### Schema Exploration

```bash
# List all tables in the schema
pgslice --host localhost --database mydb --tables

# Describe table structure and relationships
pgslice --host localhost --database mydb --describe users
```

### SSH Remote Execution

Run pgslice on a remote server and capture output locally:

```bash
# Execute on remote server, save output locally
ssh remote.server.com "PGPASSWORD=xxx pgslice --host db.internal --database mydb \
    --table users --pks 1 --create-schema" > local_dump.sql

# With SSH tunnel for database access
ssh -f -N -L 5433:db.internal:5432 bastion.example.com
PGPASSWORD=xxx pgslice --host localhost --port 5433 --database mydb \
    --table users --pks 42 > user.sql
```

### Interactive REPL

```bash
# Start interactive REPL
pgslice --host localhost --database mydb

pgslice> dump "film" 1 --output film_1.sql
pgslice> tables
pgslice> describe "film"
```

## CLI vs REPL: Output Behavior

Understanding the difference between CLI and REPL modes:

### CLI Mode (stdout by default)
The CLI streams SQL to **stdout** by default, perfect for piping and scripting:

```bash
# Streams to stdout - redirect with >
pgslice --table users --pks 42 > user_42.sql

# Or use --output flag
pgslice --table users --pks 42 --output user_42.sql

# Pipe to other commands
pgslice --table users --pks 42 | gzip > user_42.sql.gz
```

### REPL Mode (files by default)
The REPL writes to **`~/.pgslice/dumps/`** by default when `--output` is not specified:

```bash
# In REPL: writes to ~/.pgslice/dumps/public_users_42.sql
pgslice> dump "users" 42

# Specify custom output path
pgslice> dump "users" 42 --output /path/to/user.sql
```

### Same Operations, Different Modes

| Operation | CLI | REPL |
|-----------|-----|------|
| **List tables** | `pgslice --tables` | `pgslice> tables` |
| **Describe table** | `pgslice --describe users` | `pgslice> describe "users"` |
| **Dump to stdout** | `pgslice --table users --pks 42` | N/A (REPL always writes to file) |
| **Dump to file** | `pgslice --table users --pks 42 --output user.sql` | `pgslice> dump "users" 42 --output user.sql` |
| **Dump (default)** | Stdout | `~/.pgslice/dumps/public_users_42.sql` |
| **Multiple PKs** | `pgslice --table users --pks 1,2,3` | `pgslice> dump "users" 1,2,3` |
| **Truncate filter** | `pgslice --table users --pks 42 --truncate "orders:2024-01-01:2024-12-31"` | `pgslice> dump "users" 42 --truncate "orders:2024-01-01:2024-12-31"` |
| **Wide mode** | `pgslice --table users --pks 42 --wide` | `pgslice> dump "users" 42 --wide` |

### When to Use Each Mode

**Use CLI mode when:**
- Piping output to other commands
- Scripting and automation
- Remote execution via SSH
- One-off dumps

**Use REPL mode when:**
- Exploring database schema interactively
- Running multiple dumps in a session
- You prefer persistent file output
- Testing different dump configurations

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
