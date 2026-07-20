from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.rpg_world_authoring_routes import register_rpg_world_authoring_routes


def test_authoring_manifest_and_projection_routes_are_hidden_from_openapi(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.gateway.rpg_world_authoring_routes.read_authoring_manifest",
        lambda world_id: {
            "ok": True,
            "world": {"id": world_id, "title": "Aurelia"},
            "sections": [{"id": "overview", "label": "Overview"}],
            "generation": {},
        },
    )
    monkeypatch.setattr(
        "app.gateway.rpg_world_authoring_routes.read_authoring_section",
        lambda world_id, section_id: {
            "ok": True,
            "world_id": world_id,
            "section_id": section_id,
            "page_kind": "document",
            "title": "Overview",
            "body": [],
            "related_entities": [],
        },
    )
    app = FastAPI()
    register_rpg_world_authoring_routes(app)
    client = TestClient(app)

    manifest = client.get("/api/rpg/worlds/world:aurelia/authoring-manifest")
    section = client.get(
        "/api/rpg/worlds/world:aurelia/authoring-sections/overview"
    )

    assert manifest.status_code == 200
    assert manifest.json()["sections"][0]["id"] == "overview"
    assert section.status_code == 200
    assert section.json()["section_id"] == "overview"
    assert "/api/rpg/worlds/{world_id}/authoring-manifest" not in app.openapi()[
        "paths"
    ]


def test_world_metadata_patch_requires_concurrency_token(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_update(world_id: str, **kwargs):
        captured.update({"world_id": world_id, **kwargs})
        return {
            "ok": True,
            "world": {
                "id": world_id,
                "title": kwargs["changes"]["title"],
                "draft_revision": kwargs["expected_draft_revision"],
            },
        }

    monkeypatch.setattr(
        "app.gateway.rpg_world_authoring_routes.update_world_metadata",
        fake_update,
    )
    app = FastAPI()
    register_rpg_world_authoring_routes(app)
    client = TestClient(app)

    missing = client.patch(
        "/api/rpg/worlds/world:aurelia",
        json={"title": "Aurelia II"},
    )
    updated = client.patch(
        "/api/rpg/worlds/world:aurelia",
        json={"expected_draft_revision": 4, "title": "Aurelia II"},
    )

    assert missing.status_code == 422
    assert updated.status_code == 200
    assert captured == {
        "world_id": "world:aurelia",
        "expected_draft_revision": 4,
        "changes": {"title": "Aurelia II"},
    }
