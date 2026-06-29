from __future__ import annotations

from fastapi.testclient import TestClient

from app.assist_core.hermes_api import router
from app.assist_core.hermes_candidate import HermesCandidate, hermes_candidate_payload, hermes_demo_candidate
from app.gateway.main import create_gateway_app


def test_hermes_candidate_payload_is_preview_only() -> None:
    payload = hermes_candidate_payload(
        HermesCandidate(
            name="demo_note",
            target="local_preview",
            before={"note": "ready"},
            after={"note": "updated"},
        )
    )

    assert payload["ok"] is True
    assert payload["preview_only"] is True
    assert payload["candidate"]["name"] == "demo_note"
    assert payload["candidate"]["target"] == "local_preview"
    assert payload["candidate"]["risk"] == "review_required"
    assert payload["candidate"]["before"] == {"note": "ready"}
    assert payload["candidate"]["after"] == {"note": "updated"}
    assert "execute" not in payload
    assert "mutation" not in payload


def test_hermes_demo_candidate_bounds_note_and_keeps_preview_shape() -> None:
    payload = hermes_demo_candidate(note="x" * 120)

    assert payload["preview_only"] is True
    assert payload["candidate"]["before"] == {"note": "ready"}
    assert payload["candidate"]["after"] == {"note": "x" * 80}
    assert payload["candidate"]["note"] == "Preview only."


def test_hermes_candidate_demo_route_returns_preview_only_payload() -> None:
    client = TestClient(create_gateway_app())
    response = client.get("/api/hermes/candidate/demo", params={"note": "review"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["preview_only"] is True
    assert payload["candidate"]["name"] == "demo_note"
    assert payload["candidate"]["target"] == "local_preview"
    assert payload["candidate"]["before"] == {"note": "ready"}
    assert payload["candidate"]["after"] == {"note": "review"}
    assert "execute" not in payload
    assert "mutation" not in payload


def test_hermes_api_router_keeps_candidate_route_hidden_from_schema() -> None:
    schema_paths = {route.path for route in router.routes if getattr(route, "include_in_schema", True)}

    assert "/api/hermes/candidate/demo" not in schema_paths
