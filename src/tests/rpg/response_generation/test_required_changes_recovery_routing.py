from __future__ import annotations

from app.rpg.response_generation.forward_motion import ForwardMotionPolicy
from app.rpg.response_generation.recovery import LocalRecoveryCoordinator
from app.rpg.response_generation.retrieval import build_retrieval_sources


def test_unknown_social_entity_requires_clarification():
    analysis = LocalRecoveryCoordinator().analyze(
        "Ask Bran's sister Mira to join us.",
        retrieval_sources=build_retrieval_sources(),
    )

    assert analysis.intent.selected.affordance == "entity_search"
    plan = ForwardMotionPolicy().select(analysis)
    assert plan.strategy == "clarify_unknown_entity"
    assert plan.outcome == "clarification"


def test_unknown_travel_destination_still_offers_a_lead():
    analysis = LocalRecoveryCoordinator().analyze(
        "Travel to the sealed Royal Vault.",
        retrieval_sources=build_retrieval_sources(),
    )

    plan = ForwardMotionPolicy().select(analysis)
    assert plan.outcome == "lead"
    assert plan.strategy == "offer_investigation_lead"
