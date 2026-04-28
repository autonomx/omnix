from copy import deepcopy

from app.rpg.world.companion_acceptance import (
    record_companion_join_offer,
    resolve_pending_companion_offer_response,
)
from app.rpg.world.companion_join_intent import maybe_create_companion_join_intent
from app.rpg.world.npc_evolution_triggers import evolve_npcs_from_world_event
from app.rpg.world.npc_reputation_state import update_npc_reputation


def _bran_lost_tavern_state():
    state = {
        "player_state": {
            "location_id": "loc_tavern",
        },
        "location_id": "loc_tavern",
    }

    evolve_npcs_from_world_event(
        state,
        world_event={
            "event_id": "event:test:bandit_attack_persistence",
            "kind": "location_destroyed",
            "location_id": "loc_tavern",
            "summary": "Bandits attacked and burned the Rusty Flagon.",
            "affected_npcs": ["npc:Bran"],
        },
        tick=10,
    )

    update_npc_reputation(
        state,
        npc_id="npc:Bran",
        tick=11,
        familiarity_delta=3,
        trust_delta=2,
        respect_delta=2,
        reason="test",
    )

    return state


def test_pending_offer_can_be_hydrated_from_conversation_thread_state():
    state = _bran_lost_tavern_state()

    intent = maybe_create_companion_join_intent(
        state,
        npc_id="npc:Bran",
        player_input="Bran, come with me and help me find the bandits.",
    )
    assert intent["offered"] is True

    record = record_companion_join_offer(
        state,
        npc_id="npc:Bran",
        join_intent=intent,
        tick=12,
    )
    assert record["recorded"] is True

    assert "npc:Bran" in state["companion_acceptance_state"]["pending_offers"]
    assert "npc:Bran" in state["conversation_thread_state"]["pending_companion_offers"]

    # Simulate a persistence layer that keeps conversation_thread_state but drops
    # the top-level companion_acceptance_state. The resolver must still hydrate.
    next_turn_state = deepcopy(state)
    next_turn_state.pop("companion_acceptance_state", None)

    accepted = resolve_pending_companion_offer_response(
        next_turn_state,
        player_input="Yes. Let's go.",
        tick=13,
    )

    assert accepted["resolved"] is True
    assert accepted["accepted"] is True
    assert accepted["reason"] == "player_accepted_companion_offer"

    companions = next_turn_state["player_state"]["party_state"]["companions"]
    assert len(companions) == 1

    bran = companions[0]
    assert bran["npc_id"] == "npc:Bran"
    assert bran["name"] == "Bran"
    assert bran["role"] == "companion"
    assert bran["identity_arc"] == "revenge_after_losing_tavern"
    assert bran["current_role"] == "Displaced tavern keeper"

    assert "npc:Bran" not in next_turn_state["companion_acceptance_state"]["pending_offers"]
    assert "npc:Bran" not in next_turn_state["conversation_thread_state"]["pending_companion_offers"]