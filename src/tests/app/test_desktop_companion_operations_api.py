from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.desktop_companion.operations import DesktopCompanionOperationalStatus
from app.desktop_companion.routes import register_desktop_companion_routes


class ExplodingRuntime:
    def observe(self, request):
        raise AssertionError("kill switch must suppress observation")

    def reset(self, session_id: str, capture_generation: str | None = None) -> None:
        pass


class ExplodingPreflight:
    def check(self, request):
        raise AssertionError("kill switch must suppress preflight")


def killed() -> DesktopCompanionOperationalStatus:
    return DesktopCompanionOperationalStatus(
        available=False,
        kill_switch=True,
        reason="deployment_kill_switch",
    )


def observe_payload() -> dict:
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
        },
        "policy": {"enabled": True, "shadow_mode": True},
    }


def test_kill_switch_disables_preflight_observation_and_rollout() -> None:
    app = FastAPI()
    register_desktop_companion_routes(
        app,
        orchestrator_factory=ExplodingRuntime,
        preflight_service_factory=ExplodingPreflight,
        operational_status_factory=killed,
    )
    client = TestClient(app)

    status = client.get("/api/desktop-companion/operational-status")
    preflight = client.post("/api/desktop-companion/preflight", json={})
    observed = client.post("/api/desktop-companion/observe", json=observe_payload())
    rollout = client.get("/api/desktop-companion/rollout-status?requested_stage=speech")

    assert status.json()["kill_switch"] is True
    assert preflight.json()["ready"] is False
    assert preflight.json()["reason"] == "deployment_kill_switch"
    assert observed.json()["status"] == "suppressed"
    assert observed.json()["reason"] == "deployment_kill_switch"
    assert rollout.json()["effective_stage"] == "disabled"
    assert rollout.json()["reason"] == "deployment_kill_switch"
