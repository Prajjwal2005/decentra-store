# discovery/server.py
"""
Discovery Service for DecentraStore.

Central registry where storage nodes register and maintain presence.
Clients (backend servers) query for available peers.

Endpoints:
- POST /register   - Node joins network
- POST /heartbeat  - Node maintains presence
- GET  /peers      - Get list of active nodes
- GET  /peer/<id>  - Get specific node info
- GET  /health     - Service health check
- GET  /stats      - Network statistics
"""

import time
import threading
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import NODE_TTL

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [discovery] %(levelname)s: %(message)s"
)
LOG = logging.getLogger("discovery")

app = Flask(__name__)
CORS(app)

# In-memory peer registry
# node_id -> { node_id, ip, port, public_ip, capacity, last_heartbeat, registered_at, meta }
PEERS = {}
LOCK = threading.Lock()
TTL = NODE_TTL  # seconds before marking node as dead


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy", "service": "discovery", "timestamp": int(time.time())})


@app.route("/register", methods=["POST"])
def register():
    """
    Register a new storage node.
    
    Expected JSON:
    {
        "node_id": "unique-node-identifier",
        "ip": "internal-ip-address",
        "port": 6001,
        "public_ip": "optional-public-ip",  # For NAT traversal
        "capacity_gb": 100,  # Storage capacity
        "meta": { ... }  # Optional metadata
    }
    """
    data = request.get_json(force=True)
    
    node_id = data.get("node_id")
    ip = data.get("ip")
    port = data.get("port")
    
    if not all([node_id, ip, port]):
        return jsonify({"error": "node_id, ip, and port are required"}), 400
    
    try:
        port = int(port)
    except (ValueError, TypeError):
        return jsonify({"error": "port must be an integer"}), 400
    
    now = time.time()
    
    with LOCK:
        is_new = node_id not in PEERS
        
        PEERS[node_id] = {
            "node_id": node_id,
            "ip": ip,
            "port": port,
            "public_ip": data.get("public_ip", ip),
            "capacity_gb": data.get("capacity_gb", 0),
            "meta": data.get("meta", {}),
            "last_heartbeat": now,
            "registered_at": PEERS.get(node_id, {}).get("registered_at", now),
            "status": "active",
        }
    
    action = "registered" if is_new else "re-registered"
    LOG.info(f"Node {action}: {node_id} at {ip}:{port}")
    
    return jsonify({
        "status": action,
        "node_id": node_id,
        "ttl_seconds": TTL,
    })


@app.route("/heartbeat", methods=["POST"])
def heartbeat():
    """
    Node heartbeat to maintain presence.
    
    Expected JSON:
    {
        "node_id": "node-identifier",
        "ip": "current-ip",  # Optional, for IP change detection
        "port": 6001,        # Optional
        "stats": { ... }     # Optional runtime stats
    }
    """
    data = request.get_json(force=True)
    node_id = data.get("node_id")
    
    if not node_id:
        return jsonify({"error": "node_id is required"}), 400
    
    with LOCK:
        if node_id not in PEERS:
            return jsonify({"error": "not registered", "action": "register"}), 404
        
        peer = PEERS[node_id]
        peer["last_heartbeat"] = time.time()
        peer["status"] = "active"
        
        # Update optional fields if provided
        if "ip" in data:
            peer["ip"] = data["ip"]
        if "port" in data:
            peer["port"] = int(data["port"])
        if "public_ip" in data:
            peer["public_ip"] = data["public_ip"]
        if "stats" in data:
            peer["stats"] = data["stats"]
        if "meta" in data:
            peer["meta"].update(data["meta"])
    
    return jsonify({"status": "ok", "ttl_seconds": TTL})


@app.route("/unregister", methods=["POST"])
def unregister():
    """
    Gracefully unregister a node (e.g., during shutdown).
    """
    data = request.get_json(force=True)
    node_id = data.get("node_id")
    
    if not node_id:
        return jsonify({"error": "node_id is required"}), 400
    
    with LOCK:
        if node_id in PEERS:
            del PEERS[node_id]
            LOG.info(f"Node unregistered: {node_id}")
            return jsonify({"status": "unregistered"})
    
    return jsonify({"status": "not_found"}), 404


@app.route("/peers", methods=["GET"])
def get_peers():
    """
    Get list of active peers.
    
    Query params:
    - limit: Max number of peers (default 50)
    - min_capacity: Minimum capacity in GB
    """
    limit = int(request.args.get("limit", 50))
    min_capacity = float(request.args.get("min_capacity", 0))
    
    with LOCK:
        now = time.time()
        alive = []
        
        for peer in PEERS.values():
            # Check if still alive
            if (now - peer["last_heartbeat"]) > TTL:
                continue
            
            # Check capacity filter
            if peer.get("capacity_gb", 0) < min_capacity:
                continue
            
            alive.append({
                "node_id": peer["node_id"],
                "ip": peer["ip"],
                "port": peer["port"],
                "public_ip": peer.get("public_ip", peer["ip"]),
                "capacity_gb": peer.get("capacity_gb", 0),
                "meta": peer.get("meta", {}),
                "last_heartbeat": peer["last_heartbeat"],
            })
        
        # Sort by most recent heartbeat
        alive.sort(key=lambda x: x["last_heartbeat"], reverse=True)
    
    return jsonify({
        "peers": alive[:limit],
        "total_active": len(alive),
    })


@app.route("/peer/<node_id>", methods=["GET"])
def get_peer(node_id):
    """Get info for a specific peer."""
    with LOCK:
        peer = PEERS.get(node_id)
        
        if not peer:
            return jsonify({"error": "not found"}), 404
        
        now = time.time()
        is_alive = (now - peer["last_heartbeat"]) <= TTL
        
        return jsonify({
            **peer,
            "is_alive": is_alive,
        })


@app.route("/stats", methods=["GET"])
def stats():
    """Get network statistics."""
    with LOCK:
        now = time.time()
        
        total = len(PEERS)
        alive = sum(1 for p in PEERS.values() if (now - p["last_heartbeat"]) <= TTL)
        total_capacity = sum(p.get("capacity_gb", 0) for p in PEERS.values() if (now - p["last_heartbeat"]) <= TTL)
        
    return jsonify({
        "total_nodes": total,
        "active_nodes": alive,
        "dead_nodes": total - alive,
        "total_capacity_gb": total_capacity,
        "ttl_seconds": TTL,
        "timestamp": int(time.time()),
    })


def reaper_thread():
    """
    Background thread that cleans up dead peers.
    Runs periodically to remove nodes that haven't sent heartbeat.
    """
    while True:
        time.sleep(max(10, TTL // 3))
        
        with LOCK:
            now = time.time()
            dead = [
                node_id for node_id, peer in PEERS.items()
                if (now - peer["last_heartbeat"]) > TTL * 2  # Grace period
            ]
            
            for node_id in dead:
                LOG.info(f"Reaping dead node: {node_id}")
                del PEERS[node_id]


def start_server(host: str = "0.0.0.0", port: int = 4000, debug: bool = False):
    """Start the discovery service."""
    # Start reaper thread
    reaper = threading.Thread(target=reaper_thread, daemon=True)
    reaper.start()
    
    LOG.info(f"Starting discovery service on {host}:{port}")
    LOG.info(f"Node TTL: {TTL} seconds")
    
    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="DecentraStore Discovery Service")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    parser.add_argument("--port", type=int, default=4000, help="Bind port")
    parser.add_argument("--debug", action="store_true", help="Debug mode")
    
    args = parser.parse_args()
    start_server(host=args.host, port=args.port, debug=args.debug)
