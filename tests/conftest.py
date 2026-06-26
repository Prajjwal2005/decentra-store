import os
import sys
from pathlib import Path
import pytest

# Ensure the root directory is in the sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set test environment variables BEFORE importing models/app
test_db_path = Path(__file__).parent / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{test_db_path}"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["DATA_DIR"] = "/tmp/decentrastore_test_data"

from backend.app import app as flask_app
from backend.models import Base, get_engine, get_session, User, init_db

@pytest.fixture
def app():
    """Provides a Flask application instance."""
    flask_app.config.update({
        "TESTING": True,
    })
    
    # Initialize the test database
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    
    yield flask_app
    
    # Teardown
    Base.metadata.drop_all(engine)
    try:
        if test_db_path.exists():
            test_db_path.unlink()
    except Exception:
        pass

@pytest.fixture
def client(app):
    """Provides a Flask test client."""
    return app.test_client()

@pytest.fixture
def db_session(app):
    """Provides a database session for tests."""
    session = get_session()
    yield session
    session.rollback()
    session.close()

@pytest.fixture
def test_user(client, db_session):
    """Creates a test user and returns their credentials and user object."""
    from backend.auth import register_user
    user, error = register_user("testuser", "testpass123", "test@example.com")
    assert user is not None
    assert error is None
    return {"username": "testuser", "password": "testpass123", "user": user}
