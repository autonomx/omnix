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


def test_manual_summary_includes_recalled_service_memories_from_narration_debug():
    result = {
        "result": {
            "narration_debug": {
                "recalled_service_memories": [
                    {
                        "memory_id": "memory:recall",
                        "kind": "service_purchase_blocked",
                        "summary": "The player tried to buy Torch without enough coin.",
                    }
                ],
                "service_memory_recall_debug": {
                    "source": "deterministic_service_memory_recall",
                    "count": 1,
                    "memory_ids": ["memory:recall"],
                },
            }
        },
        "session": {
            "setup_payload": {
                "metadata": {
                    "simulation_state": {}
                }
            },
            "runtime_state": {
                "last_turn_contract": {
                    "resolved_result": {},
                    "presentation": {},
                }
            },
        },
    }

    recalled = transcript._extract_recalled_service_memories(result)
    debug = transcript._extract_service_memory_recall_debug(result)

    assert recalled[0]["memory_id"] == "memory:recall"
    assert debug["count"] == 1


def test_manual_summary_recalled_memories_excludes_current_memory_entry():
    result = {
        "result": {
            "narration_debug": {
                "recalled_service_memories": [
                    {"memory_id": "prior", "kind": "service_inquiry"},
                    {"memory_id": "current", "kind": "service_inquiry"},
                ],
                "service_memory_recall_debug": {"count": 2},
            }
        },
        "session": {
            "setup_payload": {
                "metadata": {
                    "simulation_state": {}
                }
            },
            "runtime_state": {
                "last_turn_contract": {
                    "resolved_result": {
                        "memory_entry": {
                            "memory_id": "current",
                            "kind": "service_inquiry",
                        },
                        "service_application": {
                            "memory_entry": {
                                "memory_id": "current",
                                "kind": "service_inquiry",
                            }
                        },
                    },
                    "presentation": {},
                }
            },
        },
    }

    recalled = transcript._extract_recalled_service_memories(result)

    assert [memory["memory_id"] for memory in recalled] == ["prior"]


def test_extract_simulation_state_prefers_fresh_result_state_over_session_metadata():
    result = {
        "result": {
            "memory_state": {
                "service_memories": [
                    {"memory_id": "memory:fresh"}
                ]
            },
            "relationship_state": {"npc:Elara::player": {"axes": {"familiarity": 1.0}}},
            "npc_emotion_state": {"npc:Elara": {"dominant_emotion": "neutral"}},
            "service_offer_state": {"offers": {"elara_torch": {"stock_remaining": 2}}},
        },
        "session": {
            "setup_payload": {
                "metadata": {
                    "simulation_state": {
                        "memory_state": {"service_memories": []},
                        "relationship_state": {},
                        "npc_emotion_state": {},
                        "service_offer_state": {},
                    }
                }
            },
            "runtime_state": {
                "last_turn_contract": {
                    "resolved_result": {},
                    "presentation": {},
                }
            },
        },
    }

    simulation_state = transcript._extract_simulation_state(result)

    assert simulation_state["memory_state"]["service_memories"][0]["memory_id"] == "memory:fresh"
    assert simulation_state["relationship_state"]["npc:Elara::player"]["axes"]["familiarity"] == 1.0
    assert simulation_state["npc_emotion_state"]["npc:Elara"]["dominant_emotion"] == "neutral"
    assert simulation_state["service_offer_state"]["offers"]["elara_torch"]["stock_remaining"] == 2


def test_manual_regression_warns_when_directions_inquiry_travels():
    result = {
        "result": {
            "travel_result": {
                "matched": True,
                "applied": True,
                "from_location_id": "loc_tavern",
                "to_location_id": "loc_market",
            },
            "current_location_id": "loc_market",
            "narration": "You arrive at Market Square.",
        },
        "session": {
            "runtime_state": {
                "last_turn_contract": {
                    "resolved_result": {
                        "travel_result": {
                            "matched": True,
                            "applied": True,
                            "from_location_id": "loc_tavern",
                            "to_location_id": "loc_market",
                        }
                    }
                }
            }
        },
    }

    warnings = transcript._manual_regression_warnings(
        turn_index=4,
        player_input="I ask Bran for directions to the market",
        result=result,
    )

    assert "directions_inquiry_unexpectedly_travelled" in warnings
    assert "flat_turn_4_directions_inquiry_should_not_travel" in warnings


def test_manual_regression_warns_when_follow_directions_does_not_travel():
    result = {
        "result": {
            "travel_result": {
                "matched": True,
                "applied": False,
                "from_location_id": "loc_tavern",
            },
            "current_location_id": "loc_tavern",
            "narration": "No available route matches that destination.",
        },
        "session": {
            "runtime_state": {
                "last_turn_contract": {
                    "resolved_result": {
                        "travel_result": {
                            "matched": True,
                            "applied": False,
                            "from_location_id": "loc_tavern",
                        }
                    }
                }
            }
        },
    }

    warnings = transcript._manual_regression_warnings(
        turn_index=5,
        player_input="I follow Bran's directions to the market",
        result=result,
    )

    assert "follow_directions_expected_travel_success" in warnings
    assert "flat_turn_5_follow_directions_should_travel" in warnings


