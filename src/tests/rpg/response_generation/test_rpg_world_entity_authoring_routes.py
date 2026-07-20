from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.rpg_world_authoring_routes import register_rpg_world_authoring_routes


def test_entity_routes_read_edit_and_regenerate_with_topic_tokens(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    monkeypatch.setattr(
        "app.gateway.rpg_world_authoring_routes.read_world_entity",
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

    monkeypatch.setattr("app.gateway.rpg_world_authoring_routes.update_world_entity", fake_update)
    monkeypatch.setattr("app.gateway.rpg_world_authoring_routes.regenerate_world_entity", fake_regenerate)

    app = FastAPI()
    register_rpg_world_authoring_routes(app)
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
    assert "/api/rpg/worlds/{world_id}/topics/{topic_id}/entities/{entity_id}" not in app.openapi()["paths"]


def test_entity_patch_requires_changes_and_concurrency_tokens() -> None:
    app = FastAPI()
    register_rpg_world_authoring_routes(app)
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
