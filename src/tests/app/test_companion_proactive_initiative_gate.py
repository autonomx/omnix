from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.characters import api as character_api
from app.characters.api import register_character_routes
from app.companion_activity.initiative import CompanionInitiativeAuthority


class FakeChatStore:
    def get_session(self, session_id: str):
        if session_id != "chat:1":
            return None
        return SimpleNamespace(
            id=session_id,
            messages=[],
            provider_id="test",
            model_id="test",
        )


def client(authority: CompanionInitiativeAuthority) -> TestClient:
    app = FastAPI()
    register_character_routes(
        app,
        chat_store_factory=FakeChatStore,
        initiative_authority_factory=lambda: authority,
    )
    return TestClient(app)


def fake_stream(_store, _session, *, initiative_reason: str, **_kwargs):
    turn_id = "desktop:critical" if initiative_reason.startswith("desktop_critical:") else "desktop:normal"
    yield {
        "type": "initiative",
        "turn_id": turn_id,
        "initiative_reason": initiative_reason,
    }
    yield {"type": "text_chunk", "text": "A grounded reaction."}
    yield {
        "type": "complete",
        "content": "A grounded reaction.",
        "metadata": {
            "purpose": "desktop_critical" if "critical" in turn_id else "desktop_companion",
            "turn_id": turn_id,
            "initiative_reason": initiative_reason,
        },
    }


def test_proactive_generation_is_serialized_and_critical_can_preempt(monkeypatch) -> None:
    authority = CompanionInitiativeAuthority()
    monkeypatch.setattr(character_api, "stream_proactive_turn_chunks", fake_stream)
    http = client(authority)

    first = http.post(
        "/api/chat/sessions/chat:1/live-call/greeting/stream",
        params={
            "purpose": "proactive_reengagement",
            "initiative_reason": "desktop_companion:observation:1",
        },
    )
    assert first.status_code == 200
    assert authority.snapshot("chat:1").active_lease.intent_id == "desktop:normal"

    blocked = http.post(
        "/api/chat/sessions/chat:1/live-call/greeting/stream",
        params={
            "purpose": "proactive_reengagement",
            "initiative_reason": "continue_current_topic",
        },
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == "initiative_active"

    critical = http.post(
        "/api/chat/sessions/chat:1/live-call/greeting/stream",
        params={
            "purpose": "proactive_reengagement",
            "initiative_reason": "desktop_critical:observation:2",
        },
    )
    assert critical.status_code == 200
    assert authority.snapshot("chat:1").active_lease.intent_id == "desktop:critical"

    stale_delivery = http.post(
        "/api/chat/sessions/chat:1/live-conversation/proactive/delivery",
        json={
            "turn_id": "desktop:normal",
            "content": "A grounded reaction.",
            "initiative_reason": "desktop_companion:observation:1",
            "purpose": "desktop_companion",
            "delivery_status": "completed",
        },
    )
    assert stale_delivery.status_code == 409
    assert stale_delivery.json()["detail"] == "initiative_lease_inactive"
