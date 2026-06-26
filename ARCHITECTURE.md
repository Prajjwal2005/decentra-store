# DecentraStore Architecture

## Overview
DecentraStore is a decentralized file storage system that combines end-to-end encryption, blockchain-based metadata management, Merkle tree integrity verification, and a Proof of Storage consensus mechanism. The architecture ensures data availability and integrity across decentralized storage nodes without relying on a single central storage provider.

## High-Level Architecture

The system is composed of several independent but interacting components:

1. **Web Browser (Frontend)**
   - User interface for uploading, downloading, and managing files.
   - Communicates with the Backend Server via HTTPS.

2. **Backend Server (`backend/app.py`)**
   - The primary API gateway (Flask).
   - Handles user authentication (JWT).
   - Manages file chunking, AES-256 encryption, and coordinates chunk distribution.
   - Handles file retrieval, Merkle verification, and decryption.

3. **Discovery Service (`discovery/server.py`)**
   - A central registry where Storage Nodes register when they come online.
   - Tracks node health via heartbeats.
   - Provides the Backend Server with a list of active peers to distribute chunks to.

4. **Storage Nodes (`node/storage_node.py`)**
   - Peer-to-peer nodes (which can be run by anyone) that store encrypted file chunks.
   - Nodes only see encrypted binary blobs and have zero knowledge of the file contents, file names, or ownership.
   - Register automatically with the Discovery Service.

5. **Blockchain (`shared/blockchain.py`)**
   - A private, tamper-evident blockchain that stores file metadata.
   - Records file hashes, Merkle roots, chunk locations, and encrypted file keys.
   - Provides privacy by ensuring metadata is tied only to owner IDs, with the actual decryption key encrypted.

## Security Model

### File Upload Flow
1. User authenticates and receives a JWT token.
2. User uploads a file through the frontend.
3. Backend generates a random AES-256 encryption key specifically for this file.
4. The file is split into chunks (default 256KB).
5. Each chunk is individually encrypted using AES-256-GCM.
6. Encrypted chunks are distributed to *N* peers (determined by the replication factor).
7. The file encryption key is then encrypted with a key derived from the user's password (PBKDF2).
8. Encrypted metadata is stored on the blockchain, including the file hash, Merkle root, chunk locations, and the encrypted file key.

### File Retrieval Flow
1. User requests their file. The backend verifies ownership via the blockchain metadata.
2. Backend locates the chunks using the locations stored on the blockchain.
3. Chunks are retrieved from the respective storage nodes.
4. The backend uses the Merkle tree to verify the integrity of each chunk.
5. Chunks are decrypted using the user's file key (which is decrypted using their derived key).
6. The file is reassembled and sent to the user.

## Proof of Storage Consensus

DecentraStore uses a hybrid consensus mechanism combining Proof of Storage with quorum-based validation.
- When retrieving chunks, the system can query multiple nodes to verify storage.
- A quorum (e.g., 2/3 of nodes) must agree on the integrity of the chunk.
- Byzantine fault tolerance ensures that malicious or failing nodes cannot corrupt the retrieved file, as the Merkle root on the blockchain acts as the ultimate source of truth.

## Cryptographic Specifications

- **Encryption**: AES-256-GCM (32-byte key, 12-byte nonce, 16-byte auth tag)
- **Key Derivation**: PBKDF2-HMAC-SHA256 (100,000 iterations, 16-byte salt)
- **Hashing**: SHA-256 (used for chunk hashing, Merkle trees, and the blockchain)

## Directory Structure
- `backend/`: Flask API and core business logic (auth, uploader, models).
- `discovery/`: Node registry and heartbeat service.
- `node/`: Storage node implementation.
- `frontend/`: Web user interface.
- `shared/`: Common utilities including cryptography, chunking, and the blockchain implementation.
- `config.py`: Shared configuration parameters.
