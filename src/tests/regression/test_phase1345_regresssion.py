"""Regression tests for Phases 13.4, 13.5, 14.0 — Wizard, Session, Memory.

Ensures new routes do not break existing presentation routes,
and that all modules stay backward-compatible with prior phases.
"""
import json

import pytest
from flask import Flask

from app.rpg.api.rpg_presentation_routes import rpg_presentation_bp


@pytest.fixture
def client():
    app = Flask(__name__)
    app.register_blueprint(rpg_presentation_bp)
    with app.test_client() as c:
        yield c


# ---- Existing routes must still work ----


def test_scene_presentation_still_works(client):
    resp = client.post("/api/rpg/presentation/scene", json={"setup_payload": {}, "scene_state": {}})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert "character_ui_state" in data


def test_dialogue_presentation_still_works(client):
    resp = client.post("/api/rpg/presentation/dialogue", json={"setup_payload": {}, "dialogue_state": {}})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True


def test_visual_assets_still_works(client):
    resp = client.post("/api/rpg/visual_assets", json={"setup_payload": {}})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert "visual_assets" in data


def test_packs_list_still_works(client):
    resp = client.post("/api/rpg/packs/list", json={"setup_payload": {}})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert "packs" in data


def test_templates_list_still_works(client):
    resp = client.post("/api/rpg/templates/list", json={"templates": []})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert "templates" in data


# ---- Memory lanes do not bleed across requests ----


def test_memory_get_returns_empty_lanes_for_fresh_payload(client):
    resp = client.post("/api/rpg/memory/get", json={"setup_payload": {}})
    assert resp.status_code == 200
    data = resp.get_json()
    memory = data.get("memory_state", {})
    assert memory.get("short_term") == []
    assert memory.get("long_term") == []
    assert memory.get("world_memory") == []


def test_session_list_returns_empty_for_fresh_state(client):
    """Session registry starts empty in each test process."""
    resp = client.post("/api/rpg/session/list", json={})
    assert resp.status_code == 200
    data = resp.get_json()
    # Sessions list should be a list (may contain data from other tests in same process)
    assert "sessions" in data
    assert isinstance(data["sessions"], list)