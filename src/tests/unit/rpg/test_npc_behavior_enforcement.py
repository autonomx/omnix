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

    def test_decide_preserves_target_id(self):
        """negotiate decision must preserve the target NPC id."""
        from app.rpg.ai.llm_mind.npc_mind import NPCMind
        mind = NPCMind(npc_id="npc:a")
        sim = _basic_sim_with_colocated_npc(other_id="npc:guard")
        ctx = _npc_ctx()
        mind.refresh_goals(sim, ctx)
        decision = mind.decide(sim, ctx, tick=1)
        assert decision.target_id == "npc:guard"
        assert decision.target_kind == "npc"

    def test_decide_intent_is_negotiate_not_observe(self):
        """negotiate_with_nearby_npc must map to intent=negotiate."""
        from app.rpg.ai.llm_mind.npc_mind import NPCMind
        mind = NPCMind(npc_id="npc:a")
        sim = _basic_sim_with_colocated_npc()
        ctx = _npc_ctx()
        mind.refresh_goals(sim, ctx)
        decision = mind.decide(sim, ctx, tick=1)
        assert decision.intent == "negotiate"
        assert decision.intent != "observe"
        assert decision.intent != "wait"


# ── 9. conversation_templates.py supports ambient_chat ───────────────────

class TestConversationTemplatesAmbientChat:
    """Invariant: topic_type == 'ambient_chat' must produce spoken content,
    not fall through to the generic default."""

    def test_ambient_chat_merchant_line(self):
        from app.rpg.social.conversation_templates import build_template_line
        conv = {"topic": {"type": "ambient_chat", "stance": "comment", "summary": ""}}
        sim = {"npc_index": {"npc:m": {"name": "Merchant", "role": "merchant"}}}
        result = build_template_line(conv, "npc:m", sim, {})
        assert result["text"], "Must produce non-empty text"
        assert result["text"] != "There is something we should discuss before we move on."
        assert result["kind"] in {"statement", "warning", "question", "challenge"}

    def test_ambient_chat_guard_line(self):
        from app.rpg.social.conversation_templates import build_template_line
        conv = {"topic": {"type": "ambient_chat", "stance": "comment", "summary": ""}}
        sim = {"npc_index": {"npc:g": {"name": "Guard", "role": "guard"}}}
        result = build_template_line(conv, "npc:g", sim, {})
        assert result["text"]
        assert result["kind"] == "warning"

    def test_ambient_chat_default_role_line(self):
        from app.rpg.social.conversation_templates import build_template_line
        conv = {"topic": {"type": "ambient_chat", "stance": "comment", "summary": ""}}
        sim = {"npc_index": {"npc:v": {"name": "Villager", "role": "villager"}}}
        result = build_template_line(conv, "npc:v", sim, {})
        assert result["text"]
        assert "discuss" not in result["text"].lower(), "Must not use generic default"


# ── 10. world_simulation.py event summaries ──────────────────────────────

