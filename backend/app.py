# backend/app.py
"""
Main Backend Server for DecentraStore.

Provides REST API for:
- User authentication (register, login, logout)
- File upload with encryption and distribution
- File retrieval with verification and decryption
- User's file listing (privacy-filtered)
- Blockchain explorer
"""

import os
import uuid
import time
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

from flask import Flask, request, jsonify, Response, g, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    DISCOVERY_URL,
    REPLICATION_FACTOR,
    CHUNK_SIZE,
    SECRET_KEY,
    TEMP_STORAGE,
    DATA_DIR,
)
from shared.crypto import (
    generate_file_key,
    encrypt_chunk,
    decrypt_chunk,
    encrypt_file_key,
    decrypt_file_key,
    compute_hash,
    b64_encode,
    b64_decode,
)
from shared.chunker import (
    chunk_file,
    compute_merkle_root,
    verify_chunk_hash,
)
from shared.blockchain import SimpleBlockchain
from backend.models import User, get_session, init_db
from backend.auth import (
    login_required,
    admin_required,
    get_current_user,
    register_user,
    login_user,
    get_user_encryption_key,
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

# Initialize blockchain
blockchain = SimpleBlockchain()

# Frontend directory
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


# =============================================================================
# Helpers
# =============================================================================

def get_user_key_from_header(user: User) -> Optional[bytes]:
    """
    Get user's encryption key from X-User-Password header.
    
    This is needed for encrypting/decrypting file keys.
    The password is sent in a header so we can derive the key.
    
    Note: In production, consider using a session-cached key
    or a hardware security module.
    """
    password = request.headers.get("X-User-Password")
    if not password:
        return None
    
    try:
        return get_user_encryption_key(user, password)
    except Exception:
        return None


# =============================================================================
# Static Files (Frontend)
# =============================================================================

@app.route("/")
def index():
    """Serve frontend."""
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/static/<path:filename>")
def static_files(filename):
    """Serve static files."""
    return send_from_directory(FRONTEND_DIR / "static", filename)


# =============================================================================
# Health & Info
# =============================================================================

@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "service": "backend",
        "timestamp": int(time.time()),
    })


@app.route("/config", methods=["GET"])
def get_config():
    """Get public configuration."""
    return jsonify({
        "chunk_size": CHUNK_SIZE,
        "replication_factor": REPLICATION_FACTOR,
        "discovery_url": DISCOVERY_URL,
    })


@app.route("/discovery-url", methods=["GET"])
def get_discovery_url():
    """
    Get the discovery URL for nodes to connect to.
    This helps nodes auto-configure when downloading from this server.
    """
    return jsonify({
        "discovery_url": DISCOVERY_URL,
        "note": "Use this URL when setting up your storage node"
    })


# =============================================================================
# Authentication
# =============================================================================

@app.route("/auth/register", methods=["POST"])
def register():
    """
    Register a new user.
    
    Expected JSON:
    {
        "username": "string",
        "password": "string",
        "email": "optional string"
    }
    """
    data = request.get_json()
    
    username = data.get("username", "").strip()
    password = data.get("password", "")
    email = data.get("email", "").strip() or None
    
    user, error = register_user(username, password, email)
    
    if error:
        return jsonify({"error": error}), 400
    
    return jsonify({
        "status": "registered",
        "user": user.to_dict(),
    })


@app.route("/auth/login", methods=["POST"])
def login():
    """
    Login and get JWT token.
    
    Expected JSON:
    {
        "username": "string",
        "password": "string"
    }
    
    Returns:
    {
        "token": "jwt-token",
        "user": { ... }
    }
    """
    data = request.get_json()
    
    username = data.get("username", "").strip()
    password = data.get("password", "")
    
    token, user, error = login_user(username, password)
    
    if error:
        return jsonify({"error": error}), 401
    
    return jsonify({
        "token": token,
        "user": user.to_dict(),
    })


@app.route("/auth/me", methods=["GET"])
@login_required
def me():
    """Get current user info."""
    return jsonify({"user": g.current_user.to_dict()})


@app.route("/auth/status", methods=["GET"])
def auth_status():
    """Check authentication status."""
    user = get_current_user()
    if user:
        return jsonify({
            "logged_in": True,
            "user": user.to_dict(),
        })
    return jsonify({"logged_in": False})


# =============================================================================
# File Upload
# =============================================================================

