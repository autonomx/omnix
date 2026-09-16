from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.desktop_companion.operations import DesktopCompanionOperationalStatus
from app.desktop_companion.routes import register_desktop_companion_routes
from app.desktop_companion.runtime import DesktopCompanionObserveResponse


class CaptureOrchestrator:
    def __init__(self) -> None:
        self.last_request = None

    def observe(self, request):
        self.last_request = request
        return DesktopCompanionObserveResponse(status="suppressed", reason="identity_test")

    def reset(self, session_id: str, capture_generation: str | None = None) -> None:
        return None


class FakeChatStore:
    def __init__(self, session) -> None:
        self.session = session

    def get_session(self, session_id: str):
        return self.session if self.session and self.session.id == session_id else None


class FailingChatStore:
    def get_session(self, session_id: str):
        raise RuntimeError("identity store unavailable")


def payload(*, session_id: str = "chat:character") -> dict:
    return {
        "session_id": session_id,
        "character_id": "browser-spoofed-character",
        "capture_generation": "capture:1",
        "source_fingerprint": "desktop-source:test",
        "client_sequence": 1,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "current_image_data_url": "data:image/jpeg;base64,AAAA",
        "activity": {
            "activity": "full_scene_change",
            "hypothesis": "likely_app_switch",
            "confidence": 0.9,
            "changed_ratio": 0.8,
            "mean_difference": 0.7,
            "focus": 0.3,
            "details": {},
        },
        "behavior": {"current_pattern": "settled", "sample_count": 4},
        "policy": {"enabled": True, "shadow_mode": True},
    }


def operational() -> DesktopCompanionOperationalStatus:
    return DesktopCompanionOperationalStatus(
        available=True,
        kill_switch=False,
        reason="operational",
    )


def test_observe_rebinds_browser_character_to_authoritative_chat_session() -> None:
    runtime = CaptureOrchestrator()
    app = FastAPI()
    register_desktop_companion_routes(
        app,
        orchestrator_factory=lambda: runtime,
        chat_store_factory=lambda: FakeChatStore(
            SimpleNamespace(
                id="chat:character",
                interaction_mode="character",
                character_id="sofia",
            )
        ),
        operational_status_factory=operational,
    )
    client = TestClient(app)

    response = client.post("/api/desktop-companion/observe", json=payload())

    assert response.status_code == 200
    assert runtime.last_request is not None
    assert runtime.last_request.character_id == "sofia"


def test_system_mode_legitimately_resolves_to_no_character() -> None:
    runtime = CaptureOrchestrator()
    app = FastAPI()
    register_desktop_companion_routes(
        app,
        orchestrator_factory=lambda: runtime,
        chat_store_factory=lambda: FakeChatStore(
            SimpleNamespace(
                id="chat:system",
                interaction_mode="system",
                character_id=None,
            )
        ),
        operational_status_factory=operational,
    )
    client = TestClient(app)

    response = client.post(
        "/api/desktop-companion/observe",
        json=payload(session_id="chat:system"),
    )

    assert response.status_code == 200
    assert runtime.last_request is not None
    assert runtime.last_request.character_id is None


def test_missing_authoritative_session_suppresses_before_observation() -> None:
    runtime = CaptureOrchestrator()
    app = FastAPI()
    register_desktop_companion_routes(
        app,
        orchestrator_factory=lambda: runtime,
        chat_store_factory=lambda: FakeChatStore(None),
        operational_status_factory=operational,
    )
    client = TestClient(app)

    response = client.post("/api/desktop-companion/observe", json=payload())

    assert response.status_code == 200
    assert response.json()["status"] == "suppressed"
    assert response.json()["reason"] == "authoritative_session_missing"
    assert runtime.last_request is None


def test_identity_store_failure_fails_closed_before_observation() -> None:
    runtime = CaptureOrchestrator()
    app = FastAPI()
    register_desktop_companion_routes(
        app,
        orchestrator_factory=lambda: runtime,
        chat_store_factory=lambda: FailingChatStore(),
        operational_status_factory=operational,
    )
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post("/api/desktop-companion/observe", json=payload())

    assert response.status_code == 500
    assert runtime.last_request is None
