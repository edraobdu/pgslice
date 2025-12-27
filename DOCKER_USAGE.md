# pgslice Docker Image

Python CLI tool for extracting PostgreSQL database records with ALL related data by following foreign key relationships bidirectionally.

**Features:**
- Extracts records with complete dependency trees
- Maintains referential integrity
- Generates SQL INSERT statements
- Supports interactive REPL mode
- Production-optimized Alpine-based image (50-100MB)

## Quick Start

### Pull the Image

```bash
# Latest version
docker pull edraobdu/pgslice:latest

# Specific version
docker pull edraobdu/pgslice:0.1.1

# Pin to minor version (get patch updates automatically)
docker pull edraobdu/pgslice:0.1

# Platform-specific
docker pull --platform linux/amd64 edraobdu/pgslice:latest
docker pull --platform linux/arm64 edraobdu/pgslice:latest
```

## Usage Examples

### Basic Usage

```bash
docker run --rm -it \
  -v $(pwd)/dumps:/home/pgslice/.pgslice/dumps \
  -e PGPASSWORD=your_password \
  edraobdu/pgslice:latest \
  pgslice --host your.db.host --port 5432 --user your_user --database your_db
```
### Using Environment File

Create a `.env` file:
```env
DB_HOST=your.db.host
DB_PORT=5432
DB_NAME=your_db
DB_USER=your_user
PGPASSWORD=your_password
DB_SCHEMA=public
LOG_LEVEL=INFO
```

Run with environment file:
```bash
docker run --rm -it \
  -v $(pwd)/dumps:/home/pgslice/.pgslice/dumps \
  --env-file .env \
  edraobdu/pgslice:latest \
  pgslice
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DB_HOST` | PostgreSQL host | - |
| `DB_PORT` | PostgreSQL port | `5432` |
| `DB_NAME` | Database name | - |
| `DB_USER` | Database user | - |
| `DB_SCHEMA` | Schema name | `public` |
| `PGPASSWORD` | Database password | - |
| `CACHE_ENABLED` | Enable schema caching | `true` |
| `CACHE_TTL_HOURS` | Cache TTL in hours | `24` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `PGSLICE_OUTPUT_DIR` | Output directory | `/home/pgslice/.pgslice/dumps` |

### Volume Mounts

Mount a local directory to persist SQL dumps:

```bash
-v $(pwd)/dumps:/home/pgslice/.pgslice/dumps
```

**Important:** The dumps directory is created inside the container with non-root user permissions (UID 1000).

## Links

- **GitHub:** https://github.com/edraobdu/pgslice
- **PyPI:** https://pypi.org/project/pgslice/
- **Documentation:** See [README.md](https://github.com/edraobdu/pgslice/blob/main/README.md)

## Support

For issues, questions, or contributions, visit: https://github.com/edraobdu/pgslice/issues
