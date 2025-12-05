# DecentraStore - Decentralized P2P Storage System

A secure, decentralized file storage system where files are chunked, encrypted, and distributed across peer nodes. Only the file owner can retrieve and reassemble their files.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           DecentraStore Architecture                            │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│    ┌────────────────┐                                                          │
│    │   Web Browser  │                                                          │
│    │   (Frontend)   │                                                          │
│    └───────┬────────┘                                                          │
│            │ HTTPS                                                             │
│            ▼                                                                   │
│    ┌────────────────┐         ┌────────────────┐      ┌────────────────┐      │
│    │    Backend     │◄───────►│   Discovery    │◄────►│   Blockchain   │      │
│    │    Server      │         │    Service     │      │   (Private)    │      │
│    │  (Flask API)   │         │  (Registry)    │      │                │      │
│    └───────┬────────┘         └───────┬────────┘      └────────────────┘      │
│            │                          │                                        │
│            │ Distribute               │ Heartbeat                              │
│            │ Encrypted                │ Register                               │
│            │ Chunks                   │                                        │
│            ▼                          ▼                                        │
│    ┌─────────────────────────────────────────────────────────────────┐        │
│    │                      Storage Nodes (Peers)                       │        │
│    │  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │        │
│    │  │  Node A  │    │  Node B  │    │  Node C  │    │  Node N  │  │        │
│    │  │ (Home PC)│    │ (Server) │    │ (VPS)    │    │  (...)   │  │        │
│    │  └──────────┘    └──────────┘    └──────────┘    └──────────┘  │        │
│    │       │               │               │               │         │        │
│    │       ▼               ▼               ▼               ▼         │        │
│    │   [Encrypted]    [Encrypted]    [Encrypted]    [Encrypted]     │        │
│    │   [Chunks  ]    [Chunks   ]    [Chunks   ]    [Chunks   ]     │        │
│    └─────────────────────────────────────────────────────────────────┘        │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## Security Model

### File Upload Flow
```
1. User authenticates → receives JWT token
2. User uploads file
3. Backend generates random AES-256 encryption key
4. File is split into chunks (default 256KB)
5. Each chunk is encrypted with AES-256-GCM
6. Encrypted chunks distributed to N peers (replication factor)
7. File encryption key is encrypted with user's key-derivation from password
8. Metadata (encrypted) stored on blockchain with:
   - File hash, Merkle root, chunk locations
   - Encrypted file key (only owner can decrypt)
   - Owner ID (for access control)
```

### File Retrieval Flow
```
1. User authenticates
2. User requests their file (ownership verified via blockchain)
3. Backend locates chunks via blockchain metadata
4. Chunks retrieved from storage nodes
5. Merkle tree verification ensures integrity
6. Chunks decrypted with user's file key
7. File reassembled and sent to user
```

### Privacy Guarantees
- **Storage nodes** see only encrypted binary blobs (no file names, no metadata)
- **Blockchain** stores encrypted metadata (only owner can read their files)
- **Other users** cannot see which files exist or who owns what
- **File keys** are encrypted with user's derived key

## Components

### 1. Discovery Service (`discovery/server.py`)
Central registry where storage nodes register and heartbeat.
- `POST /register` - Node joins network
- `POST /heartbeat` - Node stays alive
- `GET /peers` - Get list of active nodes

### 2. Backend Server (`backend/app.py`)
Main API server handling user requests.
- User authentication (register, login, logout)
- File upload with encryption and distribution
- File retrieval with verification and decryption
- Blockchain explorer (privacy-filtered)

### 3. Storage Node (`node/storage_node.py`)
P2P node that stores encrypted chunks.
- `POST /store` - Receive and store encrypted chunk
- `GET /retrieve/<hash>` - Serve chunk by hash
- `GET /health` - Health check
- Auto-registers with discovery service

### 4. Blockchain (`shared/blockchain.py`)
Private blockchain for metadata storage.
- Tamper-evident chain of blocks
- Stores file metadata with ownership
- Merkle proofs for integrity

## Quick Start

### Prerequisites
```bash
pip install -r requirements.txt
```

### 1. Start Discovery Service (one instance)
```bash
python -m discovery.server --host 0.0.0.0 --port 4000
```

### 2. Start Storage Nodes (on different machines/ports)
```bash
# On machine A
python -m node.storage_node \
    --host 0.0.0.0 \
    --port 6001 \
    --discovery http://DISCOVERY_IP:4000 \
    --storage-dir ./node_storage

# On machine B
python -m node.storage_node \
    --host 0.0.0.0 \
    --port 6001 \
    --discovery http://DISCOVERY_IP:4000 \
    --storage-dir ./node_storage
```

### 3. Start Backend Server
```bash
python -m backend.app \
    --host 0.0.0.0 \
    --port 5000 \
    --discovery http://DISCOVERY_IP:4000
```

### 4. Access Web UI
Open `http://BACKEND_IP:5000` in your browser.

## Configuration

Environment variables or command-line arguments:

| Variable | Default | Description |
|----------|---------|-------------|
| `DISCOVERY_URL` | `http://localhost:4000` | Discovery service URL |
| `REPLICATION` | `3` | Number of nodes to store each chunk |
| `CHUNK_SIZE` | `262144` | Chunk size in bytes (256KB) |
| `SECRET_KEY` | (random) | Flask session secret |
| `DATABASE_URL` | `sqlite:///users.db` | User database |

## File Structure
```
decentra-store/
├── README.md
├── requirements.txt
├── config.py                 # Shared configuration
├── shared/
│   ├── __init__.py
│   ├── crypto.py             # Encryption utilities
│   ├── chunker.py            # File chunking & Merkle tree
│   └── blockchain.py         # Blockchain implementation
├── discovery/
│   ├── __init__.py
│   └── server.py             # Discovery service
├── backend/
│   ├── __init__.py
│   ├── app.py                # Main Flask API
│   ├── auth.py               # Authentication logic
│   ├── models.py             # Database models
│   └── uploader.py           # Chunk distribution
├── node/
│   ├── __init__.py
│   └── storage_node.py       # Storage node server
├── frontend/
│   └── index.html            # Web UI
└── scripts/
    └── deploy.sh             # Deployment helper
```

## License

MIT License - See LICENSE file
