# node/storage_node.py
"""
Storage Node for DecentraStore P2P Network.

This is the software that peers run to participate in the network.
It receives encrypted chunks, stores them locally, and serves them on request.

Features:
- Stores encrypted chunks (node never sees plaintext)
- Auto-registers with discovery service
- Periodic heartbeat to maintain presence
- Health monitoring and statistics
- Graceful shutdown with unregistration

Endpoints:
- POST /store           - Receive and store a chunk
- GET  /retrieve/<hash> - Serve a chunk by hash
- GET  /health          - Node health check
- GET  /stats           - Storage statistics
- DELETE /chunk/<hash>  - Delete a chunk (admin only)
"""

import os
import time
import uuid
import hashlib
import threading
import signal
import logging
from pathlib import Path
from typing import Optional

import requests
from flask import Flask, request, jsonify, send_file, abort
from flask_cors import CORS

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    DISCOVERY_URL,
    NODE_HEARTBEAT_INTERVAL,
    get_node_storage_dir,
    PEER_TIMEOUT,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [node] %(levelname)s: %(message)s"
)
LOG = logging.getLogger("storage_node")

app = Flask(__name__)
CORS(app)

# Node configuration (set at startup)
NODE_ID: str = None
NODE_IP: str = None
NODE_PORT: int = None
STORAGE_DIR: Path = None
DISCOVERY: str = None

# Runtime stats
STATS = {
    "chunks_stored": 0,
    "chunks_served": 0,
    "bytes_stored": 0,
    "bytes_served": 0,
    "started_at": None,
    "last_heartbeat": None,
}

# Shutdown flag
SHUTDOWN_EVENT = threading.Event()


def get_external_ip() -> str:
    """Try to determine external IP address."""
    services = [
        "https://api.ipify.org",
        "https://icanhazip.com",
        "https://ifconfig.me/ip",
    ]
    
    for svc in services:
        try:
            resp = requests.get(svc, timeout=5)
            if resp.status_code == 200:
                return resp.text.strip()
        except Exception:
            continue
    
    return None


def compute_chunk_hash(data: bytes) -> str:
    """Compute SHA-256 hash of chunk data."""
    return hashlib.sha256(data).hexdigest()


def get_chunk_path(chunk_hash: str) -> Path:
    """Get file path for a chunk (uses subdirectories for performance)."""
    # Use first 2 chars as subdirectory to avoid too many files in one dir
    subdir = chunk_hash[:2]
    chunk_dir = STORAGE_DIR / subdir
    chunk_dir.mkdir(parents=True, exist_ok=True)
    return chunk_dir / f"{chunk_hash}.chunk"


def register_with_discovery():
    """Register this node with the discovery service."""
    if not DISCOVERY:
        LOG.warning("No discovery URL configured, running in standalone mode")
        return False
    
    try:
        external_ip = get_external_ip()
        
        payload = {
            "node_id": NODE_ID,
            "ip": NODE_IP,
            "port": NODE_PORT,
            "public_ip": external_ip or NODE_IP,
            "capacity_gb": get_storage_capacity_gb(),
            "meta": {
                "version": "1.0.0",
                "started_at": STATS["started_at"],
            }
        }
        
        resp = requests.post(
            f"{DISCOVERY}/register",
            json=payload,
            timeout=PEER_TIMEOUT
        )
        
        if resp.status_code == 200:
            data = resp.json()
            LOG.info(f"Registered with discovery: {data.get('status')}")
            return True
        else:
            LOG.error(f"Registration failed: {resp.status_code} - {resp.text}")
            return False
            
    except Exception as e:
        LOG.error(f"Failed to register with discovery: {e}")
        return False


def heartbeat_thread():
    """Background thread for periodic heartbeat."""
    while not SHUTDOWN_EVENT.is_set():
        try:
            send_heartbeat()
        except Exception as e:
            LOG.error(f"Heartbeat error: {e}")
        
        # Wait with checking shutdown flag
        SHUTDOWN_EVENT.wait(timeout=NODE_HEARTBEAT_INTERVAL)


