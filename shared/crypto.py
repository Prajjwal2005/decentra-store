# shared/crypto.py
"""
Cryptographic utilities for DecentraStore.

Security model:
- Each file gets a unique AES-256-GCM key
- Chunks are encrypted with the file key
- File key is encrypted with user's derived key (from password)
- User's derived key uses PBKDF2-SHA256 with high iterations
"""

import os
import hashlib
import base64
from typing import Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend

import sys
sys.path.insert(0, str(__file__).rsplit("/", 2)[0])
from config import (
    AES_KEY_SIZE,
    AES_NONCE_SIZE,
    KDF_ITERATIONS,
    KDF_SALT_SIZE,
)


def generate_file_key() -> bytes:
    """
    Generate a random AES-256 key for encrypting a file's chunks.
    Returns 32 bytes of cryptographically secure random data.
    """
    return os.urandom(AES_KEY_SIZE)


def encrypt_chunk(chunk_data: bytes, key: bytes) -> bytes:
    """
    Encrypt a chunk using AES-256-GCM.
    
    Args:
        chunk_data: Raw chunk bytes
        key: 32-byte AES key
    
    Returns:
        nonce (12 bytes) || ciphertext || tag (16 bytes)
    """
    if len(key) != AES_KEY_SIZE:
        raise ValueError(f"Key must be {AES_KEY_SIZE} bytes")
    
    nonce = os.urandom(AES_NONCE_SIZE)
    aesgcm = AESGCM(key)
    
    # GCM automatically appends the authentication tag
    ciphertext = aesgcm.encrypt(nonce, chunk_data, associated_data=None)
    
    # Return nonce || ciphertext (includes tag)
    return nonce + ciphertext


def decrypt_chunk(encrypted_data: bytes, key: bytes) -> bytes:
    """
    Decrypt a chunk encrypted with AES-256-GCM.
    
    Args:
        encrypted_data: nonce || ciphertext || tag
        key: 32-byte AES key
    
    Returns:
        Decrypted chunk bytes
    
    Raises:
        cryptography.exceptions.InvalidTag: If authentication fails
    """
    if len(key) != AES_KEY_SIZE:
        raise ValueError(f"Key must be {AES_KEY_SIZE} bytes")
    
    if len(encrypted_data) < AES_NONCE_SIZE + 1:
        raise ValueError("Encrypted data too short")
    
    nonce = encrypted_data[:AES_NONCE_SIZE]
    ciphertext = encrypted_data[AES_NONCE_SIZE:]
    
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, associated_data=None)


def derive_key_from_password(password: str, salt: bytes = None) -> Tuple[bytes, bytes]:
    """
    Derive an AES key from a user's password using PBKDF2-SHA256.
    
    Args:
        password: User's password string
        salt: Optional salt (generated if not provided)
    
    Returns:
        (derived_key, salt) - both as bytes
    """
    if salt is None:
        salt = os.urandom(KDF_SALT_SIZE)
    
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=AES_KEY_SIZE,
        salt=salt,
        iterations=KDF_ITERATIONS,
        backend=default_backend(),
    )
    
    derived_key = kdf.derive(password.encode("utf-8"))
    return derived_key, salt


def encrypt_file_key(file_key: bytes, user_key: bytes) -> bytes:
    """
    Encrypt the file's AES key with the user's derived key.
    This allows only the owner to decrypt their file.
    
    Args:
        file_key: The random AES key for the file
        user_key: User's key derived from password
    
    Returns:
        nonce || encrypted_file_key || tag
    """
    return encrypt_chunk(file_key, user_key)


def decrypt_file_key(encrypted_file_key: bytes, user_key: bytes) -> bytes:
    """
    Decrypt the file's AES key using the user's derived key.
    
    Args:
        encrypted_file_key: Output from encrypt_file_key
        user_key: User's key derived from password
    
    Returns:
        The original file AES key
    """
    return decrypt_chunk(encrypted_file_key, user_key)


def hash_password(password: str) -> str:
    """
    Hash a password for storage using bcrypt.
    Returns a string that can be stored in database.
    """
    import bcrypt
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """
    Verify a password against its hash.
    """
    import bcrypt
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def compute_hash(data: bytes) -> str:
    """
    Compute SHA-256 hash of data.
    Returns lowercase hex string.
    """
    return hashlib.sha256(data).hexdigest()


def encode_bytes_to_str(data: bytes) -> str:
    """Encode bytes to base64 string for JSON storage."""
    return base64.b64encode(data).decode("utf-8")


def decode_str_to_bytes(data: str) -> bytes:
    """Decode base64 string back to bytes."""
    return base64.b64decode(data.encode("utf-8"))


# Convenience aliases
b64_encode = encode_bytes_to_str
b64_decode = decode_str_to_bytes
