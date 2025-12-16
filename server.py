"""
DecentraStore Combined Server for Railway

Runs both Discovery and Backend services in one process.
Uses WebSocket for node communication (NAT-friendly).
"""

import os
import sys
import time
import threading
import logging
import uuid
import base64
import json
from pathlib import Path
from queue import Queue, Empty

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask, request, jsonify, send_from_directory, Response, g
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Import config
from config import (
    NODE_TTL, CHUNK_SIZE, REPLICATION_FACTOR,
    CONSENSUS_MIN_CONFIRMATIONS, CONSENSUS_QUORUM_PERCENT, CONSENSUS_TIMEOUT
)

# Import backend modules
from backend import auth, uploader
from backend.models import init_db, get_session, User
from shared.blockchain import SimpleBlockchain, BlockStatus
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
# Flask App with SocketIO
# =============================================================================
app = Flask(__name__, static_folder="frontend")

# CORS - restrict to same origin in production, allow all in dev
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "*").split(",")
CORS(app, origins=ALLOWED_ORIGINS, supports_credentials=True)

# Rate limiting
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["200 per minute", "1000 per hour"],
    storage_uri="memory://"
)

# WebSocket - use 'gevent' mode for production with gunicorn gevent worker
socketio = SocketIO(
    app,
    cors_allowed_origins=ALLOWED_ORIGINS,
    async_mode='gevent',
    ping_timeout=60,
    ping_interval=25,
    logger=True,
    engineio_logger=False  # Disable to avoid base64 chunk spam
)

# Max upload size (100 MB default)
MAX_UPLOAD_SIZE = int(os.environ.get("MAX_UPLOAD_SIZE", 100 * 1024 * 1024))
app.config['MAX_CONTENT_LENGTH'] = MAX_UPLOAD_SIZE

# Configuration
PORT = int(os.environ.get("PORT", 5000))
DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Initialize database
init_db()

# Initialize blockchain
blockchain = SimpleBlockchain(DATA_DIR / "blockchain.json")

# =============================================================================
# WebSocket Node Management
# =============================================================================
NODES = {}  # node_id -> {sid, capacity_gb, last_seen, response_queue}
NODES_LOCK = threading.Lock()
TTL = NODE_TTL

