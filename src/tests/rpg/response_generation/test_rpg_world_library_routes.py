from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.rpg_world_routes import register_rpg_world_routes


def test_world_library_routes_are_available_without_openapi_drift(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.gateway.rpg_world_library_routes.read_world_library",
        lambda **_kwargs: {
            "ok": True,
            "worlds": [{"id": "world:test", "title": "Test World"}],
            "scenarios": [],
            "campaigns": [],
            "generation_runs": [],
        },
    )
    monkeypatch.setattr(
        "app.gateway.rpg_world_library_routes.read_world_detail",
        lambda world_id, **_kwargs: {
            "ok": True,
            "world": {"id": world_id, "title": "Test World"},
            "topics": [],
            "revisions": [],
            "releases": [],
            "scenarios": [],
            "scenario_revisions": {},
            "generation_runs": [],
        },
    )
    app = FastAPI()
    register_rpg_world_routes(app)
    client = TestClient(app)

    library = client.get("/api/rpg/world-library")
    detail = client.get("/api/rpg/worlds/world:test/library")

    assert library.status_code == 200
    assert library.json()["worlds"][0]["id"] == "world:test"
    assert detail.status_code == 200
    assert detail.json()["world"]["id"] == "world:test"
    assert "/api/rpg/world-library" not in app.openapi()["paths"]
    assert "/api/rpg/worlds/{world_id}/library" not in app.openapi()["paths"]


def test_world_and_scenario_create_routes_allow_backend_generated_ids(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_world(contract):
        captured["world_id"] = contract.world_id
        return {"id": "world:glass-sea:abc123", "title": contract.title}

    def fake_scenario(contract):
        captured["scenario_id"] = contract.scenario_id
        return {
            "id": "scenario:first-light:def456",
            "world_id": contract.world_id,
            "title": contract.title,
        }

    monkeypatch.setattr("app.gateway.rpg_world_routes.create_world_project", fake_world)
    monkeypatch.setattr("app.gateway.rpg_world_routes.create_scenario_project", fake_scenario)
    app = FastAPI()
    register_rpg_world_routes(app)
    client = TestClient(app)

    world = client.post(
        "/api/rpg/worlds",
        json={"title": "The Glass Sea", "source_mode": "hybrid"},
    )
    scenario = client.post(
        "/api/rpg/scenarios",
        json={"world_id": "world:glass-sea:abc123", "title": "First Light"},
    )

    assert world.status_code == 200
    assert world.json()["world"]["id"] == "world:glass-sea:abc123"
    assert scenario.status_code == 200
    assert scenario.json()["scenario"]["id"] == "scenario:first-light:def456"
    assert captured == {"world_id": None, "scenario_id": None}


def test_published_scenario_launch_route_preserves_fast_launch_contract(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_launch(**kwargs):
        captured.update(kwargs)
        return {
            "ok": True,
            "status": "ready",
            "session_id": "campaign:published",
            "launch_mode": "published_scenario",
            "world_forge_invoked": False,
        }

    monkeypatch.setattr(
        "app.gateway.rpg_world_library_routes.launch_published_scenario",
        fake_launch,
    )
    app = FastAPI()
    register_rpg_world_routes(app)
    client = TestClient(app)

    response = client.post(
        "/api/rpg/scenarios/scenario:opening/revisions/2/launch",
        json={
            "world_id": "world:test",
            "world_revision": 3,
            "world_release": 1,
            "player": {"name": "Alyndra"},
        },
    )

    assert response.status_code == 200
    assert response.json()["session_id"] == "campaign:published"
    assert response.json()["world_forge_invoked"] is False
    assert captured["world_id"] == "world:test"
    assert captured["world_revision"] == 3
    assert captured["world_release"] == 1
    assert captured["scenario_id"] == "scenario:opening"
    assert captured["scenario_revision"] == 2


def test_duplicate_scenario_create_returns_conflict_instead_of_500(monkeypatch) -> None:
    def duplicate_scenario(_contract):
        raise ValueError("scenario_already_exists:scenario:opening")

    monkeypatch.setattr(
        "app.gateway.rpg_world_routes.create_scenario_project",
        duplicate_scenario,
    )
    app = FastAPI()
    register_rpg_world_routes(app)
    client = TestClient(app)

    response = client.post(
        "/api/rpg/scenarios",
        json={
            "scenario_id": "scenario:opening",
            "world_id": "world:test",
            "title": "Opening",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["error"] == (
        "scenario_already_exists:scenario:opening"
    )


def test_repair_world_for_launch_route_passes_scenario_and_location(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_repair(world_id: str, **kwargs):
        captured.update({"world_id": world_id, **kwargs})
        return {
            "ok": True,
            "status": "ready",
            "scenario_revision": {"revision": 2, "world_revision": 5},
        }

    monkeypatch.setattr(
        "app.gateway.rpg_world_library_routes.repair_world_for_launch",
        fake_repair,
    )
    app = FastAPI()
    register_rpg_world_routes(app)
    client = TestClient(app)

    response = client.post(
        "/api/rpg/worlds/world:cyberpunk/repair-for-launch",
        json={
            "scenario_id": "scenario:opening",
            "starting_location_id": "loc:glitch_bar",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert captured == {
        "world_id": "world:cyberpunk",
        "scenario_id": "scenario:opening",
        "starting_location_id": "loc:glitch_bar",
    }
