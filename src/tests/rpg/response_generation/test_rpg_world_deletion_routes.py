from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway import rpg_world_deletion_routes


def test_world_deletion_routes_register_safe_endpoints() -> None:
    app = FastAPI()
    rpg_world_deletion_routes.register_rpg_world_deletion_routes(app)
    routes = {(route.path, method) for route in app.routes for method in route.methods}

    assert (
        "/api/rpg/worlds/{world_id}/deletion-eligibility",
        "GET",
    ) in routes
    assert ("/api/rpg/worlds/{world_id}", "DELETE") in routes


def test_world_deletion_route_requires_typed_confirmation(monkeypatch) -> None:
    app = FastAPI()
    rpg_world_deletion_routes.register_rpg_world_deletion_routes(app)
    client = TestClient(app)

    response = client.request(
        "DELETE",
        "/api/rpg/worlds/world:draft",
        json={"acknowledge_permanent": True},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "confirmation_title_required"


def test_world_deletion_route_passes_explicit_decision(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_delete(
        world_id: str,
        *,
        confirmation_title: str,
        acknowledge_permanent: bool,
    ) -> dict[str, object]:
        captured.update(
            world_id=world_id,
            confirmation_title=confirmation_title,
            acknowledge_permanent=acknowledge_permanent,
        )
        return {
            "ok": True,
            "deleted": True,
            "world_id": world_id,
            "world_title": confirmation_title,
        }

    monkeypatch.setattr(rpg_world_deletion_routes, "delete_world_project", fake_delete)
    app = FastAPI()
    rpg_world_deletion_routes.register_rpg_world_deletion_routes(app)
    client = TestClient(app)

    response = client.request(
        "DELETE",
        "/api/rpg/worlds/world:draft",
        json={
            "confirmation_title": "Disposable Draft",
            "acknowledge_permanent": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["deleted"] is True
    assert captured == {
        "world_id": "world:draft",
        "confirmation_title": "Disposable Draft",
        "acknowledge_permanent": True,
    }
