from app.rpg.party.companion_memory import (
    companion_loyalty_projection,
    maybe_apply_companion_relationship_drift_from_player_input,
    record_companion_join_memory,
)
from app.rpg.party.companion_turns import maybe_build_direct_companion_turn_response
from app.rpg.party.companion_values import evaluate_companion_value_alignment


def _state_with_companion(npc_id="npc:Bran", name="Bran", identity_arc="revenge_after_losing_tavern"):
    return {
        "location_id": "loc_tavern",
        "player_state": {
            "location_id": "loc_tavern",
            "party_state": {
                "max_size": 3,
                "companions": [
                    {
                        "npc_id": npc_id,
                        "name": name,
                        "role": "companion",
                        "status": "active",
                        "follow_mode": "following_player",
                        "location_id": "loc_tavern",
                        "identity_arc": identity_arc,
                        "current_role": "Displaced tavern keeper" if npc_id == "npc:Bran" else "Companion",
                    }
                ],
            },
        },
    }


def test_bran_dislikes_dismissed_tavern_loss():
    state = _state_with_companion()

    alignment = evaluate_companion_value_alignment(
        state,
        npc_id="npc:Bran",
        player_input="Bran, forget the bandits. Your tavern does not matter now.",
    )

    assert alignment["matched"] is True
    assert alignment["alignment"] == "conflicts_with_npc"
    assert alignment["deltas"]["loyalty_delta"] == -1
    assert alignment["reason"] == "player_dismissed_companion_core_motivation"


def test_bran_likes_promise_to_find_bandits():
    state = _state_with_companion()

    alignment = evaluate_companion_value_alignment(
        state,
        npc_id="npc:Bran",
        player_input="Bran, we will find the bandits who destroyed your tavern.",
    )

    assert alignment["matched"] is True
    assert alignment["alignment"] == "aligned_with_npc"
    assert alignment["deltas"]["loyalty_delta"] == 1
    assert alignment["reason"] == "player_supported_companion_core_motivation"


def test_thief_likes_theft_guard_dislikes_theft():
    thief_state = _state_with_companion(npc_id="npc:Shade", name="Shade", identity_arc="")
    guard_state = _state_with_companion(npc_id="npc:Aldric", name="Aldric", identity_arc="")

    thief = evaluate_companion_value_alignment(
        thief_state,
        npc_id="npc:Shade",
        player_input="Shade, I steal the purse and slip away from the guards.",
    )
    guard = evaluate_companion_value_alignment(
        guard_state,
        npc_id="npc:Aldric",
        player_input="Aldric, I steal the purse and slip away from the guards.",
    )

    assert thief["matched"] is True
    assert thief["alignment"] == "aligned_with_npc"

    assert guard["matched"] is True
    assert guard["alignment"] == "conflicts_with_npc"
    assert guard["deltas"]["loyalty_delta"] == -1


def test_join_memory_is_recorded_for_bran():
    state = _state_with_companion()

    result = record_companion_join_memory(
        state,
        npc_id="npc:Bran",
        tick=1,
    )

    assert result["recorded"] is True
    assert result["memory"]["kind"] == "companion_joined_party"
    assert "Rusty Flagon" in result["memory"]["summary"]


def test_personality_aware_drift_changes_loyalty_and_memory():
    state = _state_with_companion()

    result = maybe_apply_companion_relationship_drift_from_player_input(
        state,
        player_input="Bran, forget the bandits. Your tavern does not matter now.",
        tick=2,
    )

    assert result["applied"] is True
    primary = result["primary"]
    assert primary["alignment"]["alignment"] == "conflicts_with_npc"

    rel = state["companion_memory_state"]["relationship_by_npc"]["npc:Bran"]
    assert rel["loyalty"] == -1
    assert rel["morale"] == -1
    assert rel["loyalty_state"] == "strained"

    memories = state["companion_memory_state"]["by_npc"]["npc:Bran"]["memories"]
    assert any(mem["kind"] == "player_dismissed_core_motivation" for mem in memories)


def test_direct_response_changes_with_loyalty_state():
    state = _state_with_companion()

    maybe_apply_companion_relationship_drift_from_player_input(
        state,
        player_input="Bran, forget the bandits. Your tavern does not matter now.",
        tick=2,
    )

    strained = maybe_build_direct_companion_turn_response(
        state,
        player_input="Bran, what do you think we should do next?",
        tick=3,
    )

    assert strained["matched"] is True
    assert strained["companion_loyalty_projection"]["loyalty_state"] == "strained"
    assert "matters" in strained["line"].lower()

    maybe_apply_companion_relationship_drift_from_player_input(
        state,
        player_input="Bran, we will find the bandits who destroyed your tavern.",
        tick=4,
    )

    steady = maybe_build_direct_companion_turn_response(
        state,
        player_input="Bran, what do you think we should do next?",
        tick=5,
    )

    assert steady["matched"] is True
    assert steady["companion_loyalty_projection"]["loyalty_state"] == "steady"


def test_loyalty_projection_thresholds():
    state = _state_with_companion()

    for i in range(3):
        maybe_apply_companion_relationship_drift_from_player_input(
            state,
            player_input="Bran, we will find the bandits who destroyed your tavern.",
            tick=i + 1,
        )

    projection = companion_loyalty_projection(state, npc_id="npc:Bran")
    assert projection["loyalty_state"] == "loyal"
    assert projection["response_bias"] == "volunteers_support"
