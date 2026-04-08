"""Unit tests for Product Layer Phases A1-A6.

Tests for:
- A1: Setup Flow
- A2: Intro Scene
- A3: Dialogue UX
- A4: Player Inspector
- A5: Save/Load UX
- A6: Narrative Recap
"""
import pytest

from app.rpg.presentation.dialogue_ux import build_dialogue_ux_payload
from app.rpg.presentation.intro_scene import build_intro_scene_payload
from app.rpg.presentation.narrative_recap import build_narrative_recap_payload
from app.rpg.presentation.player_inspector import build_player_inspector_overlay_payload
from app.rpg.presentation.save_load_ux import build_save_load_ux_payload
from app.rpg.presentation.setup_flow import (
    VALID_GENRES,
    VALID_TONES,
    build_setup_flow_payload,
)


class TestPhaseA1SetupFlow:
    """Unit tests for Phase A1 - Setup Flow."""

    def test_a1_setup_flow_builds_valid_payload(self):
        payload = build_setup_flow_payload({
            "genre": "fantasy",
            "tone": "heroic",
            "player_role": "knight",
            "rules": {"magic_level": 8},
            "seed_prompt": "A quest begins",
        })
        assert "setup_flow" in payload
        selected = payload["setup_flow"]["selected"]
        assert selected["genre"] == "fantasy"
        assert selected["tone"] == "heroic"
        assert selected["player_role"] == "knight"
        assert selected["seed_prompt"] == "A quest begins"

    def test_a1_setup_flow_is_deterministic(self):
        payload_a = build_setup_flow_payload({
            "genre": "cyberpunk",
            "tone": "grim",
            "player_role": "courier",
            "rules": {"tech_level": 9, "lawfulness": 2},
            "seed_prompt": "Megacity under pressure",
        })
        payload_b = build_setup_flow_payload({
            "genre": "cyberpunk",
            "tone": "grim",
            "player_role": "courier",
            "rules": {"lawfulness": 2, "tech_level": 9},
            "seed_prompt": "Megacity under pressure",
        })
        assert payload_a == payload_b

    def test_a1_setup_flow_normalizes_invalid_inputs(self):
        payload = build_setup_flow_payload({
            "genre": "invalid",
            "tone": "invalid",
            "rules": {"tech_level": 99},
        })
        selected = payload["setup_flow"]["selected"]
        assert selected["genre"] == "fantasy"
        assert selected["tone"] == "heroic"
        assert payload["setup_flow"]["rules"]["tech_level"] == 10

    def test_a1_setup_flow_has_wizard_steps(self):
        payload = build_setup_flow_payload()
        steps = payload["setup_flow"]["wizard_steps"]
        assert len(steps) == 5
        assert steps[0]["step_id"] == "genre"

    def test_a1_setup_flow_has_options(self):
        payload = build_setup_flow_payload()
        options = payload["setup_flow"]["options"]
        assert "genres" in options
        assert "tones" in options
        assert "rule_keys" in options
        assert options["genres"] == sorted(list(VALID_GENRES))


class TestPhaseA2IntroScene:
    """Unit tests for Phase A2 - Intro Scene."""

    def test_a2_intro_scene_has_required_elements(self):
        payload = build_intro_scene_payload({"world_seed": {"genre": "cyberpunk"}})
        intro = payload["intro_scene"]
        assert intro["guarantees"]["has_opening_npc"] is True
        assert intro["guarantees"]["has_tension_hook"] is True
        assert intro["guarantees"]["has_actionable_affordance"] is True
        assert len(intro["suggested_actions"]) == 3

    def test_a2_intro_scene_fantasy(self):
        payload = build_intro_scene_payload({"world_seed": {"genre": "fantasy"}})
        intro = payload["intro_scene"]
        assert intro["scene_id"] == "intro:fantasy:gate"
        assert intro["location_name"] == "South Gate"

    def test_a2_intro_scene_defaults_to_fantasy(self):
        payload = build_intro_scene_payload({"world_seed": {"genre": "unknown"}})
        intro = payload["intro_scene"]
        assert "fantasy" in intro["scene_id"]

    def test_a2_intro_scene_all_genres(self):
        for genre in ["fantasy", "cyberpunk", "horror", "science_fiction",
                      "post_apocalypse", "mystery", "western"]:
            payload = build_intro_scene_payload({"world_seed": {"genre": genre}})
            intro = payload["intro_scene"]
            assert intro["scene_id"] != ""
            assert intro["tension_hook"] != ""
            assert intro["actionable_affordance"] != ""


