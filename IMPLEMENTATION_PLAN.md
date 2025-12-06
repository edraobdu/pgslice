# Implementation Plan: db_reverse_dump

## Overview
Create a Python CLI tool that extracts a PostgreSQL record and ALL its related records by following foreign key relationships bidirectionally, outputting SQL INSERT statements for database replication.

## Project Structure

```
db_reverse_dump/
├── pyproject.toml              # Project config, dependencies, tool settings
├── requirements.txt            # Pinned dependencies
├── requirements-dev.txt        # Dev dependencies
├── docker-compose.yml          # PostgreSQL test database
├── .env.example                # Example environment variables
├── mypy.ini                    # MyPy strict configuration
├── README.md                   # Documentation
│
├── src/db_reverse_dump/
│   ├── __init__.py
│   ├── __main__.py             # Entry point: python -m db_reverse_dump
│   ├── cli.py                  # CLI argument parsing, main()
│   ├── repl.py                 # Interactive REPL with prompt_toolkit
│   ├── config.py               # Configuration management
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── connection.py       # Connection manager with TTL
│   │   ├── schema.py           # PostgreSQL schema introspection
│   │   └── query_executor.py   # Safe query execution
│   │
│   ├── graph/
│   │   ├── __init__.py
│   │   ├── models.py           # Data models (Table, ForeignKey, RecordIdentifier, etc.)
│   │   ├── traverser.py        # Bidirectional graph traversal (BFS)
│   │   └── visited_tracker.py  # Circular reference prevention
│   │
│   ├── cache/
│   │   ├── __init__.py
│   │   ├── schema_cache.py     # SQLite schema caching
│   │   └── models.py           # Cache data models
│   │
│   ├── dumper/
│   │   ├── __init__.py
│   │   ├── sql_generator.py    # INSERT statement generation
│   │   ├── dependency_sorter.py # Topological sort for FK ordering
│   │   └── writer.py           # File output handler
│   │
│   └── utils/
│       ├── __init__.py
│       ├── security.py         # Password handling, SQL sanitization
│       ├── logging_config.py   # Logging setup
│       └── exceptions.py       # Custom exceptions
│
└── tests/
    ├── conftest.py             # Pytest fixtures
    ├── test_data/
    │   ├── schema.sql          # Test database schema
    │   └── sample_data.sql     # Test data with FK relationships
    ├── unit/
    │   ├── test_schema.py
    │   ├── test_traverser.py
    │   ├── test_sql_generator.py
    │   ├── test_dependency_sorter.py
    │   ├── test_cache.py
    │   └── test_security.py
    └── integration/
        ├── test_end_to_end.py
        └── test_repl.py
```

## Core Components

### 1. Data Models (`graph/models.py`)
**Purpose**: Define core data structures

**Key Classes**:
- `Column`: Database column metadata
- `ForeignKey`: FK relationship (source → target)
- `Table`: Complete table metadata with incoming/outgoing FKs
- `RecordIdentifier`: Unique record ID (table + PK values) - hashable for visited tracking
- `RecordData`: Record with data dict and dependency set

### 2. Schema Introspection (`db/schema.py`)
**Purpose**: Query PostgreSQL system catalogs to discover schema

**Key Class**: `SchemaIntrospector`

**Methods**:
- `get_table_metadata(schema, table)` → Complete Table object
- `_get_columns()` → Query `information_schema.columns`
- `_get_primary_keys()` → Query `pg_index` for PK columns
- `_get_foreign_keys_outgoing()` → Query `pg_constraint` for FKs FROM this table
- `_get_foreign_keys_incoming()` → Query `pg_constraint` for FKs TO this table
- `get_all_tables()` → List all tables in schema

**PostgreSQL Queries**:
```sql
-- Foreign keys from this table
SELECT conname, conrelid::regclass, a.attname,
       confrelid::regclass, af.attname, confdeltype
FROM pg_constraint c
JOIN pg_attribute a ON a.attnum = ANY(c.conkey) AND a.attrelid = c.conrelid
JOIN pg_attribute af ON af.attnum = ANY(c.confkey) AND af.attrelid = c.confrelid
WHERE c.contype = 'f' AND conrelid = %s::regclass
```

