"""Phase 6 — Deterministic NPC Architecture: Unit Tests.

Tests cover all Phase 6 components:
- NPCMemory: salience-based memory with trim/sort
- BeliefModel: trust/fear/respect/hostility belief tracking
- GoalEngine: priority-based goal generation and merging
- NPCDecision: structured decision dataclass
- NPCDecisionValidator: intent/action validation
- NPCPromptBuilder: prompt construction
- NPCResponseParser: payload parsing
- NPCMind: full orchestrator (observe, refresh, decide, round-trip)
- Integration helpers: _build_npc_index, _load_npc_minds, _decision_to_event
- Player action enrichment: _infer_affected_npc_ids
- Scene enrichment: _collect_scene_actors
- Narrator enrichment: _attach_npc_mind_context

Run:
    cd src && PYTHONPATH="." python3 -m pytest tests/unit/rpg/test_phase6_deterministic_npc.py -v --noconftest
"""

from __future__ import annotations

import copy
import os
import sys
import types

# ---------------------------------------------------------------------------
# Bootstrap: avoid triggering Flask / heavy AI module imports
# ---------------------------------------------------------------------------

_SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..")

for _mod_name, _rel_path in [
    ("app", "app"),
    ("app.rpg", os.path.join("app", "rpg")),
    ("app.rpg.ai", os.path.join("app", "rpg", "ai")),
    ("app.rpg.creator", os.path.join("app", "rpg", "creator")),
]:
    if _mod_name not in sys.modules:
        _m = types.ModuleType(_mod_name)
        _m.__path__ = [os.path.join(_SRC_DIR, _rel_path)]
        sys.modules[_mod_name] = _m

from app.rpg.ai.llm_mind.npc_memory import NPCMemory
from app.rpg.ai.llm_mind.belief_model import BeliefModel
from app.rpg.ai.llm_mind.goal_engine import GoalEngine
from app.rpg.ai.llm_mind.npc_decision import NPCDecision
from app.rpg.ai.llm_mind.npc_decision_validator import NPCDecisionValidator
from app.rpg.ai.llm_mind.npc_prompt_builder import NPCPromptBuilder
from app.rpg.ai.llm_mind.npc_response_parser import NPCResponseParser
from app.rpg.ai.llm_mind.npc_mind import NPCMind


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _make_event(
    event_type="attack",
    actor="player",
    target_id="npc_guard",
    target_kind="npc",
    location_id="town",
    faction_id="militia",
    salience=0.8,
    summary="",
):
    return {
        "type": event_type,
        "actor": actor,
        "target_id": target_id,
        "target_kind": target_kind,
        "location_id": location_id,
        "faction_id": faction_id,
        "salience": salience,
        "summary": summary or f"{actor} does {event_type} to {target_id}",
    }


def _make_npc_context(
    npc_id="npc_guard",
    name="Guard",
    role="sentinel",
    faction_id="militia",
    location_id="town",
):
    return {
        "npc_id": npc_id,
        "name": name,
        "role": role,
        "faction_id": faction_id,
        "location_id": location_id,
    }


def _make_simulation_state(locations=None, factions=None, events=None):
    return {
        "tick": 1,
        "locations": locations or {},
        "factions": factions or {},
        "threads": {},
        "events": events or [],
        "consequences": [],
        "incidents": [],
    }


# ===========================================================================
# NPCMemory tests
# ===========================================================================


