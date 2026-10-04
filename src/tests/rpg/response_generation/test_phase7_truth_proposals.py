from __future__ import annotations

import json

from app.rpg.response_generation.proposal_policy import (
    ProposalBudget,
    ProposalDecision,
    ProposalPolicy,
    ProposalRisk,
    ProposalStore,
    WorldProposal,
)
from app.rpg.response_generation.truth_lifetime import (
    SoftTruthRecord,
    TruthClass,
    TruthLifetime,
)


def _proposal(
    proposal_id: str,
    *,
    risk: ProposalRisk = ProposalRisk.LOW,
    lifetime: TruthLifetime = TruthLifetime.TURN,
    created_turn: int = 10,
    scene_id: str = "tavern",
    **overrides,
) -> WorldProposal:
    values = {
        "proposal_id": proposal_id,
        "proposal_type": "rumor_lead",
        "summary": f"Lead {proposal_id}",
        "risk": risk,
        "requested_lifetime": lifetime,
        "source": "hermes_recovery",
        "seed": "campaign-seed-7",
        "provenance_refs": ("evidence.local",),
        "scene_id": scene_id,
        "created_turn": created_turn,
        "created_turn_id": f"turn-{created_turn}",
        "confidence": 0.7,
    }
    values.update(overrides)
    return WorldProposal(**values)


def test_phase7_generated_details_are_turn_scoped_by_default():
    result = ProposalPolicy().evaluate(
        _proposal("turn-detail"),
        turn_id="turn-10",
    )

    assert result.decision is ProposalDecision.ACCEPT_TURN
    assert result.truth is not None
    assert result.truth.lifetime is TruthLifetime.TURN
    assert result.truth.truth_class is TruthClass.GENERATED_PROPOSAL
    assert result.truth.metadata["acceptance_reason"].startswith("accepted as ephemeral")
    assert result.event is None


def test_phase7_medium_risk_and_requested_scene_details_remain_scene_scoped():
    medium = ProposalPolicy().evaluate(
        _proposal("medium", risk=ProposalRisk.MEDIUM),
        turn_id="turn-10",
    )
    requested = ProposalPolicy().evaluate(
        _proposal("scene", lifetime=TruthLifetime.SCENE),
        turn_id="turn-10",
    )

    assert medium.decision is ProposalDecision.ACCEPT_SCENE
    assert medium.truth is not None and medium.truth.lifetime is TruthLifetime.SCENE
    assert requested.truth is not None and requested.truth.lifetime is TruthLifetime.SCENE
    assert medium.truth.expires_turn == 74


def test_phase7_persistence_requires_interaction_relevance_director_or_resolver():
    policy = ProposalPolicy()
    unearned = policy.evaluate(
        _proposal("unearned", lifetime=TruthLifetime.PERSISTENT),
        turn_id="turn-10",
    )
    interacted = policy.evaluate(
        _proposal(
            "interacted",
            lifetime=TruthLifetime.PERSISTENT,
            player_interactions=1,
        ),
        turn_id="turn-10",
    )
    repeated = policy.evaluate(
        _proposal(
            "repeated",
            lifetime=TruthLifetime.PERSISTENT,
            relevance_count=3,
        ),
        turn_id="turn-10",
    )
    directed = policy.evaluate(
        _proposal(
            "directed",
            lifetime=TruthLifetime.PERSISTENT,
            director_approved=True,
        ),
        turn_id="turn-10",
    )

    assert unearned.truth is not None
    assert unearned.truth.lifetime is TruthLifetime.SCENE
    for result in (interacted, repeated, directed):
        assert result.decision is ProposalDecision.PROMOTE_PERSISTENT
        assert result.truth is not None and result.truth.persistent
        assert result.event is not None
        assert result.truth.promotion_history
        assert result.truth.promotion_history[-1].event_id == result.event.event_id


def test_phase7_high_risk_persistence_requires_approved_deterministic_resolver():
    policy = ProposalPolicy()
    rejected = policy.evaluate(
        _proposal(
            "high-risk-rejected",
            risk=ProposalRisk.HIGH,
            lifetime=TruthLifetime.PERSISTENT,
            player_interactions=2,
        ),
        turn_id="turn-10",
    )
    accepted = policy.evaluate(
        _proposal(
            "high-risk-accepted",
            risk=ProposalRisk.HIGH,
            lifetime=TruthLifetime.PERSISTENT,
            resolver_name="quest_seed_resolver",
            resolver_approved=True,
        ),
        turn_id="turn-10",
    )

    assert rejected.truth is not None
    assert rejected.truth.lifetime is TruthLifetime.TURN
    assert rejected.event is None
    assert accepted.decision is ProposalDecision.PROMOTE_PERSISTENT
    assert accepted.event is not None
    assert accepted.event.resolver_name == "quest_seed_resolver"


