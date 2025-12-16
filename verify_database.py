#!/usr/bin/env python3
"""
Database Verification Script for DecentraStore

Checks if PostgreSQL database is correctly storing:
- User accounts
- File metadata
- Chunk assignments
- Blockchain data
- Storage nodes

Usage:
    python verify_database.py

    Or via Railway:
    railway run python verify_database.py
"""

import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from backend.models import get_session, User, File, StorageNode
from backend.blockchain import Blockchain
import json
from datetime import datetime


def format_size(bytes_size):
    """Format bytes to human-readable size."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024
    return f"{bytes_size:.2f} TB"


def verify_users(session):
    """Check user accounts in database."""
    print("\n" + "="*60)
    print("USER ACCOUNTS")
    print("="*60)

    users = session.query(User).all()

    if not users:
        print("❌ No users found in database")
        return False

    print(f"✅ Found {len(users)} user(s):\n")

    for user in users:
        created = datetime.fromtimestamp(user.created_at).strftime('%Y-%m-%d %H:%M:%S')
        print(f"  👤 {user.username}")
        print(f"     Email: {user.email}")
        print(f"     User ID: {user.user_id}")
        print(f"     Created: {created}")
        print(f"     Password Hash: {user.password_hash[:20]}...")
        print()

    return True


def verify_files(session):
    """Check file metadata in database."""
    print("\n" + "="*60)
    print("FILE METADATA")
    print("="*60)

    files = session.query(File).all()

    if not files:
        print("⚠️  No files found in database (upload a file to test)")
        return True  # Not an error, just no files yet

    print(f"✅ Found {len(files)} file(s):\n")

    total_size = 0
    total_chunks = 0

    for file in files:
        uploaded = datetime.fromtimestamp(file.uploaded_at).strftime('%Y-%m-%d %H:%M:%S')
        print(f"  📄 {file.filename}")
        print(f"     File ID: {file.file_id}")
        print(f"     Owner: {file.owner_id}")
        print(f"     Size: {format_size(file.file_size)}")
        print(f"     Chunks: {file.chunk_count}")
        print(f"     Encrypted Key: {file.encrypted_key[:40]}...")
        print(f"     IV: {file.iv}")
        print(f"     Merkle Root: {file.merkle_root}")
        print(f"     Uploaded: {uploaded}")
        print(f"     Deleted: {file.deleted}")

        # Parse chunks to see assignments
        try:
            chunks = json.loads(file.chunks)
            print(f"     Chunk Assignments: {len(chunks)} chunks")
            if chunks:
                first_chunk = chunks[0]
                if 'assignments' in first_chunk:
                    print(f"       - Replication factor: {len(first_chunk['assignments'])} nodes per chunk")
        except Exception as e:
            print(f"     Chunk Parsing Error: {e}")

        print()
        total_size += file.file_size
        total_chunks += file.chunk_count

    print(f"\n📊 Total: {format_size(total_size)} across {total_chunks} chunks")
    return True


def verify_storage_nodes(session):
    """Check registered storage nodes."""
    print("\n" + "="*60)
    print("STORAGE NODES")
    print("="*60)

    nodes = session.query(StorageNode).all()

    if not nodes:
        print("⚠️  No storage nodes registered (start a node to test)")
        return True  # Not an error, just no nodes yet

    print(f"✅ Found {len(nodes)} storage node(s):\n")

    for node in nodes:
        last_seen = datetime.fromtimestamp(node.last_seen).strftime('%Y-%m-%d %H:%M:%S')
        registered = datetime.fromtimestamp(node.registered_at).strftime('%Y-%m-%d %H:%M:%S')

        print(f"  🖥️  {node.node_id}")
        print(f"     IP: {node.ip}:{node.port}")
        print(f"     Public IP: {node.public_ip}")
        print(f"     Status: {node.status}")
        print(f"     Capacity: {node.capacity_gb} GB")
        print(f"     Registered: {registered}")
        print(f"     Last Seen: {last_seen}")

        # Check if node is online (seen in last 5 minutes)
        import time
        age = time.time() - node.last_seen
        if age < 300:
            print(f"     🟢 ONLINE (last seen {int(age)}s ago)")
        else:
            print(f"     🔴 OFFLINE (last seen {int(age/60)}m ago)")

        print()

    return True


def verify_blockchain(session):
    """Check blockchain persistence."""
    print("\n" + "="*60)
    print("BLOCKCHAIN DATA")
    print("="*60)

    try:
        blockchain = Blockchain(session)

        print(f"✅ Blockchain loaded successfully")
        print(f"   Total Blocks: {len(blockchain.chain)}")
        print(f"   Chain Valid: {blockchain.is_valid()}")
        print()

        # Show recent blocks
        recent_blocks = blockchain.chain[-5:] if len(blockchain.chain) > 5 else blockchain.chain

        print(f"Recent blocks (showing last {len(recent_blocks)}):\n")

        for block in recent_blocks:
            timestamp = datetime.fromtimestamp(block['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
            print(f"  📦 Block #{block['index']}")
            print(f"     Hash: {block['hash'][:40]}...")
            print(f"     Previous: {block['previous_hash'][:40]}...")
            print(f"     Timestamp: {timestamp}")
            print(f"     Nonce: {block['nonce']}")
            print(f"     Difficulty: {block['difficulty']}")

            # Check if it's a file block
            if block.get('file_metadata'):
                meta = block['file_metadata']
                print(f"     📄 File: {meta.get('filename')}")
                print(f"        Size: {format_size(meta.get('file_size', 0))}")
                print(f"        Chunks: {meta.get('chunk_count')}")
                print(f"        Owner: {meta.get('owner_id')}")

            print()

        return True

    except Exception as e:
        print(f"❌ Blockchain error: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_database_connection():
    """Verify database connection."""
    print("\n" + "="*60)
    print("DATABASE CONNECTION")
    print("="*60)

    database_url = os.getenv('DATABASE_URL')

    if not database_url:
        print("❌ DATABASE_URL environment variable not set")
        print("   For Railway, this should be set automatically")
        print("   For local testing, set it in .env file")
        return False

    # Hide password in output
    safe_url = database_url
    if '@' in database_url:
        parts = database_url.split('@')
        credentials = parts[0].split('//')[-1]
        if ':' in credentials:
            user = credentials.split(':')[0]
            safe_url = database_url.replace(credentials, f"{user}:***")

    print(f"✅ DATABASE_URL configured")
    print(f"   {safe_url}")

    try:
        session = get_session()
        # Test query
        result = session.execute("SELECT version()").fetchone()
        print(f"\n✅ Connection successful")
        print(f"   PostgreSQL Version: {result[0]}")
        session.close()
        return True
    except Exception as e:
        print(f"\n❌ Connection failed: {e}")
        return False


def main():
    """Run all verification checks."""
    print("\n" + "="*60)
    print("DECENTRASTORE DATABASE VERIFICATION")
    print("="*60)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Check database connection first
    if not verify_database_connection():
        print("\n❌ Cannot proceed without database connection")
        sys.exit(1)

    # Get session for all checks
    session = get_session()

    try:
        # Run all verification checks
        results = {
            'users': verify_users(session),
            'files': verify_files(session),
            'nodes': verify_storage_nodes(session),
            'blockchain': verify_blockchain(session),
        }

        # Summary
        print("\n" + "="*60)
        print("VERIFICATION SUMMARY")
        print("="*60)

        all_passed = all(results.values())

        for check, passed in results.items():
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"{status} - {check.upper()}")

        print("\n" + "="*60)

        if all_passed:
            print("✅ All checks passed - Database is working correctly!")
            sys.exit(0)
        else:
            print("❌ Some checks failed - Review errors above")
            sys.exit(1)

    finally:
        session.close()


if __name__ == "__main__":
    main()
