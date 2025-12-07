"""
Authentication module for DecentraStore.

Provides:
- User registration and login routes (Flask Blueprint)
- JWT token generation and validation
- Password hashing with bcrypt
- Password change and "me" endpoints

Drop this file in `backend/` (replace/merge with your existing auth.py).
"""

import os
import functools
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple

import jwt
import bcrypt
from flask import Blueprint, request, jsonify, g, current_app

# Keep these imports consistent with your project structure
from config import SECRET_KEY, JWT_EXPIRY_HOURS, KDF_SALT_SIZE
from shared.crypto import derive_key_from_password, b64_encode, b64_decode
from backend.models import User, get_session

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)

# -------------------------
# Utility / core functions
# -------------------------
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
        "user_id": str(user_id),
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


def get_current_user():
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
        if user and getattr(user, "is_active", True):
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
        if not getattr(user, "is_admin", False):
            return jsonify({"error": "Admin access required"}), 403
        g.current_user = user
        return f(*args, **kwargs)
    return decorated


def register_user(username: str, password: str, email: str = None) -> Tuple[Optional[User], Optional[str]]:
    """
    Register a new user.
    Returns (User, None) on success, (None, error_message) on failure.
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

        # Create user object (adjust fields to your User model)
        user = User(
            username=username,
            email=email,
            password_hash=hash_password(password),
            key_salt=b64_encode(key_salt),
            is_active=True
        )

        session.add(user)
        session.commit()

        # Refresh to get generated ID
        session.refresh(user)

        return user, None

    except Exception as e:
        session.rollback()
        logger.exception("Registration failed")
        return None, f"Registration failed: {e}"
    finally:
        session.close()


def login_user(username: str, password: str) -> Tuple[Optional[str], Optional[User], Optional[str]]:
    """
    Authenticate user and return JWT token.
    Returns (token, User, None) on success, (None, None, error_message) on failure.
    """
    session = get_session()
    try:
        user = session.query(User).filter_by(username=username).first()

        if not user:
            return None, None, "Invalid username or password"

        if not getattr(user, "is_active", True):
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
        logger.exception("Login failed")
        return None, None, f"Login failed: {e}"
    finally:
        session.close()


def get_user_encryption_key(user: User, password: str) -> bytes:
    """
    Derive the user's encryption key from their password.
    """
    salt = b64_decode(user.key_salt)
    key, _ = derive_key_from_password(password, salt)
    return key


def change_password(user: User, old_password: str, new_password: str) -> Tuple[bool, Optional[str]]:
    """
    Change user's password.
    """
    session = get_session()
    try:
        # Re-fetch user to ensure session ownership
        u = session.query(User).filter_by(id=user.id).first()
        if not u:
            return False, "User not found"

        # Verify old password
        if not verify_password(old_password, u.password_hash):
            return False, "Current password is incorrect"

        if len(new_password) < 6:
            return False, "New password must be at least 6 characters"

        # Update password and key salt
        u.password_hash = hash_password(new_password)
        u.key_salt = b64_encode(os.urandom(KDF_SALT_SIZE))

        session.merge(u)
        session.commit()

        return True, None

    except Exception as e:
        session.rollback()
        logger.exception("Change password failed")
        return False, f"Failed to change password: {e}"
    finally:
        session.close()

# -------------------------
# Flask routes
# -------------------------
def _parse_json_or_form():
    """
    Helper: accept JSON or form-encoded bodies (helps when frontend forgets Content-Type).
    """
    data = request.get_json(silent=True)
    if data:
        return data
    if request.form:
        return request.form.to_dict()
    # try to parse querystring as fallback
    return request.args.to_dict()

@auth_bp.route("/register", methods=["POST"])
def register_route():
    # Debug log raw body to help diagnose Content-Type issues
    try:
        current_app.logger.debug("RAW BODY: %s", request.get_data(as_text=True))
    except Exception:
        pass

    data = _parse_json_or_form()
    username = (data.get("username") or "").strip()
    password = data.get("password")
    email = data.get("email")

    user, error = register_user(username, password, email)
    if error:
        return jsonify({"error": error}), 400

    # Do not return the password/hash or key salt
    return jsonify({
        "message": "User registered successfully",
        "user": {"id": str(user.id), "username": user.username, "email": user.email}
    }), 201


@auth_bp.route("/login", methods=["POST"])
def login_route():
    data = _parse_json_or_form()
    username = data.get("username") or ""
    password = data.get("password")

    token, user, error = login_user(username, password)
    if error:
        return jsonify({"error": error}), 400

    return jsonify({
        "token": token,
        "user": {"id": str(user.id), "username": user.username, "email": user.email}
    }), 200


@auth_bp.route("/me", methods=["GET"])
@login_required
def me_route():
    user = g.current_user
    return jsonify({
        "user": {
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "is_admin": getattr(user, "is_admin", False)
        }
    }), 200


@auth_bp.route("/change-password", methods=["POST"])
@login_required
def change_password_route():
    data = _parse_json_or_form()
    old_password = data.get("old_password")
    new_password = data.get("new_password")

    if not old_password or not new_password:
        return jsonify({"error": "Both old_password and new_password are required"}), 400

    ok, err = change_password(g.current_user, old_password, new_password)
    if not ok:
        return jsonify({"error": err}), 400

    return jsonify({"message": "Password updated successfully"}), 200

# -------------------------
# Blueprint registration note
# -------------------------
# Make sure you register this blueprint in your main app, for example:
# from backend.auth import auth_bp
# app.register_blueprint(auth_bp, url_prefix="/auth")
