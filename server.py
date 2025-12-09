"""
DecentraStore Combined Server for Railway

Runs both Discovery and Backend services in one process.
"""

import os
import sys
import time
import threading
import logging
import uuid
import re
import base64
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask, request, jsonify, send_from_directory, Response, g
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Import config
from config import NODE_TTL, CHUNK_SIZE, REPLICATION_FACTOR

# Import backend modules
from backend import auth, uploader
from backend.models import init_db, get_session, User
from shared.blockchain import SimpleBlockchain
from shared import crypto, chunker

# =============================================================================
# Logging
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
LOG = logging.getLogger("decentrastore")

# =============================================================================
# Flask App
# =============================================================================
app = Flask(__name__, static_folder="frontend")

# CORS - restrict to same origin in production, allow specific origins via env
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "*").split(",")
CORS(app, origins=ALLOWED_ORIGINS, supports_credentials=True)

# Rate limiting
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["200 per minute", "1000 per hour"],
    storage_uri="memory://"
)

# Configuration
PORT = int(os.environ.get("PORT", 5000))
DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Max upload size (100 MB default)
MAX_UPLOAD_SIZE = int(os.environ.get("MAX_UPLOAD_SIZE", 100 * 1024 * 1024))
app.config['MAX_CONTENT_LENGTH'] = MAX_UPLOAD_SIZE

# Initialize database
init_db()

# Initialize blockchain
blockchain = SimpleBlockchain(DATA_DIR / "blockchain.json")

# =============================================================================
# DISCOVERY SERVICE (embedded)
# =============================================================================
PEERS = {}
PEERS_LOCK = threading.Lock()
TTL = NODE_TTL

@app.route("/register", methods=["POST"])
def register_node():
    data = request.get_json(force=True)
    node_id = data.get("node_id")
    ip = data.get("ip")
    port = data.get("port")
    
    if not all([node_id, ip, port]):
        return jsonify({"error": "node_id, ip, and port required"}), 400
    
    now = time.time()
    with PEERS_LOCK:
        is_new = node_id not in PEERS
        PEERS[node_id] = {
            "node_id": node_id,
            "ip": ip,
            "port": int(port),
            "public_ip": data.get("public_ip", ip),
            "capacity_gb": data.get("capacity_gb", 0),
            "meta": data.get("meta", {}),
            "last_heartbeat": now,
            "registered_at": PEERS.get(node_id, {}).get("registered_at", now),
        }
    
    LOG.info(f"Node {'registered' if is_new else 're-registered'}: {node_id}")
    return jsonify({"status": "registered", "node_id": node_id, "ttl_seconds": TTL})

@app.route("/heartbeat", methods=["POST"])
def heartbeat():
    data = request.get_json(force=True)
    node_id = data.get("node_id")
    
    if not node_id:
        return jsonify({"error": "node_id required"}), 400
    
    with PEERS_LOCK:
        if node_id not in PEERS:
            return jsonify({"error": "not registered"}), 404
        PEERS[node_id]["last_heartbeat"] = time.time()
    
    return jsonify({"status": "ok", "ttl_seconds": TTL})

@app.route("/unregister", methods=["POST"])
def unregister():
    data = request.get_json(force=True)
    node_id = data.get("node_id")
    
    with PEERS_LOCK:
        if node_id in PEERS:
            del PEERS[node_id]
            LOG.info(f"Node unregistered: {node_id}")
            return jsonify({"status": "unregistered"})
    
    return jsonify({"status": "not_found"}), 404

@app.route("/peers", methods=["GET"])
def get_peers():
    with PEERS_LOCK:
        now = time.time()
        alive = [
            {
                "node_id": p["node_id"],
                "ip": p["ip"],
                "port": p["port"],
                "public_ip": p.get("public_ip", p["ip"]),
                "capacity_gb": p.get("capacity_gb", 0),
                "last_heartbeat": p["last_heartbeat"],
            }
            for p in PEERS.values()
            if (now - p["last_heartbeat"]) <= TTL
        ]
    return jsonify({"peers": alive, "total_active": len(alive)})

# =============================================================================
# BACKEND SERVICE
# =============================================================================

# Health check
@app.route("/", methods=["GET"])
@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "service": "decentrastore",
        "timestamp": int(time.time()),
        "active_nodes": len([p for p in PEERS.values() if (time.time() - p["last_heartbeat"]) <= TTL])
    })

# Serve frontend
@app.route("/app", methods=["GET"])
@app.route("/app/", methods=["GET"])
def serve_frontend():
    return send_from_directory("frontend", "index.html")

@app.route("/static/<path:filename>")
def serve_static(filename):
    return send_from_directory("frontend/static", filename)

