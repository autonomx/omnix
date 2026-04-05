"""Phase 6.5 — Social Simulation Unit Tests.

Cover:
- reputation clamping and top-target trim
- alliance create/strengthen/break
- betrayal propagation output determinism
- rumor spawn/advance/cooling
- faction stance aggregation from NPC minds
"""

from __future__ import annotations

import pytest

from app.rpg.social import (
    ReputationGraph,
    AllianceSystem,
    BetrayalPropagation,
    RumorSystem,
    GroupDecisionEngine,
)


class TestReputationGraph:
    """Tests for ReputationGraph."""

    def test_update_and_get(self):
        graph = ReputationGraph()
        result = graph.update("faction_a", "player", "trust", 0.5)
        assert result == 0.5
        assert graph.get("faction_a", "player")["trust"] == 0.5

    def test_clamp_upper(self):
        graph = ReputationGraph()
        graph.update("a", "b", "trust", 2.0)
        assert graph.get("a", "b")["trust"] == 1.0

    def test_clamp_lower(self):
        graph = ReputationGraph()
        graph.update("a", "b", "trust", -2.0)
        assert graph.get("a", "b")["trust"] == -1.0

    def test_unknown_key_returns_zero(self):
        graph = ReputationGraph()
        result = graph.update("a", "b", "invalid_key", 1.0)
        assert result == 0.0

    def test_top_targets_sorted(self):
        graph = ReputationGraph()
        graph.update("source", "a", "trust", 0.5)
        graph.update("source", "b", "trust", 0.1)
        graph.update("source", "c", "hostility", 0.8)
        tops = graph.top_targets("source", limit=2)
        assert len(tops) == 2
        assert tops[0][0] == "c"  # highest absolute sum

    def test_trim_source_max_targets(self):
        graph = ReputationGraph()
        for i in range(30):
            graph.update("source", f"target_{i}", "trust", 0.1 * (i + 1))
        tops = graph.top_targets("source", limit=30)
        assert len(tops) <= 24  # _MAX_TARGETS_PER_SOURCE

    def test_to_dict_from_dict_roundtrip(self):
        graph = ReputationGraph()
        graph.update("a", "b", "trust", 0.5)
        data = graph.to_dict()
        restored = ReputationGraph.from_dict(data)
        assert restored.get("a", "b")["trust"] == 0.5

    def test_safe_str_none(self):
        from app.rpg.social.reputation_graph import _safe_str
        assert _safe_str(None) == ""

    def test_safe_float_error(self):
        from app.rpg.social.reputation_graph import _safe_float
        assert _safe_float("not_a_number") == 0.0

    def test_clamp_function(self):
        from app.rpg.social.reputation_graph import _clamp
        assert _clamp(2.0) == 1.0
        assert _clamp(-2.0) == -1.0
        assert _clamp(0.5) == 0.5


class TestAllianceSystem:
    """Tests for AllianceSystem."""

    def test_propose_new_alliance(self):
        system = AllianceSystem()
        result = system.propose_or_strengthen(["faction_a", "faction_b"], "test reason")
        assert result is not None
        assert result["status"] == "active"
        assert result["member_ids"] == ["faction_a", "faction_b"]

    def test_strengthen_existing_alliance(self):
        system = AllianceSystem()
        system.propose_or_strengthen(["faction_a", "faction_b"], "test")
        result = system.propose_or_strengthen(["faction_a", "faction_b"], "updated", delta=0.3)
        assert result["strength"] == 0.4  # 0.1 + 0.3

    def test_weaken_alliance(self):
        system = AllianceSystem()
        system.propose_or_strengthen(["faction_a", "faction_b"], "test", delta=0.5)
        result = system.weaken_or_break(["faction_a", "faction_b"], "reason", delta=0.3)
        assert result["strength"] == 0.2

    def test_break_alliance(self):
        system = AllianceSystem()
        system.propose_or_strengthen(["faction_a", "faction_b"], "test", delta=0.1)
        result = system.weaken_or_break(["faction_a", "faction_b"], "reason", delta=0.2)
        assert result["status"] == "broken"

    def test_insufficient_members(self):
        system = AllianceSystem()
        result = system.propose_or_strengthen(["faction_a"], "test")
        assert result is None

    def test_active_for_member(self):
        system = AllianceSystem()
        system.propose_or_strengthen(["faction_a", "faction_b"], "test1", delta=0.3)
        system.propose_or_strengthen(["faction_a", "faction_c"], "test2", delta=0.5)
        actives = system.active_for_member("faction_a", limit=1)
        assert len(actives) == 1
        assert actives[0]["strength"] == 0.5

    def test_trim_max_alliances(self):
        system = AllianceSystem()
        for i in range(40):
            system.propose_or_strengthen([f"faction_{i}", "central"], f"test_{i}", delta=0.01 * i)
        assert len(system.alliances) <= 32

    def test_to_dict_from_dict_roundtrip(self):
        system = AllianceSystem()
        system.propose_or_strengthen(["a", "b"], "test")
        data = system.to_dict()
        restored = AllianceSystem.from_dict(data)
        assert len(restored.alliances) == 1


