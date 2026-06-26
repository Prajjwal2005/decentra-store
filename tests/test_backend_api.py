def test_app_exists(app):
    """Test that the app exists and is configured for testing."""
    assert app is not None
    assert app.config["TESTING"] is True

def test_my_files_requires_auth(client):
    """Test that the /files endpoint requires authentication."""
    response = client.get('/files')
    assert response.status_code == 401