class TestWorldSimulationEventSummaries:
    """Invariant: _decision_to_event produces meaningful NPC-to-NPC summaries,
    not vague or passive descriptions."""

    def test_negotiate_summary_uses_target_name(self):
        from app.rpg.creator.world_simulation import _decision_to_event
        decision = {
            "npc_id": "npc:bran",
            "action_type": "negotiate",
            "target_id": "npc:elara",
            "target_kind": "npc",
            "location_id": "loc:market",
            "urgency": 0.5,
        }
        npc_ctx = {
            "name": "Bran",
            "npc_id": "npc:bran",
            "location_id": "loc:market",
            "npc_index": {
                "npc:elara": {"name": "Elara"},
            },
        }
        event = _decision_to_event(decision, npc_ctx, tick=5)
        assert event is not None
        assert "Bran speaks with Elara" in event["summary"]
        assert event["type"] == "negotiate"
        assert event["source"] == "npc_mind"

    def test_support_summary_uses_target_name(self):
        from app.rpg.creator.world_simulation import _decision_to_event
        decision = {
            "npc_id": "npc:bran",
            "action_type": "support",
            "target_id": "npc:elara",
            "target_kind": "npc",
            "location_id": "loc:market",
            "urgency": 0.5,
        }
        npc_ctx = {
            "name": "Bran",
            "npc_id": "npc:bran",
            "location_id": "loc:market",
            "npc_index": {
                "npc:elara": {"name": "Elara"},
            },
        }
        event = _decision_to_event(decision, npc_ctx, tick=5)
        assert event is not None
        assert "Bran checks in with Elara" in event["summary"]

    def test_move_summary(self):
        from app.rpg.creator.world_simulation import _decision_to_event
        decision = {
            "npc_id": "npc:bran",
            "action_type": "move",
            "target_id": "loc:tavern",
            "target_kind": "location",
            "location_id": "loc:market",
            "target_location": "the tavern",
            "urgency": 0.5,
        }
        npc_ctx = {"name": "Bran", "npc_id": "npc:bran", "npc_index": {}}
        event = _decision_to_event(decision, npc_ctx, tick=5)
        assert event is not None
        assert "Bran heads toward" in event["summary"]

    def test_wait_produces_no_event(self):
        from app.rpg.creator.world_simulation import _decision_to_event
        decision = {
            "npc_id": "npc:bran",
            "action_type": "wait",
            "target_id": "",
            "location_id": "loc:market",
            "urgency": 0.0,
        }
        npc_ctx = {"name": "Bran", "npc_id": "npc:bran", "npc_index": {}}
        event = _decision_to_event(decision, npc_ctx, tick=5)
        assert event is None, "wait actions must not produce events"

    def test_internal_reason_not_in_summary(self):
        """internal_reason must be stored separately, not leaked into summary."""
        from app.rpg.creator.world_simulation import _decision_to_event
        decision = {
            "npc_id": "npc:bran",
            "action_type": "negotiate",
            "target_id": "npc:elara",
            "target_kind": "npc",
            "location_id": "loc:market",
            "urgency": 0.5,
            "reason": "Force social interaction — nearby NPC present",
        }
        npc_ctx = {
            "name": "Bran",
            "npc_id": "npc:bran",
            "npc_index": {"npc:elara": {"name": "Elara"}},
        }
        event = _decision_to_event(decision, npc_ctx, tick=5)
        assert "Force social" not in event["summary"]
        assert event.get("internal_reason") == "Force social interaction — nearby NPC present"


# ── 11. conversation_engine.py allows up to 2 ambient starts ─────────────

class TestConversationEngineAmbientStarts:
    """Invariant: try_start_ambient_conversations can start up to 2
    conversations when the scene is quiet."""

    def test_two_ambient_conversations_can_start(self):
        from app.rpg.social.conversation_engine import try_start_ambient_conversations
        from app.rpg.social.npc_conversations import ensure_conversation_state, list_active_conversations
        sim = {
            "player_state": {"location_id": "loc:market", "nearby_npc_ids": ["npc:a", "npc:b", "npc:c", "npc:d"]},
            "npc_index": {
                "npc:a": {"name": "Alice", "location_id": "loc:market", "role": "merchant"},
                "npc:b": {"name": "Bob", "location_id": "loc:market", "role": "guard"},
                "npc:c": {"name": "Carol", "location_id": "loc:market", "role": "thief"},
                "npc:d": {"name": "Dan", "location_id": "loc:market", "role": "innkeeper"},
            },
            "events": [],
        }
        ensure_conversation_state(sim)
        runtime = {}
        try_start_ambient_conversations(sim, runtime, tick=5)
        active = list_active_conversations(sim, location_id="loc:market")
        # Must be able to start at least 1, up to 2
        assert len(active) >= 1
        assert len(active) <= 2

    def test_bounded_at_two(self):
        """Even with many candidate groups, at most 2 conversations start."""
        from app.rpg.social.conversation_engine import try_start_ambient_conversations
        from app.rpg.social.npc_conversations import ensure_conversation_state, list_active_conversations
        sim = {
            "player_state": {
                "location_id": "loc:market",
                "nearby_npc_ids": [f"npc:{i}" for i in range(8)],
            },
            "npc_index": {
                f"npc:{i}": {"name": f"NPC{i}", "location_id": "loc:market", "role": "villager"}
                for i in range(8)
            },
            "events": [],
        }
        ensure_conversation_state(sim)
        runtime = {}
        try_start_ambient_conversations(sim, runtime, tick=5)
        active = list_active_conversations(sim, location_id="loc:market")
        assert len(active) <= 2

    def test_no_debug_print(self):
        """conversation_engine should not have print() debug output."""
        import inspect
        from app.rpg.social import conversation_engine
        source = inspect.getsource(conversation_engine.try_start_ambient_conversations)
        assert "print(" not in source, "Debug print() must be removed"


