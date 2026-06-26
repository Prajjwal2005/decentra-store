# backend/app.py
"""
Main Backend Server for DecentraStore.

Provides REST API for:
- User authentication (register, login, logout)
- File metadata management
- File upload/download coordination
- Node discovery and heartbeats
"""

import os
import uuid
import time
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime, timedelta

from flask import Flask, request, jsonify, Response, g, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    REPLICATION_FACTOR,
    CHUNK_SIZE,
    SECRET_KEY,
    TEMP_STORAGE,
    DATA_DIR,
    NODE_TTL
)
from shared.chunker import (
    chunk_file,
    compute_merkle_root,
    verify_chunk_hash,
)
import hashlib

def compute_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
from backend.models import User, FileMetadata, ChunkLocation, Node, get_session, init_db
from backend.auth import (
    login_required,
    admin_required,
    get_current_user,
    register_user,
    login_user,
)
from backend import uploader

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [backend] %(levelname)s: %(message)s"
)
LOG = logging.getLogger("backend")

# Flask app
app = Flask(__name__, static_folder=None)
app.config["SECRET_KEY"] = SECRET_KEY
CORS(app, supports_credentials=True)

# Initialize database
init_db()

# Frontend directory
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

# =============================================================================
# Helpers
# =============================================================================

@app.before_request
def before_request():
    g.current_user = get_current_user()

@app.route("/")
def index():
    """Serve frontend."""
    return send_from_directory(FRONTEND_DIR, "index.html")

@app.route("/static/<path:filename>")
def static_files(filename):
    """Serve static files."""
    return send_from_directory(FRONTEND_DIR / "static", filename)

# =============================================================================
# Auth Routes
# =============================================================================

@app.route("/auth/register", methods=["POST"])
def register():
    data = request.get_json(force=True)
    if not data or "username" not in data or "password" not in data:
        return jsonify({"error": "Missing username or password"}), 400
    user, error = register_user(data["username"], data["password"], data.get("email"))
    if error:
        return jsonify({"error": error}), 400
    return jsonify({
        "status": "registered",
        "user": user.to_dict(include_private=True)
    }), 201

@app.route("/auth/login", methods=["POST"])
def login():
    data = request.get_json(force=True)
    if not data or "username" not in data or "password" not in data:
        return jsonify({"error": "Missing username or password"}), 400
    token, user, error = login_user(data["username"], data["password"])
    if error:
        return jsonify({"error": error}), 401
    return jsonify({
        "token": token,
        "user": user.to_dict(include_private=True)
    })

@app.route("/auth/me", methods=["GET"])
@login_required
def me():
    return jsonify({
        "status": "authenticated",
        "user": g.current_user.to_dict(include_private=True)
    })

# =============================================================================
# Node Discovery / Coordination Routes
# =============================================================================

@app.route("/nodes/register", methods=["POST"])
def node_register():
    data = request.get_json(force=True)
    node_id = data.get("node_id")
    ip = data.get("ip")
    port = data.get("port")
    public_url = data.get("public_url")
    
    if not all([node_id, ip, port]):
        return jsonify({"error": "node_id, ip, and port are required"}), 400
        
    url = public_url if public_url else f"http://{ip}:{port}"
    session = get_session()
    try:
        node = session.query(Node).filter_by(id=node_id).first()
        if not node:
            node = Node(id=node_id, url=url)
            session.add(node)
        
        node.url = url
        node.capacity_bytes = data.get("capacity_gb", 0) * 1024 * 1024 * 1024
        node.last_heartbeat = datetime.utcnow()
        node.is_active = True
        
        session.commit()
        return jsonify({"status": "registered", "node_id": node_id, "ttl_seconds": NODE_TTL})
    finally:
        session.close()

@app.route("/nodes/heartbeat", methods=["POST"])
def node_heartbeat():
    data = request.get_json(force=True)
    node_id = data.get("node_id")
    if not node_id:
        return jsonify({"error": "node_id is required"}), 400
        
    session = get_session()
    try:
        node = session.query(Node).filter_by(id=node_id).first()
        if not node:
            return jsonify({"error": "not registered", "action": "register"}), 404
            
        node.last_heartbeat = datetime.utcnow()
        node.is_active = True
        if "capacity_gb" in data:
            node.capacity_bytes = data["capacity_gb"] * 1024 * 1024 * 1024
            
        session.commit()
        return jsonify({"status": "ok", "ttl_seconds": NODE_TTL})
    finally:
        session.close()

