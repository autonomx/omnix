from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.rpg_world_dossier_routes import register_rpg_world_dossier_routes


def test_dossier_routes_preserve_concurrency_tokens_and_editorial_scope(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_update(world_id: str, topic_id: str, entity_id: str, **kwargs):
        calls.append(
            (
                "update",
                {
                    "world_id": world_id,
                    "topic_id": topic_id,
                    "entity_id": entity_id,
                    **kwargs,
                },
            )
        )
        return {
            "ok": True,
            "topic": {"content_hash": "sha256:new"},
            "entity": {"id": entity_id, "dossier": kwargs["dossier"]},
            "stale_topic_ids": [],
            "stale_entity_ids": [],
            "canonical_fields_preserved": True,
            "editorial_only": True,
        }

    def fake_preview(world_id: str, topic_id: str, entity_id: str, **kwargs):
        calls.append(
            (
                "preview",
                {
                    "world_id": world_id,
                    "topic_id": topic_id,
                    "entity_id": entity_id,
                    **kwargs,
                },
            )
        )
        return {
            "ok": True,
            "preview_only": True,
            "stored": False,
            "world_id": world_id,
            "topic_id": topic_id,
            "entity_id": entity_id,
            "expected_draft_revision": kwargs["expected_draft_revision"],
            "expected_content_hash": kwargs["expected_content_hash"],
            "short_summary": "Preview summary.",
            "dossier": {
                "schema_version": "rpg_world_entity_dossier_v1",
                "quick_facts": [],
                "sections": [
                    {
                        "id": "overview",
                        "title": "Overview",
                        "paragraphs": ["Preview prose remains unstored until explicitly applied."],
                    }
                ],
                "related_entity_ids": [],
            },
            "generation": {},
            "canonical_fields_preserved": True,
        }

    def fake_regenerate(world_id: str, topic_id: str, entity_id: str, **kwargs):
        calls.append(
            (
                "regenerate",
                {
                    "world_id": world_id,
                    "topic_id": topic_id,
                    "entity_id": entity_id,
                    **kwargs,
                },
            )
        )
        return {
            "ok": True,
            "topic": {"content_hash": "sha256:regen"},
            "entity": {"id": entity_id},
            "stale_topic_ids": [],
            "stale_entity_ids": [],
            "canonical_fields_preserved": True,
            "editorial_only": True,
        }

    monkeypatch.setattr(
        "app.gateway.rpg_world_dossier_routes.update_world_entity_dossier",
        fake_update,
    )
    monkeypatch.setattr(
        "app.gateway.rpg_world_dossier_routes.preview_world_entity_dossier_regeneration",
        fake_preview,
    )
    monkeypatch.setattr(
        "app.gateway.rpg_world_dossier_routes.regenerate_world_entity_dossier",
        fake_regenerate,
    )

    app = FastAPI()
    register_rpg_world_dossier_routes(app)
    client = TestClient(app)
    path = "/api/rpg/worlds/world:aurelia/topics/npcs/entities/npc:bran"
    dossier = {
        "schema_version": "rpg_world_entity_dossier_v1",
        "quick_facts": [],
        "sections": [
            {
                "id": "overview",
                "title": "Overview",
                "paragraphs": ["Bran protects the inn and the people who depend on it."],
            }
        ],
        "related_entity_ids": [],
    }

    updated = client.patch(
        f"{path}/dossier",
        json={
            "expected_draft_revision": 3,
            "expected_content_hash": "sha256:old",
            "short_summary": "The keeper of the Rusty Flagon.",
            "dossier": dossier,
        },
    )
    previewed = client.post(
        f"{path}/regenerate-dossier-preview",
        json={
            "expected_draft_revision": 3,
            "expected_content_hash": "sha256:new",
            "directives": {"focus": "preview the tavern history"},
        },
    )
    regenerated = client.post(
        f"{path}/regenerate-dossier",
        json={
            "expected_draft_revision": 3,
            "expected_content_hash": "sha256:new",
            "directives": {"focus": "deepen the tavern history"},
        },
    )

    assert updated.status_code == 200
    assert updated.json()["canonical_fields_preserved"] is True
    assert previewed.status_code == 200
    assert previewed.json()["stored"] is False
    assert regenerated.status_code == 200
    assert regenerated.json()["editorial_only"] is True
    assert calls == [
        (
            "update",
            {
                "world_id": "world:aurelia",
                "topic_id": "npcs",
                "entity_id": "npc:bran",
                "expected_draft_revision": 3,
                "expected_content_hash": "sha256:old",
                "short_summary": "The keeper of the Rusty Flagon.",
                "dossier": dossier,
            },
        ),
        (
            "preview",
            {
                "world_id": "world:aurelia",
                "topic_id": "npcs",
                "entity_id": "npc:bran",
                "expected_draft_revision": 3,
                "expected_content_hash": "sha256:new",
                "directives": {"focus": "preview the tavern history"},
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
                "directives": {"focus": "deepen the tavern history"},
            },
        ),
    ]
    assert f"{path}/dossier" not in app.openapi()["paths"]
    assert f"{path}/regenerate-dossier-preview" not in app.openapi()["paths"]
    assert f"{path}/regenerate-dossier" not in app.openapi()["paths"]


def test_quality_and_enrichment_routes_are_hidden_and_bounded(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []

    def fake_quality(world_id: str):
        calls.append(("quality", world_id))
        return {
            "ok": True,
            "world_id": world_id,
            "metrics": {"coverage_percent": 40},
            "enrichment_candidates": [],
        }

    def fake_enrich(world_id: str, **kwargs):
        calls.append(("enrich", {"world_id": world_id, **kwargs}))
        return {
            "ok": True,
            "world_id": world_id,
            "dry_run": kwargs["dry_run"],
            "candidate_count": kwargs["limit"],
        }

    monkeypatch.setattr(
        "app.gateway.rpg_world_dossier_routes.world_dossier_quality",
        fake_quality,
    )
    monkeypatch.setattr(
        "app.gateway.rpg_world_dossier_routes.enrich_world_dossiers",
        fake_enrich,
    )
    app = FastAPI()
    register_rpg_world_dossier_routes(app)
    client = TestClient(app)

    quality = client.get("/api/rpg/worlds/world:aurelia/dossier-quality")
    enrichment = client.post(
        "/api/rpg/worlds/world:aurelia/enrich-dossiers",
        json={"dry_run": True, "limit": 999, "directives": {"focus": "history"}},
    )

    assert quality.status_code == 200
    assert quality.json()["metrics"]["coverage_percent"] == 40
    assert enrichment.status_code == 200
    assert enrichment.json()["candidate_count"] == 25
    assert calls == [
        ("quality", "world:aurelia"),
        (
            "enrich",
            {
                "world_id": "world:aurelia",
                "limit": 25,
                "dry_run": True,
                "directives": {"focus": "history"},
            },
        ),
    ]
    assert "/api/rpg/worlds/{world_id}/dossier-quality" not in app.openapi()["paths"]
    assert "/api/rpg/worlds/{world_id}/enrich-dossiers" not in app.openapi()["paths"]


def test_dossier_routes_require_concurrency_tokens_and_structured_dossier() -> None:
    app = FastAPI()
    register_rpg_world_dossier_routes(app)
    client = TestClient(app)
    path = "/api/rpg/worlds/world:aurelia/topics/npcs/entities/npc:bran/dossier"

    missing_tokens = client.patch(path, json={"dossier": {}})
    missing_dossier = client.patch(
        path,
        json={
            "expected_draft_revision": 3,
            "expected_content_hash": "sha256:old",
        },
    )

    assert missing_tokens.status_code == 422
    assert missing_dossier.status_code == 422