### 3. Relationship Traverser (`graph/traverser.py`)
**Purpose**: Core algorithm - bidirectional BFS traversal

**Key Class**: `RelationshipTraverser`

**Algorithm**:
1. Start with initial record (table + PK)
2. Use BFS queue with (RecordIdentifier, depth) tuples
3. For each record:
   - Check if visited (skip if yes)
   - Mark as visited
   - Fetch record data
   - **Follow outgoing FKs** (forward): Extract FK column values, enqueue target records
   - **Follow incoming FKs** (reverse): Query tables that reference this record, enqueue source records
4. Track dependencies for topological sort
5. Continue until queue empty

**Key Methods**:
- `traverse(table, pk, schema, max_depth)` → Set[RecordData]
- `_fetch_record(record_id)` → Fetch single record by PK
- `_resolve_foreign_key_target(record, fk)` → Get target record ID from FK value
- `_find_referencing_records(target_id, fk)` → Find all records referencing this one

### 4. Visited Tracker (`graph/visited_tracker.py`)
**Purpose**: Prevent circular traversal

**Implementation**: Simple `Set[RecordIdentifier]` wrapper
- `is_visited(record_id)` → bool
- `mark_visited(record_id)` → void
- `reset()` → Clear all

### 5. Dependency Sorter (`dumper/dependency_sorter.py`)
**Purpose**: Topologically sort records so dependencies come before dependents

**Algorithm**: Kahn's algorithm
1. Build adjacency graph from RecordData.dependencies
2. Calculate in-degree for each record
3. Start with zero in-degree nodes
4. Process nodes, reducing neighbor in-degrees
5. Detect cycles if not all nodes processed

**Output**: List[RecordData] in dependency order

### 6. SQL Generator (`dumper/sql_generator.py`)
**Purpose**: Generate INSERT statements from RecordData

**Format**:
```sql
INSERT INTO schema.table (col1, col2, col3)
VALUES ('val1', 'val2', 'val3')
ON CONFLICT (pk_cols) DO NOTHING;
```

**Key Features**:
- Proper value escaping (strings, nulls, timestamps, UUIDs)
- ON CONFLICT to handle duplicates
- Transaction wrapping (BEGIN/COMMIT)
- Type-specific formatting

### 7. Schema Cache (`cache/schema_cache.py`)
**Purpose**: Persist schema metadata in SQLite to avoid repeated introspection

**SQLite Schema**:
- `cache_metadata`: Track cache freshness per database
- `tables`: Store table metadata
- `columns`: Store column metadata
- `foreign_keys`: Store FK relationships

**Location**: `~/.cache/db_reverse_dump/schema_cache.db`

**TTL**: 24 hours (configurable)

**Methods**:
- `is_cache_valid(db_host, db_name)` → Check TTL
- `get_table()` → Retrieve from cache
- `cache_table()` → Store in cache
- `invalidate_cache()` → Clear cache

### 8. Connection Manager (`db/connection.py`)
**Purpose**: Manage database connections with TTL

**Features**:
- Connection pooling
- Auto-reconnect on expiry
- TTL tracking (default 30 minutes)
- Secure credential handling

### 9. REPL (`repl.py`)
**Purpose**: Interactive terminal interface

**Library**: `prompt_toolkit` for rich UI

**Commands**:
- `dump "table" pk [--output file.sql] [--schema schema]`
- `tables [--schema schema]` - List all tables
- `describe "table"` - Show table structure
- `clear` - Clear schema cache
- `help` - Show help
- `exit`, `quit` - Exit REPL

**Features**:
- Command history: `~/.db_reverse_dump_history`
- Auto-completion for commands and tables
- Multi-line support (future)

### 10. CLI Entry Point (`cli.py`)
**Purpose**: Parse arguments, start REPL

**Arguments**:
- `--host` - Database host
- `--port` - Database port
- `--user` - Database user
- `--database` - Database name
- `--schema` - Schema (default: public)
- `--no-cache` - Disable caching
- `--clear-cache` - Clear cache and exit
- `--log-level` - Logging level

