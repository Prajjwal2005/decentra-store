# shared/__init__.py
"""
Shared modules for DecentraStore.
"""

from .crypto import (
    generate_file_key,
    encrypt_chunk,
    decrypt_chunk,
    derive_key_from_password,
    encrypt_file_key,
    decrypt_file_key,
)

from .chunker import (
    chunk_file,
    chunk_data,
    chunk_bytes,
    sha256_bytes,
    compute_merkle_root,
    compute_hash,
    verify_chunk_hash,
    reassemble_chunks,
)

from .blockchain import SimpleBlockchain

__all__ = [
    "generate_file_key",
    "encrypt_chunk",
    "decrypt_chunk",
    "derive_key_from_password",
    "encrypt_file_key",
    "decrypt_file_key",
    "chunk_file",
    "chunk_data",
    "chunk_bytes",
    "sha256_bytes",
    "compute_merkle_root",
    "compute_hash",
    "verify_chunk_hash",
    "reassemble_chunks",
    "SimpleBlockchain",
]