@app.route("/nodes/unregister", methods=["POST"])
def node_unregister():
    data = request.get_json(force=True)
    node_id = data.get("node_id")
    if not node_id:
        return jsonify({"error": "node_id is required"}), 400
        
    session = get_session()
    try:
        node = session.query(Node).filter_by(id=node_id).first()
        if node:
            node.is_active = False
            session.commit()
            return jsonify({"status": "unregistered"})
        return jsonify({"status": "not_found"}), 404
    finally:
        session.close()

def get_active_nodes():
    session = get_session()
    try:
        cutoff = datetime.utcnow() - timedelta(seconds=NODE_TTL)
        return session.query(Node).filter(Node.is_active == True, Node.last_heartbeat >= cutoff).all()
    finally:
        session.close()

@app.route("/network/peers", methods=["GET"])
def network_peers():
    nodes = get_active_nodes()
    return jsonify({
        "peers": [n.to_dict() for n in nodes],
        "count": len(nodes)
    })

# =============================================================================
# File Upload/Download
# =============================================================================

@app.route("/files/upload", methods=["POST"])
@login_required
def upload_file():
    user = g.current_user
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400
        
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400
        
    encrypted_key = request.form.get("encrypted_key")
    key_iv = request.form.get("key_iv")
    file_iv = request.form.get("file_iv")
    
    if not encrypted_key or not key_iv or not file_iv:
        return jsonify({"error": "Encryption metadata required (encrypted_key, key_iv, file_iv)"}), 400
        
    nodes = get_active_nodes()
    if not nodes:
        return jsonify({"error": "No storage nodes available"}), 503
        
    # Process upload locally first
    filename = secure_filename(file.filename)
    if not filename:
        filename = f"file_{int(time.time())}"
        
    file_id = str(uuid.uuid4())
    temp_path = Path(TEMP_STORAGE) / f"{file_id}.tmp"
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    file.save(temp_path)
    
    try:
        file_size = temp_path.stat().st_size
        if user.storage_used_bytes + file_size > user.storage_quota_bytes:
            return jsonify({"error": "Storage quota exceeded"}), 403
            
        chunks = chunk_file(file_path=temp_path, chunk_size=CHUNK_SIZE)
        
        chunk_records = []
        merkle_leaves = []
        
        session = get_session()
        try:
            for chunk_index, chunk_bytes, chunk_hash in chunks:
                merkle_leaves.append(chunk_hash)
                
                # Distribute (using simple round-robin for now)
                node = nodes[chunk_index % len(nodes)]
                success = uploader.upload_chunk_to_node({"url": node.url, "node_id": node.id}, chunk_hash, chunk_bytes)
                if not success:
                    raise Exception(f"Failed to upload chunk {chunk_index} to node {node.id}")
                    
                chunk_records.append({
                    "chunk_index": chunk_index,
                    "chunk_hash": chunk_hash,
                    "node_id": node.id
                })
                
            merkle_root = compute_merkle_root(merkle_leaves)
            
            # Save metadata to postgres
            file_meta = FileMetadata(
                id=file_id,
                owner_id=user.id,
                original_name=file.filename,
                stored_name=filename,
                size=file_size,
                mime_type=file.content_type or "application/octet-stream",
                merkle_root=merkle_root,
                chunk_count=len(chunk_records),
                encrypted_key=encrypted_key,
                key_iv=key_iv,
                file_iv=file_iv
            )
            session.add(file_meta)
            
            for cr in chunk_records:
                session.add(ChunkLocation(
                    file_id=file_id,
                    chunk_index=cr["chunk_index"],
                    chunk_hash=cr["chunk_hash"],
                    node_id=cr["node_id"]
                ))
                
            user.storage_used_bytes += file_size
            session.commit()
            
            return jsonify({
                "status": "success",
                "file_id": file_id,
                "filename": filename,
                "size": file_size,
                "merkle_root": merkle_root
            }), 201
            
        except Exception as e:
            session.rollback()
            LOG.error(f"Upload failed: {e}")
            return jsonify({"error": str(e)}), 500
        finally:
            session.close()
            
    finally:
        if temp_path.exists():
            temp_path.unlink()


