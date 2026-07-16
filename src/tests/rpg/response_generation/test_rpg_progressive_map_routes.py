from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.rpg_progressive_map_routes import (
    register_rpg_progressive_map_routes,
)


def test_deferred_materialization_route_is_hidden_and_revision_explicit(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_materialize(**kwargs):
        captured.update(kwargs)
        return {
            "ok": True,
            "status": "ready",
            "reused": False,
            "materialization": {
                "location_id": kwargs["location_id"],
                "world_revision": 3,
                "world_release": 1,
            },
        }

    monkeypatch.setattr(
        "app.gateway.rpg_progressive_map_routes.materialize_deferred_location",
        fake_materialize,
    )
    app = FastAPI()
    register_rpg_progressive_map_routes(app)
    client = TestClient(app)

    response = client.post(
        "/api/rpg/worlds/world:starter/deferred-locations/location:frontier/materialize",
        json={"source_world_revision": 2},
    )

    assert response.status_code == 200
    assert response.json()["materialization"]["world_revision"] == 3
    assert captured == {
        "world_id": "world:starter",
        "source_world_revision": 2,
        "location_id": "location:frontier",
    }
    assert (
        "/api/rpg/worlds/{world_id}/deferred-locations/{location_id}/materialize"
        not in app.openapi()["paths"]
    )
