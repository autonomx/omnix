"""Phase 6 — Deterministic NPC Architecture: Regression Tests.

Protects architecture invariants:
- Determinism: identical inputs produce identical outputs
- Serialization round-trips preserve all fields
- Belief model clamping never exceeds bounds
- Goal deduplication is stable
- NPC Mind state is self-consistent after operations
- Decision validator always produces valid output

Run:
    cd src && PYTHONPATH="." python3 -m pytest tests/regression/test_phase6_deterministic_npc_regression.py -v --noconftest
"""

from __future__ import annotations

import copy
import os
import sys
import types

# ---------------------------------------------------------------------------
# Bootstrap: avoid triggering Flask / heavy AI module imports
# ---------------------------------------------------------------------------

_SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "..")

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
from app.rpg.ai.llm_mind.npc_decision_validator import NPCDecisionValidator, _ALLOWED_INTENTS, _ALLOWED_ACTIONS
from app.rpg.ai.llm_mind.npc_mind import NPCMind


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(event_type="attack", actor="player", target_id="npc_guard", salience=0.8):
    return {
        "type": event_type,
        "actor": actor,
        "target_id": target_id,
        "target_kind": "npc",
        "location_id": "town",
        "faction_id": "militia",
        "salience": salience,
        "summary": f"{actor} does {event_type}",
    }


def _make_npc_context(npc_id="npc_guard", faction_id="militia", location_id="town"):
    return {
        "npc_id": npc_id,
        "name": npc_id.replace("npc_", "").capitalize(),
        "role": "guard",
        "faction_id": faction_id,
        "location_id": location_id,
    }


# ===========================================================================
# Determinism Tests
# ===========================================================================


class TestDeterminism:
    """Identical inputs must produce identical outputs."""

    def test_memory_deterministic(self):
        """Same events in same order produce same memory state."""
        events = [
            _make_event("help", "player", "npc_a", 0.7),
            _make_event("attack", "player", "npc_b", 0.9),
            _make_event("trade", "npc_c", "player", 0.3),
        ]

        mem1 = NPCMemory(npc_id="npc_guard")
        mem2 = NPCMemory(npc_id="npc_guard")

        for i, e in enumerate(events):
            mem1.remember(e, tick=i + 1, index=0)
            mem2.remember(e, tick=i + 1, index=0)

        assert mem1.to_dict() == mem2.to_dict()

    def test_belief_model_deterministic(self):
        """Same events produce same belief state."""
        events = [
            _make_event("help"),
            _make_event("attack"),
            _make_event("negotiate"),
        ]
        ctx = _make_npc_context()

        bm1 = BeliefModel()
        bm2 = BeliefModel()

        for e in events:
            bm1.update_from_event(e, ctx)
            bm2.update_from_event(e, ctx)

        assert bm1.to_dict() == bm2.to_dict()

    def test_goal_generation_deterministic(self):
        """Same context produces same goals."""
        ctx = _make_npc_context(faction_id="militia", location_id="town")
        beliefs = {"player": {"trust": 0.2, "fear": 0.1, "respect": 0.3, "hostility": 0.0}}
        state = {"locations": {"town": {"pressure": 3.0}}}

        ge1 = GoalEngine()
        ge2 = GoalEngine()

        goals1 = ge1.generate_goals(ctx, state, beliefs, [])
        goals2 = ge2.generate_goals(ctx, state, beliefs, [])

        assert goals1 == goals2

    def test_full_mind_deterministic(self):
        """Full NPCMind cycle is deterministic."""
        events = [_make_event("help"), _make_event("attack")]
        ctx = _make_npc_context()

        mind1 = NPCMind(npc_id="npc_guard")
        mind2 = NPCMind(npc_id="npc_guard")

        for tick, e in enumerate(events, 1):
            mind1.observe_events([e], tick=tick, npc_context=ctx)
            mind2.observe_events([e], tick=tick, npc_context=ctx)

        mind1.refresh_goals(simulation_state={}, npc_context=ctx)
        mind2.refresh_goals(simulation_state={}, npc_context=ctx)

        d1 = mind1.decide(simulation_state={}, npc_context=ctx, tick=3)
        d2 = mind2.decide(simulation_state={}, npc_context=ctx, tick=3)

        assert d1.to_dict() == d2.to_dict()
        assert mind1.to_dict() == mind2.to_dict()

    def test_decision_deterministic_across_runs(self):
        """Run the same cycle 5 times and verify all produce identical output."""
        results = []
        for _ in range(5):
            mind = NPCMind(npc_id="npc_guard")
            ctx = _make_npc_context()
            mind.observe_events([_make_event("help")], tick=1, npc_context=ctx)
            mind.refresh_goals(simulation_state={}, npc_context=ctx)
            d = mind.decide(simulation_state={}, npc_context=ctx, tick=1)
            results.append(d.to_dict())

        for r in results[1:]:
            assert r == results[0]