**Flow**:
1. Parse arguments
2. Load configuration
3. Prompt for password (secure)
4. Create connection manager
5. Test connection
6. Start REPL

## Dependencies

**Core**:
- `psycopg[binary]>=3.1.0` - PostgreSQL adapter (modern psycopg3)
- `prompt-toolkit>=3.0.0` - Rich REPL interface
- `rich>=13.0.0` - Beautiful terminal output
- `python-dotenv>=1.0.0` - Environment variable loading

**Development**:
- `pytest>=7.4.0` + `pytest-cov`, `pytest-mock`
- `mypy>=1.5.0` - Type checking (strict mode)
- `ruff>=0.1.0` - Linting and formatting
- `freezegun>=1.2.0` - Time mocking for tests

## Test Strategy

### Test Database Schema
Create realistic schema with:
- Self-referencing FKs (users.manager_id → users.id)
- Circular relationships (categories.parent_id → categories.id)
- Many-to-many (user_groups junction table)
- Multi-column PKs
- Various FK cascade behaviors (CASCADE, SET NULL, NO ACTION)

### Unit Tests
1. **test_schema.py**: Column/PK/FK detection, composite PKs
2. **test_traverser.py**: Forward/reverse traversal, circular detection, depth limits
3. **test_dependency_sorter.py**: Topological sort, cycle detection
4. **test_sql_generator.py**: Value formatting, escaping, ON CONFLICT
5. **test_cache.py**: Cache read/write, TTL, invalidation
6. **test_security.py**: SQL identifier validation, password handling

### Integration Tests
1. **test_end_to_end.py**: Full dump → verify SQL → import to empty DB → verify integrity
2. **test_repl.py**: Command parsing, execution

### Fixtures (conftest.py)
- `docker_db`: Start PostgreSQL container
- `db_connection`: Provide connection
- `test_schema`: Create test schema
- `sample_data`: Insert test data
- `temp_cache_db`: Temporary cache file

## Security Considerations

### Password Handling
- ✅ Never log passwords
- ✅ Prompt at runtime (getpass)
- ✅ Clear from memory after use
- ✅ Support environment variables for automation

### SQL Injection Prevention
- ✅ **Always use parameterized queries** with psycopg placeholders
- ✅ Validate identifiers with regex: `^[a-zA-Z_][a-zA-Z0-9_]*$`
- ✅ Quote user-provided identifiers with `"`
- ✅ Never use string interpolation for SQL

### OWASP Guidelines
- Input validation on all user inputs
- Least privilege database connections
- Don't expose sensitive info in error messages
- Keep dependencies updated

## Additional Features

### 1. Read-Only Connection Enforcement
**Purpose**: Prevent accidental writes to production databases

**Implementation Options**:
- **Option A**: Use PostgreSQL read-only transaction mode:
  ```python
  conn.execute("SET TRANSACTION READ ONLY")
  ```
- **Option B**: Check user permissions before allowing connection:
  ```sql
  SELECT has_database_privilege(current_user, current_database(), 'CONNECT') as can_connect,
         has_database_privilege(current_user, current_database(), 'CREATE') as can_write;
  ```
- **Option C**: Check if database is in read-only mode:
  ```sql
  SHOW default_transaction_read_only;
  ```

**Behavior**:
- Try to establish read-only connection first
- If read-only not possible, warn user with prominent message:
  ```
  ⚠️  WARNING: Could not establish read-only connection!
  ⚠️  Database allows write operations.
  ⚠️  This tool only performs SELECT queries, but proceed with caution.

  Continue? [y/N]:
  ```
- Add CLI flag: `--require-read-only` to strictly enforce (exit if not read-only)
- Add CLI flag: `--allow-write-connection` to skip warning

**Files to Modify**:
- `src/db_reverse_dump/db/connection.py` - Add read-only mode check
- `src/db_reverse_dump/cli.py` - Add CLI flags
- `src/db_reverse_dump/utils/exceptions.py` - Add `ReadOnlyEnforcementError`

### 2. Timeframe Filtering
**Purpose**: Extract only recent data, reducing dump size

**Design**:
Allow filtering records by timestamp within specific tables while maintaining referential integrity.

