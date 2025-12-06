# Docker Usage Guide

This guide shows how to use `snippy` with Docker, requiring no local Python installation.

## Quick Start

### 1. Build and Start Services

```bash
cd snippy
docker-compose up --build -d
```

This starts:
- PostgreSQL database with test data
- Application container (ready for commands)

### 2. Access the Interactive REPL

```bash
docker-compose exec app snippy \
  --host postgres \
  --port 5432 \
  --user test_user \
  --database test_db \
  --allow-write-connection
```

No password prompt! It uses the `PGPASSWORD` environment variable automatically.

### 3. Run Commands

Inside the REPL:

```bash
# Dump a single user with all related data (strict mode - default)
db> dump "users" 3 --output /app/output/user_3.sql

# Dump multiple users
db> dump "users" 3,4,5 --output /app/output/users.sql

# Dump with wide mode (includes peers/siblings)
db> dump "users" 2 --wide --output /app/output/user_2_wide.sql

# Dump with timeframe filtering (only 2024 transactions)
db> dump "users" 3 --timeframe "transactions:created_at:2024-01-01:2024-12-31" --output /app/output/charlie_2024.sql

# List all tables
db> tables

# Describe a table
db> describe "users"

# Exit
db> exit
```

## Output Files

Files saved to `/app/output/` inside the container are available in `./output/` on your host:

```bash
# In container
db> dump "users" 3 --output /app/output/user_3.sql

# On host
ls ./output/user_3.sql  # ✅ Available!
```

## Alternative: One-off Commands

Run a single command without staying in the REPL:

```bash
docker-compose run --rm app bash -c "
  echo 'test_pass' | snippy \
    --host postgres \
    --user test_user \
    --database test_db \
    --allow-write-connection
"
```

## Verify Database

Check the test data:

```bash
# List tables
docker-compose exec postgres psql -U test_user -d test_db -c "\dt"

# Query users
docker-compose exec postgres psql -U test_user -d test_db -c "SELECT * FROM users;"

# Query with relationships
docker-compose exec postgres psql -U test_user -d test_db -c "
  SELECT u.username, r.name as role, o.id as order_id
  FROM users u
  JOIN roles r ON u.role_id = r.id
  LEFT JOIN orders o ON o.user_id = u.id
  WHERE u.username = 'charlie';
"
```

## Stopping Services

```bash
# Stop but keep data
docker-compose stop

# Stop and remove containers (keeps volumes)
docker-compose down

# Stop, remove containers AND volumes (fresh start)
docker-compose down -v
```

## Rebuild After Code Changes

If you modify the source code:

```bash
docker-compose build app
docker-compose restart app
```

## Logs

View application logs:

```bash
docker-compose logs -f app
```

View PostgreSQL logs:

```bash
docker-compose logs -f postgres
```

## Troubleshooting

### Container won't start

```bash
# Check status
docker-compose ps

# View logs
docker-compose logs app
docker-compose logs postgres
```

### Connection refused

Wait for PostgreSQL to be ready:

```bash
# Check health
docker-compose ps

# Wait for healthy status
docker-compose up -d
sleep 10  # Give postgres time to initialize
```

### Permission denied on output folder

```bash
chmod 777 output/
```

### Can't access REPL

Make sure you're using `exec` (not `run`):

```bash
# ✅ Correct - connects to running container
docker-compose exec app snippy ...

# ❌ Wrong - creates new container
docker-compose run app snippy ...
```

## Test Scenarios

The test database includes:

- **5 users**: alice (admin), bob (manager), charlie/diana/eve (users)
- **Hierarchy**: alice → bob → charlie/diana/eve (manager relationships)
- **Orders**: Users have orders with different dates
- **Transactions**: Bank accounts with transactions (2023 and 2024)
- **Groups**: Many-to-many user-group relationships

### Example: Extract User "charlie" (ID=3)

```bash
db> dump "users" 3 --output /app/output/charlie.sql
```

This extracts:
- Charlie's user record
- His role (user)
- His manager (bob) and manager's manager (alice)
- His 3 orders
- Order items and products
- His 2 bank accounts
- His 7 transactions
- His group membership (Engineering)

### Example: Extract Only 2024 Data

```bash
db> dump "users" 3 \
  --timeframe "transactions:created_at:2024-01-01:2024-12-31" \
  --output /app/output/charlie_2024.sql
```

This extracts:
- Charlie and relationships (same as above)
- BUT only 5 transactions from 2024 (excludes 2 from 2023)

### Example: Extract Multiple Users

```bash
db> dump "users" 3,4,5 --output /app/output/team.sql
```

This extracts:
- Charlie, Diana, and Eve
- All their relationships
- Shared data only included once (managers, roles, etc.)

## Environment Variables

You can customize the configuration via environment variables in `docker-compose.yml`:

```yaml
environment:
  DB_HOST: postgres
  DB_PORT: 5432
  DB_NAME: test_db
  DB_USER: test_user
  PGPASSWORD: test_pass  # Avoid password prompt
  DB_SCHEMA: public
  LOG_LEVEL: INFO  # DEBUG, INFO, WARNING, ERROR
  CACHE_ENABLED: "true"
  CACHE_TTL_HOURS: 24
```

## Connect to External Database

To dump from a different PostgreSQL database (not the test one):

```bash
docker-compose run --rm app snippy \
  --host your-db-host.com \
  --port 5432 \
  --user your_user \
  --database your_db \
  --require-read-only
# Will prompt for password
```

Or set environment variables:

```bash
docker-compose run --rm \
  -e DB_HOST=your-db-host.com \
  -e DB_USER=your_user \
  -e DB_NAME=your_db \
  -e PGPASSWORD=your_password \
  app snippy \
    --host your-db-host.com \
    --user your_user \
    --database your_db \
    --require-read-only
```

## Production Use

For production dumps, **always** use `--require-read-only`:

```bash
docker-compose run --rm app snippy \
  --host production-db.com \
  --user readonly_user \
  --database prod_db \
  --require-read-only
```

This ensures the tool refuses to connect if read-only mode isn't available.

## Next Steps

- Test the basic dump: `dump "users" 3`
- Try timeframe filtering: `--timeframe "orders:2024-01-01:2024-12-31"`
- Explore the REPL commands: `help`
- Check the generated SQL: `cat output/user_3.sql`
- Import to another database: `psql -U user -d db < output/user_3.sql`
