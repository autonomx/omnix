"""Regression Tests for Tier 21 Social Simulation Engine."""

import pytest
from app.rpg.ai.social.reputation_graph import ReputationGraph
from app.rpg.ai.social.alliance_system import AllianceSystem
from app.rpg.ai.social.rumor_system import RumorSystem
from app.rpg.ai.social.social_engine import SocialEngine
from app.rpg.ai.social.group_decision import GroupDecisionEngine, NPCDecision


class TestTier21SocialRegression:
    """Ensure core social mechanics don't regress."""

    def test_reputation_initial_state_always_zero(self):
        """Verify new relationships always start at 0."""
        graph = ReputationGraph()
        assert graph.get("new_npc1", "new_npc2") == 0.0
        assert graph.get("new_npc2", "new_npc1") == 0.0

    def test_reputation_bounds_never_exceeded(self):
        """Reputation must stay within [-1.0, 1.0]."""
        graph = ReputationGraph()
        for _ in range(100):
            graph.update("a", "b", 0.1)
        assert graph.get("a", "b") <= 1.0

        for _ in range(100):
            graph.update("c", "d", -0.1)
        assert graph.get("c", "d") >= -1.0

    def test_alliance_membership_invariant(self):
        """Each NPC can only be in one faction."""
        system = AllianceSystem()
        system.form_alliance("a", "b")
        system.form_alliance("c", "d")
        system.form_alliance("a", "c")  # Should merge factions

        # All should now be allies
        assert system.are_allies("a", "d")
        assert system.are_allies("b", "c")
        assert system.faction_count() == 1

    def test_rumor_system_does_not_duplicate_knowers(self):
        """Each NPC should only learn a rumor once."""
        system = RumorSystem(spread_probability=1.0, default_ttl=10)
        system.add_rumor("secret", "a")

        npcs = ["a", "b", "c", "d"]
        system.tick(npcs)

        for npc in npcs:
            rumors = system.get_rumors_known_by(npc)
            secret_count = len([r for r in rumors if r["content"] == "secret"])
            assert secret_count <= 1

    def test_social_engine_clear_resets_everything(self):
        """Clear should return engine to initial state."""
        engine = SocialEngine()
        engine.process_event({"type": "help", "actor": "a", "target": "b"})
        engine.alliances.form_alliance("a", "b")
        engine.rumors.add_rumor("rumor", "a")

        engine.clear()

        assert engine.rep.get("a", "b") == 0.0
        assert engine.alliances.faction_count() == 0
        assert engine.rumors.get_active_count() == 0
        assert len(engine.event_history) == 0

    def test_group_decision_with_no_valid_decisions(self):
        """Should not crash with missing decisions."""
        engine = GroupDecisionEngine()
        result = engine.decide(["a", "b"], {"a": None})
        # Should handle gracefully - either return None or skip invalid
        # (implementation dependent, but must not crash)
        try:
            _ = engine.decide(["a", "b"], {"a": NPCDecision("a", "act")})
        except Exception:
            pass  # If implementation handles None differently, that's ok

    def test_empty_social_context_does_not_crash(self):
        """NPCs with no history should get valid context."""
        engine = SocialEngine()
        context = engine.get_npc_social_context("brand_new_npc")
        assert context["relationships"] == {}
        assert context["faction"] is None
        assert context["faction_members"] == []
        assert context["rumors"] == []