@app.route("/files/<file_id>/download", methods=["GET"])
@login_required
def download_file(file_id):
    user = g.current_user
        
    session = get_session()
    try:
        file_meta = session.query(FileMetadata).filter_by(id=file_id).first()
        if not file_meta:
            return jsonify({"error": "File not found"}), 404
            
        if file_meta.owner_id != user.id:
            return jsonify({"error": "Access denied"}), 403
            
        chunks = session.query(ChunkLocation).filter_by(file_id=file_id).order_by(ChunkLocation.chunk_index).all()
        
        # Generator for streaming
        def generate():
            for chunk_record in chunks:
                node = session.query(Node).filter_by(id=chunk_record.node_id).first()
                if not node:
                    raise Exception(f"Node {chunk_record.node_id} not found")
                    
                encrypted_chunk = uploader.download_chunk_from_node(
                    {"url": node.url, "node_id": node.id},
                    chunk_record.chunk_hash
                )
                
                if not encrypted_chunk:
                    raise Exception(f"Failed to retrieve chunk {chunk_record.chunk_hash}")
                    
                if not verify_chunk_hash(encrypted_chunk, chunk_record.chunk_hash):
                    raise Exception(f"Chunk integrity check failed for {chunk_record.chunk_hash}")
                    
                yield encrypted_chunk
                
        return Response(
            generate(),
            mimetype="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{file_meta.original_name}.enc"',
                "X-Encrypted-Key": file_meta.encrypted_key,
                "X-Key-Iv": file_meta.key_iv,
                "X-File-Iv": file_meta.file_iv,
                "X-Original-Mime": file_meta.mime_type or "application/octet-stream",
                "X-Original-Name": file_meta.original_name,
                "Access-Control-Expose-Headers": "X-Encrypted-Key, X-Key-Iv, X-File-Iv, X-Original-Mime, X-Original-Name"
            }
        )
    finally:
        session.close()


@app.route("/files", methods=["GET"])
@login_required
def list_files():
    user = g.current_user
    session = get_session()
    try:
        files = session.query(FileMetadata).filter_by(owner_id=user.id).order_by(FileMetadata.created_at.desc()).all()
        return jsonify({
            "files": [f.to_dict() for f in files],
            "count": len(files)
        })
    finally:
        session.close()

# =============================================================================
# Blockchain Explorer (Public but Anonymized) - Now just DB Explorer
# =============================================================================

@app.route("/blockchain/stats", methods=["GET"])
def blockchain_stats():
    session = get_session()
    try:
        file_count = session.query(FileMetadata).count()
        node_count = session.query(Node).count()
        return jsonify({
            "file_count": file_count,
            "node_count": node_count,
        })
    finally:
        session.close()

@app.route("/blockchain/blocks", methods=["GET"])
def list_blocks():
    # Stub for frontend compatibility
    session = get_session()
    try:
        limit = min(int(request.args.get("limit", 20)), 100)
        offset = int(request.args.get("offset", 0))
        files = session.query(FileMetadata).order_by(FileMetadata.created_at.desc()).offset(offset).limit(limit).all()
        
        blocks = []
        for i, f in enumerate(files):
            blocks.append({
                "index": i + offset,
                "hash": f.merkle_root,
                "prev_hash": "0"*64,
                "timestamp": int(f.created_at.timestamp()),
                "type": "file",
                "file_size": f.size,
                "chunk_count": f.chunk_count,
            })
            
        return jsonify({
            "blocks": blocks,
            "total": session.query(FileMetadata).count(),
            "offset": offset,
            "limit": limit,
        })
    finally:
        session.close()

# =============================================================================
# Node Software Download
# =============================================================================

@app.route("/download-node", methods=["GET"])
def download_node_software():
    import zipfile
    import io
    
    zip_buffer = io.BytesIO()
    node_package_dir = Path(__file__).parent.parent / "node_package"
    
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        if node_package_dir.exists():
            for file_path in node_package_dir.iterdir():
                if file_path.is_file():
                    zf.write(file_path, f"decentra-node/{file_path.name}")
        else:
            storage_node_code = '''#!/usr/bin/env python3
print("Error: Please download the complete node package from the website.")
'''
            zf.writestr("decentra-node/storage_node.py", storage_node_code)
            zf.writestr("decentra-node/README.md", "Download the full package from the website.")
    
    zip_buffer.seek(0)
    
    return Response(
        zip_buffer.getvalue(),
        mimetype="application/zip",
        headers={
            "Content-Disposition": "attachment; filename=decentra-node.zip"
        }
    )

# =============================================================================
# Run Server
# =============================================================================

def start_server(host: str = "0.0.0.0", port: int = 5000, debug: bool = False):
    LOG.info(f"Starting backend server on {host}:{port}")
    if not FRONTEND_DIR.exists():
        LOG.warning(f"Frontend directory not found: {FRONTEND_DIR}")
    
    app.run(host=host, port=port, debug=debug, threaded=True)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="DecentraStore Backend Server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    parser.add_argument("--port", "-p", type=int, default=5000, help="Bind port")
    parser.add_argument("--debug", action="store_true", help="Debug mode")
    args = parser.parse_args()
    start_server(host=args.host, port=args.port, debug=args.debug)