**CLI Syntax**:
```bash
db> dump "users" 42 --timeframe "transactions:2024-01-01:2024-12-31"
# Only extract transactions created between Jan 1 and Dec 31, 2024
# But still extract ALL related data (users, products, etc.)
```

**Multiple timeframe filters**:
```bash
db> dump "users" 42 --timeframe "transactions:2024-01-01:2024-12-31" --timeframe "orders:2024-06-01:2024-12-31"
```

**Implementation**:

1. **Parse timeframe spec**: `table_name:start_date:end_date` or `table_name:column_name:start_date:end_date`
2. **Default timestamp column**: `created_at`, `updated_at`, `timestamp` (configurable)
3. **Apply filter during traversal**:
   - When fetching records from specified table, add WHERE clause with date range
   - For other tables, fetch normally (no timeframe filter)
   - Still follow all FK relationships

**Example**:
```python
# In RelationshipTraverser._find_referencing_records()
if table_name in timeframe_filters:
    filter_config = timeframe_filters[table_name]
    query += f" AND {filter_config.column} BETWEEN %s AND %s"
    params.extend([filter_config.start_date, filter_config.end_date])
```

**Data Structure**:
```python
@dataclass
class TimeframeFilter:
    """Filter records by timestamp range."""
    table_name: str
    column_name: str  # Timestamp column (e.g., 'created_at')
    start_date: datetime
    end_date: datetime

class RelationshipTraverser:
    def __init__(self, ..., timeframe_filters: List[TimeframeFilter] = None):
        self.timeframe_filters = {f.table_name: f for f in (timeframe_filters or [])}
```

**REPL Command**:
```bash
db> dump "users" 42 --timeframe "transactions:created_at:2024-01-01:2024-12-31"
```

**Files to Modify**:
- `src/db_reverse_dump/graph/models.py` - Add `TimeframeFilter` dataclass
- `src/db_reverse_dump/graph/traverser.py` - Apply filters during traversal
- `src/db_reverse_dump/repl.py` - Parse `--timeframe` argument
- `src/db_reverse_dump/cli.py` - Support timeframe in CLI

**Edge Cases**:
- Verify column exists and is timestamp type
- Handle NULL timestamps
- Support various date formats (ISO 8601, etc.)
- Auto-detect timestamp columns if not specified

### 3. Multiple Record IDs
**Purpose**: Extract multiple records in a single dump operation

**CLI Syntax**:
```bash
# Multiple IDs for same table
db> dump "users" 42,123,456 --output multiple_users.sql

# Or space-separated
db> dump "users" 42 123 456

# Or multiple --id flags
db> dump "users" --id 42 --id 123 --id 456
```

**Implementation**:

1. **Parse multiple IDs**: Split by comma or accept multiple arguments
2. **Traverse from each starting point**: Run traversal for each ID
3. **Merge results**: Union all discovered records (no duplicates via RecordIdentifier hash)
4. **Single output**: Generate one SQL file with all records

**Algorithm**:
```python
def traverse_multiple(
    self,
    table_name: str,
    pk_values: List[Any],
    schema: str = 'public'
) -> Set[RecordData]:
    """Traverse from multiple starting records."""
    all_records: Set[RecordData] = set()

    for pk_value in pk_values:
        records = self.traverse(table_name, pk_value, schema)
        all_records.update(records)

    # visited tracker persists across all traversals,
    # so we don't re-traverse shared relationships
    return all_records
```

**Benefits**:
- Efficient: Shared relationships only traversed once (via visited tracker)
- Convenient: Extract multiple users/orders/entities in one command
- Single SQL file: All records together for easy import

**REPL Command**:
```bash
db> dump "users" 42,123,456 --output users.sql
# Dumping public.users with PKs=[42, 123, 456]...
# Found 523 related records
# Wrote 523 INSERT statements to users.sql
```

**Files to Modify**:
- `src/db_reverse_dump/graph/traverser.py` - Add `traverse_multiple()` method
- `src/db_reverse_dump/repl.py` - Parse multiple IDs from command
- `src/db_reverse_dump/cli.py` - Support multiple IDs

