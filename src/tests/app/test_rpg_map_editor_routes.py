from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.gateway.main import create_gateway_app
from app.rpg.map_fixtures import FROST_HAVEN_MAP_ID
from app.rpg.map_repository import default_map_repository
from app.rpg.map_serialization import canonical_map_json


def _definition() -> dict[str, object]:
    return json.loads(canonical_map_json(default_map_repository().get(FROST_HAVEN_MAP_ID)))


def test_validate_and_apply_editor_routes() -> None:
    client = TestClient(create_gateway_app())

    validated = client.post("/api/rpg/map-editor/validate", json={"definition": _definition()})
    assert validated.status_code == 200
    assert validated.json()["report"]["ok"] is True

    applied = client.post(
        "/api/rpg/map-editor/apply",
        json={
            "definition": _definition(),
            "operations": [
                {
                    "type": "move_object",
                    "object_id": "building:frost_haven_inn",
                    "x": 2400,
                    "y": 4100,
                }
            ],
        },
    )
    assert applied.status_code == 200
    payload = applied.json()
    assert payload["report"]["ok"] is True
    inn = next(item for item in payload["definition"]["objects"] if item["id"] == "building:frost_haven_inn")
    assert (inn["x"], inn["y"]) == (2400, 4100)


def test_export_route_is_canonical_and_attachment_safe() -> None:
    client = TestClient(create_gateway_app())

    response = client.post(
        "/api/rpg/map-editor/export",
        json={"definition": _definition(), "filename": "frost-haven.json"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["content-disposition"] == 'attachment; filename="frost-haven.json"'
    assert response.headers["x-map-definition-revision"].startswith("sha256:")
    exported = response.json()
    assert exported["map_id"] == FROST_HAVEN_MAP_ID


def test_invalid_operations_return_typed_error() -> None:
    client = TestClient(create_gateway_app())

    response = client.post(
        "/api/rpg/map-editor/apply",
        json={
            "definition": _definition(),
            "operations": [{"type": "move_object", "object_id": "missing", "x": 1, "y": 2}],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "object_not_found"