def send_heartbeat():
    """Send heartbeat to discovery service."""
    if not DISCOVERY:
        return
    
    try:
        payload = {
            "node_id": NODE_ID,
            "ip": NODE_IP,
            "port": NODE_PORT,
            "stats": {
                "chunks_stored": STATS["chunks_stored"],
                "bytes_stored": STATS["bytes_stored"],
                "uptime_seconds": int(time.time() - STATS["started_at"]) if STATS["started_at"] else 0,
            }
        }
        
        resp = requests.post(
            f"{DISCOVERY}/heartbeat",
            json=payload,
            timeout=PEER_TIMEOUT
        )
        
        if resp.status_code == 200:
            STATS["last_heartbeat"] = time.time()
        elif resp.status_code == 404:
            # Not registered, re-register
            LOG.warning("Node not registered, re-registering...")
            register_with_discovery()
        else:
            LOG.warning(f"Heartbeat failed: {resp.status_code}")
            
    except Exception as e:
        LOG.error(f"Heartbeat failed: {e}")


def unregister_from_discovery():
    """Gracefully unregister from discovery service."""
    if not DISCOVERY:
        return
    
    try:
        resp = requests.post(
            f"{DISCOVERY}/unregister",
            json={"node_id": NODE_ID},
            timeout=5
        )
        if resp.status_code == 200:
            LOG.info("Unregistered from discovery")
    except Exception as e:
        LOG.warning(f"Failed to unregister: {e}")


def get_storage_capacity_gb() -> float:
    """Get available storage capacity in GB."""
    try:
        stat = os.statvfs(STORAGE_DIR)
        free_bytes = stat.f_bavail * stat.f_frsize
        return round(free_bytes / (1024**3), 2)
    except Exception:
        return 0


def count_stored_chunks() -> tuple:
    """Count stored chunks and total bytes."""
    count = 0
    total_bytes = 0
    
    try:
        for subdir in STORAGE_DIR.iterdir():
            if subdir.is_dir():
                for chunk_file in subdir.glob("*.chunk"):
                    count += 1
                    total_bytes += chunk_file.stat().st_size
    except Exception:
        pass
    
    return count, total_bytes


# =============================================================================
# API Endpoints
# =============================================================================

@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "node_id": NODE_ID,
        "timestamp": int(time.time()),
    })


@app.route("/stats", methods=["GET"])
def stats():
    """Get node statistics."""
    chunk_count, total_bytes = count_stored_chunks()
    
    return jsonify({
        "node_id": NODE_ID,
        "ip": NODE_IP,
        "port": NODE_PORT,
        "discovery": DISCOVERY,
        "storage_dir": str(STORAGE_DIR),
        "capacity_gb": get_storage_capacity_gb(),
        "chunks_stored": chunk_count,
        "bytes_stored": total_bytes,
        "chunks_served": STATS["chunks_served"],
        "bytes_served": STATS["bytes_served"],
        "started_at": STATS["started_at"],
        "uptime_seconds": int(time.time() - STATS["started_at"]) if STATS["started_at"] else 0,
        "last_heartbeat": STATS["last_heartbeat"],
    })