@app.route("/upload", methods=["POST"])
@login_required
def upload_file():
    """
    Upload a file with encryption and distribution.
    
    Requires:
    - Authorization: Bearer <token>
    - X-User-Password: <password>  (for key derivation)
    - file: multipart file
    
    Process:
    1. Receive file
    2. Generate file encryption key
    3. Chunk file
    4. Encrypt each chunk
    5. Distribute encrypted chunks to peers
    6. Compute Merkle root
    7. Encrypt file key with user's derived key
    8. Store metadata on blockchain
    """
    user = g.current_user
    
    # Get user's encryption key
    user_key = get_user_key_from_header(user)
    if not user_key:
        return jsonify({"error": "X-User-Password header required for encryption"}), 400
    
    # Get file
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "No filename"}), 400
    
    filename = secure_filename(file.filename)
    file_id = str(uuid.uuid4())
    timestamp = int(time.time())
    
    LOG.info(f"Upload started: {filename} by user {user.username}")
    
    # Save file temporarily
    temp_path = TEMP_STORAGE / f"{file_id}_{filename}"
    file.save(str(temp_path))
    file_size = temp_path.stat().st_size
    
    try:
        # Generate file encryption key
        file_key = generate_file_key()
        
        # Chunk, encrypt, and distribute
        chunk_hashes = []
        chunk_records = []
        
        for idx, chunk_data, chunk_hash in chunk_file(file_path=temp_path, chunk_size=CHUNK_SIZE):
            # Encrypt chunk
            encrypted_chunk = encrypt_chunk(chunk_data, file_key)
            encrypted_hash = compute_hash(encrypted_chunk)
            
            # Distribute to peers
            assignments = uploader.distribute_chunk(
                chunk_data=encrypted_chunk,
                chunk_hash=encrypted_hash,
                discovery_url=DISCOVERY_URL,
                replication=REPLICATION_FACTOR,
            )
            
            chunk_hashes.append(chunk_hash)  # Original hash for Merkle tree
            chunk_records.append({
                "index": idx,
                "original_hash": chunk_hash,  # Hash of plaintext (for Merkle)
                "encrypted_hash": encrypted_hash,  # Hash of ciphertext (for retrieval)
                "size": len(encrypted_chunk),
                "assignments": assignments,
            })
            
            LOG.debug(f"Chunk {idx}: {len(assignments)} assignments")
        
        # Compute Merkle root (from original plaintext hashes)
        merkle_root = compute_merkle_root(chunk_hashes)
        
        # Encrypt file key with user's key
        encrypted_file_key = encrypt_file_key(file_key, user_key)
        
        # Compute file hash
        file_hash = compute_hash(temp_path.read_bytes())
        
        # Build metadata
        metadata = {
            "file_id": file_id,
            "owner_id": user.id,
            "owner_username": user.username,
            "filename": filename,
            "file_size": file_size,
            "file_hash": file_hash,
            "merkle_root": merkle_root,
            "chunk_count": len(chunk_records),
            "chunk_size": CHUNK_SIZE,
            "chunks": chunk_records,
            "encrypted_file_key": b64_encode(encrypted_file_key),
            "timestamp": timestamp,
            "created_at": datetime.utcnow().isoformat(),
        }
        
        # Add to blockchain
        block = blockchain.add_block(metadata)
        
        LOG.info(f"Upload complete: {filename} ({len(chunk_records)} chunks) -> block {block['index']}")
        
        # Update user's storage usage
        session = get_session()
        try:
            user_record = session.query(User).filter_by(id=user.id).first()
            if user_record:
                user_record.storage_used_bytes += file_size
                session.commit()
        finally:
            session.close()
        
        return jsonify({
            "status": "ok",
            "file_id": file_id,
            "filename": filename,
            "file_size": file_size,
            "chunk_count": len(chunk_records),
            "merkle_root": merkle_root,
            "block_index": block["index"],
            "block_hash": block["hash"],
        })
        
    finally:
        # Clean up temp file
        if temp_path.exists():
            temp_path.unlink()


# =============================================================================
# File Retrieval
# =============================================================================

