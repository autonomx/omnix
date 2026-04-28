from app.rpg.world.companion_acceptance import record_companion_join_offer
from app.rpg.world.companion_join_intent import maybe_create_companion_join_intent
from app.rpg.world.conversation_threads import maybe_advance_conversation_thread
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
            "event_id": "event:test:bandit_attack_gate_runtime",
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


def test_maybe_advance_conversation_resolves_pending_companion_offer_before_gate():
    state = _bran_lost_tavern_state()

    intent = maybe_create_companion_join_intent(
        state,
        npc_id="npc:Bran",
        player_input="Bran, come with me and help me find the bandits.",
    )
    assert intent["offered"] is True

    record_companion_join_offer(
        state,
        npc_id="npc:Bran",
        join_intent=intent,
        tick=12,
    )

    result = maybe_advance_conversation_thread(
        state,
        player_input="Yes. Let's go.",
        tick=13,
        settings={
            "enabled": True,
            "companion_acceptance_enabled": True,
            "companion_dialogue_enabled": True,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0,
        },
        autonomous=False,
        force=False,
    )

    assert result["triggered"] is True
    assert result["reason"] == "pending_companion_offer_resolved"
    assert result["participation_mode"] == "companion_acceptance"

    acceptance = result["companion_acceptance_result"]
    assert acceptance["resolved"] is True
    assert acceptance["accepted"] is True
    assert acceptance["reason"] == "player_accepted_companion_offer"

    companions = state["player_state"]["party_state"]["companions"]
    assert len(companions) == 1

    bran = companions[0]
    assert bran["npc_id"] == "npc:Bran"
    assert bran["name"] == "Bran"
    assert bran["role"] == "companion"
    assert bran["identity_arc"] == "revenge_after_losing_tavern"
    assert bran["current_role"] == "Displaced tavern keeper"