class TestBetrayalPropagation:
    """Tests for BetrayalPropagation."""

    def test_non_betrayal_returns_empty(self):
        events = BetrayalPropagation.apply({"type": "other"}, {})
        assert events == []

    def test_betrayal_emits_social_shock(self):
        event = {
            "type": "betrayal",
            "source_id": "player",
            "target_id": "npc_1",
            "faction_id": "faction_a",
            "location_id": "loc_1",
        }
        events = BetrayalPropagation.apply(event, {})
        social_shocks = [e for e in events if e["type"] == "social_shock"]
        assert len(social_shocks) == 1
        assert "faction_a" in social_shocks[0]["summary"]

    def test_betrayal_emits_trust_collapse(self):
        event = {
            "type": "betrayal",
            "source_id": "player",
            "target_id": "npc_1",
            "location_id": "loc_1",
        }
        events = BetrayalPropagation.apply(event, {})
        trust_collapses = [e for e in events if e["type"] == "trust_collapse"]
        assert len(trust_collapses) == 1
        assert "Trust collapsed" in trust_collapses[0]["summary"]

    def test_betrayal_max_4_events(self):
        event = {
            "type": "betrayal",
            "source_id": "player",
            "target_id": "npc_1",
            "faction_id": "faction_a",
        }
        events = BetrayalPropagation.apply(event, {})
        assert len(events) <= 4


