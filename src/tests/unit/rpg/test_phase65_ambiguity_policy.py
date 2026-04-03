"""Phase 6.5 — Ambiguity Policy: Unit tests.

Tests the AmbiguityPolicy confidence thresholds and decision routing.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.rpg.recovery.ambiguity import AmbiguityPolicy
from app.rpg.recovery.models import AmbiguityDecision


class TestAmbiguityPolicy:
    def test_ambiguity_policy_auto_resolves_high_confidence_input(self):
        policy = AmbiguityPolicy()
        decision = policy.decide(player_input="attack")
        assert decision == AmbiguityDecision.AUTO_RESOLVE

    def test_ambiguity_policy_requests_clarification_low_confidence_input(self):
        policy = AmbiguityPolicy()
        decision = policy.decide(player_input="what do I do here?")
        assert decision == AmbiguityDecision.REQUEST_CLARIFICATION

    def test_ambiguity_policy_narrates_uncertainty_medium_confidence_input(self):
        policy = AmbiguityPolicy()
        # Medium-length input without question mark → medium confidence
        decision = policy.decide(player_input="I try to maybe look around the room carefully")
        assert decision == AmbiguityDecision.NARRATE_UNCERTAINTY

    def test_ambiguity_policy_uses_parser_confidence_when_present(self):
        policy = AmbiguityPolicy()
        # High confidence in parser result → auto resolve
        decision = policy.decide(
            parser_result={"confidence": 0.95, "action": "attack"},
            player_input="some ambiguous text?",
        )
        assert decision == AmbiguityDecision.AUTO_RESOLVE

        # Low confidence in parser result → request clarification
        decision = policy.decide(
            parser_result={"confidence": 0.2},
            player_input="attack",
        )
        assert decision == AmbiguityDecision.REQUEST_CLARIFICATION

    def test_ambiguity_policy_falls_back_to_input_heuristics(self):
        policy = AmbiguityPolicy()
        # No parser result → use input heuristics
        decision = policy.decide(parser_result=None, player_input="run")
        assert decision == AmbiguityDecision.AUTO_RESOLVE

        # Empty input → zero confidence → clarification
        decision = policy.decide(parser_result=None, player_input="")
        assert decision == AmbiguityDecision.REQUEST_CLARIFICATION
