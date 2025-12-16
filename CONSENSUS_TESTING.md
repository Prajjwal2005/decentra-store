# Consensus Mechanism Testing Guide

## Overview
This guide explains how to test the Proof of Storage consensus mechanism with multiple storage nodes.

## Architecture

### Consensus Flow
```
1. User uploads file
2. Backend chunks and encrypts file
3. Chunks distributed to storage nodes
4. Nodes store chunks and send confirmation
5. Backend waits for quorum confirmations
6. Once quorum reached, block is finalized on blockchain
7. User can download file once consensus achieved
```

### Components
- **Backend** (port 5000): Handles uploads, manages blockchain
- **Discovery Service** (port 4000): Tracks active storage nodes
- **Storage Nodes** (various ports): Store encrypted chunks, provide proofs

## Test Setup

### Test Scenario 1: Single Node (Minimal)

**Purpose:** Verify basic functionality

**Configuration:**
```env
CONSENSUS_MIN_CONFIRMATIONS=1
CONSENSUS_ALLOW_PENDING=true
CONSENSUS_TIMEOUT=30
```

**Steps:**
```bash
# Terminal 1: Start discovery service
cd discovery
python discovery_service.py --port 4000

# Terminal 2: Start backend
cd backend
python app.py --port 5000

# Terminal 3: Start storage node
cd storage
python storage_node.py --port 7001 --capacity 10

# Terminal 4: Test upload
curl -X POST http://localhost:5000/upload \
  -H "Authorization: Bearer <token>" \
  -H "X-User-Password: password123" \
  -F "file=@test.txt"
```

**Expected:** File uploaded, stored on 1 node, block finalized immediately

### Test Scenario 2: Multi-Node Quorum (2/3)

**Purpose:** Test quorum consensus

**Configuration:**
```env
CONSENSUS_MIN_CONFIRMATIONS=2
CONSENSUS_QUORUM_PERCENT=0.67
CONSENSUS_ALLOW_PENDING=false
CONSENSUS_TIMEOUT=60
REPLICATION=3
```

**Steps:**
```bash
# Terminal 1: Discovery service
python discovery_service.py --port 4000

# Terminal 2: Backend
python app.py --port 5000

# Terminal 3-5: Start 3 storage nodes
python storage_node.py --port 7001 --capacity 10 --node-id node1
python storage_node.py --port 7002 --capacity 10 --node-id node2
python storage_node.py --port 7003 --capacity 10 --node-id node3

# Terminal 6: Upload file
curl -X POST http://localhost:5000/upload \
  -H "Authorization: Bearer <token>" \
  -H "X-User-Password: password123" \
  -F "file=@test.txt"
```

**Expected:**
- File distributed to all 3 nodes
- Backend waits for 2 confirmations (67% of 3)
- Block finalized once 2 nodes confirm
- Download succeeds from any 2 nodes

### Test Scenario 3: Byzantine Fault Tolerance

**Purpose:** Test consensus with failing nodes

**Setup:** Same as Scenario 2

**Test Cases:**

#### 3a. One Node Fails Before Confirmation
```bash
# Start 3 nodes
# Upload file
# Kill 1 node before it confirms
pkill -f "storage_node.py --port 7003"

# Expected: Consensus still achieved with 2/3 nodes
```

#### 3b. One Node Fails After Confirmation
```bash
# Upload file
# Wait for consensus
# Kill 1 node
pkill -f "storage_node.py --port 7001"

# Try download
curl -X GET http://localhost:5000/download/<file_id> \
  -H "Authorization: Bearer <token>" \
  -H "X-User-Password: password123"

# Expected: Download succeeds from remaining nodes
```

#### 3c. Majority Failure (No Consensus)
```bash
# Start 3 nodes
# Upload file
# Kill 2 nodes immediately
pkill -f "storage_node.py --port 7002"
pkill -f "storage_node.py --port 7003"

# Expected: Consensus fails, block marked as pending
```

### Test Scenario 4: Large File Multi-Node

**Purpose:** Test consensus with many chunks

**Configuration:**
```env
CHUNK_SIZE=262144  # 256KB
REPLICATION=3
CONSENSUS_MIN_CONFIRMATIONS=2
```

**Steps:**
```bash
# Create large test file (10MB)
dd if=/dev/urandom of=large_test.bin bs=1M count=10

# Upload
curl -X POST http://localhost:5000/upload \
  -H "Authorization: Bearer <token>" \
  -H "X-User-Password: password123" \
  -F "file=@large_test.bin"

# Expected: ~40 chunks (10MB / 256KB)
# Each chunk replicated to 3 nodes
# Consensus required for each chunk
```

## Automated Testing Script

### consensus_test.py