class TestNPCMemory:
    def test_create_empty(self):
        mem = NPCMemory(npc_id="npc_a")
        assert mem.npc_id == "npc_a"
        assert len(mem.entries) == 0

    def test_remember_adds_entry(self):
        mem = NPCMemory(npc_id="npc_a")
        mem.remember(_make_event(), tick=1)
        assert len(mem.entries) == 1
        assert mem.entries[0]["type"] == "attack"

    def test_remember_many(self):
        mem = NPCMemory(npc_id="npc_a")
        events = [_make_event(event_type="help"), _make_event(event_type="trade")]
        mem.remember_many(events, tick=2)
        assert len(mem.entries) == 2

    def test_salience_player_boost(self):
        mem = NPCMemory(npc_id="npc_a")
        mem.remember({"type": "idle", "actor": "player", "salience": 0.1}, tick=1)
        assert mem.entries[0]["salience"] >= 0.7

    def test_salience_target_self_boost(self):
        mem = NPCMemory(npc_id="npc_a")
        mem.remember({"type": "attack", "actor": "npc_b", "target_id": "npc_a"}, tick=1)
        assert mem.entries[0]["salience"] >= 0.9

    def test_trim_respects_max_entries(self):
        mem = NPCMemory(npc_id="npc_a", max_entries=3)
        for i in range(10):
            mem.remember({"type": f"event_{i}", "salience": float(i) / 10}, tick=i)
        assert len(mem.entries) <= 3

    def test_top_memories_returns_highest_salience(self):
        mem = NPCMemory(npc_id="npc_a")
        mem.remember({"type": "idle", "salience": 0.1}, tick=1)
        mem.remember({"type": "attack", "actor": "player", "target_id": "npc_a"}, tick=2)
        top = mem.top_memories(limit=1)
        assert len(top) == 1
        assert top[0]["salience"] >= 0.7

    def test_summary_alias(self):
        mem = NPCMemory(npc_id="npc_a")
        mem.remember({"type": "test"}, tick=1)
        assert mem.summary(limit=5) == mem.top_memories(limit=5)

    def test_to_dict_from_dict_round_trip(self):
        mem = NPCMemory(npc_id="npc_a")
        mem.remember(_make_event(), tick=1)
        mem.remember(_make_event(event_type="help"), tick=2)
        data = mem.to_dict()
        restored = NPCMemory.from_dict(data)
        assert restored.npc_id == mem.npc_id
        assert len(restored.entries) == len(mem.entries)

    def test_from_dict_none(self):
        mem = NPCMemory.from_dict(None)
        assert mem.npc_id == ""
        assert len(mem.entries) == 0

    def test_from_dict_filters_non_dict_entries(self):
        data = {"npc_id": "npc_a", "entries": [{"type": "test", "tick": 1}, "bad_entry", 42]}
        mem = NPCMemory.from_dict(data)
        assert len(mem.entries) == 1

    def test_memory_id_format(self):
        mem = NPCMemory(npc_id="npc_a")
        mem.remember({"type": "attack", "target_id": "npc_b"}, tick=5, index=0)
        assert mem.entries[0]["memory_id"].startswith("mem:npc_a:5:0:attack:")

    def test_empty_event_defaults(self):
        mem = NPCMemory(npc_id="npc_a")
        mem.remember({}, tick=1)
        entry = mem.entries[0]
        assert entry["type"] == "unknown"
        assert entry["summary"] == "unknown"


# ===========================================================================
# BeliefModel tests
# ===========================================================================


class TestBeliefModel:
    def test_create_empty(self):
        bm = BeliefModel()
        assert len(bm.beliefs) == 0

    def test_update_belief_creates_target(self):
        bm = BeliefModel()
        bm.update_belief("player", "trust", 0.5)
        assert "player" in bm.beliefs
        assert bm.beliefs["player"]["trust"] == 0.5

    def test_update_belief_accumulates(self):
        bm = BeliefModel()
        bm.update_belief("player", "trust", 0.5)
        bm.update_belief("player", "trust", 0.3)
        assert abs(bm.beliefs["player"]["trust"] - 0.8) < 0.01

    def test_update_belief_clamps(self):
        bm = BeliefModel()
        bm.update_belief("player", "trust", 2.0)
        assert bm.beliefs["player"]["trust"] == 1.0
        bm.update_belief("player", "trust", -5.0)
        assert bm.beliefs["player"]["trust"] == -1.0

    def test_update_belief_invalid_key(self):
        bm = BeliefModel()
        result = bm.update_belief("player", "invalid_key", 0.5)
        assert result == 0.0

    def test_get_beliefs(self):
        bm = BeliefModel()
        bm.update_belief("player", "fear", 0.3)
        beliefs = bm.get_beliefs("player")
        assert beliefs["fear"] == 0.3
        assert beliefs["trust"] == 0.0

    def test_summarize_limits(self):
        bm = BeliefModel()
        for i in range(20):
            bm.update_belief(f"target_{i}", "trust", 0.1)
        summary = bm.summarize(limit=5)
        assert len(summary) == 5

    def test_update_from_event_player_help(self):
        bm = BeliefModel()
        event = _make_event(event_type="help", actor="player")
        ctx = _make_npc_context()
        bm.update_from_event(event, ctx)
        assert bm.beliefs["player"]["trust"] > 0
        assert bm.beliefs["player"]["respect"] > 0

    def test_update_from_event_player_attack(self):
        bm = BeliefModel()
        event = _make_event(event_type="attack", actor="player")
        ctx = _make_npc_context()
        bm.update_from_event(event, ctx)
        assert bm.beliefs["player"]["hostility"] > 0
        assert bm.beliefs["player"]["trust"] < 0

    def test_update_from_event_threaten(self):
        bm = BeliefModel()
        event = _make_event(event_type="threaten", actor="player")
        ctx = _make_npc_context()
        bm.update_from_event(event, ctx)
        assert bm.beliefs["player"]["fear"] > 0

    def test_update_from_event_negotiate(self):
        bm = BeliefModel()
        event = _make_event(event_type="negotiate", actor="player")
        ctx = _make_npc_context()
        bm.update_from_event(event, ctx)
        assert bm.beliefs["player"]["respect"] > 0

    def test_update_from_event_direct_target(self):
        bm = BeliefModel()
        event = _make_event(event_type="help", actor="player", target_id="npc_guard")
        ctx = _make_npc_context(npc_id="npc_guard")
        bm.update_from_event(event, ctx)
        # Should get both general help boost and direct target boost
        assert bm.beliefs["player"]["trust"] > 0.2

    def test_update_from_event_faction_alignment(self):
        bm = BeliefModel()
        event = _make_event(event_type="support", actor="player", faction_id="militia")
        ctx = _make_npc_context(faction_id="militia")
        bm.update_from_event(event, ctx)
        assert bm.beliefs["player"]["trust"] > 0.1

    def test_update_from_event_location_effect(self):
        bm = BeliefModel()
        event = _make_event(event_type="stabilize", actor="player", location_id="town")
        ctx = _make_npc_context(location_id="town")
        bm.update_from_event(event, ctx)
        assert bm.beliefs["player"]["respect"] > 0

    def test_to_dict_from_dict_round_trip(self):
        bm = BeliefModel()
        bm.update_belief("player", "trust", 0.5)
        bm.update_belief("npc_b", "fear", -0.3)
        data = bm.to_dict()
        restored = BeliefModel.from_dict(data)
        assert abs(restored.beliefs["player"]["trust"] - 0.5) < 0.01
        assert abs(restored.beliefs["npc_b"]["fear"] - (-0.3)) < 0.01

    def test_from_dict_none(self):
        bm = BeliefModel.from_dict(None)
        assert len(bm.beliefs) == 0

    def test_non_player_actor_ignored(self):
        bm = BeliefModel()
        event = _make_event(event_type="help", actor="npc_b")
        ctx = _make_npc_context()
        bm.update_from_event(event, ctx)
        assert "player" not in bm.beliefs


