# Production Deployment Guide

This guide covers deploying DecentraStore across **physical machines** in a real network.

## Architecture Overview

```
                    Internet / LAN
                         │
         ┌───────────────┼───────────────┐
         │               │               │
         ▼               ▼               ▼
   ┌──────────┐   ┌──────────┐   ┌──────────────┐
   │ Discovery│   │ Backend  │   │ Storage Nodes│
   │ Server   │   │ Server   │   │ (N machines) │
   │ (1 host) │   │ (1 host) │   │              │
   └──────────┘   └──────────┘   └──────────────┘
       :4000         :5000          :6001 each
```

## Step 1: Prepare Machines

You need at minimum:
- **1 machine** for Discovery Service
- **1 machine** for Backend Server  
- **3+ machines** for Storage Nodes (for replication factor 3)

All machines need:
- Python 3.8+
- Network connectivity to each other
- Open firewall ports (4000, 5000, 6001)

## Step 2: Install on All Machines

On each machine:

```bash
# Clone or copy the project
git clone <your-repo> decentra-store
cd decentra-store

# Install dependencies
pip install -r requirements.txt
```

## Step 3: Start Discovery Service

On your **Discovery Server** (e.g., 192.168.1.100):

```bash
cd decentra-store

# Start discovery service
python -m discovery.server \
    --host 0.0.0.0 \
    --port 4000

# Or use the helper script
./scripts/deploy.sh discovery 0.0.0.0 4000
```

**Verify it's running:**
```bash
curl http://192.168.1.100:4000/health
# Should return: {"status": "healthy", ...}
```

## Step 4: Start Storage Nodes

On each **Storage Node** machine (e.g., 192.168.1.101, 192.168.1.102, 192.168.1.103):

```bash
cd decentra-store

# Replace DISCOVERY_IP with your discovery server's IP
DISCOVERY_IP=192.168.1.100

# Start storage node
python -m node.storage_node \
    --host 0.0.0.0 \
    --port 6001 \
    --discovery http://$DISCOVERY_IP:4000 \
    --storage-dir /var/decentra-store/chunks \
    --node-id "node-$(hostname)"
```

**Configure storage location:**
```bash
# Create dedicated storage directory with proper permissions
sudo mkdir -p /var/decentra-store/chunks
sudo chown $USER:$USER /var/decentra-store/chunks
```

**Verify nodes are registered:**
```bash
curl http://192.168.1.100:4000/peers
# Should list all your storage nodes
```

## Step 5: Start Backend Server

On your **Backend Server** (e.g., 192.168.1.105):

```bash
cd decentra-store

DISCOVERY_IP=192.168.1.100

# Start backend server
DISCOVERY_URL=http://$DISCOVERY_IP:4000 \
python -m backend.app \
    --host 0.0.0.0 \
    --port 5000
```

**Verify it's running:**
```bash
curl http://192.168.1.105:5000/health
curl http://192.168.1.105:5000/network/peers
```

## Step 6: Access the Web UI

Open in browser: `http://192.168.1.105:5000`

1. Click "Get Started" to create an account
2. Upload a file
3. The file will be encrypted, chunked, and distributed to your storage nodes

## Running as System Services

### Using systemd (Linux)

**Discovery Service** (`/etc/systemd/system/decentra-discovery.service`):
```ini
[Unit]
Description=DecentraStore Discovery Service
After=network.target

[Service]
Type=simple
User=decentra
WorkingDirectory=/opt/decentra-store
ExecStart=/usr/bin/python3 -m discovery.server --host 0.0.0.0 --port 4000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

**Storage Node** (`/etc/systemd/system/decentra-node.service`):
```ini
[Unit]
Description=DecentraStore Storage Node
After=network.target

[Service]
Type=simple
User=decentra
WorkingDirectory=/opt/decentra-store
Environment=DISCOVERY_URL=http://192.168.1.100:4000
ExecStart=/usr/bin/python3 -m node.storage_node --host 0.0.0.0 --port 6001 --storage-dir /var/decentra-store/chunks
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

