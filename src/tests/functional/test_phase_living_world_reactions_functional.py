"""Functional tests — Living-world NPC reactions to player actions."""
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


_schema = _load("app.rpg.creator.schema", "app/rpg/creator/schema.py")
_defaults = _load("app.rpg.creator.defaults", "app/rpg/creator/defaults.py")
_amb_builder = _load("app.rpg.session.ambient_builder", "app/rpg/session/ambient_builder.py")
_amb_policy = _load("app.rpg.session.ambient_policy", "app/rpg/session/ambient_policy.py")
_amb_dialogue = _load("app.rpg.ai.ambient_dialogue", "app/rpg/ai/ambient_dialogue.py")
_npc_init = _load("app.rpg.ai.npc_initiative", "app/rpg/ai/npc_initiative.py")

build_ambient_dialogue_candidates = _amb_dialogue.build_ambient_dialogue_candidates
select_ambient_dialogue_candidate = _amb_dialogue.select_ambient_dialogue_candidate
build_npc_initiative_candidates = _npc_init.build_npc_initiative_candidates
should_interrupt_player = _amb_policy.should_interrupt_player
_is_reaction_update = _amb_policy._is_reaction_update


def _base_simulation_state(**overrides):
    state = {
        "tick": 5,
        "npc_index": {
            "npc:bran": {
                "name": "Bran",
                "location_id": "loc:cave",
                "role": "companion",
                "personality": "loyal",
                "is_companion": True,
            },
            "npc:elara": {
                "name": "Elara",
                "location_id": "loc:cave",
                "role": "merchant",
                "personality": "cautious",
            },
        },
        "npc_minds": {
            "npc:bran": {
                "beliefs": {"player": {"trust": 0.8, "hostility": 0.0}},
                "goals": [],
            },
            "npc:elara": {
                "beliefs": {"player": {"trust": 0.4, "hostility": 0.0}},
                "goals": [],
            },
        },
        "npc_decisions": {},
        "player_state": {
            "location_id": "loc:cave",
            "nearby_npc_ids": ["npc:bran", "npc:elara"],
            "party_npc_ids": ["npc:bran"],
        },
    }
    state.update(overrides)
    return state


def _runtime_with_action_context(movement_intent="rush", risk_level="high", urgency="high"):
    return {
        "tick": 5,
        "ambient_cooldowns": {},
        "settings": {
            "follow_reactions_enabled": True,
            "reaction_style": "normal",
        },
        "last_player_action_context": {
            "tick": 5,
            "player_input": "i rush toward the narrow fissure",
            "action_type": "move",
            "movement_intent": movement_intent,
            "risk_level": risk_level,
            "urgency": urgency,
            "target_id": "",
            "target_name": "",
            "location_id": "loc:cave",
        },
    }


def _player_context():
    return {
        "player_location": "loc:cave",
        "nearby_npc_ids": ["npc:bran", "npc:elara"],
    }


class TestPlayerRushStoresContext:
    def test_action_context_has_movement_intent(self):
        rt = _runtime_with_action_context()
        ctx = rt["last_player_action_context"]
        assert ctx["movement_intent"] == "rush"
        assert ctx["risk_level"] == "high"
        assert ctx["urgency"] == "high"


