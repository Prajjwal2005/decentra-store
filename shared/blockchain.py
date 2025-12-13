# shared/blockchain.py
"""
Blockchain for storing file metadata in DecentraStore.

Features:
- JSON-persisted chain
- SHA-256 block hashing
- Tamper-evident linked blocks
- Query by owner_id for privacy filtering
- Proof of Storage consensus mechanism
- Block status: pending → confirmed
"""

import json
import hashlib
import time
import threading
from pathlib import Path
from typing import List, Dict, Optional, Any
from enum import Enum

import sys
sys.path.insert(0, str(__file__).rsplit("/", 2)[0])
from config import (
    BLOCKCHAIN_PATH,
    CONSENSUS_MIN_CONFIRMATIONS,
    CONSENSUS_QUORUM_PERCENT,
    CONSENSUS_ALLOW_PENDING,
)


class BlockStatus(str, Enum):
    """Block consensus status."""
    PENDING = "pending"      # Awaiting node confirmations
    CONFIRMED = "confirmed"  # Reached consensus
    REJECTED = "rejected"    # Failed to reach consensus


class Block:
    """Single block in the chain with consensus support."""

    def __init__(
        self,
        index: int,
        prev_hash: str,
        data: Dict[str, Any],
        timestamp: int = None,
        status: str = BlockStatus.PENDING,
        confirmations: List[Dict] = None,
    ):
        self.index = index
        self.prev_hash = prev_hash
        self.data = data
        self.timestamp = timestamp or int(time.time())
        self.status = status
        self.confirmations = confirmations or []
        self.hash = self.compute_hash()

    def compute_hash(self) -> str:
        """Compute SHA-256 hash of block contents (excludes status and confirmations)."""
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
            "status": self.status,
            "confirmations": self.confirmations,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "Block":
        """Create block from dictionary."""
        block = cls(
            index=d["index"],
            prev_hash=d["prev_hash"],
            data=d["data"],
            timestamp=d["timestamp"],
            status=d.get("status", BlockStatus.CONFIRMED),
            confirmations=d.get("confirmations", []),
        )
        # Verify hash matches
        if block.hash != d.get("hash"):
            raise ValueError(f"Block hash mismatch at index {d['index']}")
        return block


