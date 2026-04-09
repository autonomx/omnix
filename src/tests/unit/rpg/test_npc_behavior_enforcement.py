"""NPC behavior enforcement tests.

Validates the hard invariants introduced by the behavior enforcement patch:

1. Co-located NPCs must produce a negotiate_with_nearby_npc goal, even when
   player-directed goals (retaliate, avoid, approach) are also present.
2. Passive observe must never appear when nearby NPCs exist.
3. ambient_chat topic is emitted as fallback when no stronger topic exists
   and 2+ NPCs share a location.
4. negotiate_with_nearby_npc maps to a real negotiate action via the
   decision validator, never degrading to observe or wait.
5. The ambient builder suppresses observe/watch spam.
6. NPCDecision.fallback() produces a valid idle decision.
7. The validator accepts 'move' as a legal intent/action.

Run with:
    cd src && PYTHONPATH="." python3 -m pytest tests/unit/rpg/test_npc_behavior_enforcement.py -v --noconftest
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, List

import pytest

SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..")
sys.path.insert(0, SRC_DIR)

from app.rpg.ai.llm_mind.goal_engine import GoalEngine
from app.rpg.ai.llm_mind.npc_decision import NPCDecision
from app.rpg.ai.llm_mind.npc_decision_validator import NPCDecisionValidator
from app.rpg.social.conversation_topics import build_conversation_topic_candidates


# ── helpers ────────────────────────────────────────────────────────────────

def _sim_state(
    *,
    npc_entries: Dict[str, Dict[str, Any]] | None = None,
    events: List[Dict[str, Any]] | None = None,
    locations: Dict[str, Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    return {
        "npc_index": npc_entries or {},
        "events": events or [],
        "locations": locations or {},
    }


def _npc_ctx(
    npc_id: str = "npc:a",
    location_id: str = "loc:market",
    faction_id: str = "",
    role: str = "villager",
    name: str = "Alice",
) -> Dict[str, Any]:
    return {
        "npc_id": npc_id,
        "location_id": location_id,
        "faction_id": faction_id,
        "role": role,
        "name": name,
    }


def _basic_sim_with_colocated_npc(
    npc_id: str = "npc:a",
    other_id: str = "npc:b",
    location_id: str = "loc:market",
) -> Dict[str, Any]:
    """Simulation state where npc_id and other_id share a location."""
    return _sim_state(npc_entries={
        npc_id: {"name": "Alice", "location_id": location_id, "role": "villager"},
        other_id: {"name": "Bob", "location_id": location_id, "role": "merchant"},
    })


# ── 1. Hard fallback: co-located NPCs always produce negotiate goal ───────

class TestHardFallbackNearbyNPC:
    """Invariant: if nearby_npcs is non-empty, a negotiate_with_nearby_npc
    goal must appear in the generated goals, regardless of player beliefs."""

    def test_negotiate_goal_when_no_player_beliefs(self):
        engine = GoalEngine()
        sim = _basic_sim_with_colocated_npc()
        ctx = _npc_ctx()
        goals = engine.generate_goals(ctx, sim, {}, [])
        negotiate_goals = [g for g in goals if g["type"] == "negotiate_with_nearby_npc"]
        assert len(negotiate_goals) >= 1, "Must produce at least one negotiate goal"

    def test_negotiate_goal_even_with_high_hostility(self):
        """Even when hostility toward the player triggers retaliate, the
        negotiate-with-nearby-NPC goal must still be present."""
        engine = GoalEngine()
        sim = _basic_sim_with_colocated_npc()
        ctx = _npc_ctx()
        beliefs = {"player": {"hostility": 0.80, "trust": 0.0, "fear": 0.0}}
        goals = engine.generate_goals(ctx, sim, beliefs, [])
        types = {g["type"] for g in goals}
        assert "retaliate" in types, "Player-directed retaliate must still exist"
        assert "negotiate_with_nearby_npc" in types, (
            "negotiate goal must exist alongside player-directed goal"
        )

    def test_negotiate_goal_even_with_high_fear(self):
        engine = GoalEngine()
        sim = _basic_sim_with_colocated_npc()
        ctx = _npc_ctx()
        beliefs = {"player": {"hostility": 0.0, "trust": 0.0, "fear": 0.70}}
        goals = engine.generate_goals(ctx, sim, beliefs, [])
        types = {g["type"] for g in goals}
        assert "avoid_player" in types
        assert "negotiate_with_nearby_npc" in types

    def test_negotiate_goal_even_with_high_trust(self):
        engine = GoalEngine()
        sim = _basic_sim_with_colocated_npc()
        ctx = _npc_ctx()
        beliefs = {"player": {"hostility": 0.0, "trust": 0.70, "fear": 0.0}}
        goals = engine.generate_goals(ctx, sim, beliefs, [])
        types = {g["type"] for g in goals}
        assert "approach_player" in types
        assert "negotiate_with_nearby_npc" in types

    def test_negotiate_target_is_nearby_npc(self):
        engine = GoalEngine()
        sim = _basic_sim_with_colocated_npc(other_id="npc:guard")
        ctx = _npc_ctx()
        goals = engine.generate_goals(ctx, sim, {}, [])
        negotiate_goals = [g for g in goals if g["type"] == "negotiate_with_nearby_npc"]
        targets = {g["target_id"] for g in negotiate_goals}
        assert "npc:guard" in targets

    def test_hard_fallback_priority_beats_observe(self):
        """The hard fallback negotiate priority must be higher than observe."""
        engine = GoalEngine()
        sim = _basic_sim_with_colocated_npc()
        ctx = _npc_ctx()
        goals = engine.generate_goals(ctx, sim, {}, [])
        negotiate_goals = [g for g in goals if g["type"] == "negotiate_with_nearby_npc"]
        observe_goals = [g for g in goals if g["type"] == "observe"]
        # When NPCs are nearby, observe should not appear at all
        assert len(observe_goals) == 0, "observe must not appear when nearby NPCs exist"
        assert len(negotiate_goals) >= 1


# ── 2. No observe when NPCs are co-located ────────────────────────────────

class TestNoObserveWithNearbyNPCs:
    """Invariant: if nearby_npcs is non-empty, no observe goal may appear."""

    def test_no_observe_goal_when_colocated(self):
        engine = GoalEngine()
        sim = _basic_sim_with_colocated_npc()
        ctx = _npc_ctx()
        goals = engine.generate_goals(ctx, sim, {}, [])
        observe = [g for g in goals if g["type"] == "observe"]
        assert observe == [], "observe must not appear with nearby NPCs"

    def test_observe_only_when_alone(self):
        engine = GoalEngine()
        sim = _sim_state(npc_entries={
            "npc:a": {"name": "Alice", "location_id": "loc:market"},
        })
        ctx = _npc_ctx(npc_id="npc:a")
        goals = engine.generate_goals(ctx, sim, {}, [])
        observe = [g for g in goals if g["type"] == "observe"]
        assert len(observe) == 1, "observe should appear when NPC is alone"

    def test_three_colocated_npcs(self):
        """Even with multiple nearby NPCs, observe must not appear."""
        engine = GoalEngine()
        sim = _sim_state(npc_entries={
            "npc:a": {"name": "Alice", "location_id": "loc:market"},
            "npc:b": {"name": "Bob", "location_id": "loc:market"},
            "npc:c": {"name": "Carol", "location_id": "loc:market"},
        })
        ctx = _npc_ctx(npc_id="npc:a")
        goals = engine.generate_goals(ctx, sim, {}, [])
        observe = [g for g in goals if g["type"] == "observe"]
        assert observe == []
        negotiate = [g for g in goals if g["type"] == "negotiate_with_nearby_npc"]
        assert len(negotiate) >= 1


# ── 3. ambient_chat topic fallback ────────────────────────────────────────

class TestAmbientChatTopicFallback:
    """Invariant: when 2+ NPCs share a location and no events exist,
    an ambient_chat topic must be emitted."""

    def test_ambient_chat_emitted_when_no_events(self):
        topics = build_conversation_topic_candidates(
            simulation_state={"events": [], "npc_index": {}},
            runtime_state={},
            location_id="loc:market",
            participant_ids=["npc:a", "npc:b"],
            tick=5,
        )
        types = {t["type"] for t in topics}
        assert "ambient_chat" in types

    def test_no_ambient_chat_when_real_events_exist(self):
        topics = build_conversation_topic_candidates(
            simulation_state={
                "events": [
                    {"event_id": "e1", "type": "attack", "location_id": "loc:market",
                     "summary": "Fight broke out"},
                ],
                "npc_index": {},
            },
            runtime_state={},
            location_id="loc:market",
            participant_ids=["npc:a", "npc:b"],
            tick=5,
        )
        types = {t["type"] for t in topics}
        assert "local_incident" in types
        # ambient_chat should not appear when stronger topics exist
        assert "ambient_chat" not in types

    def test_no_ambient_chat_with_single_participant(self):
        topics = build_conversation_topic_candidates(
            simulation_state={"events": [], "npc_index": {}},
            runtime_state={},
            location_id="loc:market",
            participant_ids=["npc:a"],
            tick=5,
        )
        types = {t["type"] for t in topics}
        assert "ambient_chat" not in types


# ── 4. negotiate_with_nearby_npc → real negotiate action ──────────────────

class TestNegotiateActionMapping:
    """Invariant: negotiate_with_nearby_npc must map to intent=negotiate,
    action_type=negotiate — never observe or wait."""

    def test_negotiate_survives_validation(self):
        raw = {
            "npc_id": "npc:a",
            "tick": 1,
            "intent": "negotiate",
            "action_type": "negotiate",
            "target_id": "npc:b",
            "target_kind": "npc",
        }
        validated = NPCDecisionValidator.validate(raw)
        assert validated["intent"] == "negotiate"
        assert validated["action_type"] == "negotiate"

    def test_negotiate_not_clamped_to_wait(self):
        raw = {
            "intent": "negotiate",
            "action_type": "negotiate",
        }
        validated = NPCDecisionValidator.validate(raw)
        assert validated["intent"] != "wait"
        assert validated["action_type"] != "wait"

    def test_move_survives_validation(self):
        """move_to_populated_location maps to move; validator must allow it."""
        raw = {
            "intent": "move",
            "action_type": "move",
        }
        validated = NPCDecisionValidator.validate(raw)
        assert validated["intent"] == "move"
        assert validated["action_type"] == "move"


# ── 5. Ambient builder suppresses observe/watch spam ──────────────────────

class TestAmbientObserveSuppression:
    """Invariant: ambient builder must filter out observe/watch events
    and 'watches the situation carefully' text."""

    def test_observe_event_suppressed(self):
        """npc_mind observe events are always suppressed by the world filter."""
        from app.rpg.session.ambient_builder import _is_low_value_npc_world_event
        event = {
            "type": "observe",
            "source": "npc_mind",
            "location_id": "loc:market",
            "summary": "Guard observes",
        }
        assert _is_low_value_npc_world_event(event, "loc:market") is True

    def test_watch_event_suppressed(self):
        from app.rpg.session.ambient_builder import _is_low_value_npc_world_event
        event = {
            "type": "watch",
            "source": "npc_mind",
            "location_id": "loc:market",
            "summary": "Guard watches",
        }
        assert _is_low_value_npc_world_event(event, "loc:market") is True

    def test_negotiate_event_not_suppressed(self):
        from app.rpg.session.ambient_builder import _is_low_value_npc_world_event
        event = {
            "type": "negotiate",
            "source": "npc_mind",
            "location_id": "loc:market",
            "summary": "Guard speaks with merchant",
        }
        assert _is_low_value_npc_world_event(event, "loc:market") is False

    def test_npc_mind_observe_suppressed_offscreen(self):
        """Internal NPC event filter suppresses off-screen observe events."""
        from app.rpg.session.ambient_builder import _is_low_value_internal_npc_event
        event = {
            "type": "observe",
            "source": "npc_mind",
            "location_id": "loc:alley",
            "summary": "Guard observes",
            "target_id": "npc:merchant",
        }
        assert _is_low_value_internal_npc_event(event, "loc:market") is True

    def test_npc_mind_negotiate_not_suppressed(self):
        from app.rpg.session.ambient_builder import _is_low_value_internal_npc_event
        event = {
            "type": "negotiate",
            "source": "npc_mind",
            "location_id": "loc:market",
            "summary": "Guard negotiates",
            "target_id": "npc:merchant",
        }
        assert _is_low_value_internal_npc_event(event, "loc:market") is False


# ── 6. NPCDecision.fallback ──────────────────────────────────────────────

class TestNPCDecisionFallback:
    """NPCDecision.fallback must produce a valid idle decision."""

    def test_fallback_returns_decision(self):
        d = NPCDecision.fallback(npc_id="npc:a", tick=10, location_id="loc:market")
        assert isinstance(d, NPCDecision)
        assert d.npc_id == "npc:a"
        assert d.tick == 10
        assert d.intent == "wait"
        assert d.action_type == "wait"
        assert d.location_id == "loc:market"
        assert d.urgency == 0.0

    def test_fallback_to_dict(self):
        d = NPCDecision.fallback(npc_id="npc:x", tick=3)
        data = d.to_dict()
        assert data["intent"] == "wait"
        assert data["action_type"] == "wait"

    def test_fallback_custom_reason(self):
        d = NPCDecision.fallback(npc_id="npc:a", tick=1, reason="Custom reason")
        assert d.reason == "Custom reason"


# ── 7. Goal deduplication preserves highest-priority negotiate goal ───────

class TestGoalDeduplication:
    """When the hard fallback negotiate goal duplicates a loop-generated
    negotiate goal for the same target, deduplication must keep the
    higher-priority version."""

    def test_higher_priority_negotiate_wins(self):
        engine = GoalEngine()
        # NPC:b is co-located, neutral, trust >= -0.10 → loop generates negotiate
        # at base priority ~0.40–0.48.  Hard fallback adds another at 0.55.
        # After dedup, the 0.55 version should survive.
        sim = _basic_sim_with_colocated_npc()
        ctx = _npc_ctx()
        goals = engine.generate_goals(ctx, sim, {}, [])
        negotiate_for_b = [
            g for g in goals
            if g["type"] == "negotiate_with_nearby_npc" and g["target_id"] == "npc:b"
        ]
        # Should be exactly one after dedup
        assert len(negotiate_for_b) == 1
        assert negotiate_for_b[0]["priority"] >= 0.55


# ── 8. End-to-end: NPCMind.decide produces negotiate, not observe ────────

class TestNPCMindEndToEnd:
    """When an NPC has a nearby peer, NPCMind.decide should produce an
    action_type of 'negotiate', not 'observe'."""

    def test_decide_produces_negotiate(self):
        from app.rpg.ai.llm_mind.npc_mind import NPCMind
        mind = NPCMind(npc_id="npc:a")
        sim = _basic_sim_with_colocated_npc()
        ctx = _npc_ctx()
        mind.refresh_goals(sim, ctx)
        decision = mind.decide(sim, ctx, tick=1)
        assert decision.action_type == "negotiate", (
            f"Expected negotiate but got {decision.action_type}"
        )

    def test_decide_fallback_when_no_goals(self):
        """If goal engine produces nothing, fallback must return wait."""
        from app.rpg.ai.llm_mind.npc_mind import NPCMind
        mind = NPCMind(npc_id="npc:a")
        # Empty sim, empty ctx → no goals at all after merge
        decision = mind.decide({}, _npc_ctx(), tick=1)
        assert decision.action_type == "wait"
