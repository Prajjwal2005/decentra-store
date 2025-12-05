# backend/uploader.py
"""
Chunk distribution module for DecentraStore.

Handles:
- Discovering available peers
- Measuring peer latency (RTT)
- Parallel chunk upload to multiple peers
- Retry logic with exponential backoff
"""

import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed, wait
from typing import List, Dict, Optional, Any
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    DISCOVERY_URL,
    REPLICATION_FACTOR,
    PEER_TIMEOUT,
    UPLOAD_TIMEOUT,
    DISCOVERY_TIMEOUT,
)

LOG = logging.getLogger("uploader")

# Configuration
CANDIDATE_LIMIT = 40  # Max peers to consider
HEAD_TIMEOUT = 2.0  # Timeout for RTT measurement
MEASURE_MAX_WORKERS = 16
UPLOAD_MAX_WORKERS = 8
UPLOAD_RETRIES = 2
BACKOFF_BASE = 0.5


def _make_session(retries: int = 2, backoff_factor: float = 1.0) -> requests.Session:
    """Create a requests Session with retry policy."""
    session = requests.Session()
    
    retry_kwargs = {
        "total": retries,
        "backoff_factor": backoff_factor,
        "status_forcelist": [500, 502, 503, 504],
    }
    
    # Handle different urllib3 versions
    try:
        retry = Retry(**retry_kwargs, allowed_methods=frozenset(["GET", "POST", "HEAD"]))
    except TypeError:
        retry = Retry(**retry_kwargs, method_whitelist=frozenset(["GET", "POST", "HEAD"]))
    
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    return session


def get_peers(discovery_url: str = None, limit: int = CANDIDATE_LIMIT) -> List[Dict]:
    """
    Query discovery service for available peers.
    
    Returns list of peer dicts with: node_id, ip, port, public_ip, etc.
    """
    url = discovery_url or DISCOVERY_URL
    if not url:
        LOG.warning("No discovery URL configured")
        return []
    
    try:
        session = _make_session(retries=1)
        resp = session.get(
            f"{url.rstrip('/')}/peers",
            params={"limit": limit},
            timeout=DISCOVERY_TIMEOUT
        )
        resp.raise_for_status()
        
        data = resp.json()
        peers = data.get("peers", [])
        LOG.info(f"Got {len(peers)} peers from discovery")
        return peers
        
    except Exception as e:
        LOG.error(f"Failed to get peers: {e}")
        return []


def measure_rtt(peer: Dict) -> float:
    """
    Measure round-trip time to a peer.
    Returns RTT in seconds, or inf on failure.
    """
    ip = peer.get("ip")
    port = peer.get("port")
    
    if not ip or not port:
        return float("inf")
    
    url = f"http://{ip}:{port}/health"
    
    try:
        session = _make_session(retries=0)
        start = time.time()
        resp = session.get(url, timeout=HEAD_TIMEOUT)
        rtt = time.time() - start
        
        if resp.status_code == 200:
            return rtt
        return float("inf")
        
    except Exception:
        return float("inf")


def select_peers(
    peers: List[Dict],
    count: int = REPLICATION_FACTOR,
    max_workers: int = MEASURE_MAX_WORKERS
) -> List[Dict]:
    """
    Select the best peers based on latency.
    
    Measures RTT to all peers in parallel and returns
    the `count` peers with lowest latency.
    """
    if not peers:
        return []
    
    if len(peers) <= count:
        return peers
    
    # Measure RTT in parallel
    with ThreadPoolExecutor(max_workers=min(max_workers, len(peers))) as executor:
        futures = {executor.submit(measure_rtt, p): p for p in peers}
        results = []
        
        done, not_done = wait(futures.keys(), timeout=HEAD_TIMEOUT * 2)
        
        for future in done:
            peer = futures[future]
            try:
                rtt = future.result()
            except Exception:
                rtt = float("inf")
            results.append((rtt, peer))
        
        # Timed out futures get infinite RTT
        for future in not_done:
            peer = futures[future]
            results.append((float("inf"), peer))
    
    # Sort by RTT
    results.sort(key=lambda x: x[0])
    
    # Select peers with finite RTT first
    selected = [p for rtt, p in results if rtt < float("inf")][:count]
    
    # If not enough, fill with remaining
    if len(selected) < count:
        remaining = [p for rtt, p in results if rtt == float("inf")]
        selected.extend(remaining[:count - len(selected)])
    
    LOG.info(f"Selected {len(selected)} peers (requested {count})")
    return selected


