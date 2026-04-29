from app.rpg.party.party_composition import project_party_composition_effects
from app.rpg.world.companion_acceptance import (
    record_manual_companion_join_offer_for_test_or_runtime,
    resolve_pending_companion_offer_response,
)


def _base_state(max_size=2):
    return {
        "location_id": "loc_tavern",
        "player_state": {
            "location_id": "loc_tavern",
            "party_state": {
                "max_size": max_size,
                "companions": [],
            },
        },
    }


def _companion_ids(state):
    return [
        companion["npc_id"]
        for companion in state["player_state"]["party_state"]["companions"]
    ]


def test_multiple_pending_offers_require_specific_acceptance():
    state = _base_state(max_size=3)

    record_manual_companion_join_offer_for_test_or_runtime(
        state,
        npc_id="npc:Bran",
        name="Bran",
        identity_arc="revenge_after_losing_tavern",
        current_role="Displaced tavern keeper",
        tick=1,
    )
    record_manual_companion_join_offer_for_test_or_runtime(
        state,
        npc_id="npc:Mira",
        name="Mira",
        identity_arc="cautious_mediator",
        current_role="Cautious mediator",
        tick=2,
    )

    result = resolve_pending_companion_offer_response(
        state,
        player_input="Yes. Let's go.",
        tick=3,
    )

    assert result["resolved"] is False
    assert result["reason"] == "multiple_pending_offers_require_specific_npc"
    assert _companion_ids(state) == []


def test_specific_acceptance_accepts_only_named_companion():
    state = _base_state(max_size=3)

    record_manual_companion_join_offer_for_test_or_runtime(
        state,
        npc_id="npc:Bran",
        name="Bran",
        identity_arc="revenge_after_losing_tavern",
        current_role="Displaced tavern keeper",
        tick=1,
    )
    record_manual_companion_join_offer_for_test_or_runtime(
        state,
        npc_id="npc:Mira",
        name="Mira",
        identity_arc="cautious_mediator",
        current_role="Cautious mediator",
        tick=2,
    )

    result = resolve_pending_companion_offer_response(
        state,
        player_input="Yes, Mira can come.",
        tick=3,
    )

    assert result["resolved"] is True
    assert result["accepted"] is True
    assert result["npc_id"] == "npc:Mira"
    assert _companion_ids(state) == ["npc:Mira"]

    pending = state["conversation_thread_state"]["pending_companion_offers"]
    assert "npc:Bran" in pending
    assert "npc:Mira" not in pending


def test_party_limit_rejects_new_companion_when_full():
    state = _base_state(max_size=1)

    record_manual_companion_join_offer_for_test_or_runtime(
        state,
        npc_id="npc:Bran",
        name="Bran",
        identity_arc="revenge_after_losing_tavern",
        current_role="Displaced tavern keeper",
        tick=1,
    )
    accepted = resolve_pending_companion_offer_response(
        state,
        player_input="Yes, Bran can come.",
        tick=2,
    )
    assert accepted["accepted"] is True

    record_manual_companion_join_offer_for_test_or_runtime(
        state,
        npc_id="npc:Mira",
        name="Mira",
        identity_arc="cautious_mediator",
        current_role="Cautious mediator",
        tick=3,
    )
    rejected = resolve_pending_companion_offer_response(
        state,
        player_input="Yes, Mira can come.",
        tick=4,
    )

    assert rejected["resolved"] is True
    assert rejected["accepted"] is False
    assert rejected["reason"] == "party_full"
    assert _companion_ids(state) == ["npc:Bran"]


def test_party_composition_projects_bran_mira_tension():
    state = _base_state(max_size=3)
    state["player_state"]["party_state"]["companions"] = [
        {
            "npc_id": "npc:Bran",
            "name": "Bran",
            "role": "companion",
            "status": "active",
            "identity_arc": "revenge_after_losing_tavern",
            "current_role": "Vengeful companion tracking bandits",
        },
        {
            "npc_id": "npc:Mira",
            "name": "Mira",
            "role": "companion",
            "status": "active",
            "identity_arc": "cautious_mediator",
            "current_role": "Cautious mediator",
        },
    ]

    result = project_party_composition_effects(state)

    assert result["projected"] is True
    assert result["active_companion_count"] == 2
    kinds = {effect["kind"] for effect in result["effects"]}
    assert "companion_pair_tension" in kinds
    assert "multi_companion_party_context" in kinds
