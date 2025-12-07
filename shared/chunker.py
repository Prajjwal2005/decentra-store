# shared/chunker.py
"""
File chunking and Merkle tree utilities for DecentraStore.

Provides:
- File splitting into fixed-size chunks
- Merkle tree computation for integrity verification
- Chunk reassembly with verification
"""

import hashlib
from pathlib import Path
from typing import List, Tuple, Generator, Optional, BinaryIO
import io

import sys
sys.path.insert(0, str(__file__).rsplit("/", 2)[0])
from config import CHUNK_SIZE


def sha256_bytes(data: bytes) -> str:
    """Compute SHA-256 hash of bytes, return lowercase hex string."""
    return hashlib.sha256(data).hexdigest()


def chunk_file(
    file_path: Path = None,
    file_obj: BinaryIO = None,
    chunk_size: int = CHUNK_SIZE
) -> Generator[Tuple[int, bytes, str], None, None]:
    """
    Split a file into chunks and yield (index, chunk_bytes, chunk_hash).
    
    Args:
        file_path: Path to file (mutually exclusive with file_obj)
        file_obj: File-like object (mutually exclusive with file_path)
        chunk_size: Size of each chunk in bytes
    
    Yields:
        (chunk_index, chunk_bytes, sha256_hash)
    """
    if file_path and file_obj:
        raise ValueError("Provide either file_path or file_obj, not both")
    
    if file_path:
        f = open(file_path, "rb")
        should_close = True
    elif file_obj:
        f = file_obj
        should_close = False
    else:
        raise ValueError("Must provide file_path or file_obj")
    
    try:
        idx = 0
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            chunk_hash = sha256_bytes(chunk)
            yield (idx, chunk, chunk_hash)
            idx += 1
    finally:
        if should_close:
            f.close()


def chunk_bytes(data: bytes, chunk_size: int = CHUNK_SIZE) -> Generator[Tuple[int, bytes, str], None, None]:
    """
    Split bytes into chunks and yield (index, chunk_bytes, chunk_hash).
    """
    return chunk_file(file_obj=io.BytesIO(data), chunk_size=chunk_size)


def compute_merkle_root(chunk_hashes: List[str]) -> str:
    """
    Compute Merkle root from a list of chunk hashes.
    
    Algorithm:
    - Leaf nodes are the chunk hashes (already SHA-256)
    - Parent = SHA-256(left_child || right_child)
    - If odd number of nodes, duplicate the last one
    - Return the root hash
    
    Args:
        chunk_hashes: List of hex-encoded SHA-256 hashes
    
    Returns:
        Merkle root as hex string
    """
    if not chunk_hashes:
        # Empty file: hash of empty string
        return hashlib.sha256(b"").hexdigest()
    
    # Convert hex strings to bytes
    layer = [bytes.fromhex(h) for h in chunk_hashes]
    
    while len(layer) > 1:
        # If odd, duplicate last
        if len(layer) % 2 == 1:
            layer.append(layer[-1])
        
        # Compute next layer
        next_layer = []
        for i in range(0, len(layer), 2):
            combined = layer[i] + layer[i + 1]
            parent_hash = hashlib.sha256(combined).digest()
            next_layer.append(parent_hash)
        
        layer = next_layer
    
    return layer[0].hex()


def build_merkle_tree(chunk_hashes: List[str]) -> List[List[str]]:
    """
    Build full Merkle tree and return all layers (for debugging/proofs).
    
    Returns:
        List of layers, from leaves (index 0) to root (last index)
    """
    if not chunk_hashes:
        return [[hashlib.sha256(b"").hexdigest()]]
    
    layers = [chunk_hashes.copy()]
    current = [bytes.fromhex(h) for h in chunk_hashes]
    
    while len(current) > 1:
        if len(current) % 2 == 1:
            current.append(current[-1])
        
        next_layer = []
        next_layer_hex = []
        for i in range(0, len(current), 2):
            combined = current[i] + current[i + 1]
            parent = hashlib.sha256(combined).digest()
            next_layer.append(parent)
            next_layer_hex.append(parent.hex())
        
        current = next_layer
        layers.append(next_layer_hex)
    
    return layers


def verify_chunk_hash(chunk_data: bytes, expected_hash: str) -> bool:
    """
    Verify that chunk data matches expected SHA-256 hash.
    """
    actual_hash = sha256_bytes(chunk_data)
    return actual_hash == expected_hash.lower()


def verify_merkle_root(chunk_hashes: List[str], expected_root: str) -> bool:
    """
    Verify that chunk hashes produce the expected Merkle root.
    """
    computed_root = compute_merkle_root(chunk_hashes)
    return computed_root == expected_root.lower()


def reassemble_chunks(
    chunks: List[Tuple[int, bytes]],
    output_path: Path = None,
    expected_file_hash: str = None
) -> Tuple[bool, bytes, str]:
    """
    Reassemble chunks into original file.
    
    Args:
        chunks: List of (index, chunk_bytes) in any order
        output_path: Optional path to write reassembled file
        expected_file_hash: Optional SHA-256 hash to verify
    
    Returns:
        (success, file_bytes, actual_hash)
    """
    # Sort by index
    sorted_chunks = sorted(chunks, key=lambda x: x[0])
    
    # Verify indices are contiguous
    for i, (idx, _) in enumerate(sorted_chunks):
        if idx != i:
            return (False, b"", f"Missing chunk at index {i}")
    
    # Reassemble
    file_data = b"".join(chunk for _, chunk in sorted_chunks)
    actual_hash = sha256_bytes(file_data)
    
    # Write to file if requested
    if output_path:
        with open(output_path, "wb") as f:
            f.write(file_data)
    
    # Verify hash if provided
    if expected_file_hash:
        if actual_hash != expected_file_hash.lower():
            return (False, file_data, actual_hash)
    
    return (True, file_data, actual_hash)


def compute_file_hash(file_path: Path = None, file_obj: BinaryIO = None) -> str:
    """
    Compute SHA-256 hash of entire file.
    """
    h = hashlib.sha256()
    
    if file_path:
        with open(file_path, "rb") as f:
            while True:
                data = f.read(8192)
                if not data:
                    break
                h.update(data)
    elif file_obj:
        pos = file_obj.tell()
        file_obj.seek(0)
        while True:
            data = file_obj.read(8192)
            if not data:
                break
            h.update(data)
        file_obj.seek(pos)
    else:
        raise ValueError("Must provide file_path or file_obj")
    
    return h.hexdigest()
