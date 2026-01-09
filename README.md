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
- ✅ **Natural key support**: Idempotent SQL generation for tables without unique constraints
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

**Transaction Safety**: All generated SQL dumps are wrapped in `BEGIN`/`COMMIT` transactions by default. If any part of the import fails, everything automatically rolls back, leaving your database unchanged.

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

## Idempotent Imports with Natural Keys

### What Are Natural Keys?

**Natural keys** are columns (or combinations of columns) that uniquely identify a record by its business meaning, even without explicit database constraints. They represent the "real-world" identifier for your data.

Examples:
- `roles.name` - Role names like "Admin", "User", "Guest" are naturally unique
- `statuses.code` - Status codes like "ACTIVE", "INACTIVE", "PENDING"
- `(tenant_id, setting_key)` - Configuration settings in multi-tenant systems
- `countries.iso_code` - ISO country codes like "US", "CA", "UK"

### Why Use Natural Keys?

By default, pgslice remaps auto-generated primary keys (SERIAL, IDENTITY) to avoid conflicts when importing. However, this can create duplicate records if you reimport the same dump multiple times:

```sql
-- First import: Creates record with new id=1
INSERT INTO roles (name) VALUES ('Admin');

-- Second import: Creates duplicate with new id=2 (no UNIQUE constraint to prevent it!)
INSERT INTO roles (name) VALUES ('Admin');
```

The `--natural-keys` flag solves this by generating **idempotent SQL** - scripts that check "does a record with this natural key already exist?" before inserting. Run the same dump multiple times safely with no duplicates.

### When to Use `--natural-keys`

Use this flag when:
- ✅ Tables have auto-generated PKs (SERIAL, IDENTITY columns)
- ✅ You need to reimport dumps multiple times (development, testing, CI/CD)
- ✅ Tables lack explicit UNIQUE constraints on natural key columns
- ✅ You need composite natural keys (multiple columns for uniqueness)
- ✅ Auto-detection fails or you want explicit control

### Usage Examples

```bash
# Single-column natural key (common for reference/lookup tables)
pgslice --host localhost --database mydb --dump users --pks 42 \
  --natural-keys "roles=name"

# With schema prefix (explicit schema)
pgslice --host localhost --database mydb --dump users --pks 42 \
  --natural-keys "public.roles=name"

# Composite natural key (multiple columns define uniqueness)
pgslice --host localhost --database mydb --dump customers --pks 1 \
  --natural-keys "tenant_settings=tenant_id,setting_key"

# Multiple tables (semicolon-separated)
pgslice --host localhost --database mydb --dump orders --pks 123 \
  --natural-keys "roles=name;statuses=code;countries=iso_code"

# Complex example with mixed single and composite keys
pgslice --host localhost --database mydb --dump products --pks 456 \
  --natural-keys "roles=name;tenant_configs=tenant_id,config_key;categories=slug"
```

**Format**: `--natural-keys "schema.table=col1,col2;other_table=col1;..."`
- Tables separated by `;`
- Columns separated by `,`
- Schema prefix optional (defaults to `public`)

### Auto-Detection

pgslice automatically detects natural keys in this priority order:

1. **Manual specification** (highest priority) - Your `--natural-keys` flag
2. **Common column names** - Recognizes patterns like:
   - Exact matches: `name`, `code`, `slug`, `email`, `username`, `key`, `identifier`, `handle`
   - Suffix patterns: `*_code`, `*_key`, `*_identifier`, `*_slug`
3. **Reference table heuristic** - Small tables (2-3 columns) with one non-PK text column
4. **Error if none found** - Suggests using `--natural-keys` manually

For most reference tables (roles, statuses, categories), auto-detection works automatically. Use manual specification for:
- Tables with unconventional column names
- Composite natural keys
- When you want explicit control

### How It Works

When natural keys are specified, pgslice generates sophisticated CTE-based SQL that:

1. Checks if records with matching natural keys already exist
2. Only inserts records that don't exist yet
3. Maps old primary keys to new (or existing) primary keys for foreign key resolution
4. Ensures idempotency - running multiple times produces the same result

Example generated SQL structure:
```sql
WITH to_insert AS (
    -- Values to potentially insert
    SELECT * FROM (VALUES (...)) AS v(...)
),
existing AS (
    -- Find records that already exist by natural key
    SELECT t.id, ti.old_id
    FROM roles t
    INNER JOIN to_insert ti ON t.name IS NOT DISTINCT FROM ti.name
),
inserted AS (
    -- Insert only new records (skip existing)
    INSERT INTO roles (name, permissions)
    SELECT name, permissions FROM to_insert
    WHERE old_id NOT IN (SELECT old_id FROM existing)
    RETURNING id, name
)
-- Map old IDs to new IDs for FK resolution
...
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