# ── 12. Ambient builder: on-screen observe/watch also suppressed ─────────

class TestAmbientBuilderOnScreenSuppression:
    """Invariant: observe/watch events from npc_mind must be suppressed
    even when they occur at the player's location."""

    def test_onscreen_observe_suppressed_by_internal_filter(self):
        from app.rpg.session.ambient_builder import _is_low_value_internal_npc_event
        event = {
            "type": "observe",
            "source": "npc_mind",
            "location_id": "loc:market",
            "summary": "Guard observes",
            "target_id": "npc:merchant",
        }
        # Even same-location observe must be suppressed
        assert _is_low_value_internal_npc_event(event, "loc:market") is True

    def test_onscreen_watch_suppressed_by_internal_filter(self):
        from app.rpg.session.ambient_builder import _is_low_value_internal_npc_event
        event = {
            "type": "watch",
            "source": "npc_mind",
            "location_id": "loc:market",
            "summary": "Guard watches",
            "target_id": "npc:merchant",
        }
        assert _is_low_value_internal_npc_event(event, "loc:market") is True

    def test_watches_situation_carefully_text_suppressed(self):
        """The specific spam phrase must be caught by build_ambient_updates."""
        from app.rpg.session.ambient_builder import build_ambient_updates
        before = {"events": [], "tick": 4, "player_state": {"location_id": "loc:market"}}
        after = {
            "events": [
                {
                    "event_id": "e1",
                    "type": "observe",
                    "summary": "Bran watches the situation carefully.",
                    "location_id": "loc:market",
                    "source": "npc_mind",
                },
            ],
            "tick": 5,
            "player_state": {"location_id": "loc:market"},
            "npc_decisions": {},
        }
        updates = build_ambient_updates(before, after, {})
        texts = [u.get("text", "") for u in updates]
        assert not any("watches the situation carefully" in t for t in texts)


# ── 13. Ambient builder surfaces negotiate NPC-to-NPC decisions ──────────

class TestAmbientBuilderNPCtoNPCDecisions:
    """Invariant: negotiate decisions between nearby NPCs should surface
    as npc_to_npc ambient updates so the player sees social interactions."""

    def test_negotiate_decision_surfaces(self):
        from app.rpg.session.ambient_builder import build_ambient_updates
        before = {
            "events": [],
            "npc_decisions": {},
            "tick": 4,
            "player_state": {
                "location_id": "loc:market",
                "nearby_npc_ids": ["npc:bran"],
            },
        }
        after = {
            "events": [],
            "npc_decisions": {
                "npc:bran": {
                    "action_type": "negotiate",
                    "target_id": "npc:elara",
                    "location_id": "loc:market",
                },
            },
            "npc_index": {
                "npc:bran": {"name": "Bran", "location_id": "loc:market"},
                "npc:elara": {"name": "Elara", "location_id": "loc:market"},
            },
            "tick": 5,
            "player_state": {
                "location_id": "loc:market",
                "nearby_npc_ids": ["npc:bran"],
            },
        }
        updates = build_ambient_updates(before, after, {})
        npc_to_npc = [u for u in updates if u.get("kind") == "npc_to_npc"]
        assert len(npc_to_npc) >= 1
        assert "Bran speaks with Elara" in npc_to_npc[0]["text"]

    def test_support_decision_surfaces(self):
        from app.rpg.session.ambient_builder import build_ambient_updates
        before = {
            "events": [],
            "npc_decisions": {},
            "tick": 4,
            "player_state": {
                "location_id": "loc:market",
                "nearby_npc_ids": ["npc:bran"],
            },
        }
        after = {
            "events": [],
            "npc_decisions": {
                "npc:bran": {
                    "action_type": "support",
                    "target_id": "npc:elara",
                    "location_id": "loc:market",
                },
            },
            "npc_index": {
                "npc:bran": {"name": "Bran", "location_id": "loc:market"},
                "npc:elara": {"name": "Elara", "location_id": "loc:market"},
            },
            "tick": 5,
            "player_state": {
                "location_id": "loc:market",
                "nearby_npc_ids": ["npc:bran"],
            },
        }
        updates = build_ambient_updates(before, after, {})
        npc_to_npc = [u for u in updates if u.get("kind") == "npc_to_npc"]
        assert len(npc_to_npc) >= 1
        assert "Bran checks in with Elara" in npc_to_npc[0]["text"]
