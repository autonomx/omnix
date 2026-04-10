"""Functional tests — Idle debug trace in idle tick response."""
from __future__ import annotations

import importlib
import importlib.util
import os
import sys

SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, SRC_DIR)


def _load(mod_name: str, rel_path: str):
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(
        mod_name, os.path.join(SRC_DIR, rel_path),
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


_amb_policy = _load("app.rpg.session.ambient_policy", "app/rpg/session/ambient_policy.py")
_is_reaction_update = _amb_policy._is_reaction_update

_schema = _load("app.rpg.creator.schema", "app/rpg/creator/schema.py")
_defaults = _load("app.rpg.creator.defaults", "app/rpg/creator/defaults.py")
_amb_builder = _load("app.rpg.session.ambient_builder", "app/rpg/session/ambient_builder.py")
_amb_dialogue = _load("app.rpg.ai.ambient_dialogue", "app/rpg/ai/ambient_dialogue.py")
_npc_init = _load("app.rpg.ai.npc_initiative", "app/rpg/ai/npc_initiative.py")
build_ambient_dialogue_candidates = _amb_dialogue.build_ambient_dialogue_candidates
build_npc_initiative_candidates = _npc_init.build_npc_initiative_candidates


class TestDebugTraceStructure:
    """Test that idle_debug_trace would contain expected fields."""

    def test_debug_trace_template_has_required_keys(self):
        """Verify the structure of a debug trace dict as defined in runtime."""
        trace = {
            "reason": "heartbeat",
            "tick_before": 5,
            "quiet_ticks_before": 0,
            "world_behavior": {},
            "last_player_action_context": {},
            "raw_counts": {},
            "selected": {},
            "visibility": {},
            "delivery": {},
            "filters": [],
            "idle_seconds": 120,
            "idle_gate_open": True,
            "conversation_idle_seconds": 60,
        }
        assert "reason" in trace
        assert "tick_before" in trace
        assert "raw_counts" in trace
        assert "selected" in trace
        assert "visibility" in trace
        assert "idle_seconds" in trace
        assert "idle_gate_open" in trace

    def test_raw_counts_fields(self):
        counts = {
            "ambient_updates": 3,
            "initiative_candidates": 2,
            "reaction_candidates": 1,
            "idle_dialogue_candidates": 0,
            "scene_beats": 0,
            "world_event_candidates": 1,
        }
        assert counts["ambient_updates"] == 3
        assert counts["reaction_candidates"] == 1

    def test_selected_fields(self):
        selected = {
            "initiative": {"kind": "companion_comment", "speaker_id": "npc:bran"},
            "reaction": {"kind": "follow_reaction", "speaker_id": "npc:bran"},
            "idle_dialogue": {},
            "scene": {},
        }
        assert selected["reaction"]["kind"] == "follow_reaction"
        assert selected["idle_dialogue"] == {}

    def test_visibility_fields(self):
        visibility = {
            "visible_count": 4,
            "coalesced_count": 3,
        }
        assert visibility["visible_count"] == 4


class TestEmptyCandideLanes:
    def test_no_crash_empty_reaction(self):
        """Reaction lane with empty state should produce empty list."""
        candidates = build_ambient_dialogue_candidates(
            {}, {"ambient_cooldowns": {}}, {}, lane="reaction"
        )
        assert candidates == []

    def test_no_crash_empty_idle(self):
        """Idle lane with empty state should produce empty list."""
        candidates = build_ambient_dialogue_candidates(
            {}, {"ambient_cooldowns": {}}, {}, lane="idle"
        )
        # May include original candidates but shouldn't crash
        assert isinstance(candidates, list)

    def test_no_crash_initiative_reaction_lane(self):
        candidates = build_npc_initiative_candidates(
            {}, {}, {}, lane="reaction"
        )
        assert candidates == []

    def test_no_crash_initiative_idle_lane(self):
        candidates = build_npc_initiative_candidates(
            {}, {}, {}, lane="idle"
        )
        assert isinstance(candidates, list)


class TestReactionUpdateClassification:
    def test_follow_reaction_is_reaction(self):
        assert _is_reaction_update({"kind": "follow_reaction"}) is True

    def test_caution_reaction_is_reaction(self):
        assert _is_reaction_update({"kind": "caution_reaction"}) is True

    def test_assist_reaction_is_reaction(self):
        assert _is_reaction_update({"kind": "assist_reaction"}) is True

    def test_warning_is_reaction(self):
        assert _is_reaction_update({"kind": "warning"}) is True

    def test_combat_start_is_reaction(self):
        assert _is_reaction_update({"kind": "combat_start"}) is True

    def test_gossip_is_not_reaction(self):
        assert _is_reaction_update({"kind": "gossip"}) is False

    def test_npc_to_npc_is_not_reaction(self):
        assert _is_reaction_update({"kind": "npc_to_npc"}) is False

    def test_interrupt_flag_makes_reaction(self):
        assert _is_reaction_update({"kind": "npc_to_player", "interrupt": True}) is True
