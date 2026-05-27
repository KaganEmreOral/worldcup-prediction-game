"""Authentication API tests."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.auth.security import create_access_token, decode_token, hash_password, verify_password
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def unique_username():
    return f"testuser_{uuid.uuid4().hex[:10]}"


def test_password_hash_roundtrip():
    hashed = hash_password("secret123")
    assert verify_password("secret123", hashed)
    assert not verify_password("wrong", hashed)


def test_jwt_create_and_decode():
    token = create_access_token(42, is_admin=True)
    payload = decode_token(token)
    assert payload is not None
    assert payload["sub"] == "42"
    assert payload["admin"] is True


def test_register_success(client, unique_username):
    res = client.post(
        "/api/auth/register",
        json={"username": unique_username, "password": "password123"},
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert "access_token" in data
    assert data["user"]["username"] == unique_username.lower()
    assert data["user"]["is_admin"] is False


def test_register_duplicate_username(client, unique_username):
    payload = {"username": unique_username, "password": "password123"}
    first = client.post("/api/auth/register", json=payload)
    assert first.status_code == 201, first.text

    second = client.post("/api/auth/register", json=payload)
    assert second.status_code == 400
    assert "already taken" in second.json()["detail"].lower()


def test_register_validation_errors(client):
    res = client.post("/api/auth/register", json={"username": "ab", "password": "123"})
    assert res.status_code == 422


def test_login_success(client, unique_username):
    client.post(
        "/api/auth/register",
        json={"username": unique_username, "password": "password123"},
    )
    res = client.post(
        "/api/auth/login",
        json={"username": unique_username, "password": "password123"},
    )
    assert res.status_code == 200, res.text
    assert "access_token" in res.json()


def test_login_invalid_password(client, unique_username):
    client.post(
        "/api/auth/register",
        json={"username": unique_username, "password": "password123"},
    )
    res = client.post(
        "/api/auth/login",
        json={"username": unique_username, "password": "wrongpassword"},
    )
    assert res.status_code == 401
    assert "invalid" in res.json()["detail"].lower()


def test_jwt_me_endpoint(client, unique_username):
    reg = client.post(
        "/api/auth/register",
        json={"username": unique_username, "password": "password123"},
    )
    token = reg.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["username"] == unique_username.lower()


def test_jwt_invalid_token(client):
    res = client.get("/api/auth/me", headers={"Authorization": "Bearer invalid.token.here"})
    assert res.status_code == 401
