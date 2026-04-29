from app.rpg.party.companion_quests import (
    companion_quest_summary,
    maybe_progress_companion_quest_from_player_input,
    seed_companion_quest_from_arc,
)
from app.rpg.party.companion_turns import maybe_build_direct_companion_turn_response


def _state_with_bran_companion():
    return {
        "location_id": "loc_tavern",
        "player_state": {
            "location_id": "loc_tavern",
            "party_state": {
                "max_size": 3,
                "companions": [
                    {
                        "npc_id": "npc:Bran",
                        "name": "Bran",
                        "role": "companion",
                        "status": "active",
                        "follow_mode": "following_player",
                        "location_id": "loc_tavern",
                        "identity_arc": "revenge_after_losing_tavern",
                        "current_role": "Displaced tavern keeper",
                    }
                ],
            },
        },
        "npc_evolution_state": {
            "by_npc": {
                "npc:Bran": {
                    "npc_id": "npc:Bran",
                    "identity_arc": "revenge_after_losing_tavern",
                    "current_role": "Displaced tavern keeper",
                }
            }
        },
    }


def test_seed_bran_revenge_quest_from_arc():
    state = _state_with_bran_companion()

    result = seed_companion_quest_from_arc(
        state,
        npc_id="npc:Bran",
        tick=1,
    )

    assert result["seeded"] is True
    quest = result["quest"]
    assert quest["quest_id"] == "companion_bran_revenge"
    assert quest["stage"] == "find_bandit_leads"
    assert quest["source_arc"] == "revenge_after_losing_tavern"


def test_progress_to_follow_bandit_lead_from_rumor_search():
    state = _state_with_bran_companion()
    seed_companion_quest_from_arc(state, npc_id="npc:Bran", tick=1)

    result = maybe_progress_companion_quest_from_player_input(
        state,
        player_input="Bran, we ask around for rumors about the bandits who burned your tavern.",
        tick=2,
    )

    assert result["progressed"] is True
    progress = result["progress"]
    assert progress["quest"]["stage"] == "follow_bandit_lead"

    quest = state["companion_quest_state"]["by_quest"]["companion_bran_revenge"]
    assert quest["stage"] == "follow_bandit_lead"


def test_progress_to_track_bandits_from_tracks():
    state = _state_with_bran_companion()
    seed_companion_quest_from_arc(state, npc_id="npc:Bran", tick=1)
    maybe_progress_companion_quest_from_player_input(
        state,
        player_input="Bran, we ask around for rumors about the bandits who burned your tavern.",
        tick=2,
    )

    result = maybe_progress_companion_quest_from_player_input(
        state,
        player_input="Bran, we follow the bandit tracks into the woods.",
        tick=3,
    )

    assert result["progressed"] is True
    assert result["progress"]["quest"]["stage"] == "track_bandits"

    bran = state["player_state"]["party_state"]["companions"][0]
    assert bran["arc_stage"] == "track_bandits"
    assert bran["current_role"] == "Vengeful companion tracking bandits"


def test_prevent_skipping_companion_quest_stage():
    state = _state_with_bran_companion()
    seed_companion_quest_from_arc(state, npc_id="npc:Bran", tick=1)

    result = maybe_progress_companion_quest_from_player_input(
        state,
        player_input="Bran, we follow the bandit tracks into the woods.",
        tick=2,
    )

    assert result["progressed"] is False
    assert result["progress"]["reason"] == "quest_stage_skip_blocked"


def test_direct_companion_response_uses_quest_stage():
    state = _state_with_bran_companion()
    seed_companion_quest_from_arc(state, npc_id="npc:Bran", tick=1)
    maybe_progress_companion_quest_from_player_input(
        state,
        player_input="Bran, we ask around for rumors about the bandits who burned your tavern.",
        tick=2,
    )

    response = maybe_build_direct_companion_turn_response(
        state,
        player_input="Bran, what do you think we should do next?",
        tick=3,
    )

    assert response["matched"] is True
    assert response["active_companion_quest"]["stage"] == "follow_bandit_lead"
    assert response["npc_response_beat"]["companion_quest_stage"] == "follow_bandit_lead"
    assert "rumors" in response["line"].lower() or "lead" in response["line"].lower()


def test_companion_quest_summary_for_bran():
    state = _state_with_bran_companion()
    seed_companion_quest_from_arc(state, npc_id="npc:Bran", tick=1)

    summary = companion_quest_summary(state, npc_id="npc:Bran")

    assert summary["npc_id"] == "npc:Bran"
    assert summary["quests"][0]["quest_id"] == "companion_bran_revenge"
    assert summary["events"][0]["kind"] == "companion_quest_seeded"
