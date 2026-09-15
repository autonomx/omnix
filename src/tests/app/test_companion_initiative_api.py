from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.companion_activity.initiative import CompanionInitiativeAuthority
from app.companion_activity.routes import register_companion_activity_routes


class FakeChatStore:
    def get_session(self, session_id: str):
        if session_id == "chat:1":
            return SimpleNamespace(id=session_id)
        return None


def app_client(authority: CompanionInitiativeAuthority) -> TestClient:
    app = FastAPI()
    register_companion_activity_routes(
        app,
        authority_factory=lambda: authority,
        chat_store_factory=FakeChatStore,
    )
    return TestClient(app)


def acquire_payload(**updates) -> dict:
    payload = {
        "session_id": "chat:1",
        "owner": "desktop",
        "intent_id": "intent:1",
        "channel": "text",
        "urgency": "normal",
        "interruptibility": "idle_only",
        "ttl_seconds": 15.0,
        "minimum_spacing_seconds": 0.0,
    }
    payload.update(updates)
    return payload


def test_acquire_and_finish_use_server_owned_session_generation() -> None:
    authority = CompanionInitiativeAuthority()
    client = app_client(authority)

    acquired = client.post("/api/companion-initiative/acquire", json=acquire_payload())
    assert acquired.status_code == 200
    body = acquired.json()
    assert body["accepted"] is True
    assert body["lease"]["generation"] == "session"

    blocked = client.post(
        "/api/companion-initiative/acquire",
        json=acquire_payload(intent_id="intent:2"),
    )
    assert blocked.status_code == 200
    assert blocked.json()["accepted"] is False
    assert blocked.json()["reason"] == "initiative_active"

    finished = client.post(
        "/api/companion-initiative/finish",
        json={
            "session_id": "chat:1",
            "lease_id": body["lease"]["lease_id"],
            "delivered": False,
        },
    )
    assert finished.status_code == 200
    assert finished.json() == {"finished": True}


def test_client_cannot_supply_authoritative_time_or_generation() -> None:
    client = app_client(CompanionInitiativeAuthority())
    payload = acquire_payload()
    payload["generation"] = "browser-controlled"
    payload["requested_at"] = "2026-09-15T00:00:00Z"

    response = client.post("/api/companion-initiative/acquire", json=payload)

    assert response.status_code == 422


def test_missing_chat_session_is_rejected_before_authority_mutation() -> None:
    authority = CompanionInitiativeAuthority()
    client = app_client(authority)

    response = client.post(
        "/api/companion-initiative/acquire",
        json=acquire_payload(session_id="chat:missing"),
    )

    assert response.status_code == 404
    assert authority.snapshot("chat:missing").generation is None