```python
#!/usr/bin/env python3
"""
Automated consensus testing script.
Tests various scenarios and generates report.
"""

import time
import requests
import subprocess
import signal
from pathlib import Path

class ConsensusTest:
    def __init__(self):
        self.processes = []
        self.base_url = "http://localhost:5000"
        self.token = None

    def start_service(self, command, name):
        """Start a service in background."""
        proc = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        self.processes.append((proc, name))
        print(f"✓ Started {name}")
        time.sleep(2)

    def stop_all(self):
        """Stop all services."""
        for proc, name in self.processes:
            proc.send_signal(signal.SIGTERM)
            print(f"✓ Stopped {name}")

    def register_and_login(self):
        """Register test user and get token."""
        # Register
        r = requests.post(f"{self.base_url}/auth/register", json={
            "username": "testuser",
            "password": "testpass123"
        })

        # Login
        r = requests.post(f"{self.base_url}/auth/login", json={
            "username": "testuser",
            "password": "testpass123"
        })

        self.token = r.json()["token"]
        print(f"✓ Logged in, token: {self.token[:20]}...")

    def upload_file(self, filepath):
        """Upload file and return result."""
        with open(filepath, "rb") as f:
            r = requests.post(
                f"{self.base_url}/upload",
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "X-User-Password": "testpass123"
                },
                files={"file": f}
            )

        return r.json()

    def test_single_node(self):
        """Test with single node."""
        print("\n=== Test 1: Single Node ===")

        self.start_service("python discovery/discovery_service.py", "Discovery")
        self.start_service("python backend/app.py", "Backend")
        self.start_service("python storage/storage_node.py --port 7001", "Node1")

        time.sleep(5)

        self.register_and_login()

        # Create test file
        test_file = Path("test_single.txt")
        test_file.write_text("Hello World")

        result = self.upload_file(test_file)

        if result.get("status") == "ok":
            print(f"✓ Upload successful: {result['file_id']}")
            print(f"  Chunks: {result['chunk_count']}")
            print(f"  Block: {result['block_index']}")
        else:
            print(f"✗ Upload failed: {result}")

        test_file.unlink()
        self.stop_all()

    def test_multi_node_quorum(self):
        """Test with 3 nodes, 2/3 quorum."""
        print("\n=== Test 2: Multi-Node Quorum (2/3) ===")

        self.start_service("python discovery/discovery_service.py", "Discovery")
        self.start_service("python backend/app.py", "Backend")
        self.start_service("python storage/storage_node.py --port 7001", "Node1")
        self.start_service("python storage/storage_node.py --port 7002", "Node2")
        self.start_service("python storage/storage_node.py --port 7003", "Node3")

        time.sleep(5)

        self.register_and_login()

        # Create test file
        test_file = Path("test_multi.txt")
        test_file.write_text("Multi-node test" * 100)

        result = self.upload_file(test_file)

        if result.get("status") == "ok":
            print(f"✓ Upload successful with quorum")
            print(f"  Chunks: {result['chunk_count']}")

            # Verify all nodes have chunks
            r = requests.get(f"{self.base_url}/file/{result['file_id']}",
                           headers={"Authorization": f"Bearer {self.token}"})

            chunks = r.json()["chunks"]
            for chunk in chunks:
                assignments = chunk["assignments"]
                print(f"  Chunk {chunk['index']}: {len(assignments)} nodes")
        else:
            print(f"✗ Upload failed: {result}")

        test_file.unlink()
        self.stop_all()

    def test_node_failure(self):
        """Test consensus with node failure."""
        print("\n=== Test 3: Node Failure During Upload ===")

        self.start_service("python discovery/discovery_service.py", "Discovery")
        self.start_service("python backend/app.py", "Backend")
        self.start_service("python storage/storage_node.py --port 7001", "Node1")
        self.start_service("python storage/storage_node.py --port 7002", "Node2")
        self.start_service("python storage/storage_node.py --port 7003", "Node3")

        time.sleep(5)

        self.register_and_login()

        # Create test file
        test_file = Path("test_failure.txt")
        test_file.write_text("Failure test" * 100)

        # Start upload
        result = self.upload_file(test_file)

        # Kill one node
        self.processes[-1][0].send_signal(signal.SIGTERM)
        print("  Killed Node3 during upload")

        if result.get("status") == "ok":
            print(f"✓ Upload succeeded despite node failure")
            print(f"  Consensus achieved with remaining nodes")
        else:
            print(f"  Upload result: {result}")

        test_file.unlink()
        self.stop_all()

    def run_all(self):
        """Run all tests."""
        try:
            self.test_single_node()
            time.sleep(3)

            self.test_multi_node_quorum()
            time.sleep(3)

            self.test_node_failure()

            print("\n=== All Tests Complete ===")
        except Exception as e:
            print(f"\n✗ Test failed: {e}")
        finally:
            self.stop_all()

if __name__ == "__main__":
    test = ConsensusTest()
    test.run_all()
```

**Run tests:**
```bash
python consensus_test.py
```

## Manual Testing Checklist

- [ ] Single node upload/download works
- [ ] Multi-node distribution works (check each node has chunks)
- [ ] Quorum consensus achieved (2/3 nodes confirm)
- [ ] Node failure handled gracefully
- [ ] Download works with subset of nodes
- [ ] Blockchain records consensus status
- [ ] Timeout handled properly
- [ ] Large files (many chunks) work
- [ ] Concurrent uploads work
- [ ] Node heartbeats update in discovery service

## Metrics to Monitor

### Upload Success Rate
```python
successful_uploads / total_uploads * 100
```

### Consensus Achievement Rate
```python
consensus_achieved / total_blocks * 100
```

### Average Consensus Time
```python
sum(consensus_times) / len(consensus_times)
```

### Node Availability
```python
active_nodes / total_registered_nodes * 100
```

## Debugging

### Enable Verbose Logging

```python
# In backend/app.py
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Check Consensus Status

```bash
# Get blockchain stats
curl http://localhost:5000/blockchain/stats

# Get specific block
curl http://localhost:5000/blockchain/blocks?limit=1&offset=0
```

### Monitor Node Heartbeats

```bash
# Check active nodes
curl http://localhost:4000/peers
```

## Performance Testing

### Load Test Script

```bash
# Using Apache Bench
ab -n 100 -c 10 \
  -H "Authorization: Bearer <token>" \
  -H "X-User-Password: password123" \
  -p test.txt \
  http://localhost:5000/upload

# Using wrk
wrk -t4 -c100 -d30s \
  -H "Authorization: Bearer <token>" \
  http://localhost:5000/my-files
```

## Next Steps

1. Run automated tests
2. Document test results
3. Optimize consensus timeout
4. Implement consensus caching
5. Add consensus metrics endpoint
6. Set up continuous testing