@socketio.on('connect')
def handle_connect():
    LOG.info(f"WebSocket client connected: {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    with NODES_LOCK:
        # Find and remove node by sid
        to_remove = [nid for nid, info in NODES.items() if info.get('sid') == sid]
        for node_id in to_remove:
            LOG.info(f"Node disconnected: {node_id}")
            del NODES[node_id]

@socketio.on('node_register')
def handle_node_register(data):
    """Node registers itself via WebSocket."""
    node_id = data.get('node_id')
    capacity_gb = data.get('capacity_gb', 0)

    if not node_id:
        return {'error': 'node_id required'}

    with NODES_LOCK:
        is_new = node_id not in NODES
        NODES[node_id] = {
            'sid': request.sid,
            'capacity_gb': capacity_gb,
            'last_seen': time.time(),
            'response_queues': {}  # request_id -> Queue for responses
        }

    join_room(f'node_{node_id}')
    LOG.info(f"Node {'registered' if is_new else 're-registered'} via WebSocket: {node_id}")

    return {'status': 'registered', 'node_id': node_id}

@socketio.on('node_heartbeat')
def handle_node_heartbeat(data):
    """Node sends heartbeat."""
    node_id = data.get('node_id')

    with NODES_LOCK:
        if node_id in NODES:
            NODES[node_id]['last_seen'] = time.time()
            return {'status': 'ok'}

    return {'error': 'not registered'}

@socketio.on('chunk_stored')
def handle_chunk_stored(data):
    """Node confirms chunk was stored."""
    node_id = data.get('node_id')
    request_id = data.get('request_id')
    success = data.get('success', False)
    chunk_hash = data.get('chunk_hash')

    with NODES_LOCK:
        if node_id in NODES and request_id in NODES[node_id].get('response_queues', {}):
            NODES[node_id]['response_queues'][request_id].put({
                'success': success,
                'chunk_hash': chunk_hash
            })

@socketio.on('chunk_retrieved')
def handle_chunk_retrieved(data):
    """Node sends back requested chunk."""
    node_id = data.get('node_id')
    request_id = data.get('request_id')
    chunk_data = data.get('chunk_data')  # base64 encoded
    success = data.get('success', False)

    with NODES_LOCK:
        if node_id in NODES and request_id in NODES[node_id].get('response_queues', {}):
            NODES[node_id]['response_queues'][request_id].put({
                'success': success,
                'chunk_data': base64.b64decode(chunk_data) if chunk_data else None
            })

def get_active_nodes():
    """Get list of active WebSocket-connected nodes."""
    with NODES_LOCK:
        now = time.time()
        return [
            {'node_id': nid, 'capacity_gb': info.get('capacity_gb', 0), 'sid': info['sid']}
            for nid, info in NODES.items()
            if (now - info['last_seen']) <= TTL
        ]

def send_chunk_to_node(node_id, chunk_data, chunk_hash, timeout=30):
    """Send chunk to node via WebSocket and wait for confirmation."""
    with NODES_LOCK:
        if node_id not in NODES:
            return False

        node_info = NODES[node_id]
        request_id = str(uuid.uuid4())
        response_queue = Queue()
        node_info['response_queues'][request_id] = response_queue
        sid = node_info['sid']

    try:
        # Send store request to node
        room_name = f'node_{node_id}'
        LOG.info(f"Emitting store_chunk to room '{room_name}' for node {node_id}, request_id={request_id}")
        socketio.emit('store_chunk', {
            'request_id': request_id,
            'chunk_hash': chunk_hash,
            'chunk_data': base64.b64encode(chunk_data).decode('utf-8')
        }, room=room_name)
        LOG.info(f"Emitted store_chunk, waiting for response...")

        # Wait for response
        try:
            response = response_queue.get(timeout=timeout)
            return response.get('success', False)
        except Empty:
            LOG.error(f"Timeout waiting for chunk store confirmation from {node_id}")
            return False
    finally:
        # Cleanup
        with NODES_LOCK:
            if node_id in NODES and request_id in NODES[node_id].get('response_queues', {}):
                del NODES[node_id]['response_queues'][request_id]

def retrieve_chunk_from_node(node_id, chunk_hash, timeout=30):
    """Request chunk from node via WebSocket."""
    with NODES_LOCK:
        if node_id not in NODES:
            return None

        node_info = NODES[node_id]
        request_id = str(uuid.uuid4())
        response_queue = Queue()
        node_info['response_queues'][request_id] = response_queue
        sid = node_info['sid']

    try:
        # Send retrieve request to node
        socketio.emit('retrieve_chunk', {
            'request_id': request_id,
            'chunk_hash': chunk_hash
        }, room=f'node_{node_id}')

        # Wait for response
        try:
            response = response_queue.get(timeout=timeout)
            if response.get('success'):
                return response.get('chunk_data')
            return None
        except Empty:
            LOG.error(f"Timeout waiting for chunk from {node_id}")
            return None
    finally:
        # Cleanup
        with NODES_LOCK:
            if node_id in NODES and request_id in NODES[node_id].get('response_queues', {}):
                del NODES[node_id]['response_queues'][request_id]

# =============================================================================
# Legacy HTTP Discovery (for backwards compatibility)
# =============================================================================
PEERS = {}
PEERS_LOCK = threading.Lock()

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
    ws_nodes = len(get_active_nodes())
    return jsonify({
        "status": "healthy",
        "service": "decentrastore",
        "timestamp": int(time.time()),
        "active_nodes": ws_nodes,
        "websocket_nodes": ws_nodes
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

    # Input validation
    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

    # Username validation
    if len(username) < 3:
        return jsonify({"error": "Username must be at least 3 characters"}), 400
    if len(username) > 50:
        return jsonify({"error": "Username must be less than 50 characters"}), 400
    if not username.replace("_", "").replace("-", "").isalnum():
        return jsonify({"error": "Username can only contain letters, numbers, underscores, and hyphens"}), 400

    # Password strength validation
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400
    if len(password) > 128:
        return jsonify({"error": "Password must be less than 128 characters"}), 400
    if not any(c.isupper() for c in password):
        return jsonify({"error": "Password must contain at least one uppercase letter"}), 400
    if not any(c.islower() for c in password):
        return jsonify({"error": "Password must contain at least one lowercase letter"}), 400
    if not any(c.isdigit() for c in password):
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

    token, user, error = auth.login_user(username, password)
    if error:
        return jsonify({"error": error}), 401

    # Generate token pair (access + refresh)
    tokens = auth.generate_token_pair(user.id, user.username)

    return jsonify({
        "status": "success",
        "token": tokens["access_token"],  # For backwards compatibility
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "expires_in": tokens["expires_in"],
        "user_id": user.id,
        "username": user.username
    })


@app.route("/auth/refresh", methods=["POST"])
@limiter.limit("30 per minute")
def auth_refresh():
    """Refresh access token using refresh token."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400

    refresh_token = data.get("refresh_token")
    if not refresh_token:
        return jsonify({"error": "Refresh token required"}), 400

    payload = auth.decode_token(refresh_token)
    if not payload:
        return jsonify({"error": "Invalid or expired refresh token"}), 401

    if payload.get("type") != "refresh":
        return jsonify({"error": "Invalid token type"}), 401

    # Verify user still exists
    session = get_session()
    try:
        user = session.query(User).filter_by(id=payload["user_id"]).first()
        if not user or not getattr(user, "is_active", True):
            return jsonify({"error": "User not found or inactive"}), 401

        tokens = auth.generate_token_pair(user.id, user.username)
        return jsonify(tokens)
    finally:
        session.close()


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
    ws_scheme = "wss" if scheme == "https" else "ws"
    return jsonify({
        "discovery_url": f"{scheme}://{host}",
        "websocket_url": f"{ws_scheme}://{host}",
        "note": "Use WebSocket URL for NAT-friendly node connection"
    })

# Network status
@app.route("/network/peers", methods=["GET"])
def network_peers():
    # Combine WebSocket nodes and legacy HTTP nodes
    ws_nodes = get_active_nodes()

    with PEERS_LOCK:
        now = time.time()
        http_peers = [
            {"node_id": p["node_id"], "capacity_gb": p.get("capacity_gb", 0)}
            for p in PEERS.values()
            if (now - p["last_heartbeat"]) <= TTL
        ]

    # Combine, preferring WebSocket nodes
    all_nodes = {n['node_id']: n for n in http_peers}
    for n in ws_nodes:
        all_nodes[n['node_id']] = {'node_id': n['node_id'], 'capacity_gb': n['capacity_gb']}

    peers = list(all_nodes.values())
    return jsonify({"peers": peers, "count": len(peers)})

@app.route("/stats", methods=["GET"])
def stats():
    ws_nodes = get_active_nodes()
    return jsonify({
        "active_nodes": len(ws_nodes),
        "total_capacity_gb": sum(n.get("capacity_gb", 0) for n in ws_nodes),
        "timestamp": int(time.time())
    })

# File upload - now uses WebSocket for chunk distribution
@app.route("/upload", methods=["POST"])
@limiter.limit("10 per minute")  # Prevent upload spam
@auth.login_required
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "No filename"}), 400

    user_password = request.headers.get("X-User-Password")
    if not user_password:
        return jsonify({"error": "Password required for encryption"}), 400

    # Get active WebSocket nodes
    nodes = get_active_nodes()

    if len(nodes) < 1:
        return jsonify({"error": "No storage nodes available. Please wait for a node to connect."}), 503

    try:
        file_data = file.read()
        filename = file.filename

        file_key = crypto.generate_file_key()
        chunks = list(chunker.chunk_bytes(file_data, CHUNK_SIZE))
        chunk_hashes = [c[2] for c in chunks]  # (index, bytes, hash)
        merkle_root = chunker.compute_merkle_root(chunk_hashes)

        chunk_assignments = []
        replication = min(REPLICATION_FACTOR, len(nodes))

        # Track confirmations for consensus
        node_confirmations = {}  # node_id -> list of chunk hashes stored

        for idx, chunk_bytes_data, chunk_hash in chunks:
            encrypted = crypto.encrypt_chunk(chunk_bytes_data, file_key)
            encrypted_hash = chunker.sha256_bytes(encrypted)

            assigned_nodes = []
            for node in nodes[:replication]:
                node_id = node['node_id']
                LOG.info(f"Sending chunk {idx} to node {node_id} via WebSocket")

                success = send_chunk_to_node(node_id, encrypted, encrypted_hash)
                if success:
                    assigned_nodes.append({"node_id": node_id})
                    # Track confirmation
                    if node_id not in node_confirmations:
                        node_confirmations[node_id] = []
                    node_confirmations[node_id].append(encrypted_hash)
                    LOG.info(f"Chunk {idx} stored on {node_id}")
                else:
                    LOG.error(f"Failed to store chunk {idx} on {node_id}")

            chunk_assignments.append({
                "index": idx,
                "hash": chunk_hash,
                "encrypted_hash": encrypted_hash,
                "nodes": assigned_nodes
            })

        key_salt = base64.b64decode(g.current_user.key_salt)
        user_key, _ = crypto.derive_key_from_password(user_password, key_salt)
        encrypted_file_key = crypto.encrypt_file_key(file_key, user_key)
        encrypted_file_key_b64 = base64.b64encode(encrypted_file_key).decode('utf-8')

        file_id = str(uuid.uuid4())

        # Build initial confirmations from successful storage
        initial_confirmations = [
            {
                "node_id": node_id,
                "chunk_hashes": chunk_hashes,
                "timestamp": int(time.time()),
                "signature": None  # Could add node signatures in future
            }
            for node_id, chunk_hashes in node_confirmations.items()
        ]

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

        # Add block with consensus info
        total_nodes = len(nodes)
        block = blockchain.add_block(
            metadata,
            initial_confirmations=initial_confirmations,
            total_nodes=total_nodes
        )

        return jsonify({
            "status": "success",
            "file_id": file_id,
            "filename": filename,
            "size": len(file_data),
            "chunks": len(chunks),
            "consensus": {
                "status": block.get("status", "pending"),
                "confirmations": len(initial_confirmations),
                "required": blockchain.calculate_required_confirmations(total_nodes)
            }
        })

    except Exception as e:
        LOG.error(f"Upload error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# File download - now uses WebSocket for chunk retrieval
@app.route("/download/<file_id>", methods=["GET"])
@auth.login_required
def download_file(file_id):
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
        key_salt = base64.b64decode(g.current_user.key_salt)
        user_key, _ = crypto.derive_key_from_password(user_password, key_salt)
        encrypted_file_key = base64.b64decode(file_meta["encrypted_file_key"])
        file_key = crypto.decrypt_file_key(encrypted_file_key, user_key)

        chunks_data = []
        for chunk_info in sorted(file_meta["chunks"], key=lambda x: x["index"]):
            encrypted_hash = chunk_info["encrypted_hash"]

            # Try WebSocket nodes first
            nodes = chunk_info.get("nodes", [])
            chunk_retrieved = False

            for node_info in nodes:
                node_id = node_info["node_id"]
                LOG.info(f"Retrieving chunk {chunk_info['index']} from node {node_id}")

                encrypted_chunk = retrieve_chunk_from_node(node_id, encrypted_hash)
                if encrypted_chunk:
                    decrypted = crypto.decrypt_chunk(encrypted_chunk, file_key)
                    chunks_data.append((chunk_info["index"], decrypted))
                    chunk_retrieved = True
                    break

            if not chunk_retrieved:
                LOG.error(f"Failed to retrieve chunk {chunk_info['index']}")
                return jsonify({"error": f"Failed to retrieve chunk {chunk_info['index']}"}), 500

        chunks_data.sort(key=lambda x: x[0])

        # Verify merkle root for file integrity
        chunk_hashes = [chunker.sha256_bytes(c[1]) for c in chunks_data]
        expected_merkle_root = file_meta.get("merkle_root", "")
        if expected_merkle_root and not chunker.verify_merkle_root(chunk_hashes, expected_merkle_root):
            LOG.error(f"Merkle root verification failed for file {file_id}")
            return jsonify({"error": "File integrity check failed - data may be corrupted"}), 500

        file_data = b"".join([c[1] for c in chunks_data])

        return Response(
            file_data,
            mimetype="application/octet-stream",
            headers={"Content-Disposition": f"attachment; filename={file_meta['filename']}"}
        )

    except Exception as e:
        LOG.error(f"Download error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

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

    # Calculate total storage used
    total_size = sum(f["size"] for f in active_files)

    return jsonify({
        "files": [
            {
                "file_id": f["file_id"],
                "filename": f["filename"],
                "size": f["size"],
                "uploaded_at": f["uploaded_at"],
                "chunks": len(f["chunks"]),
                "status": f.get("status", "confirmed"),
                "confirmations": f.get("confirmations_count", 0)
            }
            for f in active_files
        ],
        "total_size": total_size,
        "file_count": len(active_files)
    })


# User storage stats
@app.route("/storage/usage", methods=["GET"])
@auth.login_required
def storage_usage():
    """Get storage usage statistics for current user."""
    files = blockchain.get_user_files(g.current_user.id)

    # Get deleted file IDs
    deleted_file_ids = set()
    for block in blockchain.chain:
        data = block.get("data", {})
        if data.get("action") == "delete":
            deleted_file_ids.add(data.get("file_id"))

    # Filter active files
    active_files = [f for f in files if f["file_id"] not in deleted_file_ids]

    total_size = sum(f["size"] for f in active_files)
    total_chunks = sum(len(f["chunks"]) for f in active_files)

    return jsonify({
        "user_id": g.current_user.id,
        "username": g.current_user.username,
        "file_count": len(active_files),
        "total_size": total_size,
        "total_chunks": total_chunks,
        "storage_limit": None,  # No limit implemented yet
        "usage_percent": None   # Would be calculated if limit exists
    })


# File sharing
@app.route("/share/<file_id>", methods=["POST"])
@auth.login_required
def share_file(file_id):
    """Share a file with another user."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400

    target_username = data.get("username", "").strip()
    if not target_username:
        return jsonify({"error": "Username required"}), 400

    # Find the file
    file_meta = None
    for block in blockchain.chain:
        if block.get("data", {}).get("file_id") == file_id:
            file_meta = block["data"]
            break

    if not file_meta:
        return jsonify({"error": "File not found"}), 404

    if file_meta.get("owner_id") != g.current_user.id:
        return jsonify({"error": "Only file owner can share"}), 403

    # Check if file is deleted
    for block in blockchain.chain:
        block_data = block.get("data", {})
        if block_data.get("action") == "delete" and block_data.get("file_id") == file_id:
            return jsonify({"error": "Cannot share deleted file"}), 400

    # Find target user
    session = get_session()
    target_user = session.query(User).filter_by(username=target_username).first()
    if not target_user:
        return jsonify({"error": "User not found"}), 404

    if target_user.id == g.current_user.id:
        return jsonify({"error": "Cannot share with yourself"}), 400

    # Check if already shared
    for block in blockchain.chain:
        block_data = block.get("data", {})
        if (block_data.get("action") == "share" and
            block_data.get("file_id") == file_id and
            block_data.get("shared_with") == target_user.id):
            return jsonify({"error": "Already shared with this user"}), 400

    # Create share record in blockchain
    share_metadata = {
        "file_id": file_id,
        "owner_id": g.current_user.id,
        "shared_with": target_user.id,
        "shared_with_username": target_username,
        "action": "share",
        "filename": file_meta.get("filename"),
        "size": file_meta.get("size"),
        "shared_at": time.time()
    }
    blockchain.add_block(share_metadata)

    return jsonify({
        "status": "success",
        "file_id": file_id,
        "shared_with": target_username,
        "message": f"File shared with {target_username}"
    })


@app.route("/shared-with-me", methods=["GET"])
@auth.login_required
def shared_with_me():
    """Get files shared with current user."""
    shared_files = []

    # Get all share records for this user
    for block in blockchain.chain:
        data = block.get("data", {})
        if data.get("action") == "share" and data.get("shared_with") == g.current_user.id:
            # Check if file was later unshared or deleted
            file_id = data.get("file_id")

            # Check for unshare
            is_unshared = False
            for b in blockchain.chain:
                bd = b.get("data", {})
                if (bd.get("action") == "unshare" and
                    bd.get("file_id") == file_id and
                    bd.get("unshared_from") == g.current_user.id):
                    is_unshared = True
                    break

            # Check for delete
            is_deleted = False
            for b in blockchain.chain:
                bd = b.get("data", {})
                if bd.get("action") == "delete" and bd.get("file_id") == file_id:
                    is_deleted = True
                    break

            if not is_unshared and not is_deleted:
                shared_files.append({
                    "file_id": file_id,
                    "filename": data.get("filename"),
                    "size": data.get("size"),
                    "shared_by": data.get("owner_id"),
                    "shared_at": data.get("shared_at")
                })

    return jsonify({"files": shared_files, "count": len(shared_files)})


@app.route("/unshare/<file_id>", methods=["POST"])
@auth.login_required
def unshare_file(file_id):
    """Revoke file sharing from a user."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400

    target_username = data.get("username", "").strip()
    if not target_username:
        return jsonify({"error": "Username required"}), 400

    # Find the file
    file_meta = None
    for block in blockchain.chain:
        if block.get("data", {}).get("file_id") == file_id:
            file_meta = block["data"]
            break

    if not file_meta:
        return jsonify({"error": "File not found"}), 404

    if file_meta.get("owner_id") != g.current_user.id:
        return jsonify({"error": "Only file owner can unshare"}), 403

    # Find target user
    session = get_session()
    try:
        target_user = session.query(User).filter_by(username=target_username).first()
        if not target_user:
            return jsonify({"error": "User not found"}), 404

        # Create unshare record
        unshare_metadata = {
            "file_id": file_id,
            "owner_id": g.current_user.id,
            "unshared_from": target_user.id,
            "action": "unshare",
            "unshared_at": time.time()
        }
        blockchain.add_block(unshare_metadata)

        return jsonify({
            "status": "success",
            "file_id": file_id,
            "unshared_from": target_username
        })
    finally:
        session.close()


# File deletion - marks file as deleted in blockchain
@app.route("/delete/<file_id>", methods=["DELETE"])
@auth.login_required
def delete_file(file_id):
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
    for block in blockchain.chain:
        data = block.get("data", {})
        if data.get("action") == "delete" and data.get("file_id") == file_id:
            return jsonify({"error": "File already deleted"}), 400

    try:
        # Try to delete chunks from storage nodes via WebSocket
        deleted_chunks = 0
        for chunk_info in file_meta.get("chunks", []):
            encrypted_hash = chunk_info["encrypted_hash"]
            # Support both "nodes" (new format) and "peers" (legacy format)
            nodes_list = chunk_info.get("nodes", chunk_info.get("peers", []))
            for node_entry in nodes_list:
                node_id = node_entry.get("node_id")
                if node_id:
                    with NODES_LOCK:
                        node_info = NODES.get(node_id)
                        if node_info:
                            try:
                                socketio.emit('delete_chunk', {
                                    'chunk_hash': encrypted_hash
                                }, room=node_info['sid'])
                                deleted_chunks += 1
                            except Exception as e:
                                LOG.warning(f"Failed to delete chunk from {node_id}: {e}")

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
            "message": f"File deleted, {deleted_chunks} chunk(s) removal requested"
        })

    except Exception as e:
        LOG.error(f"Delete error: {e}")
        return jsonify({"error": "Deletion failed"}), 500


# Blockchain explorer
@app.route("/blockchain/stats", methods=["GET"])
def blockchain_stats():
    # Use the enhanced stats from ConsensusBlockchain
    stats = blockchain.get_stats()

    # Get deleted file IDs for filtering
    deleted_file_ids = set()
    for block in blockchain.chain:
        data = block.get("data", {})
        if data.get("action") == "delete":
            deleted_file_ids.add(data.get("file_id"))

    # Count only active (non-deleted) files
    active_files = [
        b for b in blockchain.chain
        if b.get("data", {}).get("file_id") and
           b.get("data", {}).get("action") != "delete" and
           b.get("data", {}).get("file_id") not in deleted_file_ids
    ]

    return jsonify({
        "total_blocks": len(blockchain.chain),
        "total_files": len(active_files),
        "pending_blocks": stats.get("pending_files", 0),
        "confirmed_blocks": stats.get("confirmed_files", 0),
        "total_confirmations": stats.get("total_confirmations", 0),
        "consensus": stats.get("consensus_config", {})
    })


# Consensus endpoints
@app.route("/consensus/status/<block_hash>", methods=["GET"])
def get_consensus_status(block_hash):
    """Get consensus status for a specific block."""
    block = blockchain.get_block_by_hash(block_hash)
    if not block:
        return jsonify({"error": "Block not found"}), 404

    total_nodes = len(get_active_nodes())
    required = blockchain.calculate_required_confirmations(total_nodes)

    return jsonify({
        "block_hash": block_hash,
        "status": block.get("status", "confirmed"),
        "confirmations": block.get("confirmations", []),
        "confirmations_count": len(block.get("confirmations", [])),
        "required_confirmations": required,
        "active_nodes": total_nodes
    })


@app.route("/consensus/pending", methods=["GET"])
def get_pending_blocks():
    """Get all blocks awaiting consensus."""
    pending = blockchain.get_pending_blocks()
    total_nodes = len(get_active_nodes())
    required = blockchain.calculate_required_confirmations(total_nodes)

    return jsonify({
        "pending_blocks": [
            {
                "block_hash": b["hash"],
                "block_index": b["index"],
                "file_id": b.get("data", {}).get("file_id"),
                "filename": b.get("data", {}).get("filename"),
                "confirmations_count": len(b.get("confirmations", [])),
                "required": required,
                "timestamp": b["timestamp"]
            }
            for b in pending
        ],
        "count": len(pending),
        "required_confirmations": required,
        "active_nodes": total_nodes
    })


@app.route("/consensus/config", methods=["GET"])
def get_consensus_config():
    """Get current consensus configuration."""
    total_nodes = len(get_active_nodes())
    return jsonify({
        "min_confirmations": CONSENSUS_MIN_CONFIRMATIONS,
        "quorum_percent": CONSENSUS_QUORUM_PERCENT,
        "timeout_seconds": CONSENSUS_TIMEOUT,
        "active_nodes": total_nodes,
        "current_required": blockchain.calculate_required_confirmations(total_nodes)
    })

@app.route("/blockchain/blocks", methods=["GET"])
def blockchain_blocks():
    """Get all blockchain blocks (public explorer)"""
    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))

    # Get blocks in reverse order (newest first)
    all_blocks = list(reversed(blockchain.chain))
    paginated = all_blocks[offset:offset + limit]

    blocks = []
    for block in paginated:
        data = block.get("data", {})
        blocks.append({
            "index": block.get("index"),
            "hash": block.get("hash", "")[:16] + "..." if block.get("hash") else "",
            "previous_hash": block.get("previous_hash", "")[:16] + "..." if block.get("previous_hash") else "",
            "timestamp": block.get("timestamp"),
            "file_id": data.get("file_id"),
            "filename": data.get("filename", "Genesis Block" if block.get("index") == 0 else "N/A"),
            "size": data.get("size", 0),
            "chunks": len(data.get("chunks", [])),
            "owner_id": data.get("owner_id"),
            "merkle_root": data.get("merkle_root", "")[:16] + "..." if data.get("merkle_root") else "",
        })
    return jsonify({
        "blocks": blocks,
        "total": len(blockchain.chain),
        "offset": offset,
        "limit": limit
    })

@app.route("/blockchain/my-blocks", methods=["GET"])
@auth.login_required
def my_blockchain_blocks():
    """Get blocks created by the current user"""
    limit = int(request.args.get("limit", 50))

    user_blocks = []
    for block in reversed(blockchain.chain):
        data = block.get("data", {})
        if data.get("owner_id") == g.current_user.id:
            user_blocks.append({
                "index": block.get("index"),
                "hash": block.get("hash", "")[:16] + "..." if block.get("hash") else "",
                "previous_hash": block.get("previous_hash", "")[:16] + "..." if block.get("previous_hash") else "",
                "timestamp": block.get("timestamp"),
                "file_id": data.get("file_id"),
                "filename": data.get("filename", "N/A"),
                "size": data.get("size", 0),
                "chunks": len(data.get("chunks", [])),
                "merkle_root": data.get("merkle_root", "")[:16] + "..." if data.get("merkle_root") else "",
            })
            if len(user_blocks) >= limit:
                break

    return jsonify({
        "blocks": user_blocks,
        "total": len(user_blocks)
    })

# Node package download
@app.route("/download-node", methods=["GET"])
def download_node():
    import zipfile
    import io

    zip_buffer = io.BytesIO()
    node_package_dir = Path(__file__).parent / "node_package"

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        if node_package_dir.exists():
            for file_path in node_package_dir.rglob("*"):
                if file_path.is_file():
                    arcname = f"decentra-node/{file_path.relative_to(node_package_dir)}"
                    zf.write(file_path, arcname)

    zip_buffer.seek(0)
    return Response(
        zip_buffer.getvalue(),
        mimetype="application/zip",
        headers={"Content-Disposition": "attachment; filename=decentra-node.zip"}
    )

# =============================================================================
# Reaper Thread (for legacy HTTP nodes)
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
    LOG.info(f"Starting DecentraStore with WebSocket support on port {PORT}")
    socketio.run(app, host="0.0.0.0", port=PORT, debug=False, allow_unsafe_werkzeug=True)
