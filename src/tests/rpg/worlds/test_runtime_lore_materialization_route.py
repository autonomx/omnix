from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway import rpg_campaign_lore_routes as routes


def test_runtime_materialization_route_returns_document_and_definition(
    monkeypatch,
) -> None:
    document_id = "lore:runtime:creature:echo-wolf"
    document = {
        "document_id": document_id,
        "topic_id": "monsters",
        "title": "Echo Wolf",
        "full_text": "Rich Echo Wolf lore.",
        "summary_500": "Rich Echo Wolf lore.",
        "summary_120": "Rich Echo Wolf lore.",
        "keywords": ["Echo Wolf"],
        "visibility": "public",
        "canon_revision": 4,
    }
    updated = {
        "campaign_bible_projection": {
            "documents": [document],
            "entities": {},
            "discovery_state": {
                "pages": {document_id: "learned"},
                "entities": {},
                "discoveries": [],
            },
            "canon_revision": 4,
            "content_hash": "sha256:new",
        },
        "state": {
            "campaign_bible": {
                "canon_revision": 4,
                "content_hash": "sha256:new",
                "discovery_state": {
                    "pages": {document_id: "learned"},
                    "entities": {},
                    "discoveries": [],
                },
            }
        },
        "runtime_state": {},
        "setup_payload": {},
    }
    definition = {
        "definition_id": "creature:echo-wolf",
        "definition_revision": 1,
        "name": "Echo Wolf",
    }
    storage = {
        "document_id": document_id,
        "definition": definition,
        "persisted": True,
        "revision": 4,
    }
    monkeypatch.setattr(routes, "load_session", lambda _session_id: {"id": "test"})
    monkeypatch.setattr(routes, "_kick_genesis_recovery", lambda: None)

    captured = {}

    def materialize(_session_id, _session, **kwargs):
        captured.update(kwargs)
        return updated, storage

    monkeypatch.setattr(routes, "materialize_runtime_lore", materialize)
    app = FastAPI()
    routes.register_rpg_campaign_lore_routes(app)

    response = TestClient(app).post(
        "/api/rpg/sessions/campaign:test/lore/materialize",
        json={
            "kind": "creature",
            "name": "Echo Wolf",
            "direction": "Bells disrupt its form.",
            "document_id": "",
        },
    )

    assert response.status_code == 200
    assert captured == {
        "kind": "creature",
        "name": "Echo Wolf",
        "direction": "Bells disrupt its form.",
        "document_id": "",
    }
    payload = response.json()
    assert payload["document"]["document_id"] == document_id
    assert payload["definition"] == definition
    assert payload["storage"]["persisted"] is True