# ===========================================================================
# Serialization Round-Trip Tests
# ===========================================================================


class TestSerializationRoundTrip:
    """Serialization must preserve all fields exactly."""

    def test_npc_memory_round_trip(self):
        mem = NPCMemory(npc_id="npc_guard")
        mem.remember(_make_event(), tick=1)
        mem.remember(_make_event("help"), tick=2)

        data = mem.to_dict()
        restored = NPCMemory.from_dict(data)
        assert restored.to_dict() == data

    def test_belief_model_round_trip(self):
        bm = BeliefModel()
        bm.update_belief("player", "trust", 0.7)
        bm.update_belief("player", "fear", -0.3)
        bm.update_belief("npc_b", "hostility", 0.5)

        data = bm.to_dict()
        restored = BeliefModel.from_dict(data)
        assert restored.to_dict() == data

    def test_goal_engine_round_trip(self):
        ge = GoalEngine()
        ge.goals = [{
            "goal_id": "g1",
            "type": "observe",
            "target_id": "player",
            "priority": 0.35,
            "reason": "watching",
            "status": "active",
            "progress": 0.1,
        }]

        data = ge.to_dict()
        restored = GoalEngine.from_dict(data)
        assert restored.to_dict() == data

    def test_npc_decision_round_trip(self):
        d = NPCDecision(
            npc_id="npc_guard", tick=5, intent="observe",
            action_type="observe", target_id="player",
            target_kind="actor", location_id="town",
            reason="watching", dialogue_hint="...", urgency=0.5,
        )
        data = d.to_dict()
        restored = NPCDecision.from_dict(data)
        assert restored.to_dict() == data

    def test_npc_mind_full_round_trip(self):
        mind = NPCMind(npc_id="npc_guard")
        ctx = _make_npc_context()

        mind.observe_events([_make_event("help"), _make_event("attack")], tick=1, npc_context=ctx)
        mind.refresh_goals(simulation_state={}, npc_context=ctx)
        mind.decide(simulation_state={}, npc_context=ctx, tick=1)

        data = mind.to_dict()
        restored = NPCMind.from_dict(data)
        assert restored.to_dict() == data

    def test_double_round_trip(self):
        """Serialize → deserialize → serialize → deserialize must be stable."""
        mind = NPCMind(npc_id="npc_guard")
        ctx = _make_npc_context()
        mind.observe_events([_make_event()], tick=1, npc_context=ctx)
        mind.refresh_goals(simulation_state={}, npc_context=ctx)
        mind.decide(simulation_state={}, npc_context=ctx, tick=1)

        data1 = mind.to_dict()
        mind2 = NPCMind.from_dict(data1)
        data2 = mind2.to_dict()
        mind3 = NPCMind.from_dict(data2)
        data3 = mind3.to_dict()

        assert data1 == data2 == data3


# ===========================================================================
# Boundary / Invariant Tests
# ===========================================================================


