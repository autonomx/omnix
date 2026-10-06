import secrets

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.security.service_token import require_service_token


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("OMNIX_SERVICE_TOKEN", raising=False)
    app = FastAPI()

    @app.get("/internal/test", dependencies=[Depends(require_service_token)])
    def internal():
        return {"ok": True}

    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield client


def test_missing_configuration_fails_closed(client):
    assert client.get("/internal/test").status_code == 401


def test_only_the_issued_service_token_is_accepted(client, monkeypatch):
    token = secrets.token_urlsafe(32)
    monkeypatch.setenv("OMNIX_SERVICE_TOKEN", token)
    assert client.get("/internal/test").status_code == 401
    assert client.get("/internal/test", headers={"X-Omnix-Service-Token": secrets.token_urlsafe(32)}).status_code == 401
    assert client.get("/internal/test", headers={"X-Omnix-Service-Token": token}).status_code == 200
    assert client.get("/internal/test", headers=[("X-Omnix-Service-Token", token), ("X-Omnix-Service-Token", token)]).status_code == 401


@pytest.mark.parametrize("token", ["short", "a" * 32, "contains whitespace " * 4, "non-ascii-\u2603" * 5])
def test_invalid_issued_tokens_fail_closed(client, monkeypatch, token):
    monkeypatch.setenv("OMNIX_SERVICE_TOKEN", token)
    assert client.get("/internal/test", headers={"X-Omnix-Service-Token": "a" * 43}).status_code == 401