**Edge Cases**:
- Validate all IDs before starting
- Handle composite PKs with multiple IDs
- Progress indicator for multiple records
- Skip non-existent IDs with warning

## Implementation Phases

### Phase 1: Foundation
1. Create project structure
2. Set up `pyproject.toml` with dependencies
3. Configure mypy (strict), ruff
4. Create Docker Compose with PostgreSQL
5. Implement data models (`graph/models.py`)
6. Implement config (`config.py`)
7. Implement security utils (`utils/security.py`, `utils/exceptions.py`)
8. Write tests for models and config

### Phase 2: Database Layer
1. Implement connection manager (`db/connection.py`)
2. Implement schema introspector (`db/schema.py`)
3. Write unit tests for schema introspection
4. Test against Docker database
5. Verify FK detection (both directions)

### Phase 3: Graph Traversal
1. Implement visited tracker (`graph/visited_tracker.py`)
2. Implement relationship traverser (`graph/traverser.py`)
3. Write unit tests for traversal
4. Test circular reference detection
5. Test bidirectional traversal

### Phase 4: SQL Generation
1. Implement dependency sorter (`dumper/dependency_sorter.py`)
2. Implement SQL generator (`dumper/sql_generator.py`)
3. Write unit tests
4. Test topological sorting
5. Test value formatting/escaping

### Phase 5: Caching
1. Implement SQLite cache (`cache/schema_cache.py`)
2. Integrate with schema introspector
3. Write unit tests
4. Test TTL expiration

### Phase 6: CLI and REPL
1. Implement basic CLI (`cli.py`)
2. Implement REPL (`repl.py`)
3. Add command parsing with `shlex`
4. Add history and auto-completion
5. Wire all components together
6. Write integration tests

### Phase 7: Additional Features
1. **Read-only connection enforcement**:
   - Add read-only mode check in `ConnectionManager`
   - Implement warning system with user confirmation
   - Add CLI flags: `--require-read-only`, `--allow-write-connection`
   - Write tests for read-only enforcement

2. **Timeframe filtering**:
   - Add `TimeframeFilter` dataclass to models
   - Implement timeframe parsing in REPL/CLI
   - Modify `RelationshipTraverser` to apply date filters
   - Add column existence/type validation
   - Write tests for timeframe filtering

3. **Multiple record IDs**:
   - Add `traverse_multiple()` method to `RelationshipTraverser`
   - Update REPL/CLI to parse multiple IDs (comma-separated)
   - Update output messages to show multiple PKs
   - Write tests for multi-record extraction

### Phase 8: Testing & Polish
1. Create comprehensive test data
2. Write end-to-end tests
3. Test SQL roundtrip (dump → import → verify)
4. Add progress indicators
5. Improve error messages
6. Write README and documentation

## Critical Files for Implementation

1. **src/db_reverse_dump/graph/models.py** - Foundation: all data models
2. **src/db_reverse_dump/db/schema.py** - Schema introspection via PostgreSQL catalogs
3. **src/db_reverse_dump/graph/traverser.py** - Core algorithm: bidirectional BFS
4. **src/db_reverse_dump/dumper/dependency_sorter.py** - Topological sort for correct ordering
5. **src/db_reverse_dump/dumper/sql_generator.py** - SQL generation with proper escaping
6. **src/db_reverse_dump/cache/schema_cache.py** - SQLite caching layer
7. **src/db_reverse_dump/repl.py** - Interactive terminal interface
8. **src/db_reverse_dump/cli.py** - Main entry point

## Configuration

### Environment Variables (.env)
```bash
DB_HOST=localhost
DB_PORT=5432
DB_NAME=my_database
DB_USER=postgres
DB_SCHEMA=public

CACHE_ENABLED=true
CACHE_TTL_HOURS=24

CONNECTION_TTL_MINUTES=30
MAX_DEPTH=10
LOG_LEVEL=INFO
```

### Cache Location
`~/.cache/db_reverse_dump/schema_cache.db`

### History
`~/.db_reverse_dump_history`

