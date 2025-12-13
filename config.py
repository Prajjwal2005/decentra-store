# config.py
"""
Central configuration for DecentraStore.
Can be overridden via environment variables.

PRODUCTION DEPLOYMENT (Railway/Render/Heroku):
Required environment variables:
  - SECRET_KEY: A secure random string (use: python -c "import secrets; print(secrets.token_hex(32))")
  - DATABASE_URL: PostgreSQL connection string (provided by Railway PostgreSQL addon)

Optional environment variables:
  - ALLOWED_ORIGINS: Comma-separated list of allowed CORS origins (default: *)
  - MAX_UPLOAD_SIZE: Maximum file upload size in bytes (default: 104857600 = 100MB)
  - JWT_EXPIRY_HOURS: JWT token expiry in hours (default: 24)
  - REPLICATION: Number of chunk copies across nodes (default: 3)
  - NODE_TTL: Seconds before node considered offline (default: 60)
"""

import os
import secrets
from pathlib import Path

# Detect production environment (Railway, Render, Heroku, etc.)
IS_PRODUCTION = bool(os.environ.get("RAILWAY_ENVIRONMENT") or
                     os.environ.get("RENDER") or
                     os.environ.get("DYNO") or
                     os.environ.get("PRODUCTION"))

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
# In production, SECRET_KEY MUST be set via environment variable
# If not set, generate a random one (acceptable for development only)
_secret_key = os.environ.get("SECRET_KEY")
if not _secret_key:
    if IS_PRODUCTION:
        import warnings
        warnings.warn(
            "CRITICAL: SECRET_KEY not set in production! "
            "JWT tokens will invalidate on every restart. "
            "Set SECRET_KEY in Railway environment variables.",
            RuntimeWarning
        )
    _secret_key = secrets.token_hex(32)
SECRET_KEY = _secret_key

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

# =============================================================================
# Consensus Configuration (Proof of Storage + Quorum)
# =============================================================================
# Minimum nodes required to confirm storage before block is finalized
CONSENSUS_MIN_CONFIRMATIONS = int(os.environ.get("CONSENSUS_MIN_CONFIRMATIONS", 1))

# Percentage of nodes that must confirm (if more nodes available than minimum)
# e.g., 0.67 means 2/3 of nodes must confirm
CONSENSUS_QUORUM_PERCENT = float(os.environ.get("CONSENSUS_QUORUM_PERCENT", 0.67))

# Timeout for waiting for node confirmations (seconds)
CONSENSUS_TIMEOUT = int(os.environ.get("CONSENSUS_TIMEOUT", 60))

# Whether to allow blocks without consensus (for single-node testing)
CONSENSUS_ALLOW_PENDING = os.environ.get("CONSENSUS_ALLOW_PENDING", "true").lower() == "true"


def get_node_storage_dir(node_id: str = None) -> Path:
    """Get storage directory for a node."""
    base = Path(os.environ.get("NODE_STORAGE_DIR", DATA_DIR / "node_storage"))
    if node_id:
        base = base / node_id
    base.mkdir(parents=True, exist_ok=True)
    return base