def test_phase7_duplicate_inconsistent_and_hidden_proposals_fail_closed():
    policy = ProposalPolicy()
    accepted = policy.evaluate(_proposal("first"), turn_id="turn-10")
    assert accepted.truth is not None
    existing = (accepted.truth,)
    duplicate = policy.evaluate(
        _proposal("second", dedupe_key=accepted.truth.metadata["dedupe_key"]),
        existing=existing,
        turn_id="turn-10",
    )
    inconsistent = policy.evaluate(
        _proposal("bad", world_consistent=False),
        turn_id="turn-10",
    )
    hidden = policy.evaluate(
        _proposal("hidden", visibility="hidden"),
        turn_id="turn-10",
    )

    assert duplicate.decision is ProposalDecision.REJECT_DUPLICATE
    assert inconsistent.decision is ProposalDecision.REJECT_INCONSISTENT
    assert hidden.decision is ProposalDecision.REJECT_HIDDEN
    assert duplicate.truth is inconsistent.truth is hidden.truth is None


def test_phase7_budgets_bound_turn_scene_and_campaign_growth():
    policy = ProposalPolicy(ProposalBudget(max_turn=1, max_scene=1, max_persistent=1))
    turn_truth = policy.evaluate(_proposal("turn-one"), turn_id="turn-10").truth
    scene_truth = policy.evaluate(
        _proposal("scene-one", lifetime=TruthLifetime.SCENE),
        turn_id="turn-10",
    ).truth
    persistent_truth = policy.evaluate(
        _proposal(
            "persistent-one",
            lifetime=TruthLifetime.PERSISTENT,
            player_interactions=1,
        ),
        turn_id="turn-10",
    ).truth
    existing = tuple(row for row in (turn_truth, scene_truth, persistent_truth) if row)

    assert policy.evaluate(
        _proposal("turn-two", dedupe_key="turn-two"),
        existing=existing,
        turn_id="turn-10",
    ).decision is ProposalDecision.REJECT_BUDGET
    assert policy.evaluate(
        _proposal("scene-two", lifetime=TruthLifetime.SCENE, dedupe_key="scene-two"),
        existing=existing,
        turn_id="turn-10",
    ).decision is ProposalDecision.REJECT_BUDGET
    assert policy.evaluate(
        _proposal(
            "persistent-two",
            lifetime=TruthLifetime.PERSISTENT,
            player_interactions=1,
            dedupe_key="persistent-two",
        ),
        existing=existing,
        turn_id="turn-10",
    ).decision is ProposalDecision.REJECT_BUDGET


def test_phase7_store_save_load_is_idempotent_and_replay_stable():
    result = ProposalPolicy().evaluate(
        _proposal(
            "persistent",
            lifetime=TruthLifetime.PERSISTENT,
            player_interactions=1,
        ),
        turn_id="turn-10",
    )
    store = ProposalStore()

    assert store.apply(result) is True
    assert store.apply(result) is False
    first_payload = store.as_dict()
    restored = ProposalStore.from_dict(json.loads(json.dumps(first_payload)))
    second_payload = restored.as_dict()

    assert first_payload == second_payload
    assert len(restored.truths) == 1
    assert len(restored.promotion_events) == 1
    assert next(iter(restored.promotion_events)) == result.event.event_id


def test_phase7_garbage_collection_expires_turn_and_scene_but_keeps_persistent():
    store = ProposalStore(
        truths={
            "turn": SoftTruthRecord(
                "turn",
                TruthClass.INFERENCE,
                "turn detail",
                created_turn=5,
                lifetime=TruthLifetime.TURN,
            ),
            "scene": SoftTruthRecord(
                "scene",
                TruthClass.RUMOR,
                "scene detail",
                created_turn=5,
                scene_id="old-scene",
                lifetime=TruthLifetime.SCENE,
            ),
            "persistent": SoftTruthRecord(
                "persistent",
                TruthClass.RETRIEVED_LORE,
                "persistent detail",
                created_turn=5,
                lifetime=TruthLifetime.PERSISTENT,
            ),
        }
    )

    removed = store.garbage_collect(current_turn=6, scene_id="new-scene")

    assert removed == ("scene", "turn")
    assert set(store.truths) == {"persistent"}


def test_phase7_event_identity_is_deterministic_for_replay():
    proposal = _proposal(
        "stable",
        lifetime=TruthLifetime.PERSISTENT,
        player_interactions=1,
    )
    first = ProposalPolicy().evaluate(proposal, turn_id="turn-10")
    second = ProposalPolicy().evaluate(proposal, turn_id="turn-10")

    assert first.event == second.event
    assert first.truth == second.truth
