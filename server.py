#!/usr/bin/env python3
"""
DecentraStore Combined Server

Runs both Discovery and Backend services in one process.
Useful for simple deployments where you want everything in one container.

Usage:
    python server.py                    # Default ports (4000, 5000)
    python server.py --port 8080        # Custom backend port
    PORT=8080 python server.py          # Using environment variable
"""

import os
import sys
import threading
import time
import logging
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
LOG = logging.getLogger("server")


def run_discovery(host: str, port: int):
    """Run discovery service in a thread."""
    from discovery.server import app as discovery_app
    
    LOG.info(f"Starting Discovery Service on {host}:{port}")
    
    # Disable Flask's default logging for cleaner output
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.WARNING)
    
    discovery_app.run(host=host, port=port, threaded=True, use_reloader=False)


def run_backend(host: str, port: int, discovery_url: str):
    """Run backend service."""
    # Set discovery URL
    os.environ["DISCOVERY_URL"] = discovery_url
    
    from backend.app import app as backend_app
    
    LOG.info(f"Starting Backend Server on {host}:{port}")
    LOG.info(f"Discovery URL: {discovery_url}")
    
    backend_app.run(host=host, port=port, threaded=True, use_reloader=False)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="DecentraStore Combined Server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    parser.add_argument("--port", type=int, default=None, help="Backend port (default: 5000 or $PORT)")
    parser.add_argument("--discovery-port", type=int, default=None, help="Discovery port (default: 4000 or $DISCOVERY_PORT)")
    
    args = parser.parse_args()
    
    # Get ports from args or environment
    backend_port = args.port or int(os.environ.get("PORT", 5000))
    discovery_port = args.discovery_port or int(os.environ.get("DISCOVERY_PORT", 4000))
    host = args.host
    
    # Discovery URL for backend to use
    discovery_url = f"http://127.0.0.1:{discovery_port}"
    
    print()
    print("=" * 60)
    print("  DecentraStore Server")
    print("=" * 60)
    print(f"  Backend:    http://{host}:{backend_port}")
    print(f"  Discovery:  http://{host}:{discovery_port}")
    print("=" * 60)
    print()
    
    # Start discovery in background thread
    discovery_thread = threading.Thread(
        target=run_discovery,
        args=(host, discovery_port),
        daemon=True
    )
    discovery_thread.start()
    
    # Wait a moment for discovery to start
    time.sleep(1)
    
    # Run backend in main thread
    run_backend(host, backend_port, discovery_url)


if __name__ == "__main__":
    main()
