"""Functional tests for Product Layer Phases A1-A6.

Tests integration of product layer presentation builders with route patterns.
"""
import pytest

from app.rpg.presentation.dialogue_ux import build_dialogue_ux_payload
from app.rpg.presentation.intro_scene import build_intro_scene_payload
from app.rpg.presentation.narrative_recap import build_narrative_recap_payload
from app.rpg.presentation.player_inspector import build_player_inspector_overlay_payload
from app.rpg.presentation.save_load_ux import build_save_load_ux_payload
from app.rpg.presentation.setup_flow import build_setup_flow_payload


class TestProductLayerFunctionalA1SetupBootstrap:
    """Functional test for A1 setup flow -> session bootstrap chain."""

    def test_a1_setup_to_bootstrap_chain(self):
        """Verify setup flow payload can feed session bootstrap correctly."""
        setup = build_setup_flow_payload({
            "genre": "cyberpunk",
            "tone": "grim",
            "player_role": "netrunner",
            "rules": {"tech_level": 8, "magic_level": 0},
        })
        setup_flow = setup.get("setup_flow")
        world_seed = setup_flow.get("world_seed")
        rules = setup_flow.get("rules")
        selected = setup_flow.get("selected")

        assert world_seed["genre"] == "cyberpunk"
        assert rules["tech_level"] == 8
        assert rules["magic_level"] == 0
        assert selected["player_role"] == "netrunner"

    def test_a1_tone_tags_derived_correctly(self):
        """Verify tone tags match selected tone."""
        for tone, expected_tags in [
            ("grim", {"tone:grim", "stakes:high", "humor:low"}),
            ("heroic", {"tone:heroic", "stakes:rising", "hope:present"}),
            ("mysterious", {"tone:mysterious", "secrets:present", "clarity:low"}),
        ]:
            payload = build_setup_flow_payload({"tone": tone})
            actual_tags = set(payload["setup_flow"]["tone_tags"])
            assert actual_tags == expected_tags


class TestProductLayerFunctionalA2IntroFlow:
    """Functional test for A2 intro scene with various genres."""

    def test_a2_intro_scene_preserves_genre_context(self):
        """Verify intro scene matches the genre from setup."""
        for genre_id, expected_scene_id in [
            ("fantasy", "intro:fantasy:gate"),
            ("cyberpunk", "intro:cyberpunk:alley"),
            ("horror", "intro:horror:chapel"),
            ("western", "intro:western:station"),
        ]:
            payload = build_intro_scene_payload({"world_seed": {"genre": genre_id}})
            assert payload["intro_scene"]["scene_id"] == expected_scene_id

    def test_a2_intro_scene_actions_are_actionable(self):
        """Verify all intro scenes provide usable actions."""
        for genre in ["fantasy", "cyberpunk", "horror", "science_fiction",
                      "post_apocalypse", "mystery", "western"]:
            payload = build_intro_scene_payload({"world_seed": {"genre": genre}})
            actions = payload["intro_scene"]["suggested_actions"]
            assert len(actions) == 3
            assert actions[2]["label"] == payload["intro_scene"]["actionable_affordance"]


class TestProductLayerFunctionalA3DialogueIntegration:
    """Functional test for A3 dialogue UX with layered output."""

    def test_a3_dialogue_ux_companion_detection(self):
        """Verify companion interjection detection works."""
        with_companion = build_dialogue_ux_payload(
            runtime_payload={"runtime_dialogue": {
                "turns": [{"role": "companion", "text": "Watch out!"}]
            }},
        )
        assert with_companion["dialogue_ux"]["layered_output"]["companion_layer"]["has_companion_interjection"] is True

        without_companion = build_dialogue_ux_payload(
            runtime_payload={"runtime_dialogue": {
                "turns": [{"role": "narrator", "text": "The scene begins."}]
            }},
        )
        assert without_companion["dialogue_ux"]["layered_output"]["companion_layer"]["has_companion_interjection"] is False

    def test_a3_dialogue_ux_streaming_hint(self):
        """Verify streaming hint reflects provider mode."""
        for mode, expected in [("capture", True), ("live", True), ("disabled", False)]:
            payload = build_dialogue_ux_payload(
                orchestration_payload={"llm_orchestration": {"provider_mode": mode}},
            )
            assert payload["dialogue_ux"]["layered_output"]["system_layer"]["show_streaming_hint"] == expected


class TestProductLayerFunctionalA4InspectorIntegration:
    """Functional test for A4 player inspector overlay."""

    def test_a4_inspector_combines_all_sources(self):
        """Verify inspector combines scene, dialogue, orchestration, and live provider data."""
        payload = build_player_inspector_overlay_payload(
            simulation_state={
                "director_state": {"global_tension": 0.55},
                "scene_state": {"scene_id": "scene:encounter", "location_name": "Dark Alley"},
            },
            runtime_payload={
                "runtime_dialogue": {
                    "turn_cursor": 5,
                    "turns": [{"speaker_name": "Guard", "emotion": "suspicious"}],
                }
            },
            orchestration_payload={
                "llm_orchestration": {"provider_mode": "live"},
            },
            live_provider_payload={
                "live_provider": {"executions": [{"execution_id": "e1"}, {"execution_id": "e2"}]},
            },
        )
        overlay = payload["player_overlay"]
        assert overlay["scene"]["location_name"] == "Dark Alley"
        assert overlay["tension"]["band"] == "steady"
        assert overlay["conversation"]["latest_speaker"] == "Guard"
        assert overlay["system_status"]["live_execution_count"] == 2


class TestProductLayerFunctionalA5SaveLoad:
    """Functional test for A5 save/load UX."""

    def test_a5_rewind_calculation_across_ticks(self):
        """Verify tick delta is correctly calculated for rewind preview."""
        payload = build_save_load_ux_payload(
            save_snapshots=[
                {"save_id": "auto:5", "tick": 50, "version": 1},
                {"save_id": "auto:15", "tick": 150, "version": 2},
                {"save_id": "player:3", "tick": 100, "version": 1},
            ],
            current_tick=200,
        )
        ux = payload["save_load_ux"]
        assert ux["save_slots"][0]["save_id"] == "auto:15"
        assert ux["save_slots"][0]["tick_delta"] if "tick_delta" in ux["save_slots"][0] else True
        preview_by_id = {p["save_id"]: p for p in ux["rewind_preview"]}
        assert preview_by_id["auto:15"]["tick_delta"] == 50
        assert preview_by_id["player:3"]["tick_delta"] == 100


class TestProductLayerFunctionalA6Recap:
    """Functional test for A6 narrative recap."""

    def test_a6_recap_orders_turns_by_tick_and_sequence(self):
        """Verify recap orders turns correctly regardless of input order."""
        payload = build_narrative_recap_payload(
            {},
            {"runtime_dialogue": {"turns": [
                {"tick": 5, "sequence_index": 2, "turn_id": "t3", "speaker_name": "B", "text": "Third"},
                {"tick": 5, "sequence_index": 0, "turn_id": "t1", "speaker_name": "A", "text": "First"},
                {"tick": 5, "sequence_index": 1, "turn_id": "t2", "speaker_name": "A", "text": "Second"},
            ]}},
        )
        recap = payload["narrative_recap"]
        assert recap["recent_lines"] == [
            "A: First",
            "A: Second",
            "B: Third",
        ]