# Auth endpoints
@app.route("/auth/register", methods=["POST"])
@limiter.limit("5 per minute")  # Prevent registration spam
def auth_register():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400

    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

    # Username validation
    if len(username) < 3 or len(username) > 32:
        return jsonify({"error": "Username must be 3-32 characters"}), 400
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        return jsonify({"error": "Username can only contain letters, numbers, and underscores"}), 400

    # Password strength requirements
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400
    if not re.search(r'[A-Z]', password):
        return jsonify({"error": "Password must contain at least one uppercase letter"}), 400
    if not re.search(r'[a-z]', password):
        return jsonify({"error": "Password must contain at least one lowercase letter"}), 400
    if not re.search(r'[0-9]', password):
        return jsonify({"error": "Password must contain at least one number"}), 400

    user, error = auth.register_user(username, password)
    if error:
        return jsonify({"error": error}), 400

    # Generate token for auto-login after registration
    token = auth.generate_token(user.id, user.username)
    return jsonify({
        "status": "success",
        "token": token,
        "user_id": user.id,
        "username": user.username
    })

@app.route("/auth/login", methods=["POST"])
@limiter.limit("10 per minute")  # Prevent brute force attacks
def auth_login():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400

    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

    token, user, error = auth.login_user(username, password)
    if error:
        return jsonify({"error": error}), 401

    return jsonify({
        "status": "success",
        "token": token,
        "user_id": user.id,
        "username": user.username
    })

@app.route("/auth/me", methods=["GET"])
@auth.login_required
def auth_me():
    return jsonify({
        "user_id": g.current_user.id,
        "username": g.current_user.username,
    })

# Config endpoint
@app.route("/config", methods=["GET"])
def get_config():
    return jsonify({
        "chunk_size": CHUNK_SIZE,
        "replication_factor": REPLICATION_FACTOR,
    })

@app.route("/discovery-url", methods=["GET"])
def get_discovery_url():
    host = request.host
    scheme = "https" if request.is_secure or request.headers.get("X-Forwarded-Proto") == "https" else "http"
    return jsonify({
        "discovery_url": f"{scheme}://{host}",
        "note": "Use this URL when setting up your storage node"
    })

# Network status
@app.route("/network/peers", methods=["GET"])
def network_peers():
    with PEERS_LOCK:
        now = time.time()
        peers = [
            {"node_id": p["node_id"], "capacity_gb": p.get("capacity_gb", 0)}
            for p in PEERS.values()
            if (now - p["last_heartbeat"]) <= TTL
        ]
    return jsonify({"peers": peers, "count": len(peers)})

@app.route("/stats", methods=["GET"])
def stats():
    with PEERS_LOCK:
        now = time.time()
        active = [p for p in PEERS.values() if (now - p["last_heartbeat"]) <= TTL]
    return jsonify({
        "active_nodes": len(active),
        "total_capacity_gb": sum(p.get("capacity_gb", 0) for p in active),
        "timestamp": int(time.time())
    })

# File upload
@app.route("/upload", methods=["POST"])
@auth.login_required
@limiter.limit("10 per minute")  # Prevent upload spam
def upload_file():
    import requests as req

    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "No filename"}), 400

    user_password = request.headers.get("X-User-Password")
    if not user_password:
        return jsonify({"error": "Password required for encryption"}), 400

    # Get active peers
    with PEERS_LOCK:
        now = time.time()
        peers = [
            {"ip": p["public_ip"] or p["ip"], "port": p["port"], "node_id": p["node_id"]}
            for p in PEERS.values()
            if (now - p["last_heartbeat"]) <= TTL
        ]

    if len(peers) < 1:
        return jsonify({"error": "No storage nodes available"}), 503

    try:
        file_data = file.read()
        filename = file.filename

        file_key = crypto.generate_file_key()
        chunks = list(chunker.chunk_data(file_data, CHUNK_SIZE))
        chunk_hashes = [c[1] for c in chunks]
        merkle_root = chunker.compute_merkle_root(chunk_hashes)

        chunk_assignments = []
        replication = min(REPLICATION_FACTOR, len(peers))

        for idx, (chunk_data, chunk_hash) in enumerate(chunks):
            encrypted = crypto.encrypt_chunk(chunk_data, file_key)
            encrypted_hash = chunker.compute_hash(encrypted)

            assigned_peers = []
            for peer in peers[:replication]:
                try:
                    url = f"http://{peer['ip']}:{peer['port']}/store"
                    resp = req.post(url,
                        files={"file": encrypted},
                        data={"chunk_hash": encrypted_hash},
                        timeout=30
                    )
                    if resp.status_code == 200:
                        assigned_peers.append({
                            "node_id": peer["node_id"],
                            "ip": peer["ip"],
                            "port": peer["port"]
                        })
                except (req.RequestException, ConnectionError, TimeoutError) as e:
                    LOG.error(f"Failed to store chunk on {peer['node_id']}: {e}")

            chunk_assignments.append({
                "index": idx,
                "hash": chunk_hash,
                "encrypted_hash": encrypted_hash,
                "peers": assigned_peers
            })

        # Decode salt from base64 before deriving key
        user_salt = base64.b64decode(g.current_user.key_salt)
        user_key = crypto.derive_key_from_password(user_password, user_salt)
        encrypted_file_key = crypto.encrypt_file_key(file_key, user_key)
        # Base64 encode the encrypted file key for JSON storage
        encrypted_file_key_b64 = base64.b64encode(encrypted_file_key).decode('utf-8')

        file_id = str(uuid.uuid4())

        metadata = {
            "file_id": file_id,
            "filename": filename,
            "owner_id": g.current_user.id,
            "size": len(file_data),
            "merkle_root": merkle_root,
            "encrypted_file_key": encrypted_file_key_b64,
            "chunks": chunk_assignments,
            "uploaded_at": time.time()
        }
        blockchain.add_block(metadata)

        return jsonify({
            "status": "success",
            "file_id": file_id,
            "filename": filename,
            "size": len(file_data),
            "chunks": len(chunks)
        })

    except (ValueError, TypeError) as e:
        LOG.error(f"Upload validation error: {e}")
        return jsonify({"error": "Invalid data format"}), 400
    except (OSError, IOError) as e:
        LOG.error(f"Upload I/O error: {e}")
        return jsonify({"error": "File storage error"}), 500

