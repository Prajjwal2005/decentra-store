# backend/auth.py
"""
Authentication module for DecentraStore.

Provides:
- User registration and login
- JWT token generation and validation
- Password hashing with bcrypt
- Key derivation for file encryption
"""

import os
import time
import functools
from datetime import datetime, timedelta
from typing import Optional, Tuple

import jwt
import bcrypt
from flask import request, jsonify, g

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import SECRET_KEY, JWT_EXPIRY_HOURS, KDF_SALT_SIZE
from shared.crypto import derive_key_from_password, b64_encode, b64_decode
from backend.models import User, get_session


def hash_password(password: str) -> str:
    """Hash password using bcrypt."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Verify password against hash."""
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def generate_token(user_id: str, username: str) -> str:
    """Generate JWT token for authenticated user."""
    payload = {
        "user_id": user_id,
        "username": username,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def decode_token(token: str) -> Optional[dict]:
    """Decode and validate JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def get_current_user() -> Optional[User]:
    """
    Get current authenticated user from request.
    Checks Authorization header for Bearer token.
    """
    auth_header = request.headers.get("Authorization", "")
    
    if not auth_header.startswith("Bearer "):
        return None
    
    token = auth_header[7:]  # Remove "Bearer " prefix
    payload = decode_token(token)
    
    if not payload:
        return None
    
    session = get_session()
    try:
        user = session.query(User).filter_by(id=payload["user_id"]).first()
        if user and user.is_active:
            return user
    finally:
        session.close()
    
    return None


def login_required(f):
    """Decorator to require authentication."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({"error": "Authentication required"}), 401
        g.current_user = user
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    """Decorator to require admin authentication."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({"error": "Authentication required"}), 401
        if not user.is_admin:
            return jsonify({"error": "Admin access required"}), 403
        g.current_user = user
        return f(*args, **kwargs)
    return decorated


def register_user(username: str, password: str, email: str = None) -> Tuple[Optional[User], Optional[str]]:
    """
    Register a new user.
    
    Returns:
        (User, None) on success
        (None, error_message) on failure
    """
    if not username or len(username) < 3:
        return None, "Username must be at least 3 characters"
    
    if not password or len(password) < 6:
        return None, "Password must be at least 6 characters"
    
    session = get_session()
    try:
        # Check if username exists
        existing = session.query(User).filter_by(username=username).first()
        if existing:
            return None, "Username already taken"
        
        # Check email if provided
        if email:
            existing_email = session.query(User).filter_by(email=email).first()
            if existing_email:
                return None, "Email already registered"
        
        # Generate key derivation salt for this user
        key_salt = os.urandom(KDF_SALT_SIZE)
        
        # Create user
        user = User(
            username=username,
            email=email,
            password_hash=hash_password(password),
            key_salt=b64_encode(key_salt),
        )
        
        session.add(user)
        session.commit()
        
        # Refresh to get generated ID
        session.refresh(user)
        
        return user, None
        
    except Exception as e:
        session.rollback()
        return None, f"Registration failed: {e}"
    finally:
        session.close()


def login_user(username: str, password: str) -> Tuple[Optional[str], Optional[User], Optional[str]]:
    """
    Authenticate user and return JWT token.
    
    Returns:
        (token, User, None) on success
        (None, None, error_message) on failure
    """
    session = get_session()
    try:
        user = session.query(User).filter_by(username=username).first()
        
        if not user:
            return None, None, "Invalid username or password"
        
        if not user.is_active:
            return None, None, "Account is disabled"
        
        if not verify_password(password, user.password_hash):
            return None, None, "Invalid username or password"
        
        # Update last login
        user.last_login = datetime.utcnow()
        session.commit()
        
        # Generate token
        token = generate_token(user.id, user.username)
        
        return token, user, None
        
    except Exception as e:
        session.rollback()
        return None, None, f"Login failed: {e}"
    finally:
        session.close()


def get_user_encryption_key(user: User, password: str) -> bytes:
    """
    Derive the user's encryption key from their password.
    This key is used to encrypt/decrypt file keys.
    
    The salt is stored in the database, so the same password
    always produces the same key for this user.
    """
    salt = b64_decode(user.key_salt)
    key, _ = derive_key_from_password(password, salt)
    return key


def change_password(user: User, old_password: str, new_password: str) -> Tuple[bool, Optional[str]]:
    """
    Change user's password.
    
    Note: This invalidates the encryption key! All file keys would need
    to be re-encrypted with the new key. For simplicity, we generate
    a new key salt, which means old files can't be decrypted.
    
    In production, you'd want to re-encrypt all file keys.
    """
    session = get_session()
    try:
        # Verify old password
        if not verify_password(old_password, user.password_hash):
            return False, "Current password is incorrect"
        
        if len(new_password) < 6:
            return False, "New password must be at least 6 characters"
        
        # Update password and key salt
        user.password_hash = hash_password(new_password)
        user.key_salt = b64_encode(os.urandom(KDF_SALT_SIZE))
        
        session.merge(user)
        session.commit()
        
        return True, None
        
    except Exception as e:
        session.rollback()
        return False, f"Failed to change password: {e}"
    finally:
        session.close()
