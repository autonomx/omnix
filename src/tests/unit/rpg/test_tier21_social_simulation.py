"""Unit Tests for Tier 21 Social Simulation Engine."""

import pytest

from app.rpg.ai.social.alliance_system import AllianceSystem
from app.rpg.ai.social.group_decision import GroupDecisionEngine, NPCDecision
from app.rpg.ai.social.reputation_graph import ReputationGraph
from app.rpg.ai.social.rumor_system import Rumor, RumorSystem
from app.rpg.ai.social.social_engine import SocialEngine, SocialEvent


class TestReputationGraph:
    def setup_method(self):
        self.graph = ReputationGraph()

    def test_initial_reputation_is_zero(self):
        assert self.graph.get("a", "b") == 0.0

    def test_update_positive(self):
        self.graph.update("a", "b", 0.5)
        assert self.graph.get("a", "b") == 0.5

    def test_update_negative(self):
        self.graph.update("a", "b", -0.3)
        assert self.graph.get("a", "b") == -0.3

    def test_clamp_positive(self):
        self.graph.update("a", "b", 0.8)
        self.graph.update("a", "b", 0.5)
        assert self.graph.get("a", "b") == 1.0

    def test_clamp_negative(self):
        self.graph.update("a", "b", -0.8)
        self.graph.update("a", "b", -0.5)
        assert self.graph.get("a", "b") == -1.0

    def test_directional(self):
        self.graph.update("a", "b", 0.5)
        self.graph.update("b", "a", -0.3)
        assert self.graph.get("a", "b") == 0.5
        assert self.graph.get("b", "a") == -0.3

    def test_set_direct(self):
        self.graph.set("a", "b", 0.7)
        assert self.graph.get("a", "b") == 0.7

    def test_neighbors(self):
        self.graph.update("a", "b", 0.5)
        self.graph.update("a", "c", -0.3)
        neighbors = self.graph.neighbors("a")
        assert len(neighbors) == 2
        assert "b" in neighbors

    def test_top_relations(self):
        self.graph.set("a", "b", 0.8)
        self.graph.set("a", "c", 0.5)
        self.graph.set("a", "d", 0.9)
        top = self.graph.top_relations("a", n=2)
        assert top[0] == ("d", 0.9)
        assert top[1] == ("b", 0.8)

    def test_worst_relations(self):
        self.graph.set("a", "b", -0.8)
        self.graph.set("a", "c", -0.5)
        self.graph.set("a", "d", -0.9)
        worst = self.graph.worst_relations("a", n=2)
        assert worst[0] == ("d", -0.9)
        assert worst[1] == ("b", -0.8)

    def test_get_mutual_reputation(self):
        self.graph.update("a", "b", 0.5)
        self.graph.update("b", "a", -0.3)
        a_to_b, b_to_a = self.graph.get_mutual_reputation("a", "b")
        assert a_to_b == 0.5
        assert b_to_a == -0.3

    def test_average_reputation(self):
        self.graph.set("a", "b", 0.5)
        self.graph.set("a", "c", -0.5)
        assert self.graph.get_average_reputation("a") == 0.0

    def test_average_reputation_empty(self):
        assert self.graph.get_average_reputation("x") == 0.0

    def test_clear(self):
        self.graph.update("a", "b", 0.5)
        self.graph.clear()
        assert self.graph.get("a", "b") == 0.0