# ===========================================================================
# GoalEngine tests
# ===========================================================================


class TestGoalEngine:
    def test_create_empty(self):
        ge = GoalEngine()
        assert len(ge.goals) == 0

    def test_from_dict_empty(self):
        ge = GoalEngine.from_dict(None)
        assert len(ge.goals) == 0

    def test_generate_goals_observe_default(self):
        ge = GoalEngine()
        ctx = _make_npc_context()
        goals = ge.generate_goals(
            npc_context=ctx,
            simulation_state={},
            belief_summary={},
            memory_summary=[],
        )
        assert len(goals) >= 1
        types = [g["type"] for g in goals]
        assert "observe" in types

    def test_generate_goals_retaliate_on_hostility(self):
        ge = GoalEngine()
        ctx = _make_npc_context()
        beliefs = {"player": {"trust": 0.0, "fear": 0.0, "respect": 0.0, "hostility": 0.5}}
        goals = ge.generate_goals(
            npc_context=ctx,
            simulation_state={},
            belief_summary=beliefs,
            memory_summary=[],
        )
        types = [g["type"] for g in goals]
        assert "retaliate" in types

    def test_generate_goals_avoid_on_fear(self):
        ge = GoalEngine()
        ctx = _make_npc_context()
        beliefs = {"player": {"trust": 0.0, "fear": 0.5, "respect": 0.0, "hostility": 0.0}}
        goals = ge.generate_goals(
            npc_context=ctx,
            simulation_state={},
            belief_summary=beliefs,
            memory_summary=[],
        )
        types = [g["type"] for g in goals]
        assert "avoid_player" in types

    def test_generate_goals_approach_on_trust(self):
        ge = GoalEngine()
        ctx = _make_npc_context()
        beliefs = {"player": {"trust": 0.5, "fear": 0.0, "respect": 0.0, "hostility": 0.0}}
        goals = ge.generate_goals(
            npc_context=ctx,
            simulation_state={},
            belief_summary=beliefs,
            memory_summary=[],
        )
        types = [g["type"] for g in goals]
        assert "approach_player" in types

    def test_generate_goals_support_faction(self):
        ge = GoalEngine()
        ctx = _make_npc_context(faction_id="militia")
        goals = ge.generate_goals(
            npc_context=ctx,
            simulation_state={},
            belief_summary={},
            memory_summary=[],
        )
        types = [g["type"] for g in goals]
        assert "support_faction" in types

    def test_generate_goals_stabilize_location(self):
        ge = GoalEngine()
        ctx = _make_npc_context(location_id="town")
        state = {"locations": {"town": {"pressure": 3.0}}}
        goals = ge.generate_goals(
            npc_context=ctx,
            simulation_state=state,
            belief_summary={},
            memory_summary=[],
        )
        types = [g["type"] for g in goals]
        assert "stabilize_location" in types

    def test_generate_goals_investigate_memory(self):
        ge = GoalEngine()
        ctx = _make_npc_context()
        memory = [{"target_id": "some_entity", "type": "attack"}]
        goals = ge.generate_goals(
            npc_context=ctx,
            simulation_state={},
            belief_summary={},
            memory_summary=memory,
        )
        types = [g["type"] for g in goals]
        assert "investigate" in types

    def test_generate_goals_max_limit(self):
        ge = GoalEngine(max_goals=2)
        ctx = _make_npc_context(faction_id="militia", location_id="town")
        state = {"locations": {"town": {"pressure": 3.0}}}
        beliefs = {"player": {"trust": 0.0, "fear": 0.0, "respect": 0.0, "hostility": 0.5}}
        goals = ge.generate_goals(
            npc_context=ctx,
            simulation_state=state,
            belief_summary=beliefs,
            memory_summary=[],
        )
        assert len(goals) <= 2

    def test_merge_goals(self):
        ge = GoalEngine()
        ge.goals = [{"goal_id": "g1", "type": "observe", "priority": 0.3, "target_id": "player"}]
        generated = [{"goal_id": "g1", "type": "observe", "priority": 0.5, "target_id": "player"}]
        ge.merge_goals(generated)
        assert ge.goals[0]["priority"] == 0.5

    def test_top_goal(self):
        ge = GoalEngine()
        ge.goals = [
            {"goal_id": "g1", "priority": 0.3},
            {"goal_id": "g2", "priority": 0.9},
        ]
        top = ge.top_goal()
        assert top["goal_id"] == "g2"

    def test_top_goal_empty(self):
        ge = GoalEngine()
        assert ge.top_goal() is None

    def test_advance_from_event(self):
        ge = GoalEngine()
        ge.goals = [{"goal_id": "g1", "type": "stabilize", "target_id": "town", "priority": 0.8, "progress": 0.0}]
        ge.advance_from_event({"type": "stabilize", "target_id": "town"})
        assert ge.goals[0]["progress"] > 0

    def test_to_dict_from_dict_round_trip(self):
        ge = GoalEngine()
        ge.goals = [{"goal_id": "g1", "type": "observe", "target_id": "player", "priority": 0.35, "reason": "test", "status": "active", "progress": 0.0}]
        data = ge.to_dict()
        restored = GoalEngine.from_dict(data)
        assert len(restored.goals) == 1
        assert restored.goals[0]["goal_id"] == "g1"

    def test_dedup_goals(self):
        ge = GoalEngine()
        ctx = _make_npc_context()
        goals = ge.generate_goals(
            npc_context=ctx,
            simulation_state={},
            belief_summary={},
            memory_summary=[],
        )
        ids = [g["goal_id"] for g in goals]
        assert len(ids) == len(set(ids))


