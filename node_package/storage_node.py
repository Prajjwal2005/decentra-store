#!/usr/bin/env python3
"""
DecentraStore Storage Node - Standalone Version

This is a self-contained storage node that can run independently.
Just configure the DISCOVERY_URL and run!

Usage:
    python storage_node.py --discovery http://SERVER:4000 --port 6001
"""

import os
import sys
import time
import uuid
import hashlib
import threading
import signal
import logging
import argparse
from pathlib import Path
from typing import Optional

# Check dependencies
try:
    import requests
    from flask import Flask, request, jsonify, send_file
    from flask_cors import CORS
except ImportError:
    print("Missing dependencies! Installing...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", 
                          "flask", "flask-cors", "requests", "-q"])
    import requests
    from flask import Flask, request, jsonify, send_file
    from flask_cors import CORS


# =============================================================================
# Configuration
# =============================================================================

DEFAULT_CONFIG = {
    "discovery_url": "http://localhost:4000",
    "host": "0.0.0.0",
    "port": 6001,
    "storage_dir": "./chunks",
    "node_id": None,  # Auto-generated if not set
    "heartbeat_interval": 15,  # seconds
    "node_ttl": 60,  # seconds
}


# =============================================================================
# Logging
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [NODE] %(levelname)s: %(message)s"
)
LOG = logging.getLogger("storage_node")


# =============================================================================
# Flask App
# =============================================================================

app = Flask(__name__)
CORS(app)

# Runtime state
NODE_ID: str = None
NODE_HOST: str = None
NODE_PORT: int = None
STORAGE_DIR: Path = None
DISCOVERY_URL: str = None
HEARTBEAT_INTERVAL: int = 15

STATS = {
    "chunks_stored": 0,
    "chunks_served": 0,
    "bytes_stored": 0,
    "bytes_served": 0,
    "started_at": None,
}

SHUTDOWN_EVENT = threading.Event()


# =============================================================================
# Helper Functions
# =============================================================================

def get_external_ip() -> Optional[str]:
    """Try to get external IP address."""
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
        except:
            continue
    return None


def compute_hash(data: bytes) -> str:
    """Compute SHA-256 hash."""
    return hashlib.sha256(data).hexdigest()


def get_chunk_path(chunk_hash: str) -> Path:
    """Get file path for a chunk (uses subdirectories)."""
    subdir = chunk_hash[:2]
    chunk_dir = STORAGE_DIR / subdir
    chunk_dir.mkdir(parents=True, exist_ok=True)
    return chunk_dir / f"{chunk_hash}.chunk"


def get_storage_capacity_gb() -> float:
    """Get available storage in GB."""
    try:
        if sys.platform == "win32":
            import ctypes
            free_bytes = ctypes.c_ulonglong(0)
            ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                ctypes.c_wchar_p(str(STORAGE_DIR)),
                None, None, ctypes.pointer(free_bytes)
            )
            return round(free_bytes.value / (1024**3), 2)
        else:
            stat = os.statvfs(STORAGE_DIR)
            return round((stat.f_bavail * stat.f_frsize) / (1024**3), 2)
    except:
        return 0


def count_chunks() -> tuple:
    """Count stored chunks and total bytes."""
    count = 0
    total_bytes = 0
    try:
        for subdir in STORAGE_DIR.iterdir():
            if subdir.is_dir():
                for chunk in subdir.glob("*.chunk"):
                    count += 1
                    total_bytes += chunk.stat().st_size
    except:
        pass
    return count, total_bytes


# =============================================================================
# Discovery Service Communication
# =============================================================================

def register_with_discovery():
    """Register this node with discovery service."""
    if not DISCOVERY_URL:
        LOG.warning("No discovery URL, running standalone")
        return False
    
    try:
        external_ip = get_external_ip()
        payload = {
            "node_id": NODE_ID,
            "ip": NODE_HOST if NODE_HOST != "0.0.0.0" else "127.0.0.1",
            "port": NODE_PORT,
            "public_ip": external_ip or NODE_HOST,
            "capacity_gb": get_storage_capacity_gb(),
            "meta": {"version": "1.0.0", "standalone": True}
        }
        
        resp = requests.post(f"{DISCOVERY_URL}/register", json=payload, timeout=10)
        if resp.status_code == 200:
            LOG.info(f"Registered with discovery: {resp.json().get('status')}")
            return True
        else:
            LOG.error(f"Registration failed: {resp.status_code}")
            return False
    except Exception as e:
        LOG.error(f"Failed to register: {e}")
        return False


def send_heartbeat():
    """Send heartbeat to discovery."""
    if not DISCOVERY_URL:
        return
    
    try:
        chunk_count, total_bytes = count_chunks()
        payload = {
            "node_id": NODE_ID,
            "stats": {
                "chunks_stored": chunk_count,
                "bytes_stored": total_bytes,
            }
        }
        resp = requests.post(f"{DISCOVERY_URL}/heartbeat", json=payload, timeout=5)
        if resp.status_code == 404:
            LOG.warning("Not registered, re-registering...")
            register_with_discovery()
    except Exception as e:
        LOG.error(f"Heartbeat failed: {e}")


def heartbeat_thread():
    """Background heartbeat thread."""
    while not SHUTDOWN_EVENT.is_set():
        try:
            send_heartbeat()
        except:
            pass
        SHUTDOWN_EVENT.wait(timeout=HEARTBEAT_INTERVAL)


def unregister():
    """Unregister from discovery on shutdown."""
    if DISCOVERY_URL:
        try:
            requests.post(f"{DISCOVERY_URL}/unregister", 
                         json={"node_id": NODE_ID}, timeout=5)
            LOG.info("Unregistered from discovery")
        except:
            pass


