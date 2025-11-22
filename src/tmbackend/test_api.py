# src/tmbackend/test_api.py

import os
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from jose import jwt

# Use a separate test database so you don't pollute your real dev DB
os.environ.setdefault("DATABASE_NAME", "resume_builder_test")

from tmbackend.api import app
import tmbackend.api as api_module
import tmbackend.auth as auth


# =========================
# FIXTURES
# =========================

@pytest.fixture
def client():
    """
    Creates a TestClient that triggers startup/shutdown
    so Mongo initializes before tests.
    """
    with TestClient(app) as c:
        yield c


@pytest.fixture
def mock_google_token(monkeypatch):
    """
    Monkeypatches verify_google_token so we don't hit Google during tests.
    Ensures /auth/google always returns the same fake user.
    """

    async def fake_verify_google_token(token: str):
        return {
            "google_sub": "test-google-sub-123",
            "email": "testuser@example.com",
        }

    # Patch the already-imported reference inside api_module
    monkeypatch.setattr(api_module, "verify_google_token", fake_verify_google_token)

    return fake_verify_google_token


# =========================
# HEALTH CHECK
# =========================

def test_health_check(client: TestClient):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "healthy"}


# =========================
# AUTH TESTS
# =========================

def test_google_login_creates_user_and_sets_cookie(client: TestClient, mock_google_token):
    resp = client.post("/auth/google", json={"token": "fake-token"})
    assert resp.status_code == 200

    body = resp.json()
    assert "user" in body
    assert body["user"]["email"] == "testuser@example.com"
    assert "id" in body["user"]

    # Cookie set?
    assert "access_token" in resp.cookies
    assert resp.cookies.get("access_token") is not None


def test_get_current_user_requires_auth(client: TestClient):
    resp = client.get("/auth/me")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Not authenticated"


def test_get_current_user_after_login(client: TestClient, mock_google_token):
    client.post("/auth/google", json={"token": "fake-token"})

    resp = client.get("/auth/me")
    assert resp.status_code == 200

    data = resp.json()
    assert data["email"] == "testuser@example.com"
    assert "created_at" in data
    assert "last_login_at" in data


# =========================
# RESUME TESTS
# =========================

def test_create_resume_requires_auth(client: TestClient):
    resp = client.post("/resumes", json={
        "target_role": "Software Engineer",
        "content": {"summary": "Test"}
    })
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Not authenticated"


def test_create_and_list_resumes(client: TestClient, mock_google_token):
    # Login
    client.post("/auth/google", json={"token": "fake-token"})

    # Create resume
    create_resp = client.post("/resumes", json={
        "target_role": "Backend Intern",
        "content": {"summary": "Strong coder"},
    })
    assert create_resp.status_code == 200
    resume_id = create_resp.json()["id"]

    # List resumes
    list_resp = client.get("/resumes")
    assert list_resp.status_code == 200

    resumes = list_resp.json()
    assert any(r["id"] == resume_id for r in resumes)


def test_get_single_resume(client: TestClient, mock_google_token):
    client.post("/auth/google", json={"token": "fake-token"})

    create_resp = client.post("/resumes", json={
        "target_role": "Data Scientist",
        "content": {"summary": "ML student"},
    })
    resume_id = create_resp.json()["id"]

    get_resp = client.get(f"/resumes/{resume_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == resume_id


def test_get_resume_invalid_id_format(client: TestClient, mock_google_token):
    client.post("/auth/google", json={"token": "fake-token"})
    resp = client.get("/resumes/not-a-valid-objectid")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid resume ID"


def test_update_resume(client: TestClient, mock_google_token):
    client.post("/auth/google", json={"token": "fake-token"})

    create_resp = client.post("/resumes", json={
        "target_role": "Old Role",
        "content": {"summary": "Old"},
    })
    resume_id = create_resp.json()["id"]

    update_resp = client.put(f"/resumes/{resume_id}", json={
        "target_role": "New Role",
        "content": {"summary": "New"},
    })
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["target_role"] == "New Role"
    assert updated["content"]["summary"] == "New"


def test_delete_resume_soft_delete(client: TestClient, mock_google_token):
    client.post("/auth/google", json={"token": "fake-token"})

    create_resp = client.post("/resumes", json={
        "target_role": "Delete Me",
        "content": {"summary": "bye"},
    })
    resume_id = create_resp.json()["id"]

    delete_resp = client.delete(f"/resumes/{resume_id}")
    assert delete_resp.status_code == 200

    # Should disappear from list
    list_resp = client.get("/resumes")
    assert all(r["id"] != resume_id for r in list_resp.json())

    # Should 404 when fetched directly
    get_resp = client.get(f"/resumes/{resume_id}")
    assert get_resp.status_code == 404


# =========================
# SESSION / COOKIE TESTS
# =========================

def test_invalid_token_in_cookie_returns_401(client: TestClient):
    client.cookies.set("access_token", "garbage-token")

    resp = client.get("/auth/me")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid authentication credentials"


def test_expired_token_in_cookie_returns_401(client: TestClient):
    expired_payload = {
        "sub": "some-user",
        "exp": datetime.utcnow() - timedelta(hours=1),
    }
    expired_jwt = jwt.encode(
        expired_payload,
        auth.SECRET_KEY,
        algorithm=auth.ALGORITHM,
    )

    client.cookies.set("access_token", expired_jwt)

    resp = client.get("/auth/me")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid authentication credentials"


def test_session_cookie_persists(client: TestClient, mock_google_token):
    login_resp = client.post("/auth/google", json={"token": "fake-token"})
    assert login_resp.status_code == 200

    cookie = client.cookies.get("access_token")
    assert cookie is not None

    me_resp = client.get("/auth/me")
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "testuser@example.com"