# File download
@app.route("/download/<file_id>", methods=["GET"])
@auth.login_required
def download_file(file_id):
    import requests as req

    user_password = request.headers.get("X-User-Password")
    if not user_password:
        return jsonify({"error": "Password required"}), 400

    file_meta = None
    for block in blockchain.chain:
        if block.get("data", {}).get("file_id") == file_id:
            file_meta = block["data"]
            break

    if not file_meta:
        return jsonify({"error": "File not found"}), 404

    if file_meta.get("owner_id") != g.current_user.id:
        return jsonify({"error": "Access denied"}), 403

    try:
        # Decode salt from base64 before deriving key
        user_salt = base64.b64decode(g.current_user.key_salt)
        user_key = crypto.derive_key_from_password(user_password, user_salt)
        # Decode the encrypted file key from base64
        encrypted_file_key = base64.b64decode(file_meta["encrypted_file_key"])
        file_key = crypto.decrypt_file_key(encrypted_file_key, user_key)

        chunks_data = []
        for chunk_info in sorted(file_meta["chunks"], key=lambda x: x["index"]):
            encrypted_hash = chunk_info["encrypted_hash"]
            original_hash = chunk_info["hash"]

            for peer in chunk_info["peers"]:
                try:
                    url = f"http://{peer['ip']}:{peer['port']}/retrieve/{encrypted_hash}"
                    resp = req.get(url, timeout=30)
                    if resp.status_code == 200:
                        decrypted = crypto.decrypt_chunk(resp.content, file_key)
                        chunks_data.append((chunk_info["index"], decrypted, original_hash))
                        break
                except (req.RequestException, ConnectionError, TimeoutError) as e:
                    LOG.warning(f"Failed to retrieve chunk from {peer['node_id']}: {e}")
                    continue

        if len(chunks_data) != len(file_meta["chunks"]):
            return jsonify({"error": "Could not retrieve all chunks"}), 500

        # Verify merkle root for file integrity
        chunk_hashes = [chunker.sha256_bytes(c[1]) for c in sorted(chunks_data, key=lambda x: x[0])]
        expected_merkle_root = file_meta.get("merkle_root", "")
        if expected_merkle_root:
            computed_merkle_root = chunker.compute_merkle_root(chunk_hashes)
            if computed_merkle_root != expected_merkle_root:
                LOG.error(f"Merkle root verification failed for file {file_id}")
                return jsonify({"error": "File integrity check failed - data may be corrupted"}), 500

        chunks_data.sort(key=lambda x: x[0])
        file_data = b"".join([c[1] for c in chunks_data])

        return Response(
            file_data,
            mimetype="application/octet-stream",
            headers={"Content-Disposition": f"attachment; filename={file_meta['filename']}"}
        )

    except (ValueError, TypeError) as e:
        LOG.error(f"Download decryption error: {e}")
        return jsonify({"error": "Decryption failed - wrong password?"}), 400
    except (OSError, IOError) as e:
        LOG.error(f"Download I/O error: {e}")
        return jsonify({"error": "File retrieval error"}), 500

