# shared/blockchain.py
"""
Simple blockchain for storing file metadata in DecentraStore.

Features:
- JSON-persisted chain
- SHA-256 block hashing
- Tamper-evident linked blocks
- Query by owner_id for privacy filtering
"""

import json
import hashlib
import time
import threading
from pathlib import Path
from typing import List, Dict, Optional, Any

import sys
sys.path.insert(0, str(__file__).rsplit("/", 2)[0])
from config import BLOCKCHAIN_PATH


class Block:
    """Single block in the chain."""
    
    def __init__(
        self,
        index: int,
        prev_hash: str,
        data: Dict[str, Any],
        timestamp: int = None,
    ):
        self.index = index
        self.prev_hash = prev_hash
        self.data = data
        self.timestamp = timestamp or int(time.time())
        self.hash = self.compute_hash()
    
    def compute_hash(self) -> str:
        """Compute SHA-256 hash of block contents."""
        payload = json.dumps(
            {
                "index": self.index,
                "prev_hash": self.prev_hash,
                "data": self.data,
                "timestamp": self.timestamp,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode()).hexdigest()
    
    def to_dict(self) -> Dict:
        """Convert block to dictionary."""
        return {
            "index": self.index,
            "prev_hash": self.prev_hash,
            "data": self.data,
            "timestamp": self.timestamp,
            "hash": self.hash,
        }
    
    @classmethod
    def from_dict(cls, d: Dict) -> "Block":
        """Create block from dictionary."""
        block = cls(
            index=d["index"],
            prev_hash=d["prev_hash"],
            data=d["data"],
            timestamp=d["timestamp"],
        )
        # Verify hash matches
        if block.hash != d.get("hash"):
            raise ValueError(f"Block hash mismatch at index {d['index']}")
        return block


class SimpleBlockchain:
    """
    Simple JSON-persisted blockchain for file metadata.
    
    Each block contains:
    - File metadata (filename, size, merkle_root, etc.)
    - Owner ID (for filtering)
    - Encrypted file key (only owner can decrypt)
    - Chunk locations
    """
    
    def __init__(self, path: Path = None):
        self.path = Path(path) if path else BLOCKCHAIN_PATH
        self.lock = threading.Lock()
        self.chain: List[Dict] = []
        self._load()
    
    def _load(self):
        """Load chain from disk."""
        try:
            if self.path.exists():
                with open(self.path, "r") as f:
                    self.chain = json.load(f)
                # Validate chain integrity
                self._validate_chain()
        except Exception as e:
            print(f"[blockchain] Error loading chain: {e}, starting fresh")
            self.chain = []
    
    def _save(self):
        """Persist chain to disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w") as f:
            json.dump(self.chain, f, indent=2)
    
    def _validate_chain(self):
        """Validate chain integrity."""
        for i, block in enumerate(self.chain):
            # Check index
            if block["index"] != i:
                raise ValueError(f"Invalid index at position {i}")
            
            # Check prev_hash
            if i == 0:
                expected_prev = "0" * 64
            else:
                expected_prev = self.chain[i - 1]["hash"]
            
            if block["prev_hash"] != expected_prev:
                raise ValueError(f"Invalid prev_hash at index {i}")
            
            # Verify hash
            computed = Block(
                index=block["index"],
                prev_hash=block["prev_hash"],
                data=block["data"],
                timestamp=block["timestamp"],
            ).compute_hash()
            
            if computed != block["hash"]:
                raise ValueError(f"Hash mismatch at index {i}")
    
    def get_last_hash(self) -> str:
        """Get hash of the last block, or genesis hash if empty."""
        if not self.chain:
            return "0" * 64
        return self.chain[-1]["hash"]
    
    def add_block(self, data: Dict[str, Any]) -> Dict:
        """
        Add a new block to the chain.
        
        Args:
            data: Block data (file metadata)
        
        Returns:
            The new block as dictionary
        """
        with self.lock:
            index = len(self.chain)
            prev_hash = self.get_last_hash()
            
            block = Block(
                index=index,
                prev_hash=prev_hash,
                data=data,
            )
            
            entry = block.to_dict()
            self.chain.append(entry)
            self._save()
            
            return entry
    
    def get_chain(self) -> List[Dict]:
        """Get the full chain."""
        return self.chain.copy()
    
    def get_block(self, index: int) -> Optional[Dict]:
        """Get block by index."""
        if 0 <= index < len(self.chain):
            return self.chain[index]
        return None
    
    def get_blocks_by_owner(self, owner_id: str) -> List[Dict]:
        """
        Get all blocks owned by a specific user.
        This is the primary privacy filter.
        """
        return [
            block for block in self.chain
            if block.get("data", {}).get("owner_id") == owner_id
        ]
    
    def get_file_metadata(self, file_id: str) -> Optional[Dict]:
        """
        Find file metadata by file_id.
        Returns the block's data if found.
        """
        for block in self.chain:
            if block.get("data", {}).get("file_id") == file_id:
                return block["data"]
        return None
    
    def get_file_by_stored_name(self, stored_name: str) -> Optional[Dict]:
        """
        Find file metadata by stored_name.
        """
        for block in self.chain:
            if block.get("data", {}).get("stored_name") == stored_name:
                return block["data"]
        return None
    
    def get_user_files(self, owner_id: str) -> List[Dict]:
        """
        Get all file metadata for a user.
        Returns list of file data dictionaries.
        """
        files = []
        for block in self.chain:
            data = block.get("data", {})
            if data.get("owner_id") == owner_id and data.get("file_id"):
                files.append({
                    "block_index": block["index"],
                    "block_hash": block["hash"],
                    "timestamp": block["timestamp"],
                    **data,
                })
        return files
    
    def verify_ownership(self, file_id: str, owner_id: str) -> bool:
        """
        Verify that a file belongs to a specific owner.
        """
        metadata = self.get_file_metadata(file_id)
        if metadata:
            return metadata.get("owner_id") == owner_id
        return False
    
    def get_stats(self) -> Dict:
        """Get blockchain statistics."""
        total_files = sum(
            1 for block in self.chain
            if block.get("data", {}).get("file_id")
        )
        total_size = sum(
            block.get("data", {}).get("size", 0)
            for block in self.chain
        )
        unique_owners = len(set(
            block.get("data", {}).get("owner_id")
            for block in self.chain
            if block.get("data", {}).get("owner_id")
        ))
        
        return {
            "block_count": len(self.chain),
            "file_count": total_files,
            "total_size_bytes": total_size,
            "unique_owners": unique_owners,
            "last_block_time": self.chain[-1]["timestamp"] if self.chain else None,
        }