def upload_chunk_to_peer(
    peer: Dict,
    chunk_data: bytes,
    chunk_hash: str,
    timeout: int = UPLOAD_TIMEOUT,
    retries: int = UPLOAD_RETRIES
) -> Dict:
    """
    Upload a chunk to a single peer.
    
    Returns dict with: node_id, ip, port, status, error, duration
    """
    node_id = peer.get("node_id")
    ip = peer.get("ip")
    port = peer.get("port")
    
    result = {
        "node_id": node_id,
        "ip": ip,
        "port": port,
        "status": "pending",
        "error": None,
        "duration": 0,
    }
    
    if not ip or not port:
        result["status"] = "failed"
        result["error"] = "Missing IP or port"
        return result
    
    url = f"http://{ip}:{port}/store"
    session = _make_session(retries=1, backoff_factor=1)
    
    start_time = time.time()
    attempt = 0
    
    while attempt <= retries:
        try:
            # Send as multipart form
            files = {"file": (chunk_hash, chunk_data)}
            data = {"chunk_hash": chunk_hash}
            
            resp = session.post(url, files=files, data=data, timeout=timeout)
            resp.raise_for_status()
            
            result["status"] = "ok"
            result["duration"] = time.time() - start_time
            
            # Include any response data
            try:
                resp_data = resp.json()
                result.update({k: v for k, v in resp_data.items() if k not in result})
            except Exception:
                pass
            
            LOG.debug(f"Uploaded chunk {chunk_hash[:16]}... to {ip}:{port}")
            return result
            
        except Exception as e:
            attempt += 1
            result["error"] = str(e)
            
            if attempt > retries:
                result["status"] = "failed"
                result["duration"] = time.time() - start_time
                LOG.warning(f"Failed to upload chunk to {ip}:{port}: {e}")
                return result
            
            # Exponential backoff
            backoff = BACKOFF_BASE * (2 ** (attempt - 1))
            time.sleep(backoff)
    
    result["status"] = "failed"
    result["duration"] = time.time() - start_time
    return result


def distribute_chunk(
    chunk_data: bytes,
    chunk_hash: str,
    discovery_url: str = None,
    replication: int = REPLICATION_FACTOR,
    max_workers: int = UPLOAD_MAX_WORKERS
) -> List[Dict]:
    """
    Distribute a chunk to multiple peers.
    
    Steps:
    1. Get available peers from discovery
    2. Select best peers based on latency
    3. Upload to selected peers in parallel
    
    Returns list of assignment results with status.
    """
    # Get and select peers
    peers = get_peers(discovery_url or DISCOVERY_URL)
    if not peers:
        LOG.warning("No peers available for chunk distribution")
        return []
    
    selected = select_peers(peers, count=replication)
    if not selected:
        LOG.warning("No peers selected for chunk distribution")
        return []
    
    LOG.info(f"Distributing chunk {chunk_hash[:16]}... to {len(selected)} peers")
    
    # Upload in parallel
    results = []
    with ThreadPoolExecutor(max_workers=min(max_workers, len(selected))) as executor:
        futures = {
            executor.submit(upload_chunk_to_peer, peer, chunk_data, chunk_hash): peer
            for peer in selected
        }
        
        for future in as_completed(futures):
            try:
                result = future.result()
            except Exception as e:
                peer = futures[future]
                result = {
                    "node_id": peer.get("node_id"),
                    "ip": peer.get("ip"),
                    "port": peer.get("port"),
                    "status": "failed",
                    "error": str(e),
                }
            results.append(result)
    
    # Log summary
    success = sum(1 for r in results if r["status"] == "ok")
    LOG.info(f"Chunk {chunk_hash[:16]}... distributed: {success}/{len(results)} success")
    
    return results


def fetch_chunk_from_peer(peer: Dict, chunk_hash: str, timeout: int = PEER_TIMEOUT) -> bytes:
    """
    Fetch a chunk from a peer.
    
    Returns chunk bytes on success, raises exception on failure.
    """
    ip = peer.get("ip")
    port = peer.get("port")
    
    if not ip or not port:
        raise ValueError("Peer missing IP or port")
    
    url = f"http://{ip}:{port}/retrieve/{chunk_hash}"
    
    session = _make_session(retries=1, backoff_factor=1)
    resp = session.get(url, timeout=timeout)
    resp.raise_for_status()
    
    return resp.content


def fetch_chunk(
    chunk_hash: str,
    assignments: List[Dict],
    discovery_url: str = None
) -> Optional[bytes]:
    """
    Fetch a chunk, trying multiple peers.
    
    Args:
        chunk_hash: SHA-256 hash of the chunk
        assignments: List of peer assignments from blockchain
        discovery_url: Optional discovery URL for peer lookup
    
    Returns:
        Chunk bytes on success, None on failure
    """
    # Build list of peers to try
    peers_to_try = []
    
    # First, try assignments with OK status
    for a in assignments:
        if a.get("status") == "ok" and a.get("ip") and a.get("port"):
            peers_to_try.append(a)
    
    # If no valid assignments, try to look up nodes via discovery
    if not peers_to_try and discovery_url:
        for a in assignments:
            node_id = a.get("node_id")
            if node_id:
                try:
                    session = _make_session(retries=0)
                    resp = session.get(
                        f"{discovery_url.rstrip('/')}/peer/{node_id}",
                        timeout=DISCOVERY_TIMEOUT
                    )
                    if resp.status_code == 200:
                        peer_info = resp.json()
                        if peer_info.get("ip") and peer_info.get("port"):
                            peers_to_try.append(peer_info)
                except Exception:
                    pass
    
    # Try each peer
    for peer in peers_to_try:
        try:
            data = fetch_chunk_from_peer(peer, chunk_hash)
            LOG.debug(f"Fetched chunk {chunk_hash[:16]}... from {peer.get('ip')}:{peer.get('port')}")
            return data
        except Exception as e:
            LOG.warning(f"Failed to fetch chunk from {peer.get('ip')}:{peer.get('port')}: {e}")
            continue
    
    LOG.error(f"Failed to fetch chunk {chunk_hash[:16]}... from any peer")
    return None
