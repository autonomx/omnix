"""Phase 6.5 — Social Simulation Regression Tests.

Ensure social simulation systems maintain backward compatibility
and don't break existing functionality:
- simulation state structure remains compatible
- social state doesn't interfere with existing pipelines
- existing tests continue to pass after social integration
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
from app.rpg.social.reputation_graph import _safe_str, _safe_float, _clamp


class TestSocialSimulationRegression:
    """Regression tests for social simulation backward compatibility."""

    def test_reputation_graph_empty_init(self):
        """ReputationGraph should initialize with no edges."""
        graph = ReputationGraph()
        assert graph.edges == {}

    def test_reputation_graph_from_empty_dict(self):
        """ReputationGraph should handle empty dict initialization."""
        graph = ReputationGraph.from_dict({})
        assert graph.edges == {}

    def test_reputation_graph_from_none(self):
        """ReputationGraph should handle None initialization."""
        graph = ReputationGraph.from_dict(None)
        assert graph.edges == {}

    def test_reputation_graph_get_nonexistent(self):
        """Getting reputation for nonexistent entities should return zeros."""
        graph = ReputationGraph()
        result = graph.get("nonexistent", "target")
        assert result["trust"] == 0.0
        assert result["fear"] == 0.0
        assert result["respect"] == 0.0
        assert result["hostility"] == 0.0

    def test_alliance_system_empty_init(self):
        """AllianceSystem should initialize with no alliances."""
        system = AllianceSystem()
        assert system.alliances == []

    def test_alliance_system_from_empty_list(self):
        """AllianceSystem should handle empty list initialization."""
        system = AllianceSystem.from_dict([])
        assert system.alliances == []

    def test_alliance_system_from_none(self):
        """AllianceSystem should handle None initialization."""
        system = AllianceSystem.from_dict(None)
        assert system.alliances == []

    def test_rumor_system_empty_init(self):
        """RumorSystem should initialize with no rumors."""
        system = RumorSystem()
        assert system.rumors == []

    def test_rumor_system_from_empty_list(self):
        """RumorSystem should handle empty list initialization."""
        system = RumorSystem.from_dict([])
        assert system.rumors == []

    def test_rumor_system_from_none(self):
        """RumorSystem should handle None initialization."""
        system = RumorSystem.from_dict(None)
        assert system.rumors == []

    def test_group_decision_empty_init(self):
        """GroupDecisionEngine should initialize with no positions."""
        engine = GroupDecisionEngine()
        assert engine.positions == {}

    def test_group_decision_from_empty_dict(self):
        """GroupDecisionEngine should handle empty dict initialization."""
        engine = GroupDecisionEngine.from_dict({})
        assert engine.positions == {}

    def test_group_decision_from_none(self):
        """GroupDecisionEngine should handle None initialization."""
        engine = GroupDecisionEngine.from_dict(None)
        assert engine.positions == {}

    def test_betrayal_propagation_empty_event(self):
        """BetrayalPropagation should handle empty event dict."""
        events = BetrayalPropagation.apply({}, {})
        assert events == []

    def test_betrayal_propagation_none_event(self):
        """BetrayalPropagation should handle None event."""
        events = BetrayalPropagation.apply(None, {})
        assert events == []

    def test_betrayal_propagation_none_social_state(self):
        """BetrayalPropagation should handle None social state."""
        event = {"type": "betrayal", "source_id": "player", "target_id": "npc"}
        events = BetrayalPropagation.apply(event, None)
        assert len(events) >= 1

    def test_safe_str_handles_various_types(self):
        """_safe_str should handle various input types."""
        assert _safe_str(None) == ""
        assert _safe_str(123) == "123"
        assert _safe_str("test") == "test"
        assert _safe_str(0) == "0"

    def test_safe_float_handles_various_types(self):
        """_safe_float should handle various input types."""
        assert _safe_float(None) == 0.0
        assert _safe_float("1.5") == 1.5
        assert _safe_float("invalid") == 0.0
        assert _safe_float(42) == 42.0
        assert _safe_float("not_a_number", default=-1.0) == -1.0

    def test_clamp_bounds(self):
        """_clamp should clamp values to [-1.0, 1.0]."""
        assert _clamp(2.0) == 1.0
        assert _clamp(-2.0) == -1.0
        assert _clamp(0.0) == 0.0
        assert _clamp(1.0) == 1.0
        assert _clamp(-1.0) == -1.0
        assert _clamp(0.5) == 0.5

    def test_social_state_survives_serialization(self):
        """Social state should survive to_dict/from_dict roundtrip."""
        rep = ReputationGraph()
        rep.update("faction_a", "player", "trust", 0.5)
        alliances = AllianceSystem()
        alliances.propose_or_strengthen(["faction_a", "faction_b"], "test")
        rumors = RumorSystem()
        group = GroupDecisionEngine()

        social_state = {
            "reputation": rep.to_dict(),
            "alliances": alliances.to_dict(),
            "rumors": rumors.to_dict(),
            "group_positions": group.to_dict(),
        }

        # Roundtrip
        restored_rep = ReputationGraph.from_dict(social_state["reputation"])
        restored_alliances = AllianceSystem.from_dict(social_state["alliances"])
        restored_rumors = RumorSystem.from_dict(social_state["rumors"])
        restored_group = GroupDecisionEngine.from_dict(social_state["group_positions"])

        assert restored_rep.get("faction_a", "player")["trust"] == 0.5
        assert len(restored_alliances.alliances) == 1
        assert len(restored_rumors.rumors) == 0
        assert restored_group.positions == {}