class TestBoundaryInvariants:
    """Protect clamping, limits, and structural invariants."""

    def test_belief_values_always_clamped(self):
        """Beliefs must always stay in [-1.0, 1.0]."""
        bm = BeliefModel()
        for _ in range(100):
            bm.update_belief("player", "trust", 0.5)
        assert bm.beliefs["player"]["trust"] <= 1.0

        for _ in range(200):
            bm.update_belief("player", "trust", -0.5)
        assert bm.beliefs["player"]["trust"] >= -1.0

    def test_belief_all_keys_present(self):
        """All four belief keys must always be present."""
        bm = BeliefModel()
        bm.update_belief("player", "trust", 0.1)
        beliefs = bm.get_beliefs("player")
        assert set(beliefs.keys()) == {"trust", "fear", "respect", "hostility"}

    def test_memory_never_exceeds_max(self):
        """Memory entries must never exceed max_entries."""
        mem = NPCMemory(npc_id="npc_a", max_entries=5)
        for i in range(100):
            mem.remember({"type": f"event_{i}"}, tick=i)
        assert len(mem.entries) <= 5

    def test_goals_never_exceed_max(self):
        """Goals must never exceed max_goals."""
        ge = GoalEngine(max_goals=3)
        ctx = _make_npc_context(faction_id="f1", location_id="town")
        state = {"locations": {"town": {"pressure": 5.0}}}
        beliefs = {"player": {"trust": 0.0, "fear": 0.0, "respect": 0.0, "hostility": 0.8}}
        goals = ge.generate_goals(ctx, state, beliefs, [{"target_id": "x", "type": "attack"}])
        assert len(goals) <= 3

    def test_goal_ids_are_unique_after_merge(self):
        """After merge, all goal IDs must be unique."""
        ge = GoalEngine()
        ge.goals = [
            {"goal_id": "g1", "type": "a", "priority": 0.5},
            {"goal_id": "g2", "type": "b", "priority": 0.3},
        ]
        ge.merge_goals([
            {"goal_id": "g1", "type": "a", "priority": 0.8},
            {"goal_id": "g3", "type": "c", "priority": 0.6},
        ])
        ids = [g["goal_id"] for g in ge.goals]
        assert len(ids) == len(set(ids))

    def test_validator_always_produces_valid_output(self):
        """Validator output must always have valid intents and action types."""
        v = NPCDecisionValidator()
        # Random garbage input
        garbage_inputs = [
            {"intent": "fly", "action_type": "dance"},
            {"intent": None, "action_type": None},
            {"intent": 123, "action_type": []},
            {},
            None,
        ]
        for inp in garbage_inputs:
            result = v.validate(inp)
            assert result["intent"] in _ALLOWED_INTENTS
            assert result["action_type"] in _ALLOWED_ACTIONS
            assert isinstance(result["npc_id"], str)
            assert isinstance(result["tick"], int)
            assert isinstance(result["urgency"], float)

    def test_decision_fallback_is_valid(self):
        """Fallback decision must have valid intent and action_type."""
        d = NPCDecision.fallback("npc_a", 1, "town")
        v = NPCDecisionValidator()
        validated = v.validate(d.to_dict())
        assert validated["intent"] in _ALLOWED_INTENTS
        assert validated["action_type"] in _ALLOWED_ACTIONS

    def test_npc_mind_state_consistency(self):
        """After any operation, NPCMind state must remain self-consistent."""
        mind = NPCMind(npc_id="npc_guard")
        ctx = _make_npc_context()

        # Observe → state must be valid
        mind.observe_events([_make_event()], tick=1, npc_context=ctx)
        data = mind.to_dict()
        assert data["npc_id"] == "npc_guard"
        assert isinstance(data["memory"], dict)
        assert isinstance(data["beliefs"], dict)
        assert isinstance(data["goals"], dict)

        # Refresh → still valid
        mind.refresh_goals(simulation_state={}, npc_context=ctx)
        data = mind.to_dict()
        assert len(data["goals"]["goals"]) <= GoalEngine().max_goals

        # Decide → still valid
        mind.decide(simulation_state={}, npc_context=ctx, tick=1)
        data = mind.to_dict()
        assert isinstance(data["last_decision"], dict)
        if data["last_decision"]:
            assert data["last_decision"].get("intent") in _ALLOWED_INTENTS | {"wait"}

    def test_empty_events_no_crash(self):
        """Passing empty/None events must not crash."""
        mind = NPCMind(npc_id="npc_guard")
        ctx = _make_npc_context()
        mind.observe_events([], tick=1, npc_context=ctx)
        mind.observe_events(None, tick=2, npc_context=ctx)
        assert mind.last_seen_tick == 2

    def test_none_context_no_crash(self):
        """Passing None as npc_context must not crash."""
        mind = NPCMind(npc_id="npc_guard")
        mind.observe_events([_make_event()], tick=1, npc_context=None)
        mind.refresh_goals(simulation_state=None, npc_context=None)
        decision = mind.decide(simulation_state=None, npc_context=None, tick=1)
        assert decision.npc_id == "npc_guard"

    def test_deep_copy_isolation(self):
        """Modifying returned dicts must not affect internal state."""
        mind = NPCMind(npc_id="npc_guard")
        ctx = _make_npc_context()
        mind.observe_events([_make_event()], tick=1, npc_context=ctx)
        mind.refresh_goals(simulation_state={}, npc_context=ctx)

        data = mind.to_dict()
        original = copy.deepcopy(data)

        # Mutate the returned dict
        data["npc_id"] = "HACKED"
        data["memory"]["entries"].clear()

        # Internal state should be unchanged
        assert mind.npc_id == "npc_guard"
        assert len(mind.memory.entries) > 0

    def test_salience_always_clamped(self):
        """Salience values must always be in [0.0, 1.0]."""
        mem = NPCMemory(npc_id="npc_a")
        mem.remember({"type": "test", "salience": 5.0}, tick=1)
        assert mem.entries[0]["salience"] <= 1.0

        mem.remember({"type": "test", "salience": -1.0}, tick=2)
        for entry in mem.entries:
            assert 0.0 <= entry["salience"] <= 1.0
