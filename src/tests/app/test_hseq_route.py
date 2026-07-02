from __future__ import annotations

from fastapi.testclient import TestClient

from app import create_fastapi_app
from app.assist_core.hermes_rpg_approved_routes import hermes_rpg_sequence_review_payload


def sample_payload() -> dict:
    return {
        "sequence_id": "seq-1",
        "objective": "Review room details",
        "domain": "rpg",
        "state_owner": "rpg_sim",
        "risk": "low",
        "items": [{"item_id": "look", "statement": "look around", "user_gate": False}],
    }


def test_sequence_payload_ok() -> None:
    payload = hermes_rpg_sequence_review_payload(sample_payload())

    assert payload["ok"] is True
    assert payload["validation"]["ok"] is True
    assert payload["gate"]["allowed"] is True


def test_sequence_payload_invalid() -> None:
    payload = hermes_rpg_sequence_review_payload({"items": []})

    assert payload["ok"] is False
    assert payload["validation"]["ok"] is False
    assert payload["gate"] is None


def test_sequence_live_route_ok() -> None:
    response = TestClient(create_fastapi_app()).post("/api/hermes/rpg/sequence/review", json=sample_payload())

    assert response.status_code == 200
    assert response.json()["ok"] is True
