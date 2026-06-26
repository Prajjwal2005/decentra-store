# backend/models.py
"""
Database models for DecentraStore.

Uses SQLAlchemy with SQLite for user management.
"""

import uuid
import time
from datetime import datetime
from typing import Optional
from sqlalchemy import create_engine, Column, String, Integer, Float, Text, Boolean, DateTime, BigInteger, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATABASE_URL, DATA_DIR

Base = declarative_base()


class User(Base):
    """User account model."""
    
    __tablename__ = "users"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(64), unique=True, nullable=False, index=True)
    email = Column(String(120), unique=True, nullable=True)
    password_hash = Column(String(128), nullable=False)
    
    # Key derivation salt (for encrypting file keys)
    key_salt = Column(String(64), nullable=False)
    
    # Account status
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    
    # Storage quota
    storage_quota_bytes = Column(BigInteger, default=10 * 1024 * 1024 * 1024)  # 10 GB default
    storage_used_bytes = Column(BigInteger, default=0)
    
    def to_dict(self, include_private: bool = False) -> dict:
        """Convert to dictionary."""
        d = {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "storage_quota_bytes": self.storage_quota_bytes,
            "storage_used_bytes": self.storage_used_bytes,
        }
        if include_private:
            d["key_salt"] = self.key_salt
            d["is_admin"] = self.is_admin
        return d


class UploadSession(Base):
    """
    Temporary upload session tracking.
    Used for resumable uploads and tracking in-progress uploads.
    """
    
    __tablename__ = "upload_sessions"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), nullable=False, index=True)
    
    # File info
    filename = Column(String(256), nullable=False)
    file_size = Column(Integer, nullable=False)
    file_hash = Column(String(64), nullable=True)
    
    # Progress
    chunks_total = Column(Integer, default=0)
    chunks_uploaded = Column(Integer, default=0)
    
    # Status: pending, uploading, distributing, complete, failed
    status = Column(String(20), default="pending")
    error_message = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    # Encrypted file key (for the owner)
    encrypted_file_key = Column(Text, nullable=True)


class FileMetadata(Base):
    """File metadata replacing the custom blockchain."""
    
    __tablename__ = "files"
    
    id = Column(String(36), primary_key=True)
    owner_id = Column(String(36), ForeignKey('users.id'), nullable=False, index=True)
    
    original_name = Column(String(256), nullable=False)
    stored_name = Column(String(256), nullable=False)
    size = Column(BigInteger, nullable=False)
    mime_type = Column(String(128), default="application/octet-stream")
    
    merkle_root = Column(String(64), nullable=False)
    chunk_count = Column(Integer, nullable=False)
    
    # Encryption metadata
    encrypted_key = Column(Text, nullable=False)  # File key encrypted with user's key
    key_iv = Column(String(32), nullable=False)   # IV for the wrapped key (base64)
    file_iv = Column(String(32), nullable=False)  # IV for the encrypted file blob (base64)
    
    # Relationships
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            "id": self.id,
            "owner_id": self.owner_id,
            "original_name": self.original_name,
            "stored_name": self.stored_name,
            "size": self.size,
            "mime_type": self.mime_type,
            "merkle_root": self.merkle_root,
            "chunk_count": self.chunk_count,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class ChunkLocation(Base):
    """Maps chunks to the storage nodes hosting them."""
    
    __tablename__ = "chunk_locations"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    file_id = Column(String(36), ForeignKey('files.id'), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    chunk_hash = Column(String(64), nullable=False)
    node_id = Column(String(36), ForeignKey('nodes.id'), nullable=False, index=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)


class Node(Base):
    """Registered storage nodes."""
    
    __tablename__ = "nodes"
    
    id = Column(String(36), primary_key=True)
    url = Column(String(256), nullable=False)
    
    capacity_bytes = Column(BigInteger, default=0)
    used_bytes = Column(BigInteger, default=0)
    
    is_active = Column(Boolean, default=True)
    last_heartbeat = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            "id": self.id,
            "url": self.url,
            "capacity_bytes": self.capacity_bytes,
            "used_bytes": self.used_bytes,
            "is_active": self.is_active,
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None
        }

# Database initialization
def get_engine():
    """Get or create database engine."""
    # Handle SQLite path
    db_url = DATABASE_URL
    if db_url.startswith("sqlite:///"):
        db_path = db_url.replace("sqlite:///", "")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    
    return create_engine(db_url, echo=False)


def get_session():
    """Get a database session."""
    engine = get_engine()
    Session = scoped_session(sessionmaker(bind=engine))
    return Session()


def init_db():
    """Initialize database tables."""
    engine = get_engine()
    # Temporary: reset database schema for Phase 2
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


# Initialize on import
init_db()
