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
    def get_session(self, session_id: str):
        if session_id != "chat:character":
            return None
        return SimpleNamespace(
            interaction_mode="character",
            character_id="sofia",
        )


def payload() -> dict:
    return {
        "session_id": "chat:character",
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


def test_observe_rebinds_browser_character_to_authoritative_chat_session() -> None:
    runtime = CaptureOrchestrator()
    app = FastAPI()
    register_desktop_companion_routes(
        app,
        orchestrator_factory=lambda: runtime,
        chat_store_factory=lambda: FakeChatStore(),
        operational_status_factory=lambda: DesktopCompanionOperationalStatus(
            available=True,
            kill_switch=False,
            reason="operational",
        ),
    )
    client = TestClient(app)

    response = client.post("/api/desktop-companion/observe", json=payload())

    assert response.status_code == 200
    assert runtime.last_request is not None
    assert runtime.last_request.character_id == "sofia"