@app.route("/store", methods=["POST"])
def store_chunk():
    """
    Store an encrypted chunk.
    
    Expects multipart form with:
    - file: The chunk binary data
    - chunk_hash: Expected SHA-256 hash (for verification)
    
    Or JSON with:
    - data: Base64-encoded chunk data
    - chunk_hash: Expected SHA-256 hash
    """
    chunk_data = None
    expected_hash = None
    
    # Handle multipart file upload
    if "file" in request.files:
        file = request.files["file"]
        chunk_data = file.read()
        expected_hash = request.form.get("chunk_hash") or request.form.get("file_hash")
    
    # Handle JSON payload
    elif request.is_json:
        import base64
        json_data = request.get_json()
        if "data" in json_data:
            chunk_data = base64.b64decode(json_data["data"])
        expected_hash = json_data.get("chunk_hash")
    
    if not chunk_data:
        return jsonify({"error": "No chunk data provided"}), 400
    
    # Compute actual hash
    actual_hash = compute_chunk_hash(chunk_data)
    
    # Verify hash if provided
    if expected_hash and actual_hash != expected_hash.lower():
        LOG.warning(f"Hash mismatch: expected {expected_hash}, got {actual_hash}")
        return jsonify({
            "error": "hash_mismatch",
            "expected": expected_hash,
            "actual": actual_hash
        }), 400
    
    # Store chunk
    chunk_path = get_chunk_path(actual_hash)
    
    # Check if already exists
    if chunk_path.exists():
        LOG.debug(f"Chunk already exists: {actual_hash[:16]}...")
        return jsonify({
            "status": "exists",
            "chunk_hash": actual_hash,
            "node_id": NODE_ID,
            "size": len(chunk_data),
        })
    
    # Write chunk
    try:
        with open(chunk_path, "wb") as f:
            f.write(chunk_data)
        
        STATS["chunks_stored"] += 1
        STATS["bytes_stored"] += len(chunk_data)
        
        LOG.info(f"Stored chunk: {actual_hash[:16]}... ({len(chunk_data)} bytes)")
        
        return jsonify({
            "status": "stored",
            "chunk_hash": actual_hash,
            "node_id": NODE_ID,
            "size": len(chunk_data),
        })
        
    except Exception as e:
        LOG.error(f"Failed to store chunk: {e}")
        return jsonify({"error": f"Storage failed: {e}"}), 500


@app.route("/retrieve/<chunk_hash>", methods=["GET"])
def retrieve_chunk(chunk_hash: str):
    """
    Retrieve a chunk by its hash.
    Returns the raw binary data.
    """
    chunk_hash = chunk_hash.lower()
    
    # Validate hash format
    if len(chunk_hash) != 64 or not all(c in "0123456789abcdef" for c in chunk_hash):
        return jsonify({"error": "Invalid hash format"}), 400
    
    chunk_path = get_chunk_path(chunk_hash)
    
    if not chunk_path.exists():
        LOG.debug(f"Chunk not found: {chunk_hash[:16]}...")
        return jsonify({"error": "Chunk not found"}), 404
    
    try:
        # Read and verify
        with open(chunk_path, "rb") as f:
            data = f.read()
        
        # Verify hash
        actual_hash = compute_chunk_hash(data)
        if actual_hash != chunk_hash:
            LOG.error(f"Stored chunk corrupted: {chunk_hash[:16]}...")
            return jsonify({"error": "Chunk corrupted"}), 500
        
        STATS["chunks_served"] += 1
        STATS["bytes_served"] += len(data)
        
        LOG.debug(f"Served chunk: {chunk_hash[:16]}... ({len(data)} bytes)")
        
        return send_file(
            chunk_path,
            mimetype="application/octet-stream",
            as_attachment=True,
            download_name=f"{chunk_hash}.chunk"
        )
        
    except Exception as e:
        LOG.error(f"Failed to retrieve chunk: {e}")
        return jsonify({"error": f"Retrieval failed: {e}"}), 500


@app.route("/exists/<chunk_hash>", methods=["GET"])
def chunk_exists(chunk_hash: str):
    """Check if a chunk exists on this node."""
    chunk_hash = chunk_hash.lower()
    chunk_path = get_chunk_path(chunk_hash)
    
    exists = chunk_path.exists()
    size = chunk_path.stat().st_size if exists else 0
    
    return jsonify({
        "exists": exists,
        "chunk_hash": chunk_hash,
        "size": size,
        "node_id": NODE_ID,
    })


@app.route("/chunk/<chunk_hash>", methods=["DELETE"])
def delete_chunk(chunk_hash: str):
    """
    Delete a chunk (admin operation).
    In production, this should be protected.
    """
    # TODO: Add authentication for admin operations
    
    chunk_hash = chunk_hash.lower()
    chunk_path = get_chunk_path(chunk_hash)
    
    if not chunk_path.exists():
        return jsonify({"error": "Chunk not found"}), 404
    
    try:
        size = chunk_path.stat().st_size
        chunk_path.unlink()
        
        LOG.info(f"Deleted chunk: {chunk_hash[:16]}...")
        
        return jsonify({
            "status": "deleted",
            "chunk_hash": chunk_hash,
            "size": size,
        })
        
    except Exception as e:
        LOG.error(f"Failed to delete chunk: {e}")
        return jsonify({"error": f"Deletion failed: {e}"}), 500


