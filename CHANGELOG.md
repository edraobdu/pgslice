# Changelog

All notable changes to pgslice will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Schema DDL generation**: New `--create-schema` flag for dump command
  - Generates `CREATE DATABASE IF NOT EXISTS` statements
  - Generates `CREATE SCHEMA IF NOT EXISTS` for all schemas
  - Generates `CREATE TABLE IF NOT EXISTS` with complete table definitions
  - Includes columns, primary keys, unique constraints, and foreign keys
  - Handles circular dependencies via ALTER TABLE statements
  - Supports all PostgreSQL data types including arrays and user-defined types
  - All DDL uses IF NOT EXISTS for idempotency (can run multiple times safely)
  - Works with both `--keep-pks` and default PK remapping modes

### Changed
- `SQLGenerator.generate_batch()` now accepts optional DDL parameters: `create_schema`, `database_name`, `schema_name`
- `AppConfig` dataclass includes new `create_schema: bool = False` field

### Technical Details
- New module: `pgslice.dumper.ddl_generator.DDLGenerator`
- Uses Kahn's algorithm for table dependency ordering
- Foreign keys added via ALTER TABLE after table creation to handle circular dependencies
- Comprehensive type mapping from PostgreSQL information_schema to CREATE TABLE syntax
- 30 new tests added with >93% overall code coverage maintained