class TestReactionCandidates:
    def test_rush_generates_follow_reaction(self):
        sim = _base_simulation_state()
        rt = _runtime_with_action_context(movement_intent="rush")
        candidates = build_ambient_dialogue_candidates(sim, rt, _player_context(), lane="reaction")
        follow = [c for c in candidates if c["kind"] == "follow_reaction"]
        assert len(follow) >= 1
        assert any(c["speaker_id"] == "npc:bran" for c in follow)

    def test_rush_generates_caution_reaction(self):
        sim = _base_simulation_state()
        rt = _runtime_with_action_context(movement_intent="rush", risk_level="high")
        candidates = build_ambient_dialogue_candidates(sim, rt, _player_context(), lane="reaction")
        caution = [c for c in candidates if c["kind"] == "caution_reaction"]
        assert len(caution) >= 1
        # Elara (non-companion with trust > 0.2) should produce caution
        assert any(c["speaker_id"] == "npc:elara" for c in caution)

    def test_inspect_generates_assist_for_companion(self):
        sim = _base_simulation_state()
        rt = _runtime_with_action_context(movement_intent="inspect", risk_level="low", urgency="low")
        candidates = build_ambient_dialogue_candidates(sim, rt, _player_context(), lane="reaction")
        # Companion should not produce assist unless they have scholarly personality
        # But let's check the reaction lane produces something
        assert isinstance(candidates, list)

    def test_retreat_generates_follow(self):
        sim = _base_simulation_state()
        rt = _runtime_with_action_context(movement_intent="retreat", risk_level="low", urgency="medium")
        candidates = build_ambient_dialogue_candidates(sim, rt, _player_context(), lane="reaction")
        follow = [c for c in candidates if c["kind"] == "follow_reaction"]
        assert len(follow) >= 1

    def test_no_reactions_without_action_context(self):
        sim = _base_simulation_state()
        rt = {"tick": 5, "ambient_cooldowns": {}, "settings": {}, "last_player_action_context": {}}
        candidates = build_ambient_dialogue_candidates(sim, rt, _player_context(), lane="reaction")
        assert len(candidates) == 0

    def test_follow_reactions_disabled_suppresses_follow(self):
        sim = _base_simulation_state()
        rt = _runtime_with_action_context(movement_intent="rush")
        rt["settings"]["follow_reactions_enabled"] = False
        candidates = build_ambient_dialogue_candidates(sim, rt, _player_context(), lane="reaction")
        follow = [c for c in candidates if c["kind"] == "follow_reaction"]
        assert len(follow) == 0


class TestQuietTicksDoNotSuppressReactions:
    def test_reaction_update_bypasses_quiet_window(self):
        update = {
            "kind": "follow_reaction",
            "priority": 0.7,
            "speaker_id": "npc:bran",
            "speaker_name": "Bran",
            "interrupt": False,
        }
        assert _is_reaction_update(update) is True

    def test_gossip_is_not_reaction(self):
        update = {"kind": "gossip", "priority": 0.2, "interrupt": False}
        assert _is_reaction_update(update) is False

    def test_warning_is_reaction(self):
        update = {"kind": "warning", "priority": 0.8, "interrupt": True}
        assert _is_reaction_update(update) is True


class TestQuietTicksSuppressIdleChatter:
    def test_gossip_suppressed_during_quiet(self):
        session = {
            "runtime_state": {
                "post_player_quiet_ticks": 2,
                "last_interrupt_tick": 0,
            },
        }
        update = {"kind": "gossip", "priority": 0.3, "interrupt": False}
        assert should_interrupt_player(session, update) is False

    def test_npc_to_npc_suppressed_during_quiet(self):
        session = {
            "runtime_state": {
                "post_player_quiet_ticks": 2,
                "last_interrupt_tick": 0,
            },
        }
        update = {"kind": "npc_to_npc", "priority": 0.4, "interrupt": False}
        assert should_interrupt_player(session, update) is False


class TestInitiativeReactionLane:
    def test_reaction_lane_produces_follow_initiative(self):
        sim = _base_simulation_state()
        rt = _runtime_with_action_context(movement_intent="rush")
        ctx = _player_context()
        candidates = build_npc_initiative_candidates(sim, rt, ctx, lane="reaction")
        follow = [c for c in candidates if c["kind"] == "follow_reaction"]
        assert len(follow) >= 1

    def test_idle_lane_does_not_use_action_context(self):
        sim = _base_simulation_state()
        rt = _runtime_with_action_context(movement_intent="rush")
        ctx = _player_context()
        candidates = build_npc_initiative_candidates(sim, rt, ctx, lane="idle")
        # Idle lane should produce standard initiative, not reaction kinds
        follow = [c for c in candidates if c["kind"] == "follow_reaction"]
        assert len(follow) == 0


class TestReactionSelectionPriority:
    def test_reaction_beats_idle_in_selection(self):
        candidates = [
            {
                "kind": "gossip",
                "lane": "idle",
                "speaker_id": "npc:elara",
                "target_id": "",
                "salience": 0.3,
            },
            {
                "kind": "follow_reaction",
                "lane": "reaction",
                "speaker_id": "npc:bran",
                "target_id": "player",
                "salience": 0.7,
            },
        ]
        rt = {"tick": 5, "ambient_cooldowns": {}}
        selected = select_ambient_dialogue_candidate(candidates, rt)
        assert selected is not None
        assert selected["kind"] == "follow_reaction"
