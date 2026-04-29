from app.rpg.session.runtime import apply_turn


def test_companion_acceptance_early_return_persists_party_state(monkeypatch):
    saved_sessions = []

    def fake_save_session(session):
        saved_sessions.append(session.copy())

    import app.rpg.session.service as session_service

    monkeypatch.setattr(session_service, "save_session", fake_save_session)

    session = {
        "id": "test_ao_ap_aq1",
        "session_id": "test_ao_ap_aq1",
        "simulation_state": {
            "location_id": "loc_tavern",
            "player_state": {
                "location_id": "loc_tavern",
                "party_state": {
                    "companions": [],
                    "max_size": 3,
                },
            },
            "npc_evolution_state": {
                    "by_npc": {
                        "npc:Bran": {
                            "npc_id": "npc:Bran",
                            "name": "Bran",
                            "current_role": "Displaced tavern keeper",
                            "identity_arc": "revenge_after_losing_tavern",
                            "active_motivations": [
                                {
                                    "kind": "revenge",
                                    "summary": "Find the bandits who destroyed his tavern.",
                                    "strength": 4,
                                }
                            ],
                            "party_join_eligibility": {
                                "eligible": True,
                                "requires_player_trust": 0,
                                "reason": "lost_home_and_has_revenge_motivation",
                            },
                        }
                    }
            },
            "conversation_thread_state": {
                "pending_companion_offers": {
                    "npc:Bran": {
                        "offer_id": "companion_offer:npc:Bran:527",
                        "npc_id": "npc:Bran",
                        "created_tick": 527,
                        "status": "pending_player_acceptance",
                        "reason": "lost_home_and_has_revenge_motivation",
                        "party_join_eligibility_result": {
                            "eligible": True,
                            "npc_id": "npc:Bran",
                            "name": "Bran",
                            "identity_arc": "revenge_after_losing_tavern",
                            "current_role": "Displaced tavern keeper",
                            "active_motivations": [
                                {
                                    "kind": "revenge",
                                    "summary": "Find the bandits who destroyed his tavern.",
                                    "strength": 4,
                                }
                            ],
                        },
                        "source": "deterministic_companion_acceptance",
                    }
                }
            },
        },
        "setup_payload": {
            "metadata": {
                "simulation_state": {},
            }
        },
    }

    import app.rpg.session.runtime as runtime

    def fake_load_session(session_id):
        return session

    monkeypatch.setattr(runtime, "load_runtime_session", fake_load_session)

    result = apply_turn(
        session_id="test_ao_ap_aq1",
        player_input="let's go",
    )

    assert result["conversation_result"]["reason"] == "pending_companion_offer_resolved"
    assert result["conversation_result"]["companion_acceptance_result"]["accepted"]

    companions = session["simulation_state"]["player_state"]["party_state"]["companions"]
    assert len(companions) == 1
    assert companions[0]["npc_id"] == "npc:Bran"
    assert companions[0]["follow_mode"] == "following_player"
    assert companions[0]["location_id"] == "loc_tavern"

    metadata_sim = session["setup_payload"]["metadata"]["simulation_state"]
    metadata_companions = metadata_sim["player_state"]["party_state"]["companions"]
    assert len(metadata_companions) == 1
    assert metadata_companions[0]["npc_id"] == "npc:Bran"

    assert saved_sessions, "early companion acceptance path should save session"
    saved_sim = saved_sessions[-1]["simulation_state"]
    saved_companions = saved_sim["player_state"]["party_state"]["companions"]
    assert len(saved_companions) == 1
    assert saved_companions[0]["npc_id"] == "npc:Bran"