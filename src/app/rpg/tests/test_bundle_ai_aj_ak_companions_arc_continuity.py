from app.rpg.world.companion_join_intent import maybe_create_companion_join_intent
from app.rpg.world.npc_arc_continuity import update_npc_arc_continuity
from app.rpg.world.npc_evolution_triggers import evolve_npcs_from_world_event
from app.rpg.world.npc_party_eligibility import evaluate_npc_party_join_eligibility
from app.rpg.world.npc_reputation_state import update_npc_reputation


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


def test_bran_party_eligible_after_losing_tavern_with_trust():
    state = _bran_lost_tavern_state()
    result = evaluate_npc_party_join_eligibility(state, npc_id="npc:Bran")

    assert result["eligible"] is True
    assert result["npc_id"] == "npc:Bran"
    assert result["identity_arc"] == "revenge_after_losing_tavern"


def test_companion_join_intent_requires_request():
    state = _bran_lost_tavern_state()

    no_request = maybe_create_companion_join_intent(
        state,
        npc_id="npc:Bran",
        player_input="What will you do now?",
    )
    assert no_request["offered"] is False
    assert no_request["requested"] is False

    requested = maybe_create_companion_join_intent(
        state,
        npc_id="npc:Bran",
        player_input="Come with me and help me find the bandits.",
    )
    assert requested["offered"] is True
    assert requested["requires_player_acceptance"] is True


def test_arc_continuity_tracks_revenge_arc():
    state = _bran_lost_tavern_state()
    result = update_npc_arc_continuity(
        state,
        npc_id="npc:Bran",
        tick=12,
    )

    assert result["updated"] is True
    arc = state["npc_arc_continuity_state"]["by_npc"]["npc:Bran"]
    assert arc["identity_arc"] == "revenge_after_losing_tavern"
    assert "bandits" in arc["active_motivation_summary"].lower()


def test_dialogue_profile_projects_evolution_modifiers():
    from app.rpg.world.npc_dialogue_profile import build_npc_dialogue_profile
    from app.rpg.world.npc_evolution_state import apply_npc_evolution_event

    state = {}
    apply_npc_evolution_event(
        state,
        npc_id="npc:Bran",
        event_id="event:test:loyal",
        kind="trust_threshold",
        personality_modifier={
            "trait": "loyal_to_player",
            "strength": 1,
            "reason": "The player earned trust.",
        },
        tick=5,
    )

    profile = build_npc_dialogue_profile(
        npc_id="npc:Bran",
        simulation_state=state,
        runtime_state={"tick": 6},
        topic={},
        listener_id="player",
        response_intent="answer",
    )

    assert any("loyal" in str(mod).lower() for mod in profile["personality_modifiers"])
