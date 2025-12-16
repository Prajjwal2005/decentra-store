# PostgreSQL Database Configuration

## Overview
DecentraStore uses PostgreSQL for persistent user data storage. This document covers database setup, schema, and best practices.

## Database Schema

### Users Table
```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(80) UNIQUE NOT NULL,
    email VARCHAR(120) UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    salt VARCHAR(32) NOT NULL,
    storage_used_bytes BIGINT DEFAULT 0,
    storage_quota_bytes BIGINT DEFAULT 10737418240,  -- 10GB
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    is_admin BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_email ON users(email);
```

### Future Tables (for consensus tracking)
```sql
CREATE TABLE storage_nodes (
    id SERIAL PRIMARY KEY,
    node_id VARCHAR(64) UNIQUE NOT NULL,
    capacity_gb INTEGER,
    last_heartbeat TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    reputation_score FLOAT DEFAULT 1.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE chunk_storage (
    id SERIAL PRIMARY KEY,
    chunk_hash VARCHAR(64) NOT NULL,
    node_id VARCHAR(64) NOT NULL,
    block_index INTEGER,
    stored_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    verified_at TIMESTAMP,
    proof_count INTEGER DEFAULT 0,
    FOREIGN KEY (node_id) REFERENCES storage_nodes(node_id)
);

CREATE INDEX idx_chunk_storage_hash ON chunk_storage(chunk_hash);
CREATE INDEX idx_chunk_storage_node ON chunk_storage(node_id);
```

## Railway Setup

### 1. Add PostgreSQL to Railway Project

**Via Railway Dashboard:**
```
1. Open your Railway project
2. Click "New" button
3. Select "Database"
4. Choose "PostgreSQL"
5. Click "Add PostgreSQL"
```

**Via Railway CLI:**
```bash
railway add --database postgresql
```

### 2. Verify DATABASE_URL

Railway automatically sets the `DATABASE_URL` environment variable:
```bash
railway variables

# Look for:
# DATABASE_URL=postgresql://user:pass@host:port/railway
```

### 3. Test Database Connection

Create a test script:
```python
# test_db.py
import os
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL")
print(f"Connecting to: {DATABASE_URL[:30]}...")

engine = create_engine(DATABASE_URL)
with engine.connect() as conn:
    result = conn.execute(text("SELECT version()"))
    print(f"PostgreSQL version: {result.scalar()}")
    print("✓ Database connection successful!")
```

Run on Railway:
```bash
railway run python test_db.py
```

## Local Development

### 1. Install PostgreSQL Locally

**macOS:**
```bash
brew install postgresql
brew services start postgresql
```

**Ubuntu/Debian:**
```bash
sudo apt-get install postgresql postgresql-contrib
sudo systemctl start postgresql
```

**Windows:**
Download from https://www.postgresql.org/download/windows/

### 2. Create Local Database

```bash
# Create database
createdb decentrastore

# Set environment variable
export DATABASE_URL="postgresql://localhost/decentrastore"
```

### 3. Run Application

```bash
python backend/app.py
```

The `init_db()` function in `backend/models.py` will automatically create tables.

## Database Migrations

### Current Auto-Migration

The app uses SQLAlchemy's `create_all()` in `init_db()`:
```python
def init_db():
    """Initialize database tables."""
    Base.metadata.create_all(bind=engine)
```

This creates tables if they don't exist.

### Adding New Tables/Columns

**Option 1: Manual SQL (Quick)**
```bash
# Connect to Railway PostgreSQL
railway connect

# Run SQL
ALTER TABLE users ADD COLUMN new_field VARCHAR(255);
```

**Option 2: Alembic (Production-grade)**

Install Alembic:
```bash
pip install alembic
```

Initialize:
```bash
alembic init alembic
```

Create migration:
```bash
alembic revision -m "Add new_field to users"
```

Edit the migration file, then apply:
```bash
alembic upgrade head
```

## Backup and Restore

### Railway Automated Backups

Railway Pro plan includes:
- Daily automated backups
- Point-in-time recovery
- 7-day retention

Enable in Railway Dashboard → Database → Backups

### Manual Backup

**From Railway:**
```bash
# Get database connection string
railway variables

# Dump database
pg_dump $DATABASE_URL > backup.sql
```

**Restore:**
```bash
psql $DATABASE_URL < backup.sql
```

## Performance Optimization

### Indexes

Already included in schema:
- `users.username` (for login lookups)
- `users.email` (for email-based features)

### Connection Pooling

Update `backend/models.py` to use connection pooling:
```python
from sqlalchemy.pool import QueuePool

engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True  # Verify connections before use
)
```

### Query Optimization

Use SQLAlchemy query logging:
```python
import logging
logging.basicConfig()
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
```

## Security Best Practices

### 1. Connection Security

Railway uses SSL by default. For external connections:
```python
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Add SSL mode
if "sslmode" not in DATABASE_URL:
    DATABASE_URL += "?sslmode=require"
```

### 2. Credentials Management

- ✅ Never commit DATABASE_URL to git
- ✅ Use environment variables
- ✅ Rotate credentials periodically
- ✅ Use Railway's secrets management

### 3. SQL Injection Prevention

SQLAlchemy ORM prevents SQL injection by default. If using raw SQL:
```python
# ✅ GOOD - Parameterized query
session.execute(
    text("SELECT * FROM users WHERE username = :username"),
    {"username": user_input}
)

# ❌ BAD - SQL injection vulnerable
session.execute(f"SELECT * FROM users WHERE username = '{user_input}'")
```

## Monitoring

### Railway Dashboard

Monitor:
- Connection count
- Query performance
- Database size
- Memory usage

### Custom Monitoring

Add to `backend/app.py`:
```python
@app.route("/db/stats", methods=["GET"])
@admin_required
def db_stats():
    """Database statistics endpoint."""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT
                schemaname,
                tablename,
                pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
            FROM pg_tables
            WHERE schemaname = 'public'
            ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
        """))
        tables = [dict(row) for row in result]

    return jsonify({"tables": tables})
```

## Troubleshooting

### Issue: "could not connect to server"

**Check:**
1. Railway PostgreSQL service is running
2. DATABASE_URL is set correctly
3. Network connectivity

**Fix:**
```bash
railway status
railway logs --service postgresql
```

### Issue: "relation does not exist"

**Cause:** Tables not created

**Fix:**
```python
# In backend/models.py
from backend.models import init_db
init_db()
```

### Issue: "too many connections"

**Cause:** Connection pool exhausted

**Fix:**
1. Close connections properly
2. Increase pool size
3. Check for connection leaks

## Data Migration from SQLite

If migrating from SQLite to PostgreSQL:

```bash
# 1. Export from SQLite
sqlite3 data/users.db .dump > sqlite_dump.sql

# 2. Clean up SQLite-specific syntax
sed 's/AUTOINCREMENT/SERIAL/g' sqlite_dump.sql > postgres_dump.sql

# 3. Import to PostgreSQL
psql $DATABASE_URL < postgres_dump.sql
```

## Development Workflow

1. **Local development:** Use local PostgreSQL
2. **Testing:** Use Railway preview environments
3. **Production:** Use Railway main database with backups enabled

## Next Steps

- [ ] Add PostgreSQL to Railway project
- [ ] Verify DATABASE_URL environment variable
- [ ] Test database connection
- [ ] Enable automated backups (Pro plan)
- [ ] Set up monitoring/alerts
- [ ] Plan migration strategy for schema changes