## Docker Compose Setup

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: test_db
      POSTGRES_USER: test_user
      POSTGRES_PASSWORD: test_pass
    ports:
      - "5432:5432"
    volumes:
      - ./tests/test_data/schema.sql:/docker-entrypoint-initdb.d/01-schema.sql
      - ./tests/test_data/sample_data.sql:/docker-entrypoint-initdb.d/02-data.sql
```

## Usage Examples

### Start REPL with read-only enforcement
```bash
db-reverse-dump --host localhost --port 5432 --user postgres --database mydb --require-read-only
# Password: [prompt]
# ⚠️  WARNING: Could not establish read-only connection!
# ⚠️  Database allows write operations.
# Error: Read-only connection required but not available. Use --allow-write-connection to bypass.
```

### Start REPL (normal mode)
```bash
db-reverse-dump --host localhost --port 5432 --user postgres --database mydb
# Password: [prompt]
# Connection successful (READ-ONLY mode)
# db>
```

### Dump a user with all related data
```bash
db> dump "users" 42 --output user_42.sql
# Dumping public.users with PK=42...
# Found 127 related records
# Wrote 127 INSERT statements to user_42.sql
```

### Dump multiple users
```bash
db> dump "users" 42,123,456 --output multiple_users.sql
# Dumping public.users with PKs=[42, 123, 456]...
# Found 523 related records
# Wrote 523 INSERT statements to multiple_users.sql
```

### Dump user with timeframe filtering
```bash
db> dump "users" 42 --timeframe "transactions:created_at:2024-01-01:2024-12-31" --output user_2024.sql
# Dumping public.users with PK=42...
# Applying timeframe filter: transactions.created_at between 2024-01-01 and 2024-12-31
# Found 89 related records (45 transactions within timeframe)
# Wrote 89 INSERT statements to user_2024.sql
```

### Dump with multiple timeframe filters
```bash
db> dump "users" 42 --timeframe "transactions:2024-01-01:2024-12-31" --timeframe "orders:2024-06-01:2024-12-31" --output user_filtered.sql
# Dumping public.users with PK=42...
# Applying timeframe filters:
#   - transactions: 2024-01-01 to 2024-12-31
#   - orders: 2024-06-01 to 2024-12-31
# Found 67 related records
# Wrote 67 INSERT statements to user_filtered.sql
```

### List tables
```bash
db> tables
# roles
# users
# orders
# order_items
# products
```

### Describe table structure
```bash
db> describe "users"
# Table: public.users
# Columns: id, username, email, role_id, manager_id
# Primary Keys: id
# Foreign Keys:
#   - role_id → roles.id
#   - manager_id → users.id (self-referencing)
# Referenced By:
#   - orders.user_id
#   - user_groups.user_id
```

## Type Checking & Code Quality

- **Type hints**: All functions, methods, variables
- **MyPy**: Strict mode enabled
- **Ruff**: Linting and formatting
- **Test coverage**: Aim for >90%
- **Docstrings**: All public functions and classes

## Success Criteria

1. ✅ Can extract a single record with all related data (both directions)
2. ✅ Can extract multiple records in one operation
3. ✅ Handles circular relationships without infinite loops
4. ✅ Supports timeframe filtering for specific tables
5. ✅ Enforces or warns about read-only connections
6. ✅ Generates valid SQL that imports successfully
7. ✅ REPL is interactive and user-friendly
8. ✅ Schema caching improves performance on repeated runs
9. ✅ All tests pass with good coverage
10. ✅ Type checks pass with mypy strict mode
11. ✅ Code formatted with ruff
12. ✅ Secure (no SQL injection, secure password handling)
13. ✅ Well documented

## Next Steps After Planning

1. Create project folder: `db_reverse_dump/`
2. Copy this plan to `db_reverse_dump/IMPLEMENTATION_PLAN.md` for reference
3. Initialize with `pyproject.toml`
4. Set up Docker Compose
5. Implement Phase 1 (Foundation)
6. Work through phases sequentially (Phases 1-8)
7. Test continuously after each phase
8. Verify all success criteria before considering the project complete

## Plan Export

This plan will be copied to the project directory as `IMPLEMENTATION_PLAN.md` for easy reference during implementation.
