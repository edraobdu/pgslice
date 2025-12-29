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

### Connecting to Localhost Database

When your PostgreSQL database is running on your host machine (localhost), the container cannot access it using `localhost` or `127.0.0.1` because these refer to the container itself, not your host.

**Solution 1: Use host networking (Linux, simplest)**
```bash
docker run --rm -it \
  --network host \
  -v $(pwd)/dumps:/home/pgslice/.pgslice/dumps \
  -e PGPASSWORD=your_password \
  edraobdu/pgslice:latest \
  pgslice --host localhost --port 5432 --user your_user --database your_db
```

**Solution 2: Use host.docker.internal (Mac/Windows)**
```bash
docker run --rm -it \
  -v $(pwd)/dumps:/home/pgslice/.pgslice/dumps \
  -e PGPASSWORD=your_password \
  edraobdu/pgslice:latest \
  pgslice --host host.docker.internal --port 5432 --user your_user --database your_db
```

**Solution 3: Use Docker bridge IP (Linux alternative)**
```bash
# Find your host's Docker bridge IP (usually 172.17.0.1)
docker run --rm -it \
  -v $(pwd)/dumps:/home/pgslice/.pgslice/dumps \
  -e PGPASSWORD=your_password \
  edraobdu/pgslice:latest \
  pgslice --host 172.17.0.1 --port 5432 --user your_user --database your_db
```

**Note:** Make sure your PostgreSQL is configured to accept connections from Docker containers:
- Edit `postgresql.conf`: Set `listen_addresses = '*'` or `listen_addresses = '0.0.0.0'`
- Edit `pg_hba.conf`: Add entry like `host all all 172.17.0.0/16 md5` (for Docker bridge network)

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

#### Volume Permissions

The container runs as non-root user `pgslice` (UID 1000) for security. When mounting local directories:

**The entrypoint script automatically handles permissions** by:
1. Detecting mounted volumes
2. Fixing ownership to UID 1000 if needed
3. Providing helpful error messages if permissions can't be fixed

**If you encounter permission errors:**

**Option 1: Pre-fix permissions on host (recommended)**
```bash
# Create dumps directory and set ownership
mkdir -p dumps
sudo chown -R 1000:1000 dumps

# Run container
docker run --rm -it \
  -v $(pwd)/dumps:/home/pgslice/.pgslice/dumps \
  edraobdu/pgslice:latest pgslice
```

**Option 2: Run as your user ID**
```bash
# Run container as your user (bypasses UID 1000)
docker run --rm -it \
  -v $(pwd)/dumps:/home/pgslice/.pgslice/dumps \
  --user $(id -u):$(id -g) \
  edraobdu/pgslice:latest pgslice
```

**Why UID 1000?**
- Common default UID for first user on Linux systems
- Matches most developer workstations
- If your user is different, use `--user $(id -u):$(id -g)` flag

### Remote Server Workflow

When running pgslice on a remote server, dumps are created as files with visible progress:

```bash
# SSH into remote server and run dump
ssh user@remote-server "docker run --rm \
  -v /tmp/dumps:/home/pgslice/.pgslice/dumps \
  --env-file .env \
  edraobdu/pgslice:latest \
  pgslice --dump users --pks 42"

# Copy the generated file to your local machine
scp user@remote-server:/tmp/dumps/public_users_42_*.sql ./local_dumps/

# Or use rsync for better performance with large files
rsync -avz user@remote-server:/tmp/dumps/public_users_42_*.sql ./local_dumps/
```

Progress bars are visible during the dump, and the file is ready to transfer when complete.

## Links

- **GitHub:** https://github.com/edraobdu/pgslice
- **PyPI:** https://pypi.org/project/pgslice/
- **Documentation:** See [README.md](https://github.com/edraobdu/pgslice/blob/main/README.md)

## Support

For issues, questions, or contributions, visit: https://github.com/edraobdu/pgslice/issues