class TestAllianceSystem:
    def setup_method(self):
        self.system = AllianceSystem()

    def test_form_alliance_creates_faction(self):
        fid = self.system.form_alliance("a", "b")
        assert fid is not None
        assert self.system.get_faction("a") == fid
        assert self.system.get_faction("b") == fid

    def test_are_allies(self):
        self.system.form_alliance("a", "b")
        assert self.system.are_allies("a", "b")

    def test_not_allies(self):
        assert not self.system.are_allies("a", "b")

    def test_add_to_existing_faction(self):
        fid1 = self.system.form_alliance("a", "b")
        fid2 = self.system.form_alliance("b", "c")
        assert fid1 == fid2
        assert self.system.are_allies("a", "c")

    def test_break_alliance(self):
        self.system.form_alliance("a", "b")
        self.system.break_alliance("a", "b")
        assert not self.system.are_allies("a", "b")
        assert self.system.get_faction("a") is None
        assert self.system.get_faction("b") is None

    def test_remove_from_faction(self):
        self.system.form_alliance("a", "b")
        self.system.remove_from_faction("a")
        assert self.system.get_faction("a") is None
        assert self.system.get_faction("b") is not None

    def test_get_faction_members(self):
        self.system.form_alliance("a", "b")
        self.system.form_alliance("b", "c")
        members = self.system.get_faction_members("a")
        assert "b" in members
        assert "c" in members
        assert "a" not in members

    def test_merge_factions(self):
        self.system.form_alliance("a", "b")
        self.system.form_alliance("c", "d")
        self.system.form_alliance("a", "c")
        assert self.system.faction_count() == 1
        assert self.system.are_allies("a", "d")

    def test_list_factions(self):
        self.system.form_alliance("a", "b")
        factions = self.system.list_factions()
        assert len(factions) == 1
        assert len(factions[0]["members"]) == 2

    def test_clear(self):
        self.system.form_alliance("a", "b")
        self.system.clear()
        assert self.system.faction_count() == 0


class TestRumorSystem:
    def setup_method(self):
        self.system = RumorSystem(spread_probability=1.0, default_ttl=5)

    def test_add_rumor(self):
        self.system.add_rumor("secret", "a")
        assert self.system.get_active_count() == 1
        rumors = self.system.get_rumors_known_by("a")
        assert len(rumors) == 1
        assert rumors[0]["content"] == "secret"

    def test_rumor_spreads_on_tick(self):
        self.system = RumorSystem(spread_probability=1.0, default_ttl=20)
        self.system.add_rumor("secret", "a")
        npcs = ["a", "b", "c"]
        for _ in range(10):
            self.system.tick(npcs)
        for npc in npcs:
            rumors = self.system.get_rumors_known_by(npc)
            assert len(rumors) >= 1, f"{npc} should know the rumor"

    def test_rumor_expires(self):
        self.system = RumorSystem(spread_probability=0.0, default_ttl=2)
        self.system.add_rumor("expiring", "a")
        self.system.tick(["a"])  # TTL: 2->1
        self.system.tick(["a"])  # TTL: 1->0, expires
        assert self.system.get_active_count() == 0

    def test_expired_rumors_returned(self):
        self.system = RumorSystem(spread_probability=0.0, default_ttl=1)
        self.system.add_rumor("about to expire", "a")
        expired = self.system.tick(["a"])
        assert "about to expire" in expired

    def test_get_rumors_about(self):
        self.system.add_rumor("a stole gold", "b")
        self.system.add_rumor("b helped a", "c")
        results = self.system.get_rumors_about("a")
        assert len(results) == 2

    def test_who_knows_rumor(self):
        self.system.add_rumor("the secret", "a")
        known = self.system.who_knows_rumor("the secret")
        assert "a" in known
        assert "b" not in known

    def test_clear(self):
        self.system.add_rumor("rumor1", "a")
        self.system.add_rumor("rumor2", "b")
        self.system.clear()
        assert self.system.get_active_count() == 0


