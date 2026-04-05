"""Phase 10 — Presentation routes functional tests."""
from app import create_app


class TestPresentationRoutes:
    """Functional tests for presentation API routes."""

    def setup_method(self):
        self.app = create_app()
        self.client = self.app.test_client()

    def test_presentation_scene_route(self):
        res = self.client.post("/api/rpg/presentation/scene", json={
            "setup_payload": {"simulation_state": {"player_state": {"party_state": {"companions": []}}}},
            "scene_state": {"scene_id": "scene_gate", "tone": "tense"},
        })
        assert res.status_code == 200
        data = res.get_json() or {}
        assert data.get("ok") is True
        assert "presentation" in data

    def test_presentation_dialogue_route(self):
        res = self.client.post("/api/rpg/presentation/dialogue", json={
            "setup_payload": {"simulation_state": {"player_state": {"party_state": {"companions": []}}}},
            "dialogue_state": {"dialogue_id": "dlg_1", "speaker_id": "npc_1"},
        })
        assert res.status_code == 200
        data = res.get_json() or {}
        assert data.get("ok") is True
        assert "presentation" in data

    def test_presentation_speakers_route(self):
        res = self.client.post("/api/rpg/presentation/speakers", json={
            "setup_payload": {"simulation_state": {"player_state": {"party_state": {"companions": []}}}},
            "scene_state": {"scene_id": "scene_1"},
        })
        assert res.status_code == 200
        data = res.get_json() or {}
        assert data.get("ok") is True
        assert "speaker_cards" in data

    def test_presentation_scene_no_payload(self):
        res = self.client.post("/api/rpg/presentation/scene", json={})
        assert res.status_code == 200
        data = res.get_json() or {}
        assert data.get("ok") is True

    def test_presentation_dialogue_no_payload(self):
        res = self.client.post("/api/rpg/presentation/dialogue", json={})
        assert res.status_code == 200
        data = res.get_json() or {}
        assert data.get("ok") is True