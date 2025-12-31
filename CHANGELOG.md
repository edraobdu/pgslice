# Changelog

All notable changes to pgslice will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.4] - 2025-12-31

### Changed
- fix: handle ON CONFLICT for non-auto-generated primary keys in PL/pgSQL mode (#16)

## [0.2.3] - 2025-12-31

### Changed
- fix: quote column names in SQL generation and improve timeframe filtering (#14)

## [0.2.2] - 2025-12-30

### Changed
- perf: optimize travsersal relationships with batching (#11)

## [0.2.1] - 2025-12-29

### Fixed
- Docker volume permission issues with dedicated entrypoint script

### Changed
- Optimized graph traversal performance using batch queries for relationship lookups

## [0.2.0] - 2025-12-28

### Added
- **CLI-first design**: pgslice now works as a CLI tool that can dump records without entering REPL
  - `--table TABLE` + `--pks PK_VALUES`: Dump specific records by primary key (comma-separated)
  - `--timeframe COLUMN:START:END`: Filter main table by date range (alternative to `--pks`)
  - `--truncate TABLE:COL:START:END`: Apply timeframe filters to related tables (repeatable)
  - `--output FILE`: Write output to file (default: stdout for easy piping)
  - `--wide`: Enable wide mode (follow self-referencing FKs)
  - `--keep-pks`: Keep original primary key values instead of remapping
  - `--graph`: Display table relationship graph after dump completes
- **Schema introspection commands**:
  - `--tables`: List all tables in the schema with formatted output
  - `--describe TABLE`: Show table structure and relationships
- **Schema DDL generation**: New `--create-schema` flag for dump command
  - Generates `CREATE DATABASE IF NOT EXISTS` statements
  - Generates `CREATE SCHEMA IF NOT EXISTS` for all schemas
  - Generates `CREATE TABLE IF NOT EXISTS` with complete table definitions
  - Includes columns, primary keys, unique constraints, and foreign keys
  - Handles circular dependencies via ALTER TABLE statements
  - Supports all PostgreSQL data types including arrays and user-defined types
  - All DDL uses IF NOT EXISTS for idempotency (can run multiple times safely)
  - Works with both `--keep-pks` and default PK remapping modes
- **Dependency graph visualization**: New `--graph` flag displays ASCII art graph of table relationships
  - Shows record counts per table
  - Displays FK relationships between tables
  - Highlights root table(s) in the graph
- **Progress indicators**: Visual feedback for long-running operations
  - Spinner animation during traversal operations
  - Progress bar enabled in both CLI and REPL modes
  - Automatically disabled when output is piped (not a TTY)
- **Centralized operations module**: New `pgslice.operations` package for shared CLI/REPL logic
  - `operations/dump_ops.py`: Shared dump execution logic
  - `operations/parsing.py`: Timeframe/truncate filter parsing utilities
  - `operations/schema_ops.py`: List tables and describe table operations

### Changed
- **REPL mode improvements**:
  - Renamed `--timeframe` flag to `--truncate` for clarity (applies to related tables, not main table)
  - Enabled progress bar in REPL mode for better user feedback
  - Updated to use centralized operations from `operations/` module
  - Improved help text and error messages
- **Logging behavior**: Log level now defaults to disabled unless `--log-level` is explicitly specified
- **Code organization**:
  - Refactored CLI to support both interactive REPL and non-interactive CLI modes
  - Eliminated code duplication between CLI and REPL by introducing shared operations
  - `SQLGenerator.generate_batch()` now accepts optional DDL parameters: `create_schema`, `database_name`, `schema_name`
  - `AppConfig` dataclass includes new `create_schema: bool = False` field

### Fixed
- Removed `IF NOT EXISTS` from `CREATE DATABASE` statement (PostgreSQL doesn't support it)

### Technical Details
- **New modules**:
  - `pgslice.dumper.ddl_generator.DDLGenerator`: DDL generation for schema dumps
  - `pgslice.dumper.dump_service.DumpService`: Centralized dump service
  - `pgslice.operations`: Package with shared CLI/REPL operations
  - `pgslice.utils.graph_visualizer`: Dependency graph visualization
  - `pgslice.utils.spinner`: Spinner animation for progress indication
- **Test coverage**: 8 new test modules added, maintained >93% overall code coverage
- **Dependency management**: Uses Kahn's algorithm for table dependency ordering in DDL generation
- **Architecture**: Cleaner separation between CLI routing, REPL mode, and shared operations
