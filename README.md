# snippy

Extract PostgreSQL records with all related data via foreign key relationships.

## Overview

`snippy` is a Python CLI tool that extracts a specific database record and **ALL** its related records by following foreign key relationships bidirectionally. This is useful for:

- Reproducing production bugs locally with real data
- Creating partial database dumps for specific users/entities
- Testing with realistic data subsets
- Debugging issues that only occur with specific data states

Instead of dumping an entire database (which may be huge), extract only what you need while maintaining referential integrity.

## Features

- ✅ **Bidirectional FK traversal**: Follows relationships in both directions (forward and reverse)
- ✅ **Circular relationship handling**: Prevents infinite loops with visited tracking
- ✅ **Multiple records**: Extract multiple records in one operation
- ✅ **Timeframe filtering**: Filter specific tables by date ranges
- ✅ **Read-only enforcement**: Prevents accidental writes to production databases
- ✅ **Interactive REPL**: User-friendly command-line interface
- ✅ **Schema caching**: SQLite-based caching for improved performance
- ✅ **Type-safe**: Full type hints with mypy strict mode
- ✅ **Secure**: SQL injection prevention, secure password handling
- ✅ **Containerized**: Docker support, no local installation required

## Quick Start (Docker - Recommended)

**No local Python installation required!**

```bash
cd snippy

# Start everything
docker-compose up -d

# Access the REPL
docker-compose exec app snippy \
  --host postgres \
  --port 5432 \
  --user test_user \
  --database test_db \
  --allow-write-connection

# Try it out
db> dump "users" 3 --output /app/output/user_3.sql
db> tables
db> describe "users"
db> exit

# Output file available at: ./output/user_3.sql
```

📖 **See [DOCKER_USAGE.md](DOCKER_USAGE.md) for complete Docker documentation.**

## Installation (Local Development)

```bash
# Clone the repository
git clone <repository-url>
cd snippy

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements-dev.txt

# Install package in development mode
pip install -e .
```

## Quick Start

### Start the REPL

```bash
snippy --host localhost --port 5432 --user postgres --database mydb
```

### Basic Usage

```bash
# Dump a single user with all related data (strict mode - default)
db> dump "users" 42 --output user_42.sql

# Dump multiple users
db> dump "users" 42,123,456 --output users.sql

# Dump with wide mode (includes peers/siblings via self-referencing FKs)
db> dump "users" 42 --wide --output user_42_wide.sql

# Dump with timeframe filtering
db> dump "users" 42 --timeframe "transactions:2024-01-01:2024-12-31"

# List all tables
db> tables

# Describe table structure
db> describe "users"

# Clear schema cache
db> clear

# Exit
db> exit
```

## Example Scenario

Given this database schema:

```sql
CREATE TABLE companies (id INT PRIMARY KEY, name TEXT);
CREATE TABLE users (id INT PRIMARY KEY, name TEXT, company_id INT REFERENCES companies);
CREATE TABLE orders (id INT PRIMARY KEY, user_id INT REFERENCES users);
```

Running `dump "users" 42` will extract:
- The user record (id=42)
- The company record (via `company_id` FK)
- All order records (via reverse FK from `orders.user_id`)

## Advanced Features

### Strict vs Wide Mode

**Strict Mode (Default)**:
- Skips self-referencing foreign keys to prevent sibling/peer expansion
- Example: Dumping a user only includes their managers, not their peers
- Best for extracting specific records with their dependencies only

**Wide Mode (`--wide` flag)**:
- Follows all relationships including self-referencing FKs
- Example: Dumping a user includes their peers who share the same manager
- Best for exploratory dumps or when you need the full relationship graph

```bash
# Strict mode: Only user 42 and their dependencies
db> dump "users" 42 --output user_strict.sql

# Wide mode: User 42 plus all related users (peers, subordinates, etc.)
db> dump "users" 42 --wide --output user_wide.sql
```

### Timeframe Filtering

Extract only recent data:

```bash
db> dump "users" 42 --timeframe "orders:created_at:2024-01-01:2024-12-31"
```

This extracts:
- User 42 (full record)
- Only orders created in 2024
- All related data (products, etc.)

### Multiple Timeframes

```bash
db> dump "users" 42 \
  --timeframe "orders:2024-01-01:2024-12-31" \
  --timeframe "transactions:2024-06-01:2024-12-31"
```

### Read-Only Mode

Enforce read-only connections:

```bash
snippy --host prod-db --require-read-only --database mydb
```

If read-only mode isn't available, the tool will refuse to connect.

## Development

### Run Tests

```bash
# Start test database
docker-compose up -d

# Run all tests
pytest

# Run with coverage
pytest --cov=src/snippy --cov-report=html

# Run specific test file
pytest tests/unit/test_schema.py
```

### Code Quality

```bash
# Type checking
mypy src/

# Linting
ruff check src/ tests/

# Formatting
ruff format src/ tests/

# Run all checks
mypy src/ && ruff check src/ tests/ && pytest
```

## Configuration

Configuration can be provided via environment variables or a `.env` file:

```bash
# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=my_database
DB_USER=postgres
DB_SCHEMA=public

# Cache
CACHE_ENABLED=true
CACHE_TTL_HOURS=24

# Connection
CONNECTION_TTL_MINUTES=30

# Logging
LOG_LEVEL=INFO
```

## Architecture

- **graph/models.py**: Data models (Table, ForeignKey, RecordData)
- **db/schema.py**: PostgreSQL schema introspection
- **graph/traverser.py**: Bidirectional BFS relationship traversal
- **dumper/sql_generator.py**: SQL INSERT statement generation
- **dumper/dependency_sorter.py**: Topological sort for FK ordering
- **cache/schema_cache.py**: SQLite-based schema caching
- **repl.py**: Interactive terminal interface
- **cli.py**: CLI argument parsing and entry point

See [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for detailed architecture.

## Security

- ✅ **Parameterized queries**: All SQL uses proper parameterization
- ✅ **SQL injection prevention**: Identifier validation
- ✅ **Secure passwords**: Never logged, prompted at runtime
- ✅ **Read-only by default**: Attempts read-only connections first
- ✅ **OWASP compliant**: Follows security best practices

## License

MIT

## Contributing

Contributions welcome! Please ensure:
- All tests pass (`pytest`)
- Type checking passes (`mypy src/`)
- Code is formatted (`ruff format`)
- Coverage stays above 90%

## Roadmap

- [ ] Support for composite foreign keys
- [ ] Progress indicators for large dumps
- [ ] Export to other formats (JSON, CSV)
- [ ] Support for other databases (MySQL, SQLite)
- [ ] Web UI for visualization
- [ ] Incremental dumps (only changed data)

## Credits

Created to solve the common problem of debugging production issues without dumping entire databases.