# ===========================================================================
# NPCDecision tests
# ===========================================================================


class TestNPCDecision:
    def test_create(self):
        d = NPCDecision(
            npc_id="npc_a", tick=1, intent="observe", action_type="observe",
            target_id="player", target_kind="actor", location_id="town",
            reason="watching", dialogue_hint="...", urgency=0.5,
        )
        assert d.npc_id == "npc_a"
        assert d.intent == "observe"

    def test_to_dict(self):
        d = NPCDecision.fallback("npc_a", 1, "town")
        data = d.to_dict()
        assert data["npc_id"] == "npc_a"
        assert data["intent"] == "wait"
        assert data["action_type"] == "wait"

    def test_from_dict(self):
        data = {"npc_id": "npc_a", "tick": 5, "intent": "observe", "action_type": "observe"}
        d = NPCDecision.from_dict(data)
        assert d.npc_id == "npc_a"
        assert d.tick == 5

    def test_from_dict_none(self):
        d = NPCDecision.from_dict(None)
        assert d.npc_id == ""
        assert d.intent == "wait"

    def test_fallback(self):
        d = NPCDecision.fallback("npc_a", 3, "forest")
        assert d.intent == "wait"
        assert d.action_type == "wait"
        assert d.location_id == "forest"
        assert d.urgency == 0.10

    def test_round_trip(self):
        d = NPCDecision.fallback("npc_a", 1, "town")
        restored = NPCDecision.from_dict(d.to_dict())
        assert restored.to_dict() == d.to_dict()


# ===========================================================================
# NPCDecisionValidator tests
# ===========================================================================


