# Cloud Deployment Guide

Deploy DecentraStore to make it publicly accessible so anyone can become a node.

## Quick Comparison

| Platform | Cost | Setup Time | Persistent Storage | Best For |
|----------|------|------------|-------------------|----------|
| **Railway** | Free tier, ~$5/mo | 5 min | ✅ Yes | Easiest setup |
| **Render** | Free tier | 5 min | ✅ Yes (paid) | Free hosting |
| **Fly.io** | Free tier | 10 min | ✅ Yes | Global distribution |
| **DigitalOcean** | $5/mo | 15 min | ✅ Yes | Full control |

---

## Option 1: Railway (Recommended - Easiest)

### Step 1: Create Account
Go to [railway.app](https://railway.app) and sign up with GitHub.

### Step 2: Deploy
```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Initialize project
cd decentra-store
railway init

# Deploy
railway up
```

### Step 3: Get Your URL
After deployment, Railway gives you a URL like:
```
https://decentra-store-production.up.railway.app
```

### Step 4: Set Environment Variables
In Railway dashboard, add:
```
DISCOVERY_URL=https://YOUR_RAILWAY_URL:4000
```

---

## Option 2: Render (Good Free Tier)

### Step 1: Create Account
Go to [render.com](https://render.com) and sign up.

### Step 2: Connect Repository
1. Push your code to GitHub
2. In Render dashboard, click "New" → "Web Service"
3. Connect your GitHub repo

### Step 3: Configure
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `python server.py`
- **Add Disk:** Mount at `/app/data` (for persistent storage)

### Step 4: Deploy
Click "Create Web Service" and wait for deployment.

Your URL will be:
```
https://decentrastore.onrender.com
```

---

## Option 3: Fly.io (Global Edge)

### Step 1: Install CLI
```bash
# macOS
brew install flyctl

# Windows
powershell -Command "iwr https://fly.io/install.ps1 -useb | iex"

# Linux
curl -L https://fly.io/install.sh | sh
```

### Step 2: Login & Initialize
```bash
fly auth login
cd decentra-store
fly launch
```

### Step 3: Create fly.toml
```toml
app = "decentrastore"
primary_region = "sjc"

[build]
  builder = "paketobuildpacks/builder:base"

[env]
  PORT = "8080"
  DISCOVERY_PORT = "4000"

[http_service]
  internal_port = 8080
  force_https = true

[mounts]
  source = "decentra_data"
  destination = "/app/data"
```

### Step 4: Deploy
```bash
fly deploy
```

---

## Option 4: DigitalOcean Droplet (Full Control)

### Step 1: Create Droplet
1. Go to [digitalocean.com](https://digitalocean.com)
2. Create Droplet → Ubuntu 22.04 → $5/mo Basic

### Step 2: Connect via SSH
```bash
ssh root@YOUR_DROPLET_IP
```

### Step 3: Install Dependencies
```bash
apt update
apt install python3 python3-pip python3-venv git -y
```

### Step 4: Clone and Setup
```bash
cd /opt
git clone https://github.com/YOUR_USERNAME/decentra-store.git
cd decentra-store

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Step 5: Create Systemd Service
```bash
cat > /etc/systemd/system/decentrastore.service << 'EOF'
[Unit]
Description=DecentraStore Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/decentra-store
Environment=PATH=/opt/decentra-store/venv/bin
ExecStart=/opt/decentra-store/venv/bin/python server.py --port 5000
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable decentrastore
systemctl start decentrastore
```

### Step 6: Setup Nginx (Optional - for HTTPS)
```bash
apt install nginx certbot python3-certbot-nginx -y

cat > /etc/nginx/sites-available/decentrastore << 'EOF'
server {
    listen 80;
    server_name YOUR_DOMAIN.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    
    location /discovery/ {
        proxy_pass http://127.0.0.1:4000/;
        proxy_set_header Host $host;
    }
}
EOF

ln -s /etc/nginx/sites-available/decentrastore /etc/nginx/sites-enabled/
nginx -t
systemctl restart nginx

# Get SSL certificate
certbot --nginx -d YOUR_DOMAIN.com
```

---

## After Deployment

### 1. Get Your Public URL
Your deployment will give you a URL like:
- Railway: `https://xxx.up.railway.app`
- Render: `https://xxx.onrender.com`
- Fly.io: `https://xxx.fly.dev`
- DigitalOcean: `http://YOUR_IP:5000` or your domain

### 2. Test It
```bash
# Check backend
curl https://YOUR_URL/health

# Check discovery
curl https://YOUR_URL:4000/health  # May need different port handling
```

### 3. Share With Users
Users can now:
1. Visit `https://YOUR_URL`
2. Create an account
3. Upload/download files
4. Go to "Become a Node" tab
5. Download node package
6. Run node on their computer

### 4. Discovery URL for Nodes
The discovery URL users need is typically:
```
http://YOUR_SERVER_IP:4000
```

For platforms with single port, you may need to:
- Use the combined server (both on same port with different paths)
- Or deploy discovery as a separate service

---

## Troubleshooting

### "Port already in use"
Change the port in environment variables or command line.

### "Cannot connect to discovery"
Make sure the discovery service is running and the URL is correct.

### "Database locked"
SQLite doesn't handle high concurrency well. For production, consider PostgreSQL.

### Nodes can't connect
- Check firewall allows inbound connections
- Verify the discovery URL is publicly accessible
- Make sure port 4000 is exposed

---

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | 5000 | Backend server port |
| `DISCOVERY_PORT` | 4000 | Discovery service port |
| `DISCOVERY_URL` | http://localhost:4000 | URL for backend to reach discovery |
| `SECRET_KEY` | (random) | Flask session secret |
| `DATABASE_URL` | sqlite:///data/users.db | User database |
| `REPLICATION` | 3 | Chunk replication factor |
