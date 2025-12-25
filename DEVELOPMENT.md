# Development Guide

This guide is for developers contributing to pgslice. For end-user installation and usage instructions, see [README.md](README.md).

## Prerequisites

- Python 3.10+ (development uses 3.13/3.14)
- PostgreSQL database for testing
- Git
- [uv](https://docs.astral.sh/uv/) (installed automatically by `make setup`)

## Local Development Setup

### Quick Start

```bash
# One-time setup (installs uv, Python 3.14, dependencies, pre-commit hooks, copies env file)
make setup
```

This command will:
1. Install uv package manager
2. Install Python 3.14
3. Create virtual environment and install all dependencies
4. Install pre-commit hooks
5. Copy `.env.example` to `.env`

### Manual Setup

If you prefer to set up manually:

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install Python 3.14
uv python install 3.14

# Sync dependencies
uv sync --all-extras

# Install pre-commit hooks
uv run pre-commit install

# Copy environment file
cp .env.example .env
```

### Running pgslice Locally

#### Option A: Using .env file (Recommended)

```bash
# Edit .env with your database credentials
vim .env

# Run pgslice (Makefile loads .env automatically)
make run-repl

# Or override specific variables
make run-repl DB_NAME=other_database
```

#### Option B: Pass credentials directly to CLI

```bash
# Set password as environment variable (not stored)
export PGPASSWORD=your_password

# Run pgslice with all parameters
uv run pgslice --host localhost --port 5432 --user postgres --database test_db
```

## Docker Development Setup

For isolated testing without affecting your local environment:

```bash
# Build development image
make docker-build
```

### Running with Docker

#### Option A: Using .env file (Recommended)

```bash
# Edit .env, set DB_HOST=host.docker.internal for Mac/Windows
vim .env

# Run pgslice (Makefile loads .env automatically)
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
  -v $(pwd)/dumps:/home/pgslice/.pgslice/dumps \
  -e PGPASSWORD=your_password \
  pgslice:latest \
  pgslice --host host.docker.internal --port 5432 --user postgres --database test_db
```

## Development Workflow

### Code Quality & Testing

**Streamlined Workflow:**
```bash
# Run all tests
make test                # Run tests with coverage
make test-parallel       # Run tests in parallel (faster)
make test-unit           # Run unit tests only
make test-cov            # Generate HTML coverage report

# Run all checks (tests only - linting/formatting handled by pre-commit)
make all-checks

# Commit your changes (automatically runs linting, formatting, and type-checking)
git commit -m "your message"
```

**Pre-commit Hooks:**
Linting (ruff), formatting (ruff), and type-checking (mypy) are handled **automatically** by pre-commit hooks when you run `git commit`. The hooks check both `src/` and `tests/` directories.

To bypass pre-commit hooks temporarily (not recommended): `git commit --no-verify`

**Manual Quality Checks (if needed):**
```bash
# Run pre-commit hooks manually on all files
uv run pre-commit run --all-files

# Or run individual tools directly
uv run ruff check src/ tests/           # Lint
uv run ruff format src/ tests/          # Format
uv run mypy src/pgslice                 # Type check
```

### Testing

```bash
make test          # Run all tests with coverage
make test-parallel # Run tests in parallel (faster)
make test-unit     # Run unit tests only
make test-cov      # Generate HTML coverage report
make test-ci       # CI-optimized parallel test run
make test-fast     # Quick test run (no coverage)
```

Tests use pytest with:
- **pytest-xdist**: Parallel test execution for speed
- **pytest-mock**: Mocking database connections and external dependencies
- **freezegun**: Time-sensitive tests (caching TTL, timestamps)
- **Faker**: Realistic test data generation
- **80% minimum coverage** enforced (aiming for 100%)
- **Coverage exclusions**: All `__init__.py` files automatically excluded

## Version Management & Publishing

### Bumping Version

We use uv's built-in version management (following [Semantic Versioning](https://semver.org/)):

```bash
# Show current version
make show-version     # or: uv version

# Bump version
make bump-patch       # 0.1.1 → 0.1.2 (bug fixes)
make bump-minor       # 0.1.1 → 0.2.0 (new features, backward compatible)
make bump-major       # 0.1.1 → 1.0.0 (breaking changes)
```

The `uv version --bump` command automatically:
- Updates `pyproject.toml`
- Prints the version change (e.g., "0.1.1 -> 0.1.2")
- Follows semantic versioning rules

### Publishing to PyPI

**Complete workflow:**

1. **Bump version**:
   ```bash
   make bump-patch  # or bump-minor / bump-major
   ```

2. **Run all tests**:
   ```bash
   make test
   ```

3. **Commit changes**:
   ```bash
   git add .
   git commit -m "chore: bump version to 0.1.2"
   ```

4. **Create git tag**:
   ```bash
   git tag v0.1.2
   ```

5. **Push commit and tag**:
   ```bash
   git push origin main
   git push origin v0.1.2
   ```

6. **Publish to PyPI**:
   ```bash
   make publish  # Runs all checks first, prompts for confirmation
   ```

**Authentication Setup:**

Create API tokens at:
- Production PyPI: https://pypi.org/manage/account/token/
- TestPyPI: https://test.pypi.org/manage/account/token/

Set environment variable:
```bash
export UV_PUBLISH_TOKEN="pypi-..."  # For production
# or for TestPyPI
export UV_PUBLISH_TOKEN="pypi-..."  # When using --publish-url
```

**Testing before production:**
```bash
make build-dist      # Build distribution packages
make install-local   # Install locally for testing
make publish-test    # Publish to TestPyPI first
```

### Pre-publication Checklist

- [ ] Bump version (`make bump-patch`, `bump-minor`, or `bump-major`)
- [ ] All tests pass (`make test`)
- [ ] Commit changes (triggers linting, formatting, type-checking via pre-commit hooks)
- [ ] Create git tag (e.g., `git tag v0.1.2`)
- [ ] Push tag (`git push origin v0.1.2`)
- [ ] Test local installation (`make install-local`)
- [ ] Verify version (`pgslice --version`)
- [ ] Optional: Test on TestPyPI (`make publish-test`)
- [ ] Publish to PyPI (`make publish`)

## Architecture & Code Standards

### Type Safety
- Project uses **mypy strict mode** (configured in `pyproject.toml`)
- All functions must have type hints
- Use `from __future__ import annotations` for Python 3.10+ compatibility
- No `Any` types unless absolutely necessary

### Code Style
- Line length: 88 characters
- Formatter: ruff
- Target Python version: 3.10+ (for broad compatibility)
- Development Python version: 3.13/3.14
- Import sorting: ruff (isort rules)
- See `pyproject.toml` for complete ruff configuration

### Module Organization
```
src/pgslice/
├── db/          # Database connection and schema introspection
├── graph/       # Graph models and traversal algorithms
├── cache/       # SQLite-based schema caching
├── dumper/      # SQL generation and file writing
└── utils/       # Security, logging, exceptions
```

For detailed architecture documentation including:
- Bidirectional graph traversal algorithm (BFS)
- Traversal modes (strict vs wide)
- Foreign key handling patterns
- Adding new REPL commands
- Schema introspection details

See [CLAUDE.md](CLAUDE.md) for comprehensive architecture guide.

## Troubleshooting

### Common Issues

1. **Permission denied on output files (Docker)**
   - Make sure you're using `--user $(id -u):$(id -g)` with docker run
   - The Makefile commands handle this automatically

2. **Cannot connect to database from Docker**
   - Mac/Windows: Use `host.docker.internal` as DB_HOST
   - Linux: Use `host.docker.internal` or `--network host`

3. **Schema cache issues**
   - Clear cache: `pgslice --clear-cache`
   - Or delete cache directory: `rm -rf ~/.cache/pgslice`

4. **Import errors after installation**
   - Ensure virtual environment is activated: `source .venv/bin/activate`
   - Or use `uv run pgslice` which handles venv automatically

5. **Pre-commit hooks failing**
   - Run hooks manually to see details: `uv run pre-commit run --all-files`
   - Update hooks: `uv run pre-commit autoupdate`
   - Clear cache if needed: `uv run pre-commit clean`

6. **Test failures**
   - Run specific test: `uv run pytest tests/unit/test_file.py::test_name -v`
   - Run with debug output: `uv run pytest -v --capture=no`
   - Check coverage: `make test-cov` (opens HTML report)

## Available Make Commands

Run `make help` to see all available commands with descriptions.

## Contributing Guidelines

1. **Fork and clone** the repository
2. **Create a feature branch**: `git checkout -b feature/your-feature-name`
3. **Make changes** following code standards
4. **Write tests** for new functionality (maintain 80%+ coverage)
5. **Run all checks**: `make all-checks`
6. **Commit changes**: Use conventional commits (e.g., `feat:`, `fix:`, `docs:`, `chore:`)
7. **Push and create PR**: Pre-commit hooks run automatically on commit

### Code Review Guidelines

- All PRs require passing tests and pre-commit hooks
- Maintain or improve code coverage
- Follow existing code patterns and architecture
- Add documentation for new features
- Update CLAUDE.md for architectural changes

## License

MIT - See [LICENSE](LICENSE) file for details.