class TestNPCDecisionValidator:
    def test_valid_intent_passes(self):
        v = NPCDecisionValidator()
        data = {"intent": "observe", "action_type": "observe"}
        result = v.validate(data)
        assert result["intent"] == "observe"

    def test_invalid_intent_falls_back(self):
        v = NPCDecisionValidator()
        data = {"intent": "dance", "action_type": "wait"}
        result = v.validate(data)
        assert result["intent"] == "wait"

    def test_invalid_action_type_falls_back(self):
        v = NPCDecisionValidator()
        data = {"intent": "wait", "action_type": "fly"}
        result = v.validate(data)
        assert result["action_type"] == "wait"

    def test_normalizes_fields(self):
        v = NPCDecisionValidator()
        data = {"npc_id": 123, "tick": "5", "urgency": "0.7"}
        result = v.validate(data)
        assert isinstance(result["npc_id"], str)
        assert isinstance(result["tick"], int)
        assert isinstance(result["urgency"], float)

    def test_empty_input(self):
        v = NPCDecisionValidator()
        result = v.validate({})
        assert result["intent"] == "wait"
        assert result["npc_id"] == ""

    def test_none_input(self):
        v = NPCDecisionValidator()
        result = v.validate(None)
        assert result["intent"] == "wait"

    def test_all_valid_intents(self):
        v = NPCDecisionValidator()
        for intent in ["observe", "support", "confront", "avoid", "investigate", "negotiate", "stabilize", "retaliate", "wait"]:
            result = v.validate({"intent": intent, "action_type": intent})
            assert result["intent"] == intent
            assert result["action_type"] == intent


# ===========================================================================
# NPCPromptBuilder tests
# ===========================================================================


class TestNPCPromptBuilder:
    def test_build_prompt(self):
        pb = NPCPromptBuilder()
        result = pb.build_decision_prompt(
            npc_context={"name": "Guard", "npc_id": "npc_guard"},
            belief_summary={"player": {"trust": 0.5}},
            memory_summary=[{"type": "attack"}],
            goals=[{"type": "observe"}],
            simulation_state={"tick": 1},
        )
        assert "Guard" in result
        assert "Beliefs" in result

    def test_build_prompt_empty(self):
        pb = NPCPromptBuilder()
        result = pb.build_decision_prompt(
            npc_context={},
            belief_summary={},
            memory_summary=[],
            goals=[],
            simulation_state={},
        )
        assert "Unknown NPC" in result


# ===========================================================================
# NPCResponseParser tests
# ===========================================================================


class TestNPCResponseParser:
    def test_parse_dict(self):
        rp = NPCResponseParser()
        result = rp.parse_decision({"intent": "observe"})
        assert result["intent"] == "observe"

    def test_parse_non_dict(self):
        rp = NPCResponseParser()
        result = rp.parse_decision("not a dict")
        assert result == {}

    def test_parse_none(self):
        rp = NPCResponseParser()
        result = rp.parse_decision(None)
        assert result == {}


# ===========================================================================
# NPCMind tests
# ===========================================================================