**Backend Server** (`/etc/systemd/system/decentra-backend.service`):
```ini
[Unit]
Description=DecentraStore Backend Server
After=network.target

[Service]
Type=simple
User=decentra
WorkingDirectory=/opt/decentra-store
Environment=DISCOVERY_URL=http://192.168.1.100:4000
ExecStart=/usr/bin/python3 -m backend.app --host 0.0.0.0 --port 5000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

**Enable and start:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable decentra-discovery
sudo systemctl start decentra-discovery
```

## Firewall Configuration

### UFW (Ubuntu)
```bash
# Discovery server
sudo ufw allow 4000/tcp

# Backend server  
sudo ufw allow 5000/tcp

# Storage nodes
sudo ufw allow 6001/tcp
```

### iptables
```bash
# Discovery server
iptables -A INPUT -p tcp --dport 4000 -j ACCEPT

# Backend server
iptables -A INPUT -p tcp --dport 5000 -j ACCEPT

# Storage nodes
iptables -A INPUT -p tcp --dport 6001 -j ACCEPT
```

## Network Topology Options

### Option A: All on Same LAN
```
192.168.1.100 - Discovery
192.168.1.101 - Backend
192.168.1.102 - Node 1
192.168.1.103 - Node 2
192.168.1.104 - Node 3
```

### Option B: Cloud + Home Nodes
```
Cloud VPS (public IP):
  - Discovery Service
  - Backend Server

Home machines (behind NAT):
  - Storage Nodes (need port forwarding or VPN)
```

### Option C: Fully Distributed
```
Each participant runs:
  - Storage Node locally
  
Central infrastructure:
  - Discovery + Backend on cloud VPS
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DISCOVERY_URL` | `http://localhost:4000` | Discovery service URL |
| `REPLICATION` | `3` | Copies of each chunk |
| `CHUNK_SIZE` | `262144` | Chunk size (256KB) |
| `NODE_TTL` | `60` | Seconds before node considered dead |
| `NODE_HEARTBEAT_INTERVAL` | `15` | Heartbeat frequency |
| `SECRET_KEY` | (random) | Flask secret key |
| `LOG_LEVEL` | `INFO` | Logging level |

## Security Considerations

### For Production

1. **Use HTTPS** - Put nginx/caddy in front with SSL certificates
2. **Secure Discovery** - Consider authentication for node registration
3. **Firewall** - Only allow necessary ports
4. **Private Network** - Use VPN for node communication
5. **Backup** - Backup the blockchain.json and user database

### Example nginx config for HTTPS:
```nginx
server {
    listen 443 ssl;
    server_name decentra.example.com;
    
    ssl_certificate /etc/letsencrypt/live/decentra.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/decentra.example.com/privkey.pem;
    
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Monitoring

### Check service health:
```bash
# Discovery
curl http://DISCOVERY_IP:4000/health
curl http://DISCOVERY_IP:4000/stats

# Backend
curl http://BACKEND_IP:5000/health
curl http://BACKEND_IP:5000/network/peers
curl http://BACKEND_IP:5000/blockchain/stats

# Storage node
curl http://NODE_IP:6001/health
curl http://NODE_IP:6001/stats
```

### Log monitoring:
```bash
# Follow logs
journalctl -u decentra-backend -f

# View recent errors
journalctl -u decentra-node --since "1 hour ago" -p err
```

## Troubleshooting

### Node not appearing in discovery
1. Check firewall allows port 4000 outbound
2. Verify discovery URL is correct
3. Check node logs for registration errors

### File upload fails
1. Verify at least 3 nodes are active (for replication=3)
2. Check backend can reach nodes (curl node health endpoints)
3. Check disk space on nodes

### Download fails
1. Verify you're using the correct password
2. Check that original nodes are still online
3. Verify blockchain has the file metadata

## Scaling

### Adding more storage nodes
Simply start more nodes pointing to the same discovery service. They will automatically join the network.

### High availability
- Run multiple discovery services behind a load balancer
- Run multiple backend servers behind a load balancer
- Increase replication factor for better data durability
