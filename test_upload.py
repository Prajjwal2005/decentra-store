import uuid
import time
from backend.models import get_session, FileMetadata, ChunkLocation, User
from sqlalchemy import create_engine

session = get_session()
try:
    user = session.query(User).first()
    if not user:
        print('no user')
        exit()

    file_id = str(uuid.uuid4())
    file_meta = FileMetadata(
        id=file_id,
        owner_id=user.id,
        original_name='test.txt',
        stored_name='test.txt',
        size=100,
        merkle_root='root',
        chunk_count=1,
        encrypted_key='key',
        key_iv='iv1',
        file_iv='iv2'
    )
    session.add(file_meta)
    session.flush()

    chunk = ChunkLocation(
        file_id=file_id,
        chunk_index=0,
        chunk_hash='hash',
        node_id='some-node'
    )
    session.add(chunk)
    user.storage_used_bytes += 100
    session.commit()
    print('success')
except Exception as e:
    print('error:', e)
