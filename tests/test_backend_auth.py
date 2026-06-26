import json

def test_register_success(client):
    """Test successful user registration."""
    response = client.post('/auth/register', json={
        "username": "newuser",
        "password": "strongpassword123",
        "email": "newuser@example.com"
    })
    assert response.status_code in (200, 201)
    data = json.loads(response.data)
    assert "error" not in data
    assert data.get("status") == "registered"
    assert data["user"]["username"] == "newuser"

def test_register_duplicate_username(client, test_user):
    """Test registration with an already existing username."""
    response = client.post('/auth/register', json={
        "username": test_user["username"],
        "password": "anotherpassword",
        "email": "another@example.com"
    })
    assert response.status_code == 400
    data = json.loads(response.data)
    assert "Username already taken" in data["error"]

def test_login_success(client, test_user):
    """Test successful login returns a JWT token."""
    response = client.post('/auth/login', json={
        "username": test_user["username"],
        "password": test_user["password"]
    })
    assert response.status_code == 200
    data = json.loads(response.data)
    assert "token" in data
    assert data["user"]["username"] == test_user["username"]

def test_login_invalid_password(client, test_user):
    """Test login with wrong password."""
    response = client.post('/auth/login', json={
        "username": test_user["username"],
        "password": "wrongpassword"
    })
    assert response.status_code in (400, 401)
    data = json.loads(response.data)
    assert "Invalid username or password" in data["error"]

def test_me_endpoint_requires_auth(client):
    """Test that /auth/me requires authentication."""
    response = client.get('/auth/me')
    assert response.status_code == 401

def test_me_endpoint_success(client, test_user):
    """Test that /auth/me returns user data when authenticated."""
    # First login to get token
    login_resp = client.post('/auth/login', json={
        "username": test_user["username"],
        "password": test_user["password"]
    })
    token = json.loads(login_resp.data)["token"]
    
    # Then access /me
    response = client.get('/auth/me', headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["user"]["username"] == test_user["username"]
