#!/usr/bin/env python3
"""
DecentraStore WebSocket Storage Node

Connects to the server via WebSocket - works through NAT/firewalls without port forwarding.
"""

import os
import sys
import time
import json
import base64
import hashlib
import logging
import threading
from pathlib import Path

# Try to import socketio, install if missing
try:
    import socketio
except ImportError:
    print("Installing python-socketio...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "python-socketio[client]", "websocket-client", "-q"])
    import socketio

# =============================================================================
# Configuration
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
LOG = logging.getLogger("storage-node")

# =============================================================================
# Storage Node Class
# =============================================================================
class StorageNode:
    def __init__(self, server_url, node_id, storage_dir, capacity_gb=10):
        self.server_url = server_url.rstrip('/')
        self.node_id = node_id
        self.storage_dir = Path(storage_dir)
        self.capacity_gb = capacity_gb
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # Create SocketIO client with matching server timeouts
        self.sio = socketio.Client(
            reconnection=True,
            reconnection_attempts=0,  # Infinite
            reconnection_delay=1,
            reconnection_delay_max=30,
            logger=True,
            engineio_logger=True,
            request_timeout=120,  # Increase request timeout
            http_session=None  # Use default session
        )

        self._setup_handlers()
        self._running = False
        self._heartbeat_thread = None

    def _setup_handlers(self):
        """Set up WebSocket event handlers."""

        @self.sio.event
        def connect():
            LOG.info(f"Connected to server: {self.server_url}")
            # Register with server
            response = self.sio.call('node_register', {
                'node_id': self.node_id,
                'capacity_gb': self.capacity_gb
            })
            if response.get('status') == 'registered':
                LOG.info(f"Registered as node: {self.node_id}")
            else:
                LOG.error(f"Registration failed: {response}")

        @self.sio.event
        def disconnect():
            LOG.warning("Disconnected from server")

        @self.sio.event
        def connect_error(data):
            LOG.error(f"Connection error: {data}")

        @self.sio.on('store_chunk')
        def handle_store_chunk(data):
            """Server requests us to store a chunk."""
            request_id = data.get('request_id')
            chunk_hash = data.get('chunk_hash')
            chunk_data_b64 = data.get('chunk_data')

            LOG.info(f"Storing chunk: {chunk_hash[:16]}...")

            try:
                chunk_data = base64.b64decode(chunk_data_b64)

                # Verify hash
                actual_hash = hashlib.sha256(chunk_data).hexdigest()
                if actual_hash != chunk_hash:
                    LOG.error(f"Hash mismatch: expected {chunk_hash}, got {actual_hash}")
                    self.sio.emit('chunk_stored', {
                        'node_id': self.node_id,
                        'request_id': request_id,
                        'success': False,
                        'chunk_hash': chunk_hash
                    })
                    return

                # Store chunk
                chunk_path = self.storage_dir / chunk_hash
                with open(chunk_path, 'wb') as f:
                    f.write(chunk_data)

                LOG.info(f"Stored chunk: {chunk_hash[:16]}... ({len(chunk_data)} bytes)")

                self.sio.emit('chunk_stored', {
                    'node_id': self.node_id,
                    'request_id': request_id,
                    'success': True,
                    'chunk_hash': chunk_hash
                })

            except Exception as e:
                LOG.error(f"Error storing chunk: {e}")
                self.sio.emit('chunk_stored', {
                    'node_id': self.node_id,
                    'request_id': request_id,
                    'success': False,
                    'chunk_hash': chunk_hash
                })

        @self.sio.on('retrieve_chunk')
        def handle_retrieve_chunk(data):
            """Server requests a chunk from us."""
            request_id = data.get('request_id')
            chunk_hash = data.get('chunk_hash')

            LOG.info(f"Retrieving chunk: {chunk_hash[:16]}...")

            try:
                chunk_path = self.storage_dir / chunk_hash

                if not chunk_path.exists():
                    LOG.warning(f"Chunk not found: {chunk_hash[:16]}...")
                    self.sio.emit('chunk_retrieved', {
                        'node_id': self.node_id,
                        'request_id': request_id,
                        'success': False,
                        'chunk_data': None
                    })
                    return

                with open(chunk_path, 'rb') as f:
                    chunk_data = f.read()

                LOG.info(f"Retrieved chunk: {chunk_hash[:16]}... ({len(chunk_data)} bytes)")

                self.sio.emit('chunk_retrieved', {
                    'node_id': self.node_id,
                    'request_id': request_id,
                    'success': True,
                    'chunk_data': base64.b64encode(chunk_data).decode('utf-8')
                })

            except Exception as e:
                LOG.error(f"Error retrieving chunk: {e}")
                self.sio.emit('chunk_retrieved', {
                    'node_id': self.node_id,
                    'request_id': request_id,
                    'success': False,
                    'chunk_data': None
                })

        @self.sio.on('delete_chunk')
        def handle_delete_chunk(data):
            """Server requests us to delete a chunk."""
            chunk_hash = data.get('chunk_hash')

            LOG.info(f"Deleting chunk: {chunk_hash[:16]}...")

            try:
                chunk_path = self.storage_dir / chunk_hash

                if chunk_path.exists():
                    chunk_path.unlink()
                    LOG.info(f"Deleted chunk: {chunk_hash[:16]}...")
                else:
                    LOG.warning(f"Chunk not found for deletion: {chunk_hash[:16]}...")

            except Exception as e:
                LOG.error(f"Error deleting chunk: {e}")

        @self.sio.on('verify_chunk')
        def handle_verify_chunk(data):
            """Server requests proof that we have a chunk (for consensus)."""
            request_id = data.get('request_id')
            chunk_hash = data.get('chunk_hash')

            LOG.info(f"Verifying chunk: {chunk_hash[:16]}...")

            try:
                chunk_path = self.storage_dir / chunk_hash

                if not chunk_path.exists():
                    self.sio.emit('chunk_verified', {
                        'node_id': self.node_id,
                        'request_id': request_id,
                        'exists': False,
                        'chunk_hash': chunk_hash
                    })
                    return

                # Read and verify hash
                with open(chunk_path, 'rb') as f:
                    chunk_data = f.read()

                actual_hash = hashlib.sha256(chunk_data).hexdigest()
                is_valid = actual_hash == chunk_hash

                self.sio.emit('chunk_verified', {
                    'node_id': self.node_id,
                    'request_id': request_id,
                    'exists': True,
                    'valid': is_valid,
                    'chunk_hash': chunk_hash,
                    'size': len(chunk_data)
                })

                LOG.info(f"Verified chunk: {chunk_hash[:16]}... (valid={is_valid})")

            except Exception as e:
                LOG.error(f"Error verifying chunk: {e}")
                self.sio.emit('chunk_verified', {
                    'node_id': self.node_id,
                    'request_id': request_id,
                    'exists': False,
                    'chunk_hash': chunk_hash
                })

    def _heartbeat_loop(self):
        """Send periodic heartbeats to server."""
        while self._running:
            try:
                if self.sio.connected:
                    self.sio.call('node_heartbeat', {'node_id': self.node_id}, timeout=10)
            except Exception as e:
                LOG.debug(f"Heartbeat error: {e}")
            time.sleep(30)

    def start(self):
        """Connect to server and start handling requests."""
        self._running = True

        # Start heartbeat thread
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

        # Connect to server
        LOG.info(f"Connecting to {self.server_url}...")

        while self._running:
            try:
                self.sio.connect(self.server_url, transports=['websocket', 'polling'])
                self.sio.wait()
            except KeyboardInterrupt:
                LOG.info("Shutting down...")
                break
            except Exception as e:
                LOG.error(f"Connection error: {e}")
                LOG.info("Reconnecting in 5 seconds...")
                time.sleep(5)

    def stop(self):
        """Disconnect from server."""
        self._running = False
        if self.sio.connected:
            self.sio.disconnect()

    def get_storage_stats(self):
        """Get storage statistics."""
        chunks = list(self.storage_dir.glob('*'))
        total_size = sum(c.stat().st_size for c in chunks if c.is_file())
        return {
            'chunk_count': len(chunks),
            'total_size_bytes': total_size,
            'total_size_mb': round(total_size / (1024 * 1024), 2)
        }


# =============================================================================
# Main
# =============================================================================
def main():
    import argparse

    parser = argparse.ArgumentParser(description='DecentraStore WebSocket Storage Node')
    parser.add_argument('--server', '-s', required=True, help='Server URL (e.g., https://your-server.com)')
    parser.add_argument('--node-id', '-n', help='Unique node ID (default: auto-generated)')
    parser.add_argument('--storage-dir', '-d', default='./chunks', help='Directory to store chunks')
    parser.add_argument('--capacity', '-c', type=int, default=10, help='Storage capacity in GB')

    args = parser.parse_args()

    # Generate node ID if not provided
    node_id = args.node_id
    if not node_id:
        import socket
        node_id = f"node-{socket.gethostname()}"

    print()
    print("=" * 60)
    print("  DecentraStore WebSocket Storage Node")
    print("=" * 60)
    print(f"  Server:      {args.server}")
    print(f"  Node ID:     {node_id}")
    print(f"  Storage:     {args.storage_dir}")
    print(f"  Capacity:    {args.capacity} GB")
    print("=" * 60)
    print()
    print("  This node connects OUTBOUND to the server.")
    print("  No port forwarding required!")
    print()
    print("  Press Ctrl+C to stop.")
    print("=" * 60)
    print()

    node = StorageNode(
        server_url=args.server,
        node_id=node_id,
        storage_dir=args.storage_dir,
        capacity_gb=args.capacity
    )

    try:
        node.start()
    except KeyboardInterrupt:
        print("\nShutting down...")
        node.stop()


if __name__ == "__main__":
    main()