@app.route("/download/<file_id>", methods=["GET"])
@login_required
def download_file(file_id: str):
    """
    Download and reassemble a file.
    
    Requires:
    - Authorization: Bearer <token>
    - X-User-Password: <password>  (for key derivation)
    
    Process:
    1. Find file metadata on blockchain
    2. Verify ownership
    3. Get user's key and decrypt file key
    4. Fetch chunks from peers
    5. Decrypt chunks
    6. Verify Merkle root
    7. Stream reassembled file
    """
    user = g.current_user
    
    # Get user's encryption key
    user_key = get_user_key_from_header(user)
    if not user_key:
        return jsonify({"error": "X-User-Password header required for decryption"}), 400
    
    # Find file metadata
    metadata = blockchain.get_file_metadata(file_id)
    if not metadata:
        return jsonify({"error": "File not found"}), 404
    
    # Verify ownership
    if metadata.get("owner_id") != user.id:
        LOG.warning(f"Access denied: {user.username} tried to access file owned by {metadata.get('owner_id')}")
        return jsonify({"error": "Access denied"}), 403
    
    LOG.info(f"Download started: {metadata['filename']} by {user.username}")
    
    try:
        # Decrypt file key
        encrypted_file_key = b64_decode(metadata["encrypted_file_key"])
        file_key = decrypt_file_key(encrypted_file_key, user_key)
    except Exception as e:
        LOG.error(f"Failed to decrypt file key: {e}")
        return jsonify({"error": "Failed to decrypt file key (wrong password?)"}), 400
    
    # Sort chunks by index
    chunks = sorted(metadata["chunks"], key=lambda c: c["index"])
    
    def generate():
        """Generator that fetches, decrypts, and yields chunks."""
        decrypted_hashes = []
        
        for chunk_record in chunks:
            encrypted_hash = chunk_record["encrypted_hash"]
            original_hash = chunk_record["original_hash"]
            assignments = chunk_record.get("assignments", [])
            
            # Fetch encrypted chunk from peers
            encrypted_chunk = uploader.fetch_chunk(
                chunk_hash=encrypted_hash,
                assignments=assignments,
                discovery_url=DISCOVERY_URL,
            )
            
            if encrypted_chunk is None:
                raise Exception(f"Failed to fetch chunk {chunk_record['index']}")
            
            # Verify encrypted chunk hash
            if compute_hash(encrypted_chunk) != encrypted_hash:
                raise Exception(f"Encrypted chunk {chunk_record['index']} corrupted")
            
            # Decrypt chunk
            try:
                decrypted_chunk = decrypt_chunk(encrypted_chunk, file_key)
            except Exception as e:
                raise Exception(f"Failed to decrypt chunk {chunk_record['index']}: {e}")
            
            # Verify decrypted chunk hash
            if not verify_chunk_hash(decrypted_chunk, original_hash):
                raise Exception(f"Decrypted chunk {chunk_record['index']} hash mismatch")
            
            decrypted_hashes.append(compute_hash(decrypted_chunk))
            yield decrypted_chunk
        
        # Verify Merkle root
        computed_merkle = compute_merkle_root(decrypted_hashes)
        if computed_merkle != metadata["merkle_root"]:
            LOG.error(f"Merkle root mismatch: expected {metadata['merkle_root']}, got {computed_merkle}")
            # Note: We've already yielded data, so we can't return an error here
            # In production, you might buffer the entire file first
    
    LOG.info(f"Download complete: {metadata['filename']}")
    
    return Response(
        generate(),
        mimetype="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{metadata["filename"]}"',
            "Content-Length": str(metadata["file_size"]),
        }
    )


# =============================================================================
# User's Files (Privacy-Filtered)
# =============================================================================

@app.route("/my-files", methods=["GET"])
@login_required
def my_files():
    """
    Get list of current user's files.
    
    This is the privacy-filtered view - only shows files
    owned by the authenticated user.
    """
    user = g.current_user
    files = blockchain.get_user_files(user.id)
    
    # Remove sensitive data
    sanitized = []
    for f in files:
        sanitized.append({
            "file_id": f["file_id"],
            "filename": f["filename"],
            "file_size": f["file_size"],
            "chunk_count": f["chunk_count"],
            "merkle_root": f["merkle_root"],
            "timestamp": f["timestamp"],
            "created_at": f.get("created_at"),
            "block_index": f.get("block_index"),
        })
    
    return jsonify({
        "files": sanitized,
        "count": len(sanitized),
    })