# =============================================================================
# API Endpoints
# =============================================================================

@app.route("/health", methods=["GET"])
def health():
    """Health check."""
    return jsonify({
        "status": "healthy",
        "node_id": NODE_ID,
        "timestamp": int(time.time()),
    })


@app.route("/stats", methods=["GET"])
def stats():
    """Node statistics."""
    chunk_count, total_bytes = count_chunks()
    return jsonify({
        "node_id": NODE_ID,
        "port": NODE_PORT,
        "storage_dir": str(STORAGE_DIR),
        "capacity_gb": get_storage_capacity_gb(),
        "chunks_stored": chunk_count,
        "bytes_stored": total_bytes,
        "chunks_served": STATS["chunks_served"],
        "started_at": STATS["started_at"],
    })


@app.route("/store", methods=["POST"])
def store_chunk():
    """Store an encrypted chunk."""
    chunk_data = None
    expected_hash = None
    
    # Handle multipart upload
    if "file" in request.files:
        chunk_data = request.files["file"].read()
        expected_hash = request.form.get("chunk_hash")
    # Handle JSON
    elif request.is_json:
        import base64
        data = request.get_json()
        if "data" in data:
            chunk_data = base64.b64decode(data["data"])
        expected_hash = data.get("chunk_hash")
    
    if not chunk_data:
        return jsonify({"error": "No chunk data"}), 400
    
    actual_hash = compute_hash(chunk_data)
    
    if expected_hash and actual_hash != expected_hash.lower():
        return jsonify({"error": "hash_mismatch"}), 400
    
    chunk_path = get_chunk_path(actual_hash)
    
    if chunk_path.exists():
        return jsonify({"status": "exists", "chunk_hash": actual_hash, "node_id": NODE_ID})
    
    try:
        with open(chunk_path, "wb") as f:
            f.write(chunk_data)
        
        STATS["chunks_stored"] += 1
        STATS["bytes_stored"] += len(chunk_data)
        LOG.info(f"Stored: {actual_hash[:16]}... ({len(chunk_data)} bytes)")
        
        return jsonify({"status": "stored", "chunk_hash": actual_hash, "node_id": NODE_ID})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/retrieve/<chunk_hash>", methods=["GET"])
def retrieve_chunk(chunk_hash: str):
    """Retrieve a chunk by hash."""
    chunk_hash = chunk_hash.lower()
    
    if len(chunk_hash) != 64:
        return jsonify({"error": "Invalid hash"}), 400
    
    chunk_path = get_chunk_path(chunk_hash)
    
    if not chunk_path.exists():
        return jsonify({"error": "Not found"}), 404
    
    try:
        STATS["chunks_served"] += 1
        return send_file(chunk_path, mimetype="application/octet-stream")
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/exists/<chunk_hash>", methods=["GET"])
def chunk_exists(chunk_hash: str):
    """Check if chunk exists."""
    chunk_path = get_chunk_path(chunk_hash.lower())
    exists = chunk_path.exists()
    return jsonify({"exists": exists, "chunk_hash": chunk_hash})


# =============================================================================
# Main
# =============================================================================

def graceful_shutdown(signum, frame):
    """Handle shutdown."""
    LOG.info("Shutting down...")
    SHUTDOWN_EVENT.set()
    unregister()
    sys.exit(0)


def main():
    global NODE_ID, NODE_HOST, NODE_PORT, STORAGE_DIR, DISCOVERY_URL, HEARTBEAT_INTERVAL
    
    parser = argparse.ArgumentParser(description="DecentraStore Storage Node")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    parser.add_argument("--port", "-p", type=int, default=6001, help="Bind port")
    parser.add_argument("--discovery", "-d", required=True, help="Discovery server URL")
    parser.add_argument("--storage-dir", "-s", default="./chunks", help="Chunk storage directory")
    parser.add_argument("--node-id", "-n", default=None, help="Node ID (auto-generated if not set)")
    
    args = parser.parse_args()
    
    # Set globals
    NODE_ID = args.node_id or f"node-{uuid.uuid4().hex[:8]}"
    NODE_HOST = args.host
    NODE_PORT = args.port
    STORAGE_DIR = Path(args.storage_dir).resolve()
    DISCOVERY_URL = args.discovery.rstrip("/")
    
    # Create storage directory
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    
    # Initialize stats
    STATS["started_at"] = time.time()
    chunk_count, total_bytes = count_chunks()
    STATS["chunks_stored"] = chunk_count
    STATS["bytes_stored"] = total_bytes
    
    # Print banner
    print()
    print("=" * 60)
    print("  DecentraStore Storage Node")
    print("=" * 60)
    print(f"  Node ID:     {NODE_ID}")
    print(f"  Address:     {NODE_HOST}:{NODE_PORT}")
    print(f"  Storage:     {STORAGE_DIR}")
    print(f"  Discovery:   {DISCOVERY_URL}")
    print(f"  Capacity:    {get_storage_capacity_gb()} GB")
    print(f"  Chunks:      {chunk_count} ({total_bytes} bytes)")
    print("=" * 60)
    print()
    
    # Signal handlers
    signal.signal(signal.SIGINT, graceful_shutdown)
    signal.signal(signal.SIGTERM, graceful_shutdown)
    
    # Register with discovery
    register_with_discovery()
    
    # Start heartbeat
    hb = threading.Thread(target=heartbeat_thread, daemon=True)
    hb.start()
    
    # Run Flask
    LOG.info(f"Node running on {NODE_HOST}:{NODE_PORT}")
    app.run(host=NODE_HOST, port=NODE_PORT, threaded=True)


if __name__ == "__main__":
    main()
