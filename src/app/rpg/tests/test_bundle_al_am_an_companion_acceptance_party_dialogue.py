from app.rpg.world.npc_evolution_triggers import evolve_npcs_from_world_event
from app.rpg.world.npc_reputation_state import update_npc_reputation
from app.rpg.world.companion_join_intent import maybe_create_companion_join_intent
from app.rpg.world.companion_acceptance import (
    record_companion_join_offer,
    resolve_companion_acceptance,
)
from app.rpg.world.companion_dialogue import build_companion_join_dialogue


def _bran_lost_tavern_state():
    state = {}
    evolve_npcs_from_world_event(
        state,
        world_event={
            "event_id": "event:test:bandit_attack",
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


def test_companion_offer_is_pending_until_player_accepts():
    state = _bran_lost_tavern_state()

    intent = maybe_create_companion_join_intent(
        state,
        npc_id="npc:Bran",
        player_input="Come with me and help me find the bandits.",
    )
    assert intent["offered"] is True
    assert intent["requires_player_acceptance"] is True

    offer = record_companion_join_offer(
        state,
        npc_id="npc:Bran",
        join_intent=intent,
        tick=12,
    )
    assert offer["recorded"] is True

    party_before = state.get("player_state", {}).get("party_state", {}).get("companions", [])
    assert party_before == []

    unresolved = resolve_companion_acceptance(
        state,
        npc_id="npc:Bran",
        player_input="What do you need before we go?",
        tick=13,
    )
    assert unresolved["resolved"] is False
    assert unresolved["reason"] == "player_response_did_not_resolve_offer"


def test_player_acceptance_adds_bran_to_party_with_arc_metadata():
    state = _bran_lost_tavern_state()

    intent = maybe_create_companion_join_intent(
        state,
        npc_id="npc:Bran",
        player_input="Come with me and help me find the bandits.",
    )
    record_companion_join_offer(
        state,
        npc_id="npc:Bran",
        join_intent=intent,
        tick=12,
    )

    accepted = resolve_companion_acceptance(
        state,
        npc_id="npc:Bran",
        player_input="Yes. Let's go.",
        tick=13,
    )

    assert accepted["resolved"] is True
    assert accepted["accepted"] is True

    companions = state["player_state"]["party_state"]["companions"]
    assert len(companions) == 1
    assert companions[0]["npc_id"] == "npc:Bran"
    assert companions[0]["role"] == "companion"
    assert companions[0]["identity_arc"] == "revenge_after_losing_tavern"
    assert companions[0]["current_role"] == "Displaced tavern keeper"


def test_player_rejection_does_not_add_companion():
    state = _bran_lost_tavern_state()

    intent = maybe_create_companion_join_intent(
        state,
        npc_id="npc:Bran",
        player_input="Come with me and help me find the bandits.",
    )
    record_companion_join_offer(
        state,
        npc_id="npc:Bran",
        join_intent=intent,
        tick=12,
    )

    rejected = resolve_companion_acceptance(
        state,
        npc_id="npc:Bran",
        player_input="No, stay here for now.",
        tick=13,
    )

    assert rejected["resolved"] is True
    assert rejected["rejected"] is True
    assert state.get("player_state", {}).get("party_state", {}).get("companions", []) == []


def test_companion_join_dialogue_uses_revenge_arc():
    state = _bran_lost_tavern_state()

    intent = maybe_create_companion_join_intent(
        state,
        npc_id="npc:Bran",
        player_input="Come with me and help me find the bandits.",
    )
    record_companion_join_offer(
        state,
        npc_id="npc:Bran",
        join_intent=intent,
        tick=12,
    )
    accepted = resolve_companion_acceptance(
        state,
        npc_id="npc:Bran",
        player_input="Yes. Let's go.",
        tick=13,
    )

    dialogue = build_companion_join_dialogue(
        npc_id="npc:Bran",
        npc_name="Bran",
        acceptance_result=accepted,
    )

    assert dialogue["created"] is True
    assert "bandits" in dialogue["line"].lower()
    assert dialogue["beat"]["kind"] == "companion_join_dialogue"
