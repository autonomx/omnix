from app.rpg.session.runtime import apply_turn


def test_apply_turn_resolves_pending_companion_offer_before_semantic_action():
    session = {
        "id": "test_al_am_an7",
        "session_id": "test_al_am_an7",
        "simulation_state": {
            "player_state": {
                "location_id": "loc_tavern",
                "party_state": {
                    "companions": [],
                    "max_size": 3,
                },
            },
            "location_id": "loc_tavern",
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

    result = apply_turn(
        session=session,
        player_input="Yes. Let's go.",
    )

    conversation = result["conversation_result"]
    assert conversation["triggered"] is True
    assert conversation["reason"] == "pending_companion_offer_resolved"
    assert conversation["participation_mode"] == "companion_acceptance"

    acceptance = conversation["companion_acceptance_result"]
    assert acceptance["resolved"] is True
    assert acceptance["accepted"] is True
    assert acceptance["npc_id"] == "npc:Bran"

    companions = session["simulation_state"]["player_state"]["party_state"]["companions"]
    assert len(companions) == 1

    bran = companions[0]
    assert bran["npc_id"] == "npc:Bran"
    assert bran["name"] == "Bran"
    assert bran["role"] == "companion"
    assert bran["identity_arc"] == "revenge_after_losing_tavern"
    assert bran["current_role"] == "Displaced tavern keeper"