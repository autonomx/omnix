"""Functional Tests for Tier 21 Social Simulation Engine."""

import pytest
from src.app.rpg.ai.social.reputation_graph import ReputationGraph
from src.app.rpg.ai.social.alliance_system import AllianceSystem
from src.app.rpg.ai.social.rumor_system import RumorSystem
from src.app.rpg.ai.social.social_engine import SocialEngine
from src.app.rpg.ai.social.group_decision import GroupDecisionEngine, NPCDecision


class TestSocialSimulationFunctional:
    """Integration-style functional tests for the social engine."""

    def test_full_social_scenario(self):
        """Test a complete social scenario with reputation, alliances, and rumors."""
        engine = SocialEngine()
        npcs = ["alice", "bob", "charlie", "diana"]

        # Alice and Bob are allies
        engine.alliances.form_alliance("alice", "bob")

        # Alice helps Bob - strengthens their relationship
        engine.process_event({"type": "help", "actor": "alice", "target": "bob"})
        assert engine.rep.get("alice", "bob") > 0
        assert engine.rep.get("bob", "alice") > 0

        # Charlie attacks Bob - Alice should dislike Charlie
        engine.process_event({"type": "attack", "actor": "charlie", "target": "bob"})
        assert engine.rep.get("charlie", "bob") < 0
        assert engine.rep.get("bob", "charlie") < 0
        assert engine.rep.get("alice", "charlie") < 0  # Ally defense

        # Rumor spreads about the attack
        rumors = engine.rumors.get_rumors_about("charlie")
        assert len(rumors) >= 1

    def test_faction_war_emergence(self):
        """Test that faction conflicts can emerge from individual events."""
        engine = SocialEngine()

        # Create two factions
        engine.alliances.form_alliance("alpha", "beta")
        engine.alliances.form_alliance("gamma", "delta")

        # Alpha attacks Gamma
        engine.process_event({"type": "attack", "actor": "alpha", "target": "gamma"})

        # Beta should dislike Gamma and Delta
        assert engine.rep.get("beta", "gamma") < 0
        assert engine.rep.get("beta", "delta") < 0

        # Delta should dislike Alpha
        assert engine.rep.get("delta", "alpha") < 0

    def test_betrayal_cascade(self):
        """Test that betrayal breaks alliances and spreads rumors."""
        engine = SocialEngine()

        # Create alliance
        engine.alliances.form_alliance("traitor", "victim")
        assert engine.alliances.are_allies("traitor", "victim")

        # Traitor betrays victim
        engine.process_event({"type": "betrayal", "actor": "traitor", "target": "victim"})

        # Alliance should be broken
        assert not engine.alliances.are_allies("traitor", "victim")

        # Rumor should exist
        assert engine.rumors.get_active_count() >= 1

    def test_group_decision_coordinated_action(self):
        """Test that groups can coordinate through the decision engine."""
        decision_engine = GroupDecisionEngine()
        decision_engine.add_leader("leader")

        # Faction members propose actions
        decisions = {
            "leader": NPCDecision(npc_id="leader", intent="raid", confidence=0.8),
            "member1": NPCDecision(npc_id="member1", intent="defend", confidence=0.5),
            "member2": NPCDecision(npc_id="member2", intent="raid", confidence=0.6),
        }

        # Leader strategy should follow leader
        result = decision_engine.decide(["leader", "member1", "member2"], decisions, strategy="leader")
        assert result.intent == "raid"

        # Majority should also be raid (2 vs 1)
        result = decision_engine.decide(["leader", "member1", "member2"], decisions, strategy="majority")
        assert result.intent == "raid"

    def test_rumor_lifecycle(self):
        """Test that rumors spread and expire naturally."""
        rumor_system = RumorSystem(spread_probability=0.5, default_ttl=3)
        rumor_system.add_rumor("secret", "source")

        npcs = ["source", "npc1", "npc2", "npc3"]

        # After several ticks, rumor should reach most NPCs then expire
        for _ in range(6):
            expired = rumor_system.tick(npcs)

        # Rumor should eventually expire
        assert rumor_system.get_active_count() == 0

    def test_reputation_recovery(self):
        """Test that negative reputation can be repaired over time."""
        engine = SocialEngine()

        # Negative event
        engine.process_event({"type": "attack", "actor": "a", "target": "b"})
        assert engine.rep.get("b", "a") < 0

        # Multiple positive events can recover
        for _ in range(5):
            engine.process_event({"type": "help", "actor": "a", "target": "b"})

        assert engine.rep.get("b", "a") > 0
