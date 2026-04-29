from app.rpg.party.companion_quests import (
    companion_quest_summary,
    maybe_progress_companion_quest_from_player_input,
    seed_companion_quest_from_arc,
)
from app.rpg.session.runtime import (
    _sync_session_if_companion_runtime_mutated,
)


def _session_with_bran_quest():
    return {
        "id": "test_ax_ay_az1",
        "session_id": "test_ax_ay_az1",
        "simulation_state": {
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
        },
        "setup_payload": {"metadata": {"simulation_state": {}}},
    }


def test_companion_quest_progress_syncs_to_session_metadata(monkeypatch):
    saved_sessions = []

    def fake_save_session(session):
        saved_sessions.append(session.copy())

    import app.rpg.session.service as session_service

    monkeypatch.setattr(session_service, "save_session", fake_save_session)

    session = _session_with_bran_quest()
    sim = session["simulation_state"]

    seed_companion_quest_from_arc(sim, npc_id="npc:Bran", tick=1)
    progress = maybe_progress_companion_quest_from_player_input(
        sim,
        player_input="Bran, we ask around for rumors about the bandits who burned your tavern.",
        tick=2,
    )

    assert progress["progressed"] is True
    assert progress["progress"]["quest"]["stage"] == "follow_bandit_lead"

    session = _sync_session_if_companion_runtime_mutated(
        session,
        sim,
        reason="test_companion_quest_progress",
        companion_quest_progress_result=progress,
    )

    metadata_sim = session["setup_payload"]["metadata"]["simulation_state"]
    metadata_summary = companion_quest_summary(metadata_sim, npc_id="npc:Bran")
    assert metadata_summary["quests"][0]["stage"] == "follow_bandit_lead"

    assert saved_sessions
    saved_sim = saved_sessions[-1]["simulation_state"]
    saved_summary = companion_quest_summary(saved_sim, npc_id="npc:Bran")
    assert saved_summary["quests"][0]["stage"] == "follow_bandit_lead"