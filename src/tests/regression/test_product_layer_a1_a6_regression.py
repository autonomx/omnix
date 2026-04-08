"""Regression tests for Product Layer Phases A1-A6.

Ensures product layer presentation builders maintain backward compatibility
and deterministic behavior across changes.
"""
import pytest

from app.rpg.presentation.dialogue_ux import INTENT_BUTTONS, build_dialogue_ux_payload
from app.rpg.presentation.intro_scene import build_intro_scene_payload
from app.rpg.presentation.narrative_recap import build_narrative_recap_payload
from app.rpg.presentation.player_inspector import (
    _band,
    build_player_inspector_overlay_payload,
)
from app.rpg.presentation.save_load_ux import build_save_load_ux_payload
from app.rpg.presentation.setup_flow import (
    VALID_GENRES,
    VALID_TONES,
    build_setup_flow_payload,
)


class TestProductLayerRegressionA1SetupFlow:
    """Regression tests for Phase A1 - Setup Flow stability."""

    def test_a1_setup_flow_determinism_repeated_calls(self):
        """Repeated calls with same input must return identical payloads."""
        inputs = {"genre": "horror", "tone": "grim", "rules": {"violence_level": 6}}
        p1 = build_setup_flow_payload(inputs)
        p2 = build_setup_flow_payload(inputs)
        p3 = build_setup_flow_payload(inputs)
        assert p1 == p2 == p3

    def test_a1_setup_flow_rule_clamping_is_idempotent(self):
        """Rules must be clamped to [0, 10] range."""
        for value in [-10, -1, 0, 5, 10, 11, 100]:
            payload = build_setup_flow_payload({"rules": {"magic_level": value}})
            clamped = payload["setup_flow"]["rules"]["magic_level"]
            assert 0 <= clamped <= 10

    def test_a1_setup_flow_does_not_mutate_input(self):
        """Input dict must not be mutated."""
        user_input = {"genre": "fantasy", "tone": "heroic"}
        original = dict(user_input)
        build_setup_flow_payload(user_input)
        assert user_input == original

    def test_a1_wizard_steps_structure_stable(self):
        """Wizard steps must always be a list of 5 dicts with required keys."""
        payload = build_setup_flow_payload()
        steps = payload["setup_flow"]["wizard_steps"]
        assert isinstance(steps, list)
        assert len(steps) == 5
        for step in steps:
            assert "step_id" in step
            assert "label" in step
            assert "required" in step


class TestProductLayerRegressionA2IntroScene:
    """Regression tests for Phase A2 - Intro Scene stability."""

    def test_a2_intro_scene_determinism(self):
        """Same genre must always produce identical intro payload."""
        p1 = build_intro_scene_payload({"world_seed": {"genre": "mystery"}})
        p2 = build_intro_scene_payload({"world_seed": {"genre": "mystery"}})
        assert p1 == p2

    def test_a2_intro_scene_structure_invariants(self):
        """Intro payload structure must remain stable."""
        for genre in VALID_GENRES:
            payload = build_intro_scene_payload({"world_seed": {"genre": genre}})
            intro = payload["intro_scene"]
            assert "scene_id" in intro
            assert "location_name" in intro
            assert "opening_npc" in intro
            assert "tension_hook" in intro
            assert "actionable_affordance" in intro
            assert "suggested_actions" in intro
            assert "guarantees" in intro
            assert intro["guarantees"]["has_opening_npc"] is True
            assert intro["guarantees"]["has_tension_hook"] is True
            assert intro["guarantees"]["has_actionable_affordance"] is True


class TestProductLayerRegressionA3DialogueUX:
    """Regression tests for Phase A3 - Dialogue UX stability."""

    def test_a3_dialogue_ux_intent_buttons_immutable(self):
        """Intent buttons constant must not be mutated by calls."""
        original_count = len(INTENT_BUTTONS)
        build_dialogue_ux_payload()
        build_dialogue_ux_payload()
        assert len(INTENT_BUTTONS) == original_count

    def test_a3_dialogue_ux_empty_inputs_safe(self):
        """All None inputs must produce valid structure."""
        payload = build_dialogue_ux_payload(None, None, None)
        ux = payload["dialogue_ux"]
        assert len(ux["intent_buttons"]) == 5
        assert ux["hybrid_input"]["allow_free_text"] is True
        assert ux["layered_output"]["speaker_layer"]["speaker_name"] == ""
        assert ux["layered_output"]["speaker_layer"]["text"] == ""


class TestProductLayerRegressionA4PlayerInspector:
    """Regression tests for Phase A4 - Player Inspector stability."""

    def test_a4_inspector_all_none_inputs(self):
        """All None inputs must produce valid structure with defaults."""
        payload = build_player_inspector_overlay_payload(
            None, None, None, None
        )
        overlay = payload["player_overlay"]
        assert "scene" in overlay
        assert "tension" in overlay
        assert "conversation" in overlay
        assert "relationship_hint" in overlay
        assert "system_status" in overlay
        assert 0.0 <= overlay["tension"]["value"] <= 1.0

    def test_a4_band_function_coverage(self):
        """Band function must cover all expected ranges."""
        assert _band(0.0) == "low"
        assert _band(0.19) == "low"
        assert _band(0.2) == "guarded"
        assert _band(0.39) == "guarded"
        assert _band(0.4) == "steady"
        assert _band(0.59) == "steady"
        assert _band(0.6) == "rising"
        assert _band(0.79) == "rising"
        assert _band(0.8) == "high"
        assert _band(1.0) == "high"


class TestProductLayerRegressionA5SaveLoad:
    """Regression tests for Phase A5 - Save/Load UX stability."""

    def test_a5_save_load_empty_stable(self):
        """Empty inputs must produce stable empty structure."""
        payload = build_save_load_ux_payload(save_snapshots=[], current_tick=0)
        ux = payload["save_load_ux"]
        assert ux["save_slots"] == []
        assert ux["rewind_preview"] == []
        assert ux["can_rewind"] is False

    def test_a5_save_load_deterministic_ordering(self):
        """Same inputs must produce same ordering."""
        snapshots = [
            {"save_id": "s3", "tick": 30, "version": 1},
            {"save_id": "s1", "tick": 10, "version": 1},
            {"save_id": "s2", "tick": 20, "version": 1},
        ]
        p1 = build_save_load_ux_payload(save_snapshots=snapshots, current_tick=50)
        p2 = build_save_load_ux_payload(save_snapshots=list(snapshots), current_tick=50)
        assert p1 == p2


class TestProductLayerRegressionA6NarrativeRecap:
    """Regression tests for Phase A6 - Narrative Recap stability."""

    def test_a6_recap_empty_stable(self):
        """Empty inputs must produce stable default structure."""
        payload = build_narrative_recap_payload(None, None)
        recap = payload["narrative_recap"]
        assert recap["recap_text"] == "The situation is still developing."
        assert recap["recent_lines"] == []
        assert recap["surfaced_codex_entries"] == []

    def test_a6_recap_determinism(self):
        """Same inputs must produce same recap."""
        turns = [
            {"tick": 1, "sequence_index": 0, "turn_id": "t1", "speaker_name": "A", "text": "Hello"},
        ]
        p1 = build_narrative_recap_payload({}, {"runtime_dialogue": {"turns": turns}})
        p2 = build_narrative_recap_payload({}, {"runtime_dialogue": {"turns": list(turns)}})
        assert p1 == p2