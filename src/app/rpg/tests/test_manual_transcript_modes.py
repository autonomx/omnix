from tests.rpg import manual_llm_transcript as transcript


def test_extract_service_debug_prefers_resolved_applied_service_result():
    result = {
        "session": {
            "runtime_state": {
                "last_turn_contract": {
                    "service_result": {
                        "matched": True,
                        "kind": "service_purchase",
                        "status": "purchase_ready",
                        "purchase": {"applied": False},
                    },
                    "resolved_result": {
                        "service_result": {
                            "matched": True,
                            "kind": "service_purchase",
                            "status": "purchased",
                            "purchase": {"applied": True},
                        },
                        "service_application": {
                            "applied": True,
                            "transaction_record": {"transaction_id": "txn:test"},
                        },
                    },
                    "presentation": {},
                }
            }
        }
    }

    debug = transcript._extract_service_debug(result)

    assert debug["service_result"]["status"] == "purchased"
    assert debug["purchase"]["applied"] is True
    assert debug["service_application"]["applied"] is True
    assert debug["transaction_record"]["transaction_id"] == "txn:test"


def test_extract_transaction_history_includes_current_turn_record():
    result = {
        "session": {
            "setup_payload": {
                "metadata": {
                    "simulation_state": {
                        "transaction_history": [],
                    }
                }
            },
            "runtime_state": {
                "last_turn_contract": {
                    "resolved_result": {
                        "service_result": {
                            "matched": True,
                            "kind": "service_purchase",
                            "status": "purchased",
                            "purchase": {"applied": True},
                        },
                        "service_application": {
                            "applied": True,
                            "transaction_record": {
                                "transaction_id": "txn:test",
                                "kind": "service_purchase",
                            },
                        },
                        "transaction_record": {
                            "transaction_id": "txn:test",
                            "kind": "service_purchase",
                        },
                    },
                    "presentation": {},
                }
            },
        }
    }

    history = transcript._extract_transaction_history(result)

    assert len(history) == 1
    assert history[0]["transaction_id"] == "txn:test"


def test_living_world_extractors_include_current_turn_application_fields():
    result = {
        "session": {
            "setup_payload": {
                "metadata": {
                    "simulation_state": {
                        "memory_state": {"service_memories": []},
                        "relationship_state": {
                            "npc:Elara::player": {"axes": {}},
                        },
                        "npc_emotion_state": {},
                        "service_offer_state": {},
                    }
                }
            },
            "runtime_state": {
                "last_turn_contract": {
                    "resolved_result": {
                        "service_result": {
                            "matched": True,
                            "kind": "service_purchase",
                            "status": "purchased",
                            "selected_offer_id": "elara_torch",
                            "purchase": {"applied": True},
                        },
                        "service_application": {
                            "applied": True,
                            "memory_entry": {
                                "memory_id": "memory:test",
                                "kind": "service_purchase",
                            },
                            "social_effects": {
                                "relationship_key": "npc:Elara::player",
                                "relationship": {
                                    "owner_id": "npc:Elara",
                                    "subject_id": "player",
                                    "axes": {
                                        "familiarity": 1.0,
                                        "trust": 0.25,
                                        "annoyance": 0.0,
                                    },
                                },
                                "emotion": {
                                    "owner_id": "npc:Elara",
                                    "dominant_emotion": "neutral",
                                    "valence": 0.1,
                                    "arousal": 0.05,
                                },
                            },
                            "stock_update": {
                                "offer_id": "elara_torch",
                                "runtime_state": {
                                    "offer_id": "elara_torch",
                                    "stock_remaining": 2,
                                    "stock_initial": 3,
                                },
                            },
                        },
                    },
                    "presentation": {},
                }
            },
        }
    }

    memories = transcript._extract_service_memories(result)
    relationship_state = transcript._extract_relationship_state(result)
    npc_emotion_state = transcript._extract_npc_emotion_state(result)
    service_offer_state = transcript._extract_service_offer_state(result)

    assert memories[0]["memory_id"] == "memory:test"
    assert relationship_state["npc:Elara::player"]["axes"]["trust"] == 0.25
    assert npc_emotion_state["npc:Elara"]["dominant_emotion"] == "neutral"
    assert (
        service_offer_state["offers"]["elara_torch"]["stock_remaining"]
        == 2
    )
