from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.desktop_companion.build_identity import DesktopCompanionBuildIdentity
from app.desktop_companion.evaluation import DesktopCompanionEvaluationStore
from app.desktop_companion.routes import register_desktop_companion_routes

COMMIT_SHA = "94a179154dc98f6e455c604bed100c0beee06046"
GENERAL_SCENARIOS = [
    "static-screen",
    "typing",
    "rapid-browsing",
    "scene-change",
    "interruption",
    "screen-prompt-injection",
]
SPEECH_SCENARIOS = [*GENERAL_SCENARIOS, "speech-completed", "speech-stale"]


def payload(index: int, scenario: str, *, stage: str = "shadow") -> dict:
    return {
        "run_id": f"api-run-{stage}-{index}",
        "session_id": "chat-api",
        "started_at": f"2026-07-14T12:{index % 60:02d}:00Z",
        "ended_at": f"2026-07-14T12:{index % 60:02d}:30Z",
        "exact_commit_sha": COMMIT_SHA,
        "rollout_stage": stage,
        "vision_provider": "lmstudio",
        "vision_model_hash": "abc123",
        "remote_provider": False,
        "counts": {
            "max_vision_calls_per_minute": 6,
            "observations": 20,
            "deliveries": 1 if stage == "speech" else 0,
        },
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


def build_client(tmp_path: Path, *, speech_canary: bool = False) -> tuple[TestClient, DesktopCompanionEvaluationStore]:
    store = DesktopCompanionEvaluationStore(tmp_path / f"desktop-evaluations-{speech_canary}.json")
    app = FastAPI()
    register_desktop_companion_routes(
        app,
        evaluation_store_factory=lambda: store,
        build_identity_factory=lambda: DesktopCompanionBuildIdentity(
            exact_commit_sha=COMMIT_SHA,
            app_version="1.0.0",
            source="test",
        ),
        speech_canary_factory=lambda: speech_canary,
    )
    return TestClient(app), store


def evidence_query() -> str:
    return (
        f"exact_commit_sha={COMMIT_SHA}&vision_provider=lmstudio&"
        "vision_model_hash=abc123&remote_provider=false"
    )


def seed_text_evidence(client: TestClient) -> None:
    for index in range(12):
        response = client.post(
            "/api/desktop-companion/evaluations",
            json=payload(index, GENERAL_SCENARIOS[index % len(GENERAL_SCENARIOS)]),
        )
        assert response.status_code == 200


def test_desktop_companion_text_and_speech_rollout_api(tmp_path: Path):
    client, _ = build_client(tmp_path)
    seed_text_evidence(client)

    gate = client.get(f"/api/desktop-companion/release-gate?{evidence_query()}").json()
    assert gate["status"] == "pass"

    text = client.get(
        f"/api/desktop-companion/rollout-status?requested_stage=text&{evidence_query()}"
    ).json()
    speech_before = client.get(
        f"/api/desktop-companion/rollout-status?requested_stage=speech&{evidence_query()}"
    ).json()
    assert text["effective_stage"] == "text"
    assert speech_before["effective_stage"] == "text"
    assert speech_before["reason"] == "speech_evidence_missing"

    for index in range(24):
        response = client.post(
            "/api/desktop-companion/evaluations",
            json=payload(index, SPEECH_SCENARIOS[index % len(SPEECH_SCENARIOS)], stage="speech"),
        )
        assert response.status_code == 200

    speech_gate = client.get(
        f"/api/desktop-companion/release-gate?stage=speech&{evidence_query()}"
    ).json()
    speech_after = client.get(
        f"/api/desktop-companion/rollout-status?requested_stage=speech&{evidence_query()}"
    ).json()
    assert speech_gate["status"] == "pass"
    assert speech_after["effective_stage"] == "speech"
    assert speech_after["reason"] == "speech_rollout_gate_passed"


def test_explicit_speech_canary_collects_evidence_without_opening_default_rollout(tmp_path: Path):
    client, _ = build_client(tmp_path, speech_canary=True)
    seed_text_evidence(client)

    speech = client.get(
        f"/api/desktop-companion/rollout-status?requested_stage=speech&{evidence_query()}"
    ).json()

    assert speech["effective_stage"] == "speech"
    assert speech["reason"] == "speech_validation_canary"
    assert speech["release_gate_status"] == "insufficient"


def test_desktop_companion_routes_remain_internal_to_openapi(tmp_path: Path):
    store = DesktopCompanionEvaluationStore(tmp_path / "desktop-evaluations.json")
    app = FastAPI()
    register_desktop_companion_routes(app, evaluation_store_factory=lambda: store)

    schema = app.openapi()
    assert not any(path.startswith("/api/desktop-companion") for path in schema["paths"])