class TestRumorSystem:
    """Tests for RumorSystem."""

    def test_spawn_from_events(self):
        system = RumorSystem()
        events = [
            {"type": "player_support", "target_id": "faction_a", "actor": "player", "summary": "Player helped"}
        ]
        created = system.spawn_from_events(events, tick=5)
        assert len(created) == 1
        assert created[0]["type"] == "player_support"
        assert created[0]["tick"] == 5

    def test_spawn_ignores_unknown_event_types(self):
        system = RumorSystem()
        events = [{"type": "unknown_type", "target_id": "faction_a", "actor": "player", "summary": "test"}]
        created = system.spawn_from_events(events, tick=5)
        assert created == []

    def test_advance_heat_and_reach(self):
        system = RumorSystem()
        system.rumors.append({
            "rumor_id": "r1", "type": "test", "subject_id": "s", "source_id": "s",
            "location_id": "l", "faction_id": "f", "text": "t",
            "reach": 1, "credibility": 0.5, "heat": 2, "tick": 0, "status": "active",
        })
        system.advance()
        assert system.rumors[0]["heat"] == 1
        assert system.rumors[0]["reach"] == 2

    def test_advance_goes_cold(self):
        system = RumorSystem()
        system.rumors.append({
            "rumor_id": "r1", "type": "test", "subject_id": "s", "source_id": "s",
            "location_id": "l", "faction_id": "f", "text": "t",
            "reach": 1, "credibility": 0.5, "heat": 0, "tick": 0, "status": "active",
        })
        system.advance()
        assert system.rumors[0]["reach"] == 0
        assert system.rumors[0]["status"] == "cold"

    def test_active_rumors_sorted(self):
        system = RumorSystem()
        system.rumors = [
            {"rumor_id": "r1", "type": "test", "subject_id": "s", "source_id": "s",
             "location_id": "l", "faction_id": "f", "text": "t",
             "heat": 1, "reach": 1, "status": "active", "tick": 0, "credibility": 0.5},
            {"rumor_id": "r2", "type": "test", "subject_id": "s", "source_id": "s",
             "location_id": "l", "faction_id": "f", "text": "t",
             "heat": 2, "reach": 1, "status": "active", "tick": 0, "credibility": 0.5},
        ]
        active = system.active(limit=1)
        assert len(active) == 1
        assert active[0]["rumor_id"] == "r2"

    def test_trim_max_rumors(self):
        system = RumorSystem()
        for i in range(70):
            system.rumors.append({
                "rumor_id": f"r{i}", "type": "test", "subject_id": "s", "source_id": "s",
                "location_id": "l", "faction_id": "f", "text": "t",
                "heat": 1, "reach": 1, "status": "active", "tick": i, "credibility": 0.5,
            })
        system._trim()
        assert len(system.rumors) <= 64

    def test_to_dict_from_dict_roundtrip(self):
        system = RumorSystem()
        system.rumors.append({
            "rumor_id": "r1", "type": "test", "subject_id": "s", "source_id": "s",
            "location_id": "l", "faction_id": "f", "text": "t",
            "heat": 1, "reach": 1, "status": "active", "tick": 0, "credibility": 0.5,
        })
        data = system.to_dict()
        restored = RumorSystem.from_dict(data)
        assert len(restored.rumors) == 1

    def test_max_rumors_per_tick(self):
        system = RumorSystem()
        events = []
        for i in range(15):
            events.append({
                "type": "player_support", "target_id": "faction_a",
                "actor": "player", "summary": f"Event {i}"
            })
        created = system.spawn_from_events(events, tick=1)
        assert len(created) <= 8


class TestGroupDecisionEngine:
    """Tests for GroupDecisionEngine."""

    def test_evaluate_faction_oppose(self):
        engine = GroupDecisionEngine()
        minds = {
            "npc_1": {"beliefs": {"player": {"hostility": 0.5, "trust": 0.0, "fear": 0.0}}},
            "npc_2": {"beliefs": {"player": {"hostility": 0.4, "trust": 0.0, "fear": 0.0}}},
        }
        result = engine.evaluate_faction("faction_a", minds, tick=1)
        assert result["stance"] == "oppose"
        assert result["updated_tick"] == 1

    def test_evaluate_faction_support(self):
        engine = GroupDecisionEngine()
        minds = {
            "npc_1": {"beliefs": {"player": {"hostility": 0.0, "trust": 0.5, "fear": 0.0}}},
        }
        result = engine.evaluate_faction("faction_a", minds, tick=2)
        assert result["stance"] == "support"

    def test_evaluate_faction_fear(self):
        engine = GroupDecisionEngine()
        minds = {
            "npc_1": {"beliefs": {"player": {"hostility": 0.0, "trust": 0.0, "fear": 0.5}}},
        }
        result = engine.evaluate_faction("faction_a", minds, tick=3)
        assert result["stance"] == "fear"

    def test_evaluate_faction_watch(self):
        engine = GroupDecisionEngine()
        minds = {
            "npc_1": {"beliefs": {"player": {"hostility": 0.1, "trust": 0.1, "fear": 0.1}}},
        }
        result = engine.evaluate_faction("faction_a", minds, tick=4)
        assert result["stance"] == "watch"

    def test_evaluate_faction_no_members(self):
        engine = GroupDecisionEngine()
        result = engine.evaluate_faction("faction_a", {}, tick=5)
        assert result["stance"] == "watch"
        assert result["score"] == 0.0

    def test_to_dict_from_dict_roundtrip(self):
        engine = GroupDecisionEngine()
        engine.positions["faction_a"] = {"target_id": "player", "stance": "support", "score": 0.5, "updated_tick": 1}
        data = engine.to_dict()
        restored = GroupDecisionEngine.from_dict(data)
        assert restored.positions["faction_a"]["stance"] == "support"