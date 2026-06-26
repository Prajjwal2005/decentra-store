# DecentraStore - Federated Decentralized Storage

A secure, hybrid-decentralized file storage system where files are encrypted on the client side, chunked, and distributed across community peer nodes. Coordination is handled by a central tracker (backend), while storage is fully decentralized and zero-knowledge.

## Architecture

`
+---------------------------------------------------------------------------------+
¦                           DecentraStore Architecture                            ¦
+---------------------------------------------------------------------------------¦
¦                                                                                 ¦
¦    +----------------+                                                          ¦
¦    ¦   Web Browser  ¦                                                          ¦
¦    ¦   (Frontend)   ¦                                                          ¦
¦    +----------------+                                                          ¦
¦            ¦ HTTPS (Encrypted blobs & metadata)                                ¦
¦            ?                                                                   ¦
¦    +----------------+         +----------------+                               ¦
¦    ¦  Coordination  ¦?-------?¦    Postgres    ¦                               ¦
¦    ¦    Tracker     ¦         ¦    Database    ¦                               ¦
¦    ¦  (Flask API)   ¦         ¦   (Metadata)   ¦                               ¦
¦    +----------------+         +----------------+                               ¦
¦            ¦                                                                   ¦
¦            ¦ Distribute / Retrieve Encrypted Chunks                            ¦
¦            ¦ (Node discovery & heartbeat tracking)                             ¦
¦            ?                                                                   ¦
¦    +-----------------------------------------------------------------+        ¦
¦    ¦                      Storage Nodes (Peers)                       ¦        ¦
¦    ¦  +----------+    +----------+    +----------+    +----------+  ¦        ¦
¦    ¦  ¦  Node A  ¦    ¦  Node B  ¦    ¦  Node C  ¦    ¦  Node N  ¦  ¦        ¦
¦    ¦  ¦ (Home PC)¦    ¦ (Server) ¦    ¦ (VPS)    ¦    ¦  (...)   ¦  ¦        ¦
¦    ¦  +----------+    +----------+    +----------+    +----------+  ¦        ¦
¦    ¦       ¦               ¦               ¦               ¦         ¦        ¦
¦    ¦       ?               ?               ?               ?         ¦        ¦
¦    ¦   [Encrypted]    [Encrypted]    [Encrypted]    [Encrypted]     ¦        ¦
¦    ¦   [Chunks  ]    [Chunks   ]    [Chunks   ]    [Chunks   ]     ¦        ¦
¦    +-----------------------------------------------------------------+        ¦
¦                                                                                 ¦
+---------------------------------------------------------------------------------+
`

## Privacy Guarantees
- **Client-Side Encryption**: Files are encrypted with AES-256 inside the user's browser before being transmitted.
- **Untrusted Nodes**: Storage nodes see only scrambled binary chunks. They have zero knowledge of file names, contents, or ownership.
- **Federated Coordination**: The backend tracker coordinates chunk locations using a Postgres database acting as an immutable ledger. 

## Quick Start

### Prerequisites
`ash
pip install -r requirements.txt
`

### 1. Start the Coordination Tracker (Backend)
`ash
python -m backend.app \
    --host 0.0.0.0 \
    --port 5000
`
*Note: Make sure your DATABASE_URL environment variable is set (defaults to sqlite://).*

### 2. Start Storage Nodes (Community Peers)
Anyone can join the network by running a storage node and pointing it to the coordination tracker.
`ash
python -m node.storage_node \
    --host 0.0.0.0 \
    --port 6001 \
    --discovery http://localhost:5000 \
    --public-url http://YOUR_PUBLIC_IP_OR_TUNNEL:6001 \
    --storage-dir ./node_storage
`

### 3. Access Web UI
Open the frontend index.html file in your browser to access the dashboard, upload files, and view network statistics.

## Directory Structure
- ackend/: Flask API and tracker logic.
- 
ode/: Storage node implementation.
- rontend/: Web user interface.
- shared/: Common utilities (cryptography, chunking).

## License
MIT License - See LICENSE file
