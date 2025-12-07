# config.py
"""
Central configuration for DecentraStore.
Can be overridden via environment variables.
"""

import os
import secrets
from pathlib import Path

# Base directories
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Discovery Service
DISCOVERY_URL = os.environ.get("DISCOVERY_URL", "http://localhost:4000")

# Chunk settings
CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", 256 * 1024))  # 256 KB default
REPLICATION_FACTOR = int(os.environ.get("REPLICATION", 3))

# Network timeouts (seconds)
PEER_TIMEOUT = float(os.environ.get("PEER_TIMEOUT", 10.0))
DISCOVERY_TIMEOUT = float(os.environ.get("DISCOVERY_TIMEOUT", 5.0))
UPLOAD_TIMEOUT = float(os.environ.get("UPLOAD_TIMEOUT", 30.0))

# Node settings
NODE_HEARTBEAT_INTERVAL = int(os.environ.get("NODE_HEARTBEAT_INTERVAL", 15))  # seconds
NODE_TTL = int(os.environ.get("NODE_TTL", 60))  # seconds before node considered dead

# Security
SECRET_KEY = os.environ.get("SECRET_KEY", secrets.token_hex(32))
JWT_EXPIRY_HOURS = int(os.environ.get("JWT_EXPIRY_HOURS", 24))
BCRYPT_ROUNDS = int(os.environ.get("BCRYPT_ROUNDS", 12))

# Encryption
# Using AES-256-GCM for chunk encryption
AES_KEY_SIZE = 32  # 256 bits
AES_NONCE_SIZE = 12  # 96 bits for GCM
AES_TAG_SIZE = 16  # 128 bits

# Key derivation (Argon2-like via PBKDF2 with high iterations)
KDF_ITERATIONS = int(os.environ.get("KDF_ITERATIONS", 100000))
KDF_SALT_SIZE = 16

# Database
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DATA_DIR / 'users.db'}")

# Blockchain
BLOCKCHAIN_PATH = Path(os.environ.get("BLOCKCHAIN_PATH", DATA_DIR / "blockchain.json"))

# Backend storage (temporary, for chunks before distribution)
TEMP_STORAGE = DATA_DIR / "temp"
TEMP_STORAGE.mkdir(parents=True, exist_ok=True)

# Logging
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")


def get_node_storage_dir(node_id: str = None) -> Path:
    """Get storage directory for a node."""
    base = Path(os.environ.get("NODE_STORAGE_DIR", DATA_DIR / "node_storage"))
    if node_id:
        base = base / node_id
    base.mkdir(parents=True, exist_ok=True)
    return base
