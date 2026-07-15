from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.desktop_companion.routes import register_desktop_companion_routes
from app.desktop_companion.runtime import DesktopCompanionObserveResponse


class FakeOrchestrator:
    def __init__(self) -> None:
        self.reset_calls: list[tuple[str, str | None]] = []

    def observe(self, request):
        return DesktopCompanionObserveResponse(
            status="suppressed",
            reason="shadow_fixture",
        )

    def reset(self, session_id: str, capture_generation: str | None = None) -> None:
        self.reset_calls.append((session_id, capture_generation))


def payload() -> dict:
    return {
        "session_id": "chat:desktop",
        "capture_generation": "capture:1",
        "source_fingerprint": "desktop-source:1234",
        "client_sequence": 1,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "current_image_data_url": "data:image/jpeg;base64,AAAA",
        "activity": {
            "activity": "full_scene_change",
            "hypothesis": "likely_app_switch",
            "confidence": 0.9,
            "changed_ratio": 0.8,
            "mean_difference": 0.7,
            "horizontal_shift": 0,
            "vertical_shift": 0,
            "focus": 0.3,
            "details": {},
        },
        "behavior": {"current_pattern": "settled", "sample_count": 4},
        "policy": {"enabled": True, "shadow_mode": True},
    }


def test_observe_and_reset_routes_use_injected_runtime() -> None:
    runtime = FakeOrchestrator()
    app = FastAPI()
    register_desktop_companion_routes(app, orchestrator_factory=lambda: runtime)
    client = TestClient(app)

    observed = client.post("/api/desktop-companion/observe", json=payload())
    assert observed.status_code == 200
    assert observed.json()["reason"] == "shadow_fixture"

    reset = client.post(
        "/api/desktop-companion/reset",
        json={"session_id": "chat:desktop", "capture_generation": "capture:1"},
    )
    assert reset.status_code == 200
    assert runtime.reset_calls == [("chat:desktop", "capture:1")]
