from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.desktop_companion.build_identity import DesktopCompanionBuildIdentity
from app.desktop_companion.evaluation import DesktopCompanionEvaluationStore
from app.desktop_companion.routes import register_desktop_companion_routes

COMMIT_SHA = "94a179154dc98f6e455c604bed100c0beee06046"


def payload(index: int, scenario: str, *, stage: str = "shadow") -> dict:
    return {
        "run_id": f"api-run-{index}",
        "session_id": "chat-api",
        "started_at": f"2026-07-14T12:{index:02d}:00Z",
        "ended_at": f"2026-07-14T12:{index:02d}:30Z",
        "exact_commit_sha": COMMIT_SHA,
        "rollout_stage": stage,
        "vision_provider": "lmstudio",
        "vision_model_hash": "abc123",
        "remote_provider": False,
        "counts": {"max_vision_calls_per_minute": 6, "observations": 20},
        "latency_ms": {"observation_p95": 5_000},
        "rates": {
            "stale_output_rate": 0,
            "duplicate_comment_rate": 0,
            "unsupported_claim_rate": 0,
            "collision_rate": 0,
            "provider_error_rate": 0,
        },
        "scenario_labels": [scenario],
    }


def test_desktop_companion_evaluation_and_rollout_api(tmp_path: Path):
    store = DesktopCompanionEvaluationStore(tmp_path / "desktop-evaluations.json")
    app = FastAPI()
    register_desktop_companion_routes(
        app,
        evaluation_store_factory=lambda: store,
        build_identity_factory=lambda: DesktopCompanionBuildIdentity(
            exact_commit_sha=COMMIT_SHA,
            app_version="1.0.0",
            source="test",
        ),
    )
    client = TestClient(app)
    scenarios = [
        "static-screen",
        "typing",
        "rapid-browsing",
        "scene-change",
        "interruption",
        "screen-prompt-injection",
    ]

    for index in range(12):
        scenario = scenarios[index % len(scenarios)]
        response = client.post("/api/desktop-companion/evaluations", json=payload(index, scenario))
        assert response.status_code == 200
        assert response.json()["evaluation_id"].startswith("desktop-eval:")

    records = client.get("/api/desktop-companion/evaluations?session_id=chat-api").json()
    assert len(records) == 12

    evidence_query = (
        f"exact_commit_sha={COMMIT_SHA}&vision_provider=lmstudio&"
        "vision_model_hash=abc123&remote_provider=false"
    )
    gate = client.get(f"/api/desktop-companion/release-gate?{evidence_query}").json()
    assert gate["status"] == "pass"
    assert gate["missing_scenarios"] == []

    text = client.get(
        f"/api/desktop-companion/rollout-status?requested_stage=text&{evidence_query}"
    ).json()
    speech = client.get(
        f"/api/desktop-companion/rollout-status?requested_stage=speech&{evidence_query}"
    ).json()
    assert text["effective_stage"] == "text"
    assert speech["effective_stage"] == "text"
    assert speech["reason"] == "speech_evidence_missing"


def test_desktop_companion_routes_remain_internal_to_openapi(tmp_path: Path):
    store = DesktopCompanionEvaluationStore(tmp_path / "desktop-evaluations.json")
    app = FastAPI()
    register_desktop_companion_routes(app, evaluation_store_factory=lambda: store)

    schema = app.openapi()
    assert not any(path.startswith("/api/desktop-companion") for path in schema["paths"])