class TestNPCMind:
    def test_create(self):
        mind = NPCMind(npc_id="npc_guard")
        assert mind.npc_id == "npc_guard"
        assert len(mind.memory.entries) == 0

    def test_decide_no_goals(self):
        mind = NPCMind(npc_id="npc_guard")
        ctx = _make_npc_context()
        decision = mind.decide(simulation_state={}, npc_context=ctx, tick=1)
        assert decision.intent == "wait"
        assert decision.action_type == "wait"

    def test_decide_with_goals(self):
        mind = NPCMind(npc_id="npc_guard")
        ctx = _make_npc_context(faction_id="militia")
        mind.refresh_goals(simulation_state={}, npc_context=ctx)
        decision = mind.decide(simulation_state={}, npc_context=ctx, tick=1)
        assert decision.intent in {"observe", "support", "wait", "negotiate", "stabilize"}

    def test_observe_events_remembers(self):
        mind = NPCMind(npc_id="npc_guard")
        ctx = _make_npc_context()
        events = [_make_event(event_type="help", actor="player")]
        mind.observe_events(events, tick=1, npc_context=ctx)
        assert len(mind.memory.entries) > 0

    def test_observe_events_updates_beliefs(self):
        mind = NPCMind(npc_id="npc_guard")
        ctx = _make_npc_context()
        events = [_make_event(event_type="attack", actor="player")]
        mind.observe_events(events, tick=1, npc_context=ctx)
        assert mind.beliefs.beliefs.get("player", {}).get("hostility", 0) > 0

    def test_observe_events_filters_irrelevant(self):
        mind = NPCMind(npc_id="npc_guard")
        ctx = _make_npc_context(location_id="town")
        irrelevant = {"type": "trade", "actor": "npc_merchant", "location_id": "forest"}
        mind.observe_events([irrelevant], tick=1, npc_context=ctx)
        assert len(mind.memory.entries) == 0

    def test_refresh_goals_generates(self):
        mind = NPCMind(npc_id="npc_guard")
        ctx = _make_npc_context(faction_id="militia")
        mind.refresh_goals(simulation_state={}, npc_context=ctx)
        assert len(mind.goal_engine.goals) > 0

    def test_decide_after_hostility(self):
        mind = NPCMind(npc_id="npc_guard")
        ctx = _make_npc_context()
        for _ in range(5):
            mind.beliefs.update_belief("player", "hostility", 0.2)
        mind.refresh_goals(simulation_state={}, npc_context=ctx)
        decision = mind.decide(simulation_state={}, npc_context=ctx, tick=5)
        assert decision.intent in {"retaliate", "support", "observe", "wait"}

    def test_to_dict_from_dict_round_trip(self):
        mind = NPCMind(npc_id="npc_guard")
        ctx = _make_npc_context()
        mind.observe_events([_make_event()], tick=1, npc_context=ctx)
        mind.refresh_goals(simulation_state={}, npc_context=ctx)
        mind.decide(simulation_state={}, npc_context=ctx, tick=1)

        data = mind.to_dict()
        restored = NPCMind.from_dict(data)
        assert restored.npc_id == "npc_guard"
        assert len(restored.memory.entries) == len(mind.memory.entries)
        assert restored.to_dict() == data

    def test_from_dict_none(self):
        mind = NPCMind.from_dict(None)
        assert mind.npc_id == ""

    def test_apply_player_action_feedback(self):
        mind = NPCMind(npc_id="npc_guard")
        ctx = _make_npc_context()
        action_event = _make_event(event_type="help", actor="player")
        mind.apply_player_action_feedback(action_event, npc_context=ctx, tick=1)
        assert len(mind.memory.entries) == 1
        assert mind.beliefs.beliefs.get("player", {}).get("trust", 0) > 0

    def test_build_narrator_context(self):
        mind = NPCMind(npc_id="npc_guard")
        ctx = mind.build_narrator_context()
        assert "memory_summary" in ctx
        assert "belief_summary" in ctx
        assert "active_goals" in ctx
        assert "last_decision" in ctx

    def test_last_decision_stored(self):
        mind = NPCMind(npc_id="npc_guard")
        ctx = _make_npc_context()
        mind.refresh_goals(simulation_state={}, npc_context=ctx)
        decision = mind.decide(simulation_state={}, npc_context=ctx, tick=1)
        assert mind.last_decision == decision.to_dict()

    def test_last_seen_tick_updated(self):
        mind = NPCMind(npc_id="npc_guard")
        ctx = _make_npc_context()
        mind.observe_events([_make_event()], tick=42, npc_context=ctx)
        assert mind.last_seen_tick == 42

    def test_event_relevance_player_always_relevant(self):
        mind = NPCMind(npc_id="npc_guard")
        ctx = _make_npc_context()
        event = {"actor": "player", "type": "idle"}
        assert mind._event_is_relevant(event, ctx) is True

    def test_event_relevance_target_self(self):
        mind = NPCMind(npc_id="npc_guard")
        ctx = _make_npc_context(npc_id="npc_guard")
        event = {"actor": "npc_b", "target_id": "npc_guard", "type": "attack"}
        assert mind._event_is_relevant(event, ctx) is True

    def test_event_relevance_same_faction(self):
        mind = NPCMind(npc_id="npc_guard")
        ctx = _make_npc_context(faction_id="militia")
        event = {"actor": "npc_b", "faction_id": "militia", "type": "support"}
        assert mind._event_is_relevant(event, ctx) is True

    def test_event_relevance_same_location(self):
        mind = NPCMind(npc_id="npc_guard")
        ctx = _make_npc_context(location_id="town")
        event = {"actor": "npc_b", "location_id": "town", "type": "idle"}
        assert mind._event_is_relevant(event, ctx) is True

    def test_event_relevance_affected_npc_ids(self):
        mind = NPCMind(npc_id="npc_guard")
        ctx = _make_npc_context(npc_id="npc_guard")
        event = {"actor": "npc_b", "affected_npc_ids": ["npc_guard"], "type": "attack"}
        assert mind._event_is_relevant(event, ctx) is True

    def test_event_relevance_unrelated(self):
        mind = NPCMind(npc_id="npc_guard")
        ctx = _make_npc_context(npc_id="npc_guard", faction_id="militia", location_id="town")
        event = {"actor": "npc_x", "faction_id": "bandits", "location_id": "forest", "type": "idle"}
        assert mind._event_is_relevant(event, ctx) is False


# ===========================================================================
# Integration helper tests (world_simulation.py helpers)
# ===========================================================================


