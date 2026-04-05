"""Phase 10 — Presentation layer regression tests.

Ensures that presentation changes don't break existing behavior.
"""
from app import create_app
from app.rpg.presentation import (
    build_scene_presentation_payload,
    build_dialogue_presentation_payload,
    build_speaker_cards,
    build_personality_style_tags,
)


class TestPresentationRegression:
    """Regression tests for presentation layer."""

    def setup_method(self):
        self.app = create_app()
        self.client = self.app.test_client()

    def test_scene_presentation_stable_keys(self):
        """Ensure scene presentation payload keys don't change unexpectedly."""
        simulation_state = {"player_state": {"party_state": {"companions": []}}}
        payload = build_scene_presentation_payload(simulation_state, {"scene_id": "scene_1", "tone": "tense"})
        expected_keys = {"scene_id", "tone", "location_id", "scene_context", "speaker_cards", "companion_interjections", "companion_reactions", "presence_summary", "fallback_text"}
        assert expected_keys.issubset(set(payload.keys()))

    def test_dialogue_presentation_stable_keys(self):
        """Ensure dialogue presentation payload keys don't change unexpectedly."""
        simulation_state = {"player_state": {"party_state": {"companions": []}}}
        payload = build_dialogue_presentation_payload(simulation_state, {"dialogue_id": "dlg_1", "speaker_id": "npc_x"})
        expected_keys = {"dialogue_id", "speaker_id", "speaker_cards", "dialogue_context", "presence_summary"}
        assert expected_keys.issubset(set(payload.keys()))

    def test_speaker_cards_stable_keys(self):
        """Ensure speaker card keys don't change unexpectedly."""
        simulation_state = {"player_state": {"party_state": {"companions": []}}}
        cards = build_speaker_cards(simulation_state, {"scene_id": "scene_1"})
        assert len(cards) >= 1
        player_card = cards[0]
        expected_keys = {"speaker_id", "name", "kind", "portrait_key", "style_tags"}
        assert expected_keys.issubset(set(player_card.keys()))

    def test_personality_style_tags_deterministic(self):
        """Ensure personality style tags are deterministic."""
        actor = {"npc_id": "npc_a", "name": "A", "loyalty": 0.8, "morale": 0.9, "role": "support"}
        results = [build_personality_style_tags(actor) for _ in range(10)]
        assert all(r == results[0] for r in results)

    def test_presentation_routes_return_ok(self):
        """Ensure all presentation routes return ok=True."""
        base_payload = {
            "setup_payload": {"simulation_state": {"player_state": {"party_state": {"companions": []}}}},
        }

        res_scene = self.client.post("/api/rpg/presentation/scene", json={**base_payload, "scene_state": {"scene_id": "s1"}})
        res_dialogue = self.client.post("/api/rpg/presentation/dialogue", json={**base_payload, "dialogue_state": {"dialogue_id": "d1"}})
        res_speakers = self.client.post("/api/rpg/presentation/speakers", json={**base_payload, "scene_state": {"scene_id": "s1"}})

        assert res_scene.get_json()["ok"] is True
        assert res_dialogue.get_json()["ok"] is True
        assert res_speakers.get_json()["ok"] is True

    def test_build_party_speaker_cards_limits_to_six(self):
        """Ensure party speaker cards are limited to 6."""
        from app.rpg.presentation import build_party_speaker_cards
        companions = [{"npc_id": f"npc_{i}", "name": f"NPC {i}", "status": "active", "loyalty": 0.5, "morale": 0.5, "role": "ally"} for i in range(10)]
        cards = build_party_speaker_cards({}, companions)
        assert len(cards) <= 6

    def test_speaker_cards_keep_player_first(self):
        simulation_state = {
            "player_state": {
                "party_state": {
                    "companions": [
                        {"npc_id": "npc_b", "name": "B", "status": "active", "loyalty": 0.5, "morale": 0.5, "role": "ally"},
                    ]
                }
            }
        }
        cards = build_speaker_cards(simulation_state, {"scene_id": "scene_1"})
        assert cards[0]["speaker_id"] == "player"

    def test_build_party_speaker_cards_skips_inactive(self):
        from app.rpg.presentation import build_party_speaker_cards
        companions = [
            {"npc_id": "npc_a", "name": "A", "status": "active", "loyalty": 0.5, "morale": 0.5, "role": "ally"},
            {"npc_id": "npc_b", "name": "B", "status": "downed", "loyalty": 0.5, "morale": 0.5, "role": "ally"},
        ]
        cards = build_party_speaker_cards({}, companions)
        ids = [card["speaker_id"] for card in cards]
        assert "npc_a" in ids
        assert "npc_b" not in ids

    def test_personality_profile_lazy_creation(self):
        from app.rpg.presentation import get_actor_personality_profile
        simulation_state = {"presentation_state": {"personality_state": {"profiles": {}}}}
        profile = get_actor_personality_profile(simulation_state, "npc_new", default_name="New NPC")
        assert profile["actor_id"] == "npc_new"
        assert profile["display_name"] == "New NPC"
        profiles = simulation_state["presentation_state"]["personality_state"]["profiles"]
        assert "npc_new" in profiles