@app.route("/file/<file_id>", methods=["GET"])
@login_required
def get_file_info(file_id: str):
    """Get detailed info about a specific file."""
    user = g.current_user
    metadata = blockchain.get_file_metadata(file_id)
    
    if not metadata:
        return jsonify({"error": "File not found"}), 404
    
    if metadata.get("owner_id") != user.id:
        return jsonify({"error": "Access denied"}), 403
    
    # Return metadata (without encrypted key)
    return jsonify({
        "file_id": metadata["file_id"],
        "filename": metadata["filename"],
        "file_size": metadata["file_size"],
        "file_hash": metadata["file_hash"],
        "merkle_root": metadata["merkle_root"],
        "chunk_count": metadata["chunk_count"],
        "chunks": [
            {
                "index": c["index"],
                "size": c["size"],
                "assignments": [
                    {"node_id": a.get("node_id"), "status": a.get("status")}
                    for a in c.get("assignments", [])
                ],
            }
            for c in metadata["chunks"]
        ],
        "timestamp": metadata["timestamp"],
    })


@app.route("/file/<file_id>", methods=["DELETE"])
@app.route("/delete/<file_id>", methods=["DELETE"])  # Alias for frontend compatibility
@login_required
def delete_file(file_id: str):
    """
    Mark a file as deleted.

    Note: This doesn't actually delete chunks from storage nodes.
    In production, you'd need a garbage collection mechanism.
    """
    user = g.current_user
    metadata = blockchain.get_file_metadata(file_id)

    if not metadata:
        return jsonify({"error": "File not found"}), 404

    if metadata.get("owner_id") != user.id:
        return jsonify({"error": "Access denied"}), 403

    # Add deletion record to blockchain
    deletion_record = {
        "type": "deletion",
        "file_id": file_id,
        "owner_id": user.id,
        "timestamp": int(time.time()),
    }

    block = blockchain.add_block(deletion_record)

    LOG.info(f"File marked deleted: {file_id} by {user.username}")

    return jsonify({
        "status": "deleted",
        "file_id": file_id,
        "block_index": block["index"],
    })


# =============================================================================
# File Sharing (Simplified - without key re-encryption)
# =============================================================================

@app.route("/share/<file_id>", methods=["POST"])
@login_required
def share_file(file_id: str):
    """
    Share a file with another user.

    Note: This is a simplified implementation that just marks the file as shared.
    Full implementation would require re-encrypting the file key for the recipient.
    """
    user = g.current_user
    data = request.get_json()
    target_username = data.get("username", "").strip()

    if not target_username:
        return jsonify({"error": "Target username required"}), 400

    # Verify file exists and user owns it
    metadata = blockchain.get_file_metadata(file_id)
    if not metadata:
        return jsonify({"error": "File not found"}), 404

    if metadata.get("owner_id") != user.id:
        return jsonify({"error": "You can only share your own files"}), 403

    # Verify target user exists
    session = get_session()
    try:
        target_user = session.query(User).filter_by(username=target_username).first()
        if not target_user:
            return jsonify({"error": f"User '{target_username}' not found"}), 404

        # Add share record to blockchain
        share_record = {
            "type": "share",
            "file_id": file_id,
            "owner_id": user.id,
            "shared_with_id": target_user.id,
            "shared_with_username": target_username,
            "timestamp": int(time.time()),
        }

        block = blockchain.add_block(share_record)

        LOG.info(f"File {file_id} shared by {user.username} with {target_username}")

        return jsonify({
            "status": "shared",
            "file_id": file_id,
            "shared_with": target_username,
            "block_index": block["index"],
        })
    finally:
        session.close()


@app.route("/shared-with-me", methods=["GET"])
@login_required
def shared_with_me():
    """
    Get list of files shared with the current user.

    Note: This is a simplified implementation. Downloads won't work without key sharing.
    """
    user = g.current_user

    # Find share records for this user
    shared_files = []
    chain = blockchain.get_chain()

    for block in chain:
        data = block.get("data", {})
        if data.get("type") == "share" and data.get("shared_with_id") == user.id:
            # Get the original file metadata
            file_id = data.get("file_id")
            file_metadata = blockchain.get_file_metadata(file_id)

            if file_metadata:
                shared_files.append({
                    "file_id": file_id,
                    "filename": file_metadata.get("filename"),
                    "size": file_metadata.get("file_size"),
                    "shared_at": data.get("timestamp"),
                    "owner": data.get("owner_username", "Unknown"),
                })

    return jsonify({
        "files": shared_files,
        "count": len(shared_files),
    })