class TestPhaseA3DialogueUX:
    """Unit tests for Phase A3 - Dialogue UX."""

    def test_a3_dialogue_ux_has_intents(self):
        payload = build_dialogue_ux_payload()
        ux = payload["dialogue_ux"]
        assert len(ux["intent_buttons"]) == 5

    def test_a3_dialogue_ux_has_hybrid_input(self):
        payload = build_dialogue_ux_payload()
        ux = payload["dialogue_ux"]
        assert ux["hybrid_input"]["allow_free_text"] is True
        assert ux["hybrid_input"]["allow_intent_buttons"] is True

    def test_a3_dialogue_ux_layered_output(self):
        payload = build_dialogue_ux_payload(
            {"speaker_name": "Lyra", "text": "We should move."},
            {"runtime_dialogue": {"turn_cursor": 2, "turns": [{"role": "companion", "text": "Stay sharp."}]}},
            {"llm_orchestration": {"provider_mode": "capture"}},
        )
        ux = payload["dialogue_ux"]
        assert ux["layered_output"]["speaker_layer"]["speaker_name"] == "Lyra"
        assert ux["layered_output"]["companion_layer"]["has_companion_interjection"] is True
        assert ux["layered_output"]["system_layer"]["show_streaming_hint"] is True


class TestPhaseA4PlayerInspector:
    """Unit tests for Phase A4 - Player Inspector."""

    def test_a4_player_inspector_is_deterministic_and_safe(self):
        payload = build_player_inspector_overlay_payload(
            {"director_state": {"global_tension": 0.72}, "scene_state": {"scene_id": "scene:test", "location_name": "Test Plaza"}},
            {"runtime_dialogue": {"turn_cursor": 3, "turns": [{"speaker_name": "Lyra", "emotion": "guarded"}]}},
            {"llm_orchestration": {"provider_mode": "capture"}},
            {"live_provider": {"executions": [{"execution_id": "e1"}]}},
        )
        overlay = payload["player_overlay"]
        assert overlay["scene"]["scene_id"] == "scene:test"
        assert overlay["tension"]["band"] == "rising"
        assert overlay["conversation"]["latest_speaker"] == "Lyra"
        assert overlay["system_status"]["provider_mode"] == "capture"

    def test_a4_player_inspector_tension_bands(self):
        for tension, expected_band in [
            (0.1, "low"), (0.3, "guarded"), (0.5, "steady"), (0.7, "rising"), (0.9, "high"),
        ]:
            payload = build_player_inspector_overlay_payload(
                {"director_state": {"global_tension": tension}},
                {}, {}, {}
            )
            assert payload["player_overlay"]["tension"]["band"] == expected_band


class TestPhaseA5SaveLoadUX:
    """Unit tests for Phase A5 - Save/Load UX."""

    def test_a5_save_load_ux_sorts_slots(self):
        payload = build_save_load_ux_payload(
            save_snapshots=[
                {"save_id": "save:1", "tick": 10, "version": 1},
                {"save_id": "save:2", "tick": 20, "version": 1},
            ],
            current_tick=25,
        )
        ux = payload["save_load_ux"]
        assert ux["save_slots"][0]["save_id"] == "save:2"
        assert ux["rewind_preview"][0]["tick_delta"] == 5
        assert ux["can_rewind"] is True

    def test_a5_save_load_ux_empty_slots(self):
        payload = build_save_load_ux_payload(save_snapshots=[], current_tick=0)
        ux = payload["save_load_ux"]
        assert ux["can_rewind"] is False
        assert len(ux["save_slots"]) == 0


class TestPhaseA6NarrativeRecap:
    """Unit tests for Phase A6 - Narrative Recap."""

    def test_a6_narrative_recap_builds_recent_lines(self):
        payload = build_narrative_recap_payload(
            {"codex_state": {"entries": [{"entry_id": "c1", "title": "The Caravan", "summary": "It vanished on the road."}]}},
            {"runtime_dialogue": {"turns": [
                {"tick": 1, "sequence_index": 0, "turn_id": "t1", "speaker_name": "Lyra", "text": "We should investigate."},
                {"tick": 1, "sequence_index": 1, "turn_id": "t2", "speaker_name": "Guard", "text": "The road is unsafe."},
            ]}},
        )
        recap = payload["narrative_recap"]
        assert "Lyra: We should investigate." in recap["recent_lines"]
        assert recap["surfaced_codex_entries"][0]["entry_id"] == "c1"

    def test_a6_narrative_recap_default_text(self):
        payload = build_narrative_recap_payload({}, {"runtime_dialogue": {"turns": []}})
        recap = payload["narrative_recap"]
        assert recap["recap_text"] == "The situation is still developing."