class TestSocialEngine:
    def setup_method(self):
        self.rep = ReputationGraph()
        self.alliances = AllianceSystem()
        self.rumors = RumorSystem(spread_probability=0.0, default_ttl=5)
        self.engine = SocialEngine(self.rep, self.alliances, self.rumors)

    def test_process_help_event(self):
        effects = self.engine.process_event({"type": "help", "actor": "a", "target": "b"})
        assert self.rep.get("a", "b") > 0
        assert self.rep.get("b", "a") > 0

    def test_process_attack_event(self):
        effects = self.engine.process_event({"type": "attack", "actor": "a", "target": "b"})
        assert self.rep.get("a", "b") < 0
        assert self.rep.get("b", "a") < 0
        assert self.rumors.get_active_count() == 1

    def test_attack_propagates_to_allies(self):
        self.alliances.form_alliance("b", "c")
        self.engine.process_event({"type": "attack", "actor": "a", "target": "b"})
        assert self.rep.get("c", "a") < 0

    def test_process_betrayal_event(self):
        self.alliances.form_alliance("a", "b")
        effects = self.engine.process_event({"type": "betrayal", "actor": "a", "target": "b"})
        assert not self.alliances.are_allies("a", "b")
        assert self.rumors.get_active_count() == 1

    def test_empty_actor_returns_no_effects(self):
        effects = self.engine.process_event({"type": "help", "actor": "", "target": "b"})
        assert effects == []

    def test_tick_updates_rumors(self):
        self.rumors.add_rumor("test rumor", "a")
        result = self.engine.tick(["a", "b"])
        assert "expired_rumors" in result
        assert "active_rumors" in result
        assert "faction_count" in result

    def test_get_npc_social_context(self):
        self.rep.update("a", "b", 0.5)
        self.alliances.form_alliance("a", "b")
        context = self.engine.get_npc_social_context("a")
        assert "relationships" in context
        assert "faction" in context
        assert "faction_members" in context
        assert "rumors" in context

    def test_get_state_snapshot(self):
        self.engine.process_event({"type": "help", "actor": "a", "target": "b"})
        snapshot = self.engine.get_state_snapshot()
        assert "reputation_edges" in snapshot
        assert "factions" in snapshot
        assert "rumors" in snapshot
        assert "event_history" in snapshot

    def test_clear(self):
        self.engine.process_event({"type": "help", "actor": "a", "target": "b"})
        self.engine.clear()
        assert self.rep.get("a", "b") == 0.0
        assert self.alliances.faction_count() == 0
        assert self.rumors.get_active_count() == 0


class TestGroupDecisionEngine:
    def setup_method(self):
        self.engine = GroupDecisionEngine()

    def _make_decision(self, npc_id, intent, confidence=0.5):
        return NPCDecision(npc_id=npc_id, intent=intent, confidence=confidence)

    def test_majority_decision(self):
        decisions = {
            "a": self._make_decision("a", "attack"),
            "b": self._make_decision("b", "attack"),
            "c": self._make_decision("c", "flee"),
        }
        result = self.engine.decide(["a", "b", "c"], decisions)
        assert result is not None
        assert result.intent == "attack"

    def test_empty_decisions_returns_none(self):
        assert self.engine.decide([], {}) is None
        assert self.engine.decide(["a"], {}) is None

    def test_weighted_majority_decision(self):
        decisions = {
            "a": self._make_decision("a", "attack", confidence=0.9),
            "b": self._make_decision("b", "flee", confidence=0.3),
            "c": self._make_decision("c", "flee", confidence=0.3),
        }
        result = self.engine.decide(["a", "b", "c"], decisions, strategy="weighted_majority")
        assert result is not None
        assert result.intent == "attack"

    def test_leader_strategy(self):
        self.engine.add_leader("a")
        decisions = {
            "a": self._make_decision("a", "flee"),
            "b": self._make_decision("b", "attack"),
            "c": self._make_decision("c", "attack"),
        }
        result = self.engine.decide(["a", "b", "c"], decisions, strategy="leader")
        assert result is not None
        assert result.intent == "flee"

    def test_leader_fallback_to_majority(self):
        decisions = {
            "a": self._make_decision("a", "attack"),
            "b": self._make_decision("b", "attack"),
            "c": self._make_decision("c", "flee"),
        }
        result = self.engine.decide(["a", "b", "c"], decisions, strategy="leader")
        assert result is not None
        assert result.intent == "attack"

    def test_get_intents_summary(self):
        decisions = {
            "a": self._make_decision("a", "attack"),
            "b": self._make_decision("b", "attack"),
            "c": self._make_decision("c", "flee"),
        }
        summary = self.engine.get_intents_summary(["a", "b", "c"], decisions)
        assert "attack" in summary
        assert "flee" in summary
        assert len(summary["attack"]) == 2
        assert len(summary["flee"]) == 1

    def test_set_leaders(self):
        self.engine.set_leaders({"a", "b"})
        assert "a" in self.engine.leaders
        assert "b" in self.engine.leaders

    def test_remove_leader(self):
        self.engine.add_leader("a")
        self.engine.remove_leader("a")
        assert "a" not in self.engine.leaders