# My files
@app.route("/my-files", methods=["GET"])
@auth.login_required
def my_files():
    files = blockchain.get_user_files(g.current_user.id)
    # Check for deleted files by looking for deletion records
    deleted_file_ids = set()
    for block in blockchain.chain:
        data = block.get("data", {})
        if data.get("action") == "delete":
            deleted_file_ids.add(data.get("file_id"))

    # Filter out deleted files
    active_files = [f for f in files if f["file_id"] not in deleted_file_ids]

    return jsonify({
        "files": [
            {
                "file_id": f["file_id"],
                "filename": f["filename"],
                "size": f["size"],
                "uploaded_at": f["uploaded_at"],
                "chunks": len(f["chunks"])
            }
            for f in active_files
        ]
    })


# File deletion - marks file as deleted in blockchain
@app.route("/delete/<file_id>", methods=["DELETE"])
@auth.login_required
def delete_file(file_id):
    import requests as req

    # Find the file in blockchain
    file_meta = None
    for block in blockchain.chain:
        if block.get("data", {}).get("file_id") == file_id:
            file_meta = block["data"]
            break

    if not file_meta:
        return jsonify({"error": "File not found"}), 404

    if file_meta.get("owner_id") != g.current_user.id:
        return jsonify({"error": "Access denied"}), 403

    # Check if already deleted
    if file_meta.get("deleted"):
        return jsonify({"error": "File already deleted"}), 400

    try:
        # Try to delete chunks from storage nodes
        deleted_chunks = 0
        for chunk_info in file_meta.get("chunks", []):
            encrypted_hash = chunk_info["encrypted_hash"]
            for peer in chunk_info.get("peers", []):
                try:
                    url = f"http://{peer['ip']}:{peer['port']}/delete/{encrypted_hash}"
                    resp = req.delete(url, timeout=10)
                    if resp.status_code == 200:
                        deleted_chunks += 1
                        break
                except (req.RequestException, ConnectionError, TimeoutError) as e:
                    LOG.warning(f"Failed to delete chunk from {peer.get('node_id', 'unknown')}: {e}")
                    continue

        # Add deletion record to blockchain
        deletion_metadata = {
            "file_id": file_id,
            "owner_id": g.current_user.id,
            "action": "delete",
            "original_filename": file_meta.get("filename"),
            "deleted_at": time.time(),
            "chunks_deleted": deleted_chunks
        }
        blockchain.add_block(deletion_metadata)

        return jsonify({
            "status": "success",
            "file_id": file_id,
            "message": f"File deleted, {deleted_chunks} chunk(s) removed from storage"
        })

    except (ValueError, TypeError) as e:
        LOG.error(f"Delete error: {e}")
        return jsonify({"error": "Deletion failed"}), 500


# Blockchain explorer
@app.route("/blockchain/stats", methods=["GET"])
def blockchain_stats():
    return jsonify({
        "total_blocks": len(blockchain.chain),
        "total_files": len([b for b in blockchain.chain if b.get("data", {}).get("file_id")])
    })

@app.route("/blockchain/blocks", methods=["GET"])
def blockchain_blocks():
    limit = int(request.args.get("limit", 10))
    blocks = []
    for block in blockchain.chain[-limit:]:
        data = block.get("data", {})
        blocks.append({
            "index": block.get("index"),
            "timestamp": block.get("timestamp"),
            "file_id": data.get("file_id"),
            "filename": data.get("filename", "N/A"),
            "size": data.get("size", 0),
        })
    return jsonify({"blocks": blocks})

# Node package download
@app.route("/download-node", methods=["GET"])
def download_node():
    import zipfile
    import io
    
    zip_buffer = io.BytesIO()
    node_package_dir = Path(__file__).parent / "node_package"
    
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        if node_package_dir.exists():
            for file_path in node_package_dir.iterdir():
                if file_path.is_file():
                    zf.write(file_path, f"decentra-node/{file_path.name}")
    
    zip_buffer.seek(0)
    return Response(
        zip_buffer.getvalue(),
        mimetype="application/zip",
        headers={"Content-Disposition": "attachment; filename=decentra-node.zip"}
    )

# =============================================================================
# Reaper Thread
# =============================================================================
def reaper_thread():
    while True:
        time.sleep(max(10, TTL // 3))
        with PEERS_LOCK:
            now = time.time()
            dead = [nid for nid, p in PEERS.items() if (now - p["last_heartbeat"]) > TTL * 2]
            for node_id in dead:
                LOG.info(f"Reaping dead node: {node_id}")
                del PEERS[node_id]

threading.Thread(target=reaper_thread, daemon=True).start()

# =============================================================================
# Main
# =============================================================================
if __name__ == "__main__":
    LOG.info(f"Starting DecentraStore on port {PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
