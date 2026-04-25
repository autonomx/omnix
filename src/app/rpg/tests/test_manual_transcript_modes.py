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