class TestWorldSimulationHelpers:
    """Test the Phase 6 helpers added to world_simulation.py."""

    def test_build_npc_index_from_npc_seeds(self):
        from app.rpg.creator.world_simulation import _build_npc_index
        setup = {"npc_seeds": [
            {"npc_id": "npc_a", "name": "Guard A", "role": "guard", "faction_id": "f1", "location_id": "town"},
            {"npc_id": "npc_b", "name": "Merchant", "role": "merchant"},
        ]}
        idx = _build_npc_index(setup)
        assert "npc_a" in idx
        assert "npc_b" in idx
        assert idx["npc_a"]["name"] == "Guard A"

    def test_build_npc_index_from_npcs(self):
        from app.rpg.creator.world_simulation import _build_npc_index
        setup = {"npcs": [{"id": "npc_c", "name": "Scout"}]}
        idx = _build_npc_index(setup)
        assert "npc_c" in idx

    def test_build_npc_index_empty(self):
        from app.rpg.creator.world_simulation import _build_npc_index
        assert _build_npc_index({}) == {}
        assert _build_npc_index(None) == {}

    def test_load_npc_minds_fresh(self):
        from app.rpg.creator.world_simulation import _load_npc_minds
        npc_index = {"npc_a": {"npc_id": "npc_a"}}
        minds = _load_npc_minds({}, npc_index)
        assert "npc_a" in minds
        assert isinstance(minds["npc_a"], NPCMind)

    def test_load_npc_minds_from_state(self):
        from app.rpg.creator.world_simulation import _load_npc_minds
        mind = NPCMind(npc_id="npc_a")
        mind.beliefs.update_belief("player", "trust", 0.5)
        state = {"npc_minds": {"npc_a": mind.to_dict()}}
        npc_index = {"npc_a": {"npc_id": "npc_a"}}
        minds = _load_npc_minds(state, npc_index)
        assert abs(minds["npc_a"].beliefs.beliefs["player"]["trust"] - 0.5) < 0.01

    def test_decision_to_event_wait_returns_none(self):
        from app.rpg.creator.world_simulation import _decision_to_event
        dec = {"npc_id": "npc_a", "action_type": "wait", "urgency": 0.1}
        assert _decision_to_event(dec, {}, 1) is None

    def test_decision_to_event_active(self):
        from app.rpg.creator.world_simulation import _decision_to_event
        dec = {
            "npc_id": "npc_a", "action_type": "observe",
            "target_id": "player", "target_kind": "actor",
            "location_id": "town", "urgency": 0.5, "reason": "watching",
        }
        ctx = {"faction_id": "militia"}
        event = _decision_to_event(dec, ctx, 5)
        assert event is not None
        assert event["type"] == "observe"
        assert event["actor"] == "npc_a"
        assert event["tick"] == 5


# ===========================================================================
# Player action helper tests
# ===========================================================================


class TestPlayerActionHelpers:
    def test_infer_affected_npc_ids_by_location(self):
        from app.rpg.creator.world_player_actions import _infer_affected_npc_ids
        state = {"npc_index": {
            "npc_a": {"location_id": "town"},
            "npc_b": {"location_id": "forest"},
        }}
        affected = _infer_affected_npc_ids(state, location_id="town")
        assert "npc_a" in affected
        assert "npc_b" not in affected

    def test_infer_affected_npc_ids_by_faction(self):
        from app.rpg.creator.world_player_actions import _infer_affected_npc_ids
        state = {"npc_index": {
            "npc_a": {"faction_id": "militia", "location_id": ""},
            "npc_b": {"faction_id": "bandits", "location_id": ""},
        }}
        affected = _infer_affected_npc_ids(state, faction_id="militia")
        assert "npc_a" in affected
        assert "npc_b" not in affected

    def test_infer_affected_npc_ids_by_target(self):
        from app.rpg.creator.world_player_actions import _infer_affected_npc_ids
        state = {"npc_index": {"npc_a": {}, "npc_b": {}}}
        affected = _infer_affected_npc_ids(state, target_id="npc_a")
        assert "npc_a" in affected

    def test_infer_affected_npc_ids_empty(self):
        from app.rpg.creator.world_player_actions import _infer_affected_npc_ids
        assert _infer_affected_npc_ids({}) == []
        assert _infer_affected_npc_ids(None) == []


# ===========================================================================
# Scene generator helper tests
# ===========================================================================