@app.route("/blockchain/my-blocks", methods=["GET"])
@login_required
def my_blocks():
    """Get blocks created by the current user."""
    user = g.current_user
    chain = blockchain.get_chain()

    user_blocks = []
    for block in chain:
        data = block.get("data", {})
        if data.get("owner_id") == user.id:
            # Format block for frontend
            user_blocks.append({
                "index": block["index"],
                "hash": block["hash"],
                "previous_hash": block.get("prev_hash", ""),
                "timestamp": block["timestamp"],
                "filename": data.get("filename"),
                "file_id": data.get("file_id"),
                "size": data.get("file_size", 0),
                "chunks": data.get("chunk_count", 0),
                "merkle_root": data.get("merkle_root"),
            })

    return jsonify({
        "blocks": user_blocks,
        "total": len(user_blocks),
    })


# =============================================================================
# Blockchain Explorer (Public but Anonymized)
# =============================================================================

@app.route("/blockchain/stats", methods=["GET"])
def blockchain_stats():
    """Get blockchain statistics."""
    return jsonify(blockchain.get_stats())


@app.route("/blockchain/blocks", methods=["GET"])
def list_blocks():
    """
    List recent blocks (anonymized).
    
    Public endpoint but doesn't reveal file ownership or names.
    """
    limit = min(int(request.args.get("limit", 20)), 100)
    offset = int(request.args.get("offset", 0))
    
    chain = blockchain.get_chain()
    
    # Anonymize blocks
    blocks = []
    for block in chain[offset:offset + limit]:
        data = block.get("data", {})
        
        # Only show non-sensitive info
        blocks.append({
            "index": block["index"],
            "hash": block["hash"],
            "prev_hash": block["prev_hash"],
            "timestamp": block["timestamp"],
            "type": "file" if data.get("file_id") else data.get("type", "unknown"),
            "file_size": data.get("file_size"),  # Size is not sensitive
            "chunk_count": data.get("chunk_count"),
        })
    
    return jsonify({
        "blocks": blocks,
        "total": len(chain),
        "offset": offset,
        "limit": limit,
    })


# =============================================================================
# Network Status
# =============================================================================

@app.route("/network/peers", methods=["GET"])
def network_peers():
    """Get list of active storage peers."""
    peers = uploader.get_peers(DISCOVERY_URL)
    
    # Anonymize peer list
    return jsonify({
        "peers": [
            {
                "node_id": p.get("node_id"),
                "capacity_gb": p.get("capacity_gb"),
                "last_seen": p.get("last_heartbeat"),
            }
            for p in peers
        ],
        "count": len(peers),
    })


# =============================================================================
# Node Software Download
# =============================================================================

@app.route("/download-node", methods=["GET"])
def download_node_software():
    """
    Download the standalone node software package.
    Returns a zip file with everything needed to run a storage node.
    """
    import zipfile
    import io
    
    # Create in-memory zip
    zip_buffer = io.BytesIO()
    node_package_dir = Path(__file__).parent.parent / "node_package"
    
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add all files from node_package directory
        if node_package_dir.exists():
            for file_path in node_package_dir.iterdir():
                if file_path.is_file():
                    zf.write(file_path, f"decentra-node/{file_path.name}")
        else:
            # Fallback: Create minimal package inline
            storage_node_code = '''#!/usr/bin/env python3
"""DecentraStore Storage Node - Standalone"""
# Download the full package from the website
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
    """Start the backend server."""
    LOG.info(f"Starting backend server on {host}:{port}")
    LOG.info(f"Discovery URL: {DISCOVERY_URL}")
    LOG.info(f"Chunk size: {CHUNK_SIZE} bytes")
    LOG.info(f"Replication factor: {REPLICATION_FACTOR}")
    
    # Ensure frontend directory exists
    if not FRONTEND_DIR.exists():
        LOG.warning(f"Frontend directory not found: {FRONTEND_DIR}")
    
    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="DecentraStore Backend Server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    parser.add_argument("--port", "-p", type=int, default=5000, help="Bind port")
    parser.add_argument("--discovery", "-d", default=None, help="Discovery service URL")
    parser.add_argument("--debug", action="store_true", help="Debug mode")
    
    args = parser.parse_args()
    
    if args.discovery:
        DISCOVERY_URL = args.discovery
    
    start_server(host=args.host, port=args.port, debug=args.debug)
