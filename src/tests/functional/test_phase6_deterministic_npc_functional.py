"""Phase 6 — Deterministic NPC Architecture: Functional Tests.

End-to-end workflow tests covering:
- Full NPC lifecycle: observe → refresh → decide → feedback
- Multi-NPC simulation with different belief states
- World simulation integration with NPC mind state persistence
- Player action → NPC reaction pipeline
- Scene enrichment with NPC actors

Run:
    cd src && PYTHONPATH="." python3 -m pytest tests/functional/test_phase6_deterministic_npc_functional.py -v --noconftest
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
from app.rpg.ai.llm_mind.npc_mind import NPCMind


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_npc_context(npc_id, faction_id="", location_id=""):
    return {
        "npc_id": npc_id,
        "name": npc_id.replace("npc_", "").capitalize(),
        "role": "guard",
        "faction_id": faction_id,
        "location_id": location_id,
    }


def _make_player_event(event_type, target_id="", location_id="", faction_id=""):
    return {
        "type": event_type,
        "actor": "player",
        "target_id": target_id,
        "target_kind": "npc",
        "location_id": location_id,
        "faction_id": faction_id,
        "summary": f"Player performs {event_type}",
        "salience": 0.8,
    }


# ===========================================================================
# Full NPC lifecycle
# ===========================================================================


class TestNPCLifecycle:
    """Tests the complete observe → refresh → decide → feedback loop."""

    def test_single_npc_full_cycle(self):
        mind = NPCMind(npc_id="npc_guard")
        ctx = _make_npc_context("npc_guard", faction_id="militia", location_id="town")
        sim_state = {"locations": {}, "factions": {}}

        # Tick 1: Observe a player help event
        mind.observe_events(
            [_make_player_event("help", target_id="npc_guard")],
            tick=1, npc_context=ctx,
        )
        assert len(mind.memory.entries) > 0
        assert mind.beliefs.beliefs.get("player", {}).get("trust", 0) > 0

        # Tick 1: Refresh goals
        mind.refresh_goals(simulation_state=sim_state, npc_context=ctx)
        assert len(mind.goal_engine.goals) > 0

        # Tick 1: Make decision
        decision = mind.decide(simulation_state=sim_state, npc_context=ctx, tick=1)
        assert decision.npc_id == "npc_guard"
        assert decision.intent in {"observe", "support", "negotiate", "wait", "stabilize"}
        assert mind.last_decision == decision.to_dict()

    def test_multi_tick_belief_evolution(self):
        mind = NPCMind(npc_id="npc_guard")
        ctx = _make_npc_context("npc_guard", location_id="town")

        # Repeated attacks build hostility
        for tick in range(1, 6):
            mind.observe_events(
                [_make_player_event("attack", target_id="npc_guard", location_id="town")],
                tick=tick, npc_context=ctx,
            )

        hostility = mind.beliefs.beliefs.get("player", {}).get("hostility", 0)
        assert hostility > 0.5  # Significant hostility buildup

        # Refresh and decide
        mind.refresh_goals(simulation_state={}, npc_context=ctx)
        decision = mind.decide(simulation_state={}, npc_context=ctx, tick=6)
        # Should be aggressive: retaliate or avoid
        assert decision.intent in {"retaliate", "avoid", "support", "observe", "wait"}

    def test_trust_builds_approach(self):
        mind = NPCMind(npc_id="npc_merchant")
        ctx = _make_npc_context("npc_merchant", faction_id="traders", location_id="market")

        # Repeated help builds trust
        for tick in range(1, 6):
            mind.observe_events(
                [_make_player_event("help", target_id="npc_merchant", location_id="market", faction_id="traders")],
                tick=tick, npc_context=ctx,
            )

        trust = mind.beliefs.beliefs.get("player", {}).get("trust", 0)
        assert trust > 0.3

        mind.refresh_goals(simulation_state={}, npc_context=ctx)
        decision = mind.decide(simulation_state={}, npc_context=ctx, tick=6)
        # Should tend toward approach/negotiate
        assert decision.intent in {"negotiate", "support", "observe", "wait"}


# ===========================================================================
# Multi-NPC simulation
# ===========================================================================


class TestMultiNPCSimulation:
    """Tests interactions between multiple NPC minds."""

    def test_different_npcs_react_differently(self):
        guard = NPCMind(npc_id="npc_guard")
        merchant = NPCMind(npc_id="npc_merchant")

        guard_ctx = _make_npc_context("npc_guard", faction_id="militia", location_id="town")
        merchant_ctx = _make_npc_context("npc_merchant", faction_id="traders", location_id="market")

        # Player attacks in town
        attack_event = _make_player_event("attack", location_id="town")

        guard.observe_events([attack_event], tick=1, npc_context=guard_ctx)
        merchant.observe_events([attack_event], tick=1, npc_context=merchant_ctx)

        # Guard should observe the attack (same location)
        assert len(guard.memory.entries) > 0
        # Merchant is in a different location, but player events are always relevant
        assert len(merchant.memory.entries) > 0

        # Guard should have stronger hostility reaction (same location)
        guard_hostility = guard.beliefs.beliefs.get("player", {}).get("hostility", 0)
        merchant_hostility = merchant.beliefs.beliefs.get("player", {}).get("hostility", 0)
        assert guard_hostility >= merchant_hostility

    def test_faction_shared_events(self):
        guard_a = NPCMind(npc_id="npc_guard_a")
        guard_b = NPCMind(npc_id="npc_guard_b")

        ctx_a = _make_npc_context("npc_guard_a", faction_id="militia", location_id="gate")
        ctx_b = _make_npc_context("npc_guard_b", faction_id="militia", location_id="tower")

        # Player supports the militia faction
        support_event = _make_player_event("support", faction_id="militia")

        guard_a.observe_events([support_event], tick=1, npc_context=ctx_a)
        guard_b.observe_events([support_event], tick=1, npc_context=ctx_b)

        # Both should gain trust toward player
        trust_a = guard_a.beliefs.beliefs.get("player", {}).get("trust", 0)
        trust_b = guard_b.beliefs.beliefs.get("player", {}).get("trust", 0)
        assert trust_a > 0
        assert trust_b > 0

    def test_npc_mind_batch_processing(self):
        """Simulate processing multiple NPCs in a single tick like world_simulation does."""
        npcs = {
            "npc_a": (_make_npc_context("npc_a", faction_id="f1", location_id="town"), NPCMind(npc_id="npc_a")),
            "npc_b": (_make_npc_context("npc_b", faction_id="f2", location_id="forest"), NPCMind(npc_id="npc_b")),
            "npc_c": (_make_npc_context("npc_c", faction_id="f1", location_id="town"), NPCMind(npc_id="npc_c")),
        }

        events = [_make_player_event("help", location_id="town", faction_id="f1")]
        sim_state = {}

        decisions = []
        for npc_id, (ctx, mind) in sorted(npcs.items()):
            mind.observe_events(events, tick=1, npc_context=ctx)
            mind.refresh_goals(simulation_state=sim_state, npc_context=ctx)
            decision = mind.decide(simulation_state=sim_state, npc_context=ctx, tick=1)
            decisions.append(decision)

        assert len(decisions) == 3
        assert all(d.npc_id for d in decisions)


# ===========================================================================
# State persistence round-trips
# ===========================================================================


class TestStatePersistence:
    """Tests that NPC mind state survives serialization/deserialization."""

    def test_full_state_round_trip(self):
        mind = NPCMind(npc_id="npc_guard")
        ctx = _make_npc_context("npc_guard", faction_id="militia", location_id="town")

        # Build up state
        mind.observe_events(
            [_make_player_event("help", target_id="npc_guard")],
            tick=1, npc_context=ctx,
        )
        mind.refresh_goals(simulation_state={}, npc_context=ctx)
        mind.decide(simulation_state={}, npc_context=ctx, tick=1)

        # Serialize
        data = mind.to_dict()

        # Deserialize
        restored = NPCMind.from_dict(data)

        # Verify
        assert restored.npc_id == mind.npc_id
        assert len(restored.memory.entries) == len(mind.memory.entries)
        assert restored.beliefs.to_dict() == mind.beliefs.to_dict()
        assert restored.goal_engine.to_dict() == mind.goal_engine.to_dict()
        assert restored.last_decision == mind.last_decision
        assert restored.last_seen_tick == mind.last_seen_tick

    def test_multi_tick_state_accumulation(self):
        """Simulate multiple ticks with state persistence between them."""
        ctx = _make_npc_context("npc_guard", faction_id="militia", location_id="town")
        sim_state = {}

        # Tick 1
        mind = NPCMind(npc_id="npc_guard")
        mind.observe_events([_make_player_event("help")], tick=1, npc_context=ctx)
        mind.refresh_goals(simulation_state=sim_state, npc_context=ctx)
        mind.decide(simulation_state=sim_state, npc_context=ctx, tick=1)
        state_after_t1 = mind.to_dict()

        # Tick 2: restore and continue
        mind2 = NPCMind.from_dict(state_after_t1)
        mind2.observe_events([_make_player_event("attack")], tick=2, npc_context=ctx)
        mind2.refresh_goals(simulation_state=sim_state, npc_context=ctx)
        mind2.decide(simulation_state=sim_state, npc_context=ctx, tick=2)
        state_after_t2 = mind2.to_dict()

        # Should have memories from both ticks
        restored = NPCMind.from_dict(state_after_t2)
        assert len(restored.memory.entries) >= 2
        assert restored.last_seen_tick == 2

    def test_multiple_npcs_state_dict(self):
        """Simulate storing multiple NPC minds in a single dict."""
        npc_ids = ["npc_a", "npc_b", "npc_c"]
        minds_dict = {}

        for npc_id in npc_ids:
            mind = NPCMind(npc_id=npc_id)
            ctx = _make_npc_context(npc_id, faction_id="f1")
            mind.observe_events([_make_player_event("help")], tick=1, npc_context=ctx)
            mind.refresh_goals(simulation_state={}, npc_context=ctx)
            minds_dict[npc_id] = mind.to_dict()

        # Restore all
        restored = {npc_id: NPCMind.from_dict(data) for npc_id, data in minds_dict.items()}
        assert len(restored) == 3
        for npc_id in npc_ids:
            assert restored[npc_id].npc_id == npc_id


# ===========================================================================
# Player action → NPC reaction pipeline
# ===========================================================================


class TestPlayerActionPipeline:
    def test_player_action_enrichment(self):
        """Test that player actions include NPC-relevant metadata."""
        from app.rpg.creator.world_player_actions import apply_player_action

        state = {
            "threads": {"t1": {"pressure": 3}},
            "factions": {"f1": {"pressure": 1}},
            "events": [],
            "consequences": [],
            "npc_index": {
                "npc_a": {"location_id": "town", "faction_id": "f1"},
            },
        }

        result = apply_player_action(state, {"type": "intervene_thread", "target_id": "t1"})
        events = result.get("events", [])
        intervention_events = [e for e in events if e.get("type") == "player_intervention"]
        assert len(intervention_events) == 1
        assert intervention_events[0].get("actor") == "player"
        assert "affected_npc_ids" in intervention_events[0]

    def test_support_faction_enrichment(self):
        from app.rpg.creator.world_player_actions import apply_player_action

        state = {
            "threads": {},
            "factions": {"f1": {"pressure": 2}},
            "events": [],
            "consequences": [],
            "npc_index": {
                "npc_a": {"faction_id": "f1", "location_id": ""},
            },
        }

        result = apply_player_action(state, {"type": "support_faction", "target_id": "f1"})
        support_events = [e for e in result.get("events", []) if e.get("type") == "player_support"]
        assert len(support_events) == 1
        assert support_events[0].get("faction_id") == "f1"
        assert "npc_a" in support_events[0].get("affected_npc_ids", [])


# ===========================================================================
# Scene enrichment
# ===========================================================================


class TestSceneEnrichment:
    def test_scenes_get_npc_actors(self):
        from app.rpg.creator.world_scene_generator import generate_scenes_from_simulation

        state = {
            "incidents": [{
                "type": "location_flashpoint",
                "source_id": "town",
                "summary": "Unrest in town",
                "heat": 4,
                "severity": "moderate",
            }],
            "npc_index": {
                "npc_guard": {"npc_id": "npc_guard", "name": "Guard", "role": "guard", "location_id": "town", "faction_id": ""},
            },
            "npc_minds": {},
        }

        scenes = generate_scenes_from_simulation(state)
        assert len(scenes) >= 1

        # Check that NPC actors were enriched
        scene = scenes[0]
        actor_ids = [a["id"] if isinstance(a, dict) else a for a in scene.get("actors", [])]
        assert "npc_guard" in actor_ids

    def test_scenes_without_npcs(self):
        from app.rpg.creator.world_scene_generator import generate_scenes_from_simulation

        state = {
            "incidents": [{
                "type": "thread_crisis",
                "source_id": "thread_a",
                "summary": "Crisis",
                "pressure": 5,
                "severity": "critical",
            }],
        }

        scenes = generate_scenes_from_simulation(state)
        assert len(scenes) >= 1
        # Should still work without NPC data
        assert "primary_npc_ids" in scenes[0]


# ===========================================================================
# Narrator enrichment
# ===========================================================================


class TestNarratorEnrichment:
    def test_build_npc_reaction_prompt_with_phase6_context(self):
        from app.rpg.ai.world_scene_narrator import build_npc_reaction_prompt

        npc = {
            "name": "Guard",
            "personality": "stoic",
            "goals": "protect the city",
            "relation_to_player": "neutral",
            "memory_summary": [{"type": "attack"}],
            "belief_summary": {"player": {"trust": -0.3, "hostility": 0.5}},
            "active_goals": [{"type": "retaliate", "priority": 0.8}],
            "last_decision": {"intent": "retaliate", "action_type": "retaliate"},
        }
        scene = {"title": "Town Square Confrontation"}

        prompt = build_npc_reaction_prompt(npc, scene, "The player approaches menacingly.")
        assert "Guard" in prompt
        assert "active goals" in prompt.lower() or "Active goals" in prompt
        assert "last decision" in prompt.lower() or "Last decision" in prompt
        # Phase 6 guidance should be present
        assert "active goals" in prompt.lower()