@app.route("/chunks", methods=["GET"])
def list_chunks():
    """
    List all stored chunks (for debugging/admin).
    Returns summary only, not full list for large stores.
    """
    limit = int(request.args.get("limit", 100))
    
    chunks = []
    total_count = 0
    total_bytes = 0
    
    try:
        for subdir in sorted(STORAGE_DIR.iterdir()):
            if subdir.is_dir():
                for chunk_file in sorted(subdir.glob("*.chunk")):
                    total_count += 1
                    size = chunk_file.stat().st_size
                    total_bytes += size
                    
                    if len(chunks) < limit:
                        chunks.append({
                            "hash": chunk_file.stem,
                            "size": size,
                        })
    except Exception as e:
        LOG.error(f"Failed to list chunks: {e}")
    
    return jsonify({
        "chunks": chunks,
        "total_count": total_count,
        "total_bytes": total_bytes,
        "showing": len(chunks),
    })


# =============================================================================
# Startup and Shutdown
# =============================================================================

def graceful_shutdown(signum, frame):
    """Handle shutdown signals."""
    LOG.info("Received shutdown signal, cleaning up...")
    SHUTDOWN_EVENT.set()
    unregister_from_discovery()
    LOG.info("Shutdown complete")
    sys.exit(0)


def start_node(
    host: str = "0.0.0.0",
    port: int = 6001,
    discovery_url: str = None,
    storage_dir: str = None,
    node_id: str = None,
    debug: bool = False
):
    """Start the storage node."""
    global NODE_ID, NODE_IP, NODE_PORT, STORAGE_DIR, DISCOVERY
    
    # Generate node ID if not provided
    NODE_ID = node_id or f"node-{uuid.uuid4().hex[:8]}"
    NODE_IP = host if host != "0.0.0.0" else "127.0.0.1"
    NODE_PORT = port
    DISCOVERY = discovery_url or DISCOVERY_URL
    
    # Setup storage directory
    if storage_dir:
        STORAGE_DIR = Path(storage_dir)
    else:
        STORAGE_DIR = get_node_storage_dir(NODE_ID)
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    
    # Initialize stats
    STATS["started_at"] = time.time()
    chunk_count, total_bytes = count_stored_chunks()
    STATS["chunks_stored"] = chunk_count
    STATS["bytes_stored"] = total_bytes
    
    LOG.info(f"Starting storage node: {NODE_ID}")
    LOG.info(f"  IP: {NODE_IP}:{NODE_PORT}")
    LOG.info(f"  Storage: {STORAGE_DIR}")
    LOG.info(f"  Discovery: {DISCOVERY or '(none)'}")
    LOG.info(f"  Existing chunks: {chunk_count}")
    
    # Register signal handlers
    signal.signal(signal.SIGINT, graceful_shutdown)
    signal.signal(signal.SIGTERM, graceful_shutdown)
    
    # Register with discovery
    if DISCOVERY:
        register_with_discovery()
        
        # Start heartbeat thread
        hb_thread = threading.Thread(target=heartbeat_thread, daemon=True)
        hb_thread.start()
    
    # Start Flask server
    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="DecentraStore Storage Node")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    parser.add_argument("--port", "-p", type=int, default=6001, help="Bind port")
    parser.add_argument("--discovery", "-d", default=None, help="Discovery service URL")
    parser.add_argument("--storage-dir", "-s", default=None, help="Chunk storage directory")
    parser.add_argument("--node-id", "-n", default=None, help="Node identifier")
    parser.add_argument("--debug", action="store_true", help="Debug mode")
    
    args = parser.parse_args()
    
    start_node(
        host=args.host,
        port=args.port,
        discovery_url=args.discovery,
        storage_dir=args.storage_dir,
        node_id=args.node_id,
        debug=args.debug
    )
