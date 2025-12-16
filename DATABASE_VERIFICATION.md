# Database Verification Guide

Guide for verifying that PostgreSQL database is storing data correctly in Railway deployment.

## 📋 Table of Contents

1. [Quick Verification](#quick-verification)
2. [Verification Script](#verification-script)
3. [What Gets Verified](#what-gets-verified)
4. [Expected Output](#expected-output)
5. [Troubleshooting](#troubleshooting)

---

## Quick Verification

### Running on Railway

```bash
# Verify database is storing data
railway run python verify_database.py
```

### Running Locally

```bash
# Make sure DATABASE_URL is set in .env
python verify_database.py
```

---

## Verification Script

The `verify_database.py` script checks:

1. ✅ **Database Connection** - PostgreSQL is accessible
2. ✅ **User Accounts** - Users are stored correctly
3. ✅ **File Metadata** - Uploaded files are tracked
4. ✅ **Storage Nodes** - Registered nodes are recorded
5. ✅ **Blockchain Data** - Blockchain persists across restarts

---

## What Gets Verified

### 1. Database Connection

```
DATABASE CONNECTION
============================================================
✅ DATABASE_URL configured
   postgresql://user:***@host:5432/database

✅ Connection successful
   PostgreSQL Version: PostgreSQL 15.x on x86_64-pc-linux-gnu
```

**Checks:**
- Environment variable `DATABASE_URL` is set
- Can connect to PostgreSQL
- PostgreSQL version

---

### 2. User Accounts

```
USER ACCOUNTS
============================================================
✅ Found 2 user(s):

  👤 alice
     Email: alice@example.com
     User ID: user_abc123
     Created: 2025-12-16 14:30:00
     Password Hash: $2b$12$AbCdEf...

  👤 bob
     Email: bob@example.com
     User ID: user_xyz789
     Created: 2025-12-16 15:45:00
     Password Hash: $2b$12$XyZaBc...
```

**Checks:**
- Users table exists
- Registration creates user records
- Passwords are hashed with bcrypt
- User IDs are generated

---

### 3. File Metadata

```
FILE METADATA
============================================================
✅ Found 3 file(s):

  📄 document.pdf
     File ID: file_123abc
     Owner: user_abc123
     Size: 5.23 MB
     Chunks: 21
     Encrypted Key: a1b2c3d4e5f6...
     IV: 1234567890abcdef
     Merkle Root: f8e7d6c5b4a3...
     Uploaded: 2025-12-16 16:00:00
     Deleted: False
     Chunk Assignments: 21 chunks
       - Replication factor: 3 nodes per chunk

  📄 photo.jpg
     File ID: file_456def
     ...

📊 Total: 15.67 MB across 63 chunks
```

**Checks:**
- Files table exists
- Upload creates file records
- Encryption keys stored
- Merkle roots calculated
- Chunk assignments tracked
- Deletion flag works

---

### 4. Storage Nodes

```
STORAGE NODES
============================================================
✅ Found 3 storage node(s):

  🖥️  node-abc123
     IP: 192.168.1.100:6001
     Public IP: 203.0.113.42
     Status: active
     Capacity: 50.0 GB
     Registered: 2025-12-16 10:00:00
     Last Seen: 2025-12-16 16:05:00
     🟢 ONLINE (last seen 45s ago)

  🖥️  node-xyz789
     IP: 192.168.1.101:6001
     Public IP: 198.51.100.123
     Status: active
     Capacity: 100.0 GB
     Registered: 2025-12-16 11:30:00
     Last Seen: 2025-12-16 15:00:00
     🔴 OFFLINE (last seen 65m ago)
```

**Checks:**
- Storage nodes table exists
- WebSocket registration creates records
- Heartbeats update last_seen
- Online/offline status based on last_seen
- Capacity tracking

---

### 5. Blockchain Data

```
BLOCKCHAIN DATA
============================================================
✅ Blockchain loaded successfully
   Total Blocks: 8
   Chain Valid: True

Recent blocks (showing last 5):

  📦 Block #4
     Hash: a1b2c3d4e5f6...
     Previous: f9e8d7c6b5a4...
     Timestamp: 2025-12-16 15:30:00
     Nonce: 12345
     Difficulty: 4
     📄 File: document.pdf
        Size: 5.23 MB
        Chunks: 21
        Owner: user_abc123

  📦 Block #5
     Hash: b2c3d4e5f6a7...
     Previous: a1b2c3d4e5f6...
     Timestamp: 2025-12-16 15:45:00
     Nonce: 67890
     Difficulty: 4
     📄 File: photo.jpg
        Size: 2.15 MB
        Chunks: 9
        Owner: user_xyz789
```

**Checks:**
- Blockchain loads from database
- Genesis block exists
- Chain is valid (hashes link correctly)
- File metadata in blocks
- Proof-of-work nonces
- Difficulty adjustment

---

## Expected Output

### Fresh Deployment (No Data)

```
DECENTRASTORE DATABASE VERIFICATION
============================================================
Timestamp: 2025-12-16 16:00:00

DATABASE CONNECTION
============================================================
✅ DATABASE_URL configured
✅ Connection successful

USER ACCOUNTS
============================================================
❌ No users found in database

FILE METADATA
============================================================
⚠️  No files found in database (upload a file to test)

STORAGE NODES
============================================================
⚠️  No storage nodes registered (start a node to test)

BLOCKCHAIN DATA
============================================================
✅ Blockchain loaded successfully
   Total Blocks: 1
   Chain Valid: True

Recent blocks (showing last 1):

  📦 Block #0
     Hash: 0000abc...
     (Genesis block)

VERIFICATION SUMMARY
============================================================
✅ PASS - USERS
✅ PASS - FILES
✅ PASS - NODES
✅ PASS - BLOCKCHAIN

✅ All checks passed - Database is working correctly!
```

**This is normal** for a fresh deployment. The database structure is correct, just waiting for:
- User registrations
- File uploads
- Storage node connections

---

### After Testing (With Data)

```
VERIFICATION SUMMARY
============================================================
✅ PASS - USERS
✅ PASS - FILES
✅ PASS - NODES
✅ PASS - BLOCKCHAIN

✅ All checks passed - Database is working correctly!
```

With actual data showing in each section.

---

## Testing Data Storage

### 1. Test User Registration

```bash
# Using the web interface:
# 1. Go to https://web-production-dcddc.up.railway.app
# 2. Create an account
# 3. Run verification

railway run python verify_database.py
```

Should show your user account in USER ACCOUNTS section.

### 2. Test File Upload

```bash
# Using the web interface:
# 1. Log in
# 2. Upload a file
# 3. Run verification

railway run python verify_database.py
```

Should show:
- File in FILE METADATA section
- New block in BLOCKCHAIN DATA section

### 3. Test Storage Node

```bash
# On your local machine:
python node_package/websocket_node.py \
  --server https://web-production-dcddc.up.railway.app \
  --capacity 50

# Then verify:
railway run python verify_database.py
```

Should show your node in STORAGE NODES section as ONLINE.

---

## Direct Database Queries

If you want to query the database directly:

### Connect to Railway PostgreSQL

```bash
# Get database shell
railway run psql $DATABASE_URL
```

### Useful Queries

**Count users:**
```sql
SELECT COUNT(*) FROM users;
```

**List files:**
```sql
SELECT file_id, filename, file_size, chunk_count, owner_id, uploaded_at
FROM files
WHERE deleted = false;
```

**List active nodes:**
```sql
SELECT node_id, ip, port, status, last_seen
FROM storage_nodes
WHERE status = 'active';
```

**Check blockchain:**
```sql
SELECT index, hash, timestamp
FROM blockchain_blocks
ORDER BY index DESC
LIMIT 5;
```

**Get total storage:**
```sql
SELECT
  COUNT(*) as total_files,
  SUM(file_size) as total_bytes,
  SUM(chunk_count) as total_chunks
FROM files
WHERE deleted = false;
```

---

## Troubleshooting

### Error: DATABASE_URL not set

**Symptom:**
```
❌ DATABASE_URL environment variable not set
```

**Solution:**
```bash
# For Railway:
# DATABASE_URL is set automatically by PostgreSQL plugin
# Make sure PostgreSQL service is added

# For local testing:
# Add to .env file:
DATABASE_URL=postgresql://user:password@localhost:5432/decentrastore
```

### Error: Connection failed

**Symptom:**
```
❌ Connection failed: could not connect to server
```

**Solution:**
1. Verify PostgreSQL service is running in Railway
2. Check DATABASE_URL format is correct
3. Ensure firewall allows connection

### Error: No users/files but you uploaded

**Symptom:**
Data shows in web interface but not in verification

**Possible causes:**
1. Connected to different database
2. Verification script using wrong DATABASE_URL
3. Data in different schema

**Solution:**
```bash
# Verify you're checking the right database
railway run python -c "import os; print(os.getenv('DATABASE_URL'))"

# Check if tables exist
railway run psql $DATABASE_URL -c "\dt"
```

### Error: Blockchain invalid

**Symptom:**
```
❌ Chain Valid: False
```

**This is serious!** Means blockchain data is corrupted.

**Solution:**
1. Check recent logs for errors
2. Restore from backup if available
3. If testing: reinitialize database

---

## Monitoring in Production

### Set Up Regular Checks

Create a cron job or Railway scheduled task:

```bash
# Every hour
0 * * * * railway run python verify_database.py >> /tmp/db_check.log 2>&1
```

### Alert on Failures

Modify `verify_database.py` to send alerts:

```python
# At end of main()
if not all_passed:
    send_alert_email("Database verification failed!")
    send_slack_notification("Database issues detected")
```

### Dashboard

Create endpoint in `server.py`:

```python
@app.route("/admin/db-status")
def db_status():
    """Database health status."""
    session = get_session()

    return jsonify({
        'users': session.query(User).count(),
        'files': session.query(File).filter_by(deleted=False).count(),
        'nodes': session.query(StorageNode).filter_by(status='active').count(),
        'blockchain_blocks': len(Blockchain(session).chain),
        'timestamp': time.time()
    })
```

---

## Best Practices

1. **Run verification after deployment** to confirm database setup
2. **Test with sample data** before going live
3. **Monitor regularly** in production
4. **Back up database** before major changes
5. **Check blockchain validity** periodically

---

## Railway Database Backup

### Manual Backup

```bash
# Export database
railway run pg_dump $DATABASE_URL > backup.sql

# Restore
railway run psql $DATABASE_URL < backup.sql
```

### Automated Backups

Railway Pro plan includes automated backups:
- Daily backups retained for 7 days
- Restore from Railway dashboard

---

## Summary

The verification script helps you confirm:

✅ PostgreSQL is configured correctly
✅ All tables are created
✅ Data persists across restarts
✅ Blockchain integrity maintained
✅ Storage nodes tracked properly
✅ User authentication working

Run it regularly to ensure database health!

---

**Last Updated:** 2025-12-16
**Script:** `verify_database.py`
**Related:** `POSTGRESQL_SETUP.md`, `RAILWAY_DEPLOYMENT.md`