class TestSceneGeneratorHelpers:
    def test_collect_scene_actors_by_location(self):
        from app.rpg.creator.world_scene_generator import _collect_scene_actors
        state = {
            "npc_index": {
                "npc_a": {"npc_id": "npc_a", "name": "Guard", "role": "guard", "location_id": "town", "faction_id": ""},
                "npc_b": {"npc_id": "npc_b", "name": "Scout", "role": "scout", "location_id": "forest", "faction_id": ""},
            },
            "npc_minds": {},
        }
        actors = _collect_scene_actors("town", state)
        assert len(actors) == 1
        assert actors[0]["id"] == "npc_a"

    def test_collect_scene_actors_by_faction(self):
        from app.rpg.creator.world_scene_generator import _collect_scene_actors
        state = {
            "npc_index": {
                "npc_a": {"npc_id": "npc_a", "name": "Guard", "role": "guard", "location_id": "", "faction_id": "militia"},
            },
            "npc_minds": {},
        }
        actors = _collect_scene_actors("militia", state)
        assert len(actors) == 1

    def test_collect_scene_actors_with_mind_context(self):
        from app.rpg.creator.world_scene_generator import _collect_scene_actors
        state = {
            "npc_index": {
                "npc_a": {"npc_id": "npc_a", "name": "Guard", "role": "guard", "location_id": "town", "faction_id": ""},
            },
            "npc_minds": {
                "npc_a": {"last_decision": {"intent": "observe"}},
            },
        }
        actors = _collect_scene_actors("town", state)
        assert "mind_context" in actors[0]

    def test_collect_scene_actors_empty(self):
        from app.rpg.creator.world_scene_generator import _collect_scene_actors
        assert _collect_scene_actors("town", {}) == []

    def test_collect_scene_actors_max_limit(self):
        from app.rpg.creator.world_scene_generator import _collect_scene_actors
        npc_index = {f"npc_{i}": {"npc_id": f"npc_{i}", "name": f"NPC {i}", "role": "", "location_id": "town", "faction_id": ""} for i in range(10)}
        state = {"npc_index": npc_index, "npc_minds": {}}
        actors = _collect_scene_actors("town", state, max_actors=3)
        assert len(actors) == 3


# ===========================================================================
# Narrator helper tests
# ===========================================================================


class TestNarratorHelpers:
    def test_attach_npc_mind_context(self):
        from app.rpg.ai.world_scene_narrator import _attach_npc_mind_context
        actor = {"id": "npc_a", "name": "Guard"}
        state = {
            "npc_minds": {
                "npc_a": {
                    "memory": {"entries": [{"type": "attack"}]},
                    "beliefs": {"beliefs": {"player": {"trust": 0.5}}},
                    "goals": {"goals": [{"type": "observe"}]},
                    "last_decision": {"intent": "observe"},
                },
            },
        }
        enriched = _attach_npc_mind_context(actor, state)
        assert len(enriched["memory_summary"]) == 1
        assert "player" in enriched["belief_summary"]
        assert len(enriched["active_goals"]) == 1
        assert enriched["last_decision"]["intent"] == "observe"

    def test_attach_npc_mind_context_missing_mind(self):
        from app.rpg.ai.world_scene_narrator import _attach_npc_mind_context
        actor = {"id": "npc_a", "name": "Guard"}
        enriched = _attach_npc_mind_context(actor, {})
        assert enriched["memory_summary"] == []
        assert enriched["belief_summary"] == {}

    def test_attach_npc_mind_context_none(self):
        from app.rpg.ai.world_scene_narrator import _attach_npc_mind_context
        enriched = _attach_npc_mind_context(None, None)
        assert enriched["memory_summary"] == []


# ===========================================================================
# Compatibility wrapper tests
# ===========================================================================


class TestCompatibilityWrappers:
    def test_memory_wrapper(self):
        from app.rpg.ai.llm_mind.memory import NPCMemory as Mem
        assert Mem is NPCMemory

    def test_decision_wrapper(self):
        from app.rpg.ai.llm_mind.decision import NPCDecision as Dec
        assert Dec is NPCDecision

    def test_prompt_builder_wrapper(self):
        from app.rpg.ai.llm_mind.prompt_builder import NPCPromptBuilder as PB
        assert PB is NPCPromptBuilder

    def test_response_parser_wrapper(self):
        from app.rpg.ai.llm_mind.response_parser import NPCResponseParser as RP
        assert RP is NPCResponseParser

    def test_validator_wrapper(self):
        from app.rpg.ai.llm_mind.validator import NPCDecisionValidator as V
        assert V is NPCDecisionValidator

    def test_init_exports(self):
        from app.rpg.ai.llm_mind import (
            BeliefModel, NPCMemory, GoalEngine, NPCDecision,
            NPCPromptBuilder, NPCResponseParser, NPCDecisionValidator, NPCMind,
        )
        assert all([
            BeliefModel, NPCMemory, GoalEngine, NPCDecision,
            NPCPromptBuilder, NPCResponseParser, NPCDecisionValidator, NPCMind,
        ])