def test_manual_regression_warns_when_market_scenario_bounces_to_tavern():
    result = {
        "result": {
            "current_location_id": "loc_tavern",
            "travel_result": {},
            "service_result": {
                "matched": True,
                "kind": "service_inquiry",
                "service_kind": "shop_goods",
                "provider_name": "Elara",
                "current_location_id": "loc_tavern",
            },
            "narration": "Elara looks over the available goods.",
        },
        "session": {
            "runtime_state": {
                "last_turn_contract": {
                    "resolved_result": {
                        "service_result": {
                            "matched": True,
                            "kind": "service_inquiry",
                            "service_kind": "shop_goods",
                            "provider_name": "Elara",
                            "current_location_id": "loc_tavern",
                        }
                    }
                }
            }
        },
    }

    warnings = transcript._manual_regression_warnings(
        scenario_name="shop_success",
        turn_index=2,
        player_input="I ask Elara what she sells",
        result=result,
    )

    assert "shop_success_turn_2_expected_loc_market" in warnings


def test_manual_regression_allows_market_scenario_to_stay_in_market():
    result = {
        "result": {
            "current_location_id": "loc_market",
            "travel_result": {},
            "service_result": {
                "matched": True,
                "kind": "service_inquiry",
                "service_kind": "shop_goods",
                "provider_name": "Elara",
                "current_location_id": "loc_market",
            },
            "narration": "Elara looks over the available goods.",
        },
        "session": {
            "runtime_state": {
                "last_turn_contract": {
                    "resolved_result": {
                        "service_result": {
                            "matched": True,
                            "kind": "service_inquiry",
                            "service_kind": "shop_goods",
                            "provider_name": "Elara",
                            "current_location_id": "loc_market",
                        }
                    }
                }
            }
        },
    }

    warnings = transcript._manual_regression_warnings(
        scenario_name="shop_success",
        turn_index=2,
        player_input="I ask Elara what she sells",
        result=result,
    )

    assert "shop_success_turn_2_expected_loc_market" not in warnings


def test_manual_extracts_conversation_thread_state():
    result = {
        "result": {
            "conversation_result": {
                "triggered": True,
                "beat": {
                    "speaker_id": "npc:Bran",
                    "speaker_name": "Bran",
                    "line": "The room has been busier than usual.",
                },
            },
            "conversation_thread_state": {
                "threads": [{"thread_id": "conversation:loc_tavern:npc:Bran:npc:Mira"}],
                "world_signals": [{"signal_id": "world_signal:conversation:1"}],
            },
        }
    }

    assert transcript._extract_conversation_result(result)["triggered"] is True
    assert len(transcript._extract_conversation_thread_state(result)["threads"]) == 1


def test_manual_warns_if_conversation_participant_not_present():
    result = {
        "result": {
            "location_state": {
                "current_location_id": "loc_tavern",
                "current_location": {
                    "present_npcs": [{"id": "npc:Bran", "name": "Bran"}]
                },
            },
            "conversation_result": {
                "triggered": True,
                "thread": {
                    "participants": [
                        {"id": "npc:Bran", "name": "Bran"},
                        {"id": "npc:Elara", "name": "Elara"},
                    ]
                },
            },
        }
    }

    warnings = transcript._manual_regression_warnings(
        turn_index=1,
        player_input="I wait and listen",
        result=result,
    )

    assert "conversation_participant_not_present" in warnings


def test_manual_warns_if_ambient_conversation_resolves_service():
    result = {
        "result": {
            "service_result": {
                "matched": True,
                "kind": "service_inquiry",
                "service_kind": "lodging",
                "provider_name": "Bran",
            },
            "narration": "Bran looks over the available lodging options.",
        },
        "session": {
            "runtime_state": {
                "last_turn_contract": {
                    "resolved_result": {
                        "action_type": "service_inquiry",
                        "semantic_family": "commerce",
                        "service_result": {
                            "matched": True,
                            "kind": "service_inquiry",
                            "service_kind": "lodging",
                            "provider_name": "Bran",
                        },
                    }
                }
            }
        },
    }

    warnings = transcript._manual_regression_warnings(
        scenario_name="ambient_conversation",
        turn_index=1,
        player_input="I wait and listen to the room",
        result=result,
    )

    assert "ambient_conversation_unexpected_service_result" in warnings
    assert "ambient_conversation_unexpected_commerce_action" in warnings