class ConsensusBlockchain:
    """
    Blockchain with Proof of Storage consensus mechanism.

    Consensus Flow:
    1. Block created with status='pending'
    2. Storage nodes confirm they stored the chunks
    3. Once quorum reached → status='confirmed'
    4. Rejected blocks are marked but kept for audit trail

    Each block contains:
    - File metadata (filename, size, merkle_root, etc.)
    - Owner ID (for filtering)
    - Encrypted file key (only owner can decrypt)
    - Chunk locations
    - Consensus status and confirmations
    """

    def __init__(self, path: Path = None):
        self.path = Path(path) if path else BLOCKCHAIN_PATH
        self.lock = threading.Lock()
        self.chain: List[Dict] = []
        self._pending_blocks: Dict[str, Dict] = {}  # block_hash -> block for quick lookup
        self._load()

    def _load(self):
        """Load chain from disk."""
        try:
            if self.path.exists():
                with open(self.path, "r") as f:
                    self.chain = json.load(f)
                # Migrate old blocks without status
                for block in self.chain:
                    if "status" not in block:
                        block["status"] = BlockStatus.CONFIRMED
                    if "confirmations" not in block:
                        block["confirmations"] = []
                # Validate chain integrity
                self._validate_chain()
                # Index pending blocks
                self._index_pending()
        except Exception as e:
            print(f"[blockchain] Error loading chain: {e}, starting fresh")
            self.chain = []

    def _save(self):
        """Persist chain to disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w") as f:
            json.dump(self.chain, f, indent=2)

    def _index_pending(self):
        """Index pending blocks for quick lookup."""
        self._pending_blocks = {
            block["hash"]: block
            for block in self.chain
            if block.get("status") == BlockStatus.PENDING
        }

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

    def calculate_required_confirmations(self, total_nodes: int) -> int:
        """
        Calculate required confirmations based on quorum.

        Uses the higher of:
        - Minimum confirmations setting
        - Quorum percentage of available nodes
        """
        quorum_count = max(1, int(total_nodes * CONSENSUS_QUORUM_PERCENT))
        return max(CONSENSUS_MIN_CONFIRMATIONS, quorum_count)

    def add_block(
        self,
        data: Dict[str, Any],
        initial_confirmations: List[Dict] = None,
        total_nodes: int = 1,
    ) -> Dict:
        """
        Add a new block to the chain.

        Args:
            data: Block data (file metadata)
            initial_confirmations: List of node confirmations [{node_id, timestamp, signature}]
            total_nodes: Total number of active nodes for quorum calculation

        Returns:
            The new block as dictionary
        """
        with self.lock:
            index = len(self.chain)
            prev_hash = self.get_last_hash()

            confirmations = initial_confirmations or []
            required = self.calculate_required_confirmations(total_nodes)

            # Determine initial status based on confirmations
            if len(confirmations) >= required:
                status = BlockStatus.CONFIRMED
            elif CONSENSUS_ALLOW_PENDING:
                status = BlockStatus.PENDING
            else:
                # Don't add block if consensus not reached and pending not allowed
                raise ValueError(f"Consensus not reached: {len(confirmations)}/{required} confirmations")

            block = Block(
                index=index,
                prev_hash=prev_hash,
                data=data,
                status=status,
                confirmations=confirmations,
            )

            entry = block.to_dict()
            self.chain.append(entry)

            if status == BlockStatus.PENDING:
                self._pending_blocks[entry["hash"]] = entry

            self._save()

            return entry

    def add_confirmation(
        self,
        block_hash: str,
        node_id: str,
        chunk_hashes: List[str],
        signature: str = None,
        total_nodes: int = 1,
    ) -> Dict:
        """
        Add a storage confirmation from a node.

        Args:
            block_hash: Hash of the block to confirm
            node_id: ID of the confirming node
            chunk_hashes: List of chunk hashes the node stored
            signature: Optional cryptographic signature from node
            total_nodes: Total active nodes for quorum calculation

        Returns:
            Updated block or None if block not found
        """
        with self.lock:
            # Find the block
            block = None
            block_idx = None
            for i, b in enumerate(self.chain):
                if b["hash"] == block_hash:
                    block = b
                    block_idx = i
                    break

            if not block:
                return None

            # Check if node already confirmed
            existing_nodes = {c["node_id"] for c in block.get("confirmations", [])}
            if node_id in existing_nodes:
                return block  # Already confirmed

            # Add confirmation
            confirmation = {
                "node_id": node_id,
                "chunk_hashes": chunk_hashes,
                "timestamp": int(time.time()),
                "signature": signature,
            }

            if "confirmations" not in block:
                block["confirmations"] = []
            block["confirmations"].append(confirmation)

            # Check if consensus reached
            required = self.calculate_required_confirmations(total_nodes)
            if len(block["confirmations"]) >= required and block["status"] == BlockStatus.PENDING:
                block["status"] = BlockStatus.CONFIRMED
                block["confirmed_at"] = int(time.time())
                # Remove from pending index
                if block_hash in self._pending_blocks:
                    del self._pending_blocks[block_hash]

            self._save()
            return block

    def get_pending_blocks(self) -> List[Dict]:
        """Get all blocks awaiting consensus."""
        return [b for b in self.chain if b.get("status") == BlockStatus.PENDING]

    def get_confirmed_blocks(self) -> List[Dict]:
        """Get all confirmed blocks."""
        return [b for b in self.chain if b.get("status") == BlockStatus.CONFIRMED]

    def get_block_status(self, block_hash: str) -> Optional[str]:
        """Get consensus status of a block."""
        for block in self.chain:
            if block["hash"] == block_hash:
                return block.get("status", BlockStatus.CONFIRMED)
        return None

    def reject_block(self, block_hash: str, reason: str = None) -> Optional[Dict]:
        """
        Mark a block as rejected (failed consensus).

        Args:
            block_hash: Hash of the block to reject
            reason: Optional reason for rejection

        Returns:
            Updated block or None if not found
        """
        with self.lock:
            for block in self.chain:
                if block["hash"] == block_hash:
                    block["status"] = BlockStatus.REJECTED
                    block["rejected_at"] = int(time.time())
                    block["rejection_reason"] = reason
                    if block_hash in self._pending_blocks:
                        del self._pending_blocks[block_hash]
                    self._save()
                    return block
            return None

    def get_chain(self) -> List[Dict]:
        """Get the full chain."""
        return self.chain.copy()

    def get_block(self, index: int) -> Optional[Dict]:
        """Get block by index."""
        if 0 <= index < len(self.chain):
            return self.chain[index]
        return None

    def get_block_by_hash(self, block_hash: str) -> Optional[Dict]:
        """Get block by hash."""
        for block in self.chain:
            if block["hash"] == block_hash:
                return block
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
        """Find file metadata by stored_name."""
        for block in self.chain:
            if block.get("data", {}).get("stored_name") == stored_name:
                return block["data"]
        return None

    def get_user_files(self, owner_id: str, include_pending: bool = True) -> List[Dict]:
        """
        Get all file metadata for a user.

        Args:
            owner_id: User ID
            include_pending: Whether to include pending (unconfirmed) files

        Returns:
            List of file data dictionaries
        """
        files = []
        for block in self.chain:
            data = block.get("data", {})
            status = block.get("status", BlockStatus.CONFIRMED)

            # Skip rejected blocks
            if status == BlockStatus.REJECTED:
                continue

            # Skip pending if not requested
            if not include_pending and status == BlockStatus.PENDING:
                continue

            if data.get("owner_id") == owner_id and data.get("file_id"):
                files.append({
                    "block_index": block["index"],
                    "block_hash": block["hash"],
                    "timestamp": block["timestamp"],
                    "status": status,
                    "confirmations_count": len(block.get("confirmations", [])),
                    **data,
                })
        return files

    def verify_ownership(self, file_id: str, owner_id: str) -> bool:
        """Verify that a file belongs to a specific owner."""
        metadata = self.get_file_metadata(file_id)
        if metadata:
            return metadata.get("owner_id") == owner_id
        return False

    def get_stats(self) -> Dict:
        """Get blockchain statistics including consensus metrics."""
        total_files = sum(
            1 for block in self.chain
            if block.get("data", {}).get("file_id")
        )
        pending_files = sum(
            1 for block in self.chain
            if block.get("data", {}).get("file_id") and block.get("status") == BlockStatus.PENDING
        )
        confirmed_files = sum(
            1 for block in self.chain
            if block.get("data", {}).get("file_id") and block.get("status") == BlockStatus.CONFIRMED
        )
        total_size = sum(
            block.get("data", {}).get("size", 0)
            for block in self.chain
            if block.get("status") != BlockStatus.REJECTED
        )
        unique_owners = len(set(
            block.get("data", {}).get("owner_id")
            for block in self.chain
            if block.get("data", {}).get("owner_id")
        ))
        total_confirmations = sum(
            len(block.get("confirmations", []))
            for block in self.chain
        )

        return {
            "block_count": len(self.chain),
            "file_count": total_files,
            "pending_files": pending_files,
            "confirmed_files": confirmed_files,
            "rejected_files": total_files - pending_files - confirmed_files,
            "total_size_bytes": total_size,
            "unique_owners": unique_owners,
            "total_confirmations": total_confirmations,
            "last_block_time": self.chain[-1]["timestamp"] if self.chain else None,
            "consensus_config": {
                "min_confirmations": CONSENSUS_MIN_CONFIRMATIONS,
                "quorum_percent": CONSENSUS_QUORUM_PERCENT,
                "allow_pending": CONSENSUS_ALLOW_PENDING,
            },
        }


# Backwards compatibility alias
SimpleBlockchain = ConsensusBlockchain
