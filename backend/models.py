# backend/models.py
"""
Database models for DecentraStore.

Uses SQLAlchemy with SQLite for user management.
"""

import uuid
import time
from datetime import datetime
from typing import Optional

from sqlalchemy import create_engine, Column, String, Integer, Float, Text, Boolean, DateTime
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
    storage_quota_bytes = Column(Integer, default=10 * 1024 * 1024 * 1024)  # 10 GB default
    storage_used_bytes = Column(Integer, default=0)
    
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
    Base.metadata.create_all(engine)


# Initialize on import
init_db()
