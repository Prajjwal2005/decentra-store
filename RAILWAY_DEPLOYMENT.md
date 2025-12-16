# Railway Deployment Guide

## Overview
This guide explains how to deploy DecentraStore to Railway with proper environment configuration and PostgreSQL database.

## Step 1: Set Environment Variables

### Required Environment Variables

1. **SECRET_KEY** (CRITICAL for production)
   ```bash
   # Generate a secure random key:
   python -c "import secrets; print(secrets.token_hex(32))"

   # Example output: a1b2c3d4e5f6...
   ```

   **In Railway Dashboard:**
   - Go to your project
   - Click "Variables" tab
   - Add new variable: `SECRET_KEY`
   - Paste the generated key
   - Deploy

2. **DATABASE_URL** (Auto-configured when PostgreSQL addon is added)
   - Railway provides this automatically when you add PostgreSQL
   - Format: `postgresql://user:password@host:port/database`

### Optional Environment Variables

```env
# CORS Configuration
ALLOWED_ORIGINS=https://your-domain.com

# Upload Settings
MAX_UPLOAD_SIZE=104857600  # 100MB in bytes

# JWT Configuration
JWT_EXPIRY_HOURS=24

# Consensus Settings
CONSENSUS_MIN_CONFIRMATIONS=1
CONSENSUS_QUORUM_PERCENT=0.67
CONSENSUS_TIMEOUT=60
CONSENSUS_ALLOW_PENDING=true

# Chunk & Replication
CHUNK_SIZE=262144  # 256KB
REPLICATION=3

# Node Settings
NODE_HEARTBEAT_INTERVAL=15
NODE_TTL=60

# Logging
LOG_LEVEL=INFO
```

## Step 2: Add PostgreSQL Database

### Using Railway Dashboard

1. Open your Railway project
2. Click "New" → "Database" → "Add PostgreSQL"
3. Railway automatically:
   - Provisions a PostgreSQL instance
   - Sets the `DATABASE_URL` environment variable
   - Connects it to your service

### Verify Database Connection

After adding PostgreSQL, your app will automatically use it because:
- `config.py` reads `DATABASE_URL` environment variable
- SQLAlchemy in `backend/models.py` uses this URL
- Database tables are auto-created on first run via `init_db()`

## Step 3: Deploy

### Automatic Deployment

Railway automatically deploys when you:
1. Push to the main branch (if connected to GitHub)
2. Manually trigger deployment via Dashboard
3. Change environment variables (triggers redeploy)

### Verify Deployment

Check health endpoint:
```bash
curl https://your-app.railway.app/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "backend",
  "timestamp": 1234567890
}
```

## Step 4: Database Migrations

### Initial Setup

On first deployment, tables are auto-created by `init_db()` in `backend/models.py`:
- `users` table (authentication)
- Other tables as defined in models

### Manual Migrations (if needed)

Connect to Railway PostgreSQL:
```bash
# Get DATABASE_URL from Railway dashboard
railway connect

# Or use psql directly
psql $DATABASE_URL
```

## Step 5: Monitoring

### Railway Logs

View real-time logs:
```bash
railway logs
```

### Application Metrics

Railway Dashboard shows:
- CPU usage
- Memory usage
- Request metrics
- Deployment history

## Consensus Configuration

### Single Node Testing
```env
CONSENSUS_MIN_CONFIRMATIONS=1
CONSENSUS_ALLOW_PENDING=true
```

### Production Multi-Node
```env
CONSENSUS_MIN_CONFIRMATIONS=2
CONSENSUS_QUORUM_PERCENT=0.67
CONSENSUS_ALLOW_PENDING=false
CONSENSUS_TIMEOUT=60
```

## Security Checklist

- [ ] SECRET_KEY is set (64 character hex string)
- [ ] DATABASE_URL is using PostgreSQL (not SQLite)
- [ ] ALLOWED_ORIGINS is configured for your domain
- [ ] SSL/TLS is enabled (Railway does this automatically)
- [ ] Environment variables are not committed to git

## Troubleshooting

### Issue: "SECRET_KEY not set in production" Warning

**Solution:** Add SECRET_KEY environment variable in Railway dashboard

### Issue: Database connection failed

**Solution:**
1. Verify PostgreSQL addon is added
2. Check DATABASE_URL is set
3. Check Railway PostgreSQL service is running

### Issue: Health check timeout

**Solution:**
1. Increase `healthcheckTimeout` in `railway.json`
2. Check application logs for startup errors
3. Verify port 5000 is exposed in Dockerfile

### Issue: JWT tokens invalidate on restart

**Cause:** SECRET_KEY is not persistent (regenerated each restart)

**Solution:** Set SECRET_KEY environment variable (see Step 1)

## Advanced: Multi-Region Deployment

For high availability:
1. Deploy multiple Railway services in different regions
2. Use Railway's load balancer
3. Configure shared PostgreSQL database
4. Set up consensus with distributed nodes

## Next Steps

1. Set up custom domain in Railway
2. Configure CDN for static assets
3. Enable automatic backups for PostgreSQL
4. Set up monitoring/alerting (Railway + external service)
5. Implement rate limiting
6. Add Redis for session storage (optional)

## Support

- Railway Docs: https://docs.railway.app
- PostgreSQL Docs: https://www.postgresql.org/docs/
- DecentraStore Issues: [Your GitHub repo]
