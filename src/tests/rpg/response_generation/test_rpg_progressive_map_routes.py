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


def test_campaign_signal_and_telemetry_routes_are_hidden(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_schedule(campaign_id: str, **kwargs):
        captured["campaign_id"] = campaign_id
        captured.update(kwargs)
        return {"ok": True, "status": "scheduled", "scheduled": []}

    def fake_telemetry(**kwargs):
        return {"ok": True, "status": "idle", **kwargs}

    monkeypatch.setattr(
        "app.gateway.rpg_progressive_map_routes.schedule_campaign_predictive_materialization",
        fake_schedule,
    )
    monkeypatch.setattr(
        "app.gateway.rpg_progressive_map_routes.materialization_job_telemetry",
        fake_telemetry,
    )
    app = FastAPI()
    register_rpg_progressive_map_routes(app)
    client = TestClient(app)

    scheduled = client.post(
        "/api/rpg/campaigns/campaign:a/materialization-signals",
        json={
            "current_location_id": "location:harbor",
            "route_intent_location_id": "location:frontier",
            "minimum_score": 0.9,
            "kick_worker": False,
        },
    )
    telemetry = client.get(
        "/api/rpg/worlds/world:starter/materialization-jobs",
        params={"source_world_revision": 2},
    )

    assert scheduled.status_code == 200
    assert captured == {
        "campaign_id": "campaign:a",
        "current_location_id": "location:harbor",
        "route_intent_location_id": "location:frontier",
        "minimum_score": 0.9,
        "kick_worker": False,
    }
    assert telemetry.json()["source_world_revision"] == 2
    assert all(
        path not in app.openapi()["paths"]
        for path in (
            "/api/rpg/campaigns/{campaign_id}/materialization-signals",
            "/api/rpg/worlds/{world_id}/materialization-jobs",
        )
    )
