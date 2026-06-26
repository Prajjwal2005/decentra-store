# DecentraStore Architecture

## Overview
DecentraStore is a federated decentralized file storage system that combines client-side end-to-end encryption, Merkle tree integrity verification, and distributed peer-to-peer storage. The architecture ensures data privacy and fault tolerance by splitting files into encrypted chunks across untrusted storage nodes, while relying on a federated coordination server (tracker) for routing and metadata.

## High-Level Architecture (Federated Decentralized)

The system is composed of several independent but interacting components:

1. **Web Browser (Frontend)**
   - Client-side application for uploading, downloading, and managing files.
   - Performs encryption and decryption directly in the browser using the Web Crypto API, guaranteeing Zero-Knowledge.

2. **Coordination Server (Tracker/Backend)**
   - The primary API gateway (Flask) acting as a federated tracker (similar to BitTorrent trackers).
   - Handles user authentication (JWT).
   - Coordinates chunk distribution and retrieval.
   - Maintains a Postgres database containing file metadata, Merkle roots, and chunk location mappings.

3. **Storage Nodes (Peers)**
   - Untrusted peer-to-peer nodes (which can be run by anyone on home PCs, VPS, or cloud instances).
   - Store purely encrypted binary blobs and have zero knowledge of file contents, names, or ownership.
   - Register automatically with the Coordination Server via a public URL (using tools like localhost.run, ngrok, or raw IPs).

## Security Model

### File Upload Flow (Zero-Knowledge)
1. User authenticates and receives a JWT token.
2. User selects a file through the frontend.
3. The frontend generates a random AES-256 encryption key and encrypts the file *before* it leaves the browser.
4. The file encryption key itself is encrypted using a Key Encryption Key (KEK) derived from the user's password (PBKDF2).
5. The encrypted file blob and encrypted key are sent to the Coordination Server.
6. The Coordination Server splits the encrypted blob into chunks (default 256KB).
7. Chunks are distributed to *N* peers (determined by the replication factor).
8. The Postgres database stores the file hash, Merkle root, chunk locations, and the encrypted file key.

### File Retrieval Flow
1. User requests their file via the frontend.
2. Coordination Server verifies ownership and locates the chunks via the Postgres database.
3. Chunks are retrieved from the respective untrusted storage nodes.
4. The Coordination Server uses the Merkle tree to verify the integrity of each chunk.
5. The reassembled (but still encrypted) file is sent back to the browser.
6. The browser decrypts the file key using the user's password, and then decrypts the file.

## Why Federated?
Rather than relying on a slow, expensive public blockchain or a complex gossip protocol, DecentraStore opts for a **Federated** architecture. 
- **Storage** is fully decentralized across community nodes.
- **Coordination** is centralized for maximum speed and efficiency.
This mirrors the architecture of highly successful P2P systems (like early BitTorrent) and provides the perfect balance of performance and decentralized storage.

## Cryptographic Specifications

- **Encryption**: AES-256-GCM
- **Key Derivation**: PBKDF2-HMAC-SHA256
- **Hashing**: SHA-256 (used for chunk hashing and Merkle trees)

## Directory Structure
- ackend/: Flask API and coordination tracker logic.
- 
ode/: Storage node implementation (can be distributed).
- rontend/: Web user interface with client-side cryptography.
- shared/: Common utilities including cryptography and chunking.
