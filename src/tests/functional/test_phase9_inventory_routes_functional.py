"""Phase 9.0 — Functional tests for Inventory API routes."""
from __future__ import annotations

import pytest
from flask import Flask

from app.rpg.api.rpg_player_routes import rpg_player_bp
from app.rpg.player.player_inventory import (
    build_player_inventory_view,
    ensure_player_inventory,
)
from app.rpg.player.player_scene_state import ensure_player_state as real_ensure


def _make_test_app():
    app = Flask(__name__)
    app.register_blueprint(rpg_player_bp)
    return app


@pytest.fixture
def client():
    """Provide a test client for the inventory endpoints."""
    return _make_test_app().test_client()


def _make_payload(simulation_state):
    return {"setup_payload": {"metadata": {"simulation_state": simulation_state}}}


class TestInventoryRoutes:
    def test_inventory_returns_empty_for_new_player(self, client):
        resp = client.post("/api/rpg/player/inventory", json=_make_payload({}))
        data = resp.get_json()
        assert data["ok"] is True
        # Inventory should be initialised with defaults
        inv = data.get("inventory_state", {})
        assert inv.get("capacity") == 50
        assert inv.get("items") == []

    def test_inventory_has_items_after_adding(self, client):
        sim = {"player_state": {"inventory_state": {
            "items": [{"item_id": "gold_coin", "qty": 10}],
        }}}
        resp = client.post("/api/rpg/player/inventory", json=_make_payload(sim))
        data = resp.get_json()
        assert len(data["inventory_state"]["items"]) == 1
        assert data["inventory_state"]["items"][0]["qty"] == 10

    def test_use_item_decrements_quantity(self, client):
        sim = {"player_state": {"inventory_state": {
            "items": [{"item_id": "healing_potion", "qty": 2}],
        }}}
        use_payload = {
            "setup_payload": {"metadata": {"simulation_state": sim}},
            "item_id": "healing_potion",
        }
        resp = client.post("/api/rpg/player/inventory/use", json=use_payload)
        data = resp.get_json()
        assert data["ok"] is True
        assert data["inventory_state"]["items"][0]["qty"] == 1
        # Setup payload should be updated
        new_items = data["setup_payload"]["metadata"]["simulation_state"]["player_state"]["inventory_state"]["items"]
        assert new_items[0]["qty"] == 1

    def test_use_unknown_item_fails(self, client):
        sim = {"player_state": {"inventory_state": {}}}
        use_payload = {
            "setup_payload": {"metadata": {"simulation_state": sim}},
            "item_id": "nonexistent",
        }
        resp = client.post("/api/rpg/player/inventory/use", json=use_payload)
        data = resp.get_json()
        assert data["ok"] is False

    def test_registry_returns_items(self, client):
        resp = client.post("/api/rpg/player/inventory/registry", json={})
        data = resp.get_json()
        assert data["ok"] is True
        assert "gold_coin" in data["items"]
        assert "healing_potion" in data["items"]

    def test_inventory_summary_in_response(self, client):
        sim = {"player_state": {"inventory_state": {
            "items": [
                {"item_id": "gold_coin", "qty": 5},
                {"item_id": "bandit_token", "qty": 2},
            ],
        }}}
        resp = client.post("/api/rpg/player/inventory", json=_make_payload(sim))
        data = resp.get_json()
        summary = data.get("inventory_summary", {})
        assert summary.get("slots_used") == 2
        assert summary.get("total_item_qty") == 7