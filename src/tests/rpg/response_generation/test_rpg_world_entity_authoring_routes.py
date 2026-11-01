from __future__ import annotations
from tests.support.routers import include_router_registrar

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.apps.rpg.edge.api.feature_routes.rpg_world_authoring_routes import register_rpg_world_authoring_routes


def test_entity_routes_read_edit_and_regenerate_with_topic_tokens(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    monkeypatch.setattr(
        "app.apps.rpg.edge.api.feature_routes.rpg_world_authoring_routes.read_world_entity",
        lambda world_id, topic_id, entity_id: {
            "ok": True,
            "world": {"id": world_id},
            "topic": {"topic_id": topic_id, "content_hash": "sha256:old"},
            "entity": {"id": entity_id, "name": "Bran"},
            "history": [],
        },
    )

    def fake_update(world_id: str, topic_id: str, entity_id: str, **kwargs):
        calls.append(("update", {"world_id": world_id, "topic_id": topic_id, "entity_id": entity_id, **kwargs}))
        return {"ok": True, "topic": {"content_hash": "sha256:new"}, "entity": {"id": entity_id}, "stale_topic_ids": ["quests"], "stale_entity_ids": ["quest:road"]}

    def fake_regenerate(world_id: str, topic_id: str, entity_id: str, **kwargs):
        calls.append(("regenerate", {"world_id": world_id, "topic_id": topic_id, "entity_id": entity_id, **kwargs}))
        return {"ok": True, "topic": {"content_hash": "sha256:regen"}, "entity": {"id": entity_id}, "stale_topic_ids": [], "stale_entity_ids": []}

    monkeypatch.setattr("app.apps.rpg.edge.api.feature_routes.rpg_world_authoring_routes.update_world_entity", fake_update)
    monkeypatch.setattr("app.apps.rpg.edge.api.feature_routes.rpg_world_authoring_routes.regenerate_world_entity", fake_regenerate)

    app = FastAPI()
    include_router_registrar(app, register_rpg_world_authoring_routes)
    client = TestClient(app)
    path = "/api/rpg/worlds/world:aurelia/topics/npcs/entities/npc:bran"

    read = client.get(path)
    edited = client.patch(
        path,
        json={
            "expected_draft_revision": 3,
            "expected_content_hash": "sha256:old",
            "changes": {"goals": ["protect the inn"]},
        },
    )
    regenerated = client.post(
        f"{path}/regenerate",
        json={
            "expected_draft_revision": 3,
            "expected_content_hash": "sha256:new",
            "directives": {"focus": "deepen motives"},
        },
    )

    assert read.status_code == 200
    assert read.json()["entity"]["id"] == "npc:bran"
    assert edited.status_code == 200
    assert regenerated.status_code == 200
    assert calls == [
        (
            "update",
            {
                "world_id": "world:aurelia",
                "topic_id": "npcs",
                "entity_id": "npc:bran",
                "expected_draft_revision": 3,
                "expected_content_hash": "sha256:old",
                "changes": {"goals": ["protect the inn"]},
            },
        ),
        (
            "regenerate",
            {
                "world_id": "world:aurelia",
                "topic_id": "npcs",
                "entity_id": "npc:bran",
                "expected_draft_revision": 3,
                "expected_content_hash": "sha256:new",
                "directives": {"focus": "deepen motives"},
            },
        ),
    ]
    assert "/api/rpg/worlds/{world_id}/topics/{topic_id}/entities/{entity_id}" in app.openapi()["paths"]


def test_entity_patch_requires_changes_and_concurrency_tokens() -> None:
    app = FastAPI()
    include_router_registrar(app, register_rpg_world_authoring_routes)
    client = TestClient(app)
    path = "/api/rpg/worlds/world:aurelia/topics/npcs/entities/npc:bran"

    missing_tokens = client.patch(path, json={"changes": {"name": "Bran"}})
    missing_changes = client.patch(
        path,
        json={
            "expected_draft_revision": 3,
            "expected_content_hash": "sha256:old",
        },
    )

    assert missing_tokens.status_code == 422
    assert missing_changes.status_code == 422


def test_an_author_adds_an_entity_to_a_topic(monkeypatch) -> None:
    """EV-6: the editor can add an entity, not only change one."""
    calls: list[dict[str, object]] = []

    def fake_add(world_id: str, topic_id: str, **kwargs):
        calls.append({"world_id": world_id, "topic_id": topic_id, **kwargs})
        return {"ok": True, "topic": {"content_hash": "sha256:new"}, "entity": dict(kwargs["entity"]),
                "stale_topic_ids": [], "stale_entity_ids": []}

    monkeypatch.setattr("app.apps.rpg.edge.api.feature_routes.rpg_world_authoring_routes.add_world_entity", fake_add)
    app = FastAPI()
    include_router_registrar(app, register_rpg_world_authoring_routes)
    client = TestClient(app)
    added = client.post("/api/rpg/worlds/world:aurelia/topics/npcs/entities", json={
        "expected_draft_revision": 3, "expected_content_hash": "sha256:old",
        "entity": {"id": "npc:hollis", "kind": "npc", "name": "Hollis", "location_id": "loc:valecourt"}})
    assert added.status_code == 200 and added.json()["entity"]["id"] == "npc:hollis"
    assert calls[0]["entity"] == {"id": "npc:hollis", "kind": "npc", "name": "Hollis", "location_id": "loc:valecourt"}
    refused = client.post("/api/rpg/worlds/world:aurelia/topics/npcs/entities", json={
        "expected_draft_revision": 3, "expected_content_hash": "sha256:old"})
    assert refused.status_code == 422


def test_adding_an_entity_keeps_its_id_new_and_its_references_the_worlds() -> None:
    import pytest

    from app.apps.rpg.genesis.worlds.entity_authoring import validate_entity_references

    validate_entity_references({"id": "npc:new", "location_id": "loc:known"}, {"npc:new", "loc:known"})
    with pytest.raises(ValueError):
        validate_entity_references({"id": "npc:new", "location_id": "loc:nowhere"}, {"npc:new", "loc:known"})
