from tests.rpg.autoplay.manual_turn_driver import (
    load_autoplay_simulation_state,
    merge_autoplay_simulation_state,
    prepare_autoplay_manual_session,
    run_autoplay_manual_turn,
)


def test_prepare_autoplay_manual_session_persists_seed_state():
    session_id = "autoplay_manual_driver_seed_test"
    prepare_autoplay_manual_session(
        session_id=session_id,
        simulation_state={"scene": {"location": "Test Tavern"}},
        reset_session_state=True,
    )

    state = load_autoplay_simulation_state(session_id)

    assert state["scene"]["location"] == "Test Tavern"


def test_run_autoplay_manual_turn_uses_manual_turn_function(monkeypatch):
    from tests.rpg.autoplay import manual_turn_driver

    def fake_run_one_manual_turn(**kwargs):
        assert kwargs.get("include_raw_result") is True
        return {
            "turn_index": kwargs["turn_index"],
            "player_input": kwargs["turn"],
            "result": {
                "ok": True,
                "narration": "You test the manual turn driver.",
                "turn_contract": {"player_action": kwargs["turn"]},
            },
            "raw_result": {
                "ok": True,
                "narration": "You test the manual turn driver.",
                "turn_contract": {"player_action": kwargs["turn"]},
                "simulation_state": {"advanced": True},
            },
            "raw_narration": "You test the manual turn driver.",
            "raw_turn_contract": {"player_action": kwargs["turn"]},
        }

    monkeypatch.setattr(manual_turn_driver, "_run_one_manual_turn", fake_run_one_manual_turn)
    monkeypatch.setattr(
        manual_turn_driver,
        "load_autoplay_manual_session",
        lambda session_id: {"simulation_state": {"advanced": True}},
    )

    result = run_autoplay_manual_turn(
        session_id="autoplay_manual_driver_turn_test",
        player_input="I observe.",
        turn_index=1,
    )

    assert result["ok"] is True
    assert result["runtime_name"] == "manual_harness._run_one_manual_turn"
    assert result["simulation_state"] == {"advanced": True, "memory_state": {}, "presentation_state": {}}
    assert result["turn_contract"]["player_action"] == "I observe."
    assert result["narration"] == "You test the manual turn driver."


def test_merge_autoplay_simulation_state_preserves_story_roots():
    before = {
        "story_arc_state": {"arcs": {"arc:x": {"stage": "start"}}},
        "story_arc_milestone_state": {
            "arcs": {
                "arc:x": {
                    "milestones": [
                        {"milestone_id": "milestone:x", "status": "active"}
                    ]
                }
            }
        },
        "scene": {"location": "The Rusty Flagon"},
    }
    returned = {
        "memory_state": {},
        "presentation_state": {},
    }

    merged = merge_autoplay_simulation_state(
        before_state=before,
        returned_state=returned,
    )

    assert merged["story_arc_state"] == before["story_arc_state"]
    assert merged["story_arc_milestone_state"] == before["story_arc_milestone_state"]
    assert merged["scene"] == before["scene"]
    assert "memory_state" in merged
    assert "presentation_state" in merged


def test_merge_autoplay_simulation_state_allows_nonempty_returned_story_update():
    before = {
        "story_arc_state": {"arcs": {"arc:x": {"stage": "start"}}},
    }
    returned = {
        "story_arc_state": {"arcs": {"arc:x": {"stage": "middle"}}},
    }

    merged = merge_autoplay_simulation_state(
        before_state=before,
        returned_state=returned,
    )

    assert merged["story_arc_state"]["arcs"]["arc:x"]["stage"] == "middle"


def test_run_autoplay_manual_turn_preserves_seed_roots_when_raw_result_is_partial(monkeypatch):
    from tests.rpg.autoplay import manual_turn_driver

    session_holder = {
        "session": {
            "simulation_state": {
                "story_arc_state": {"arcs": {"arc:x": {"stage": "start"}}},
                "story_arc_milestone_state": {
                    "arcs": {
                        "arc:x": {
                            "milestones": [
                                {"milestone_id": "milestone:x", "status": "active"}
                            ]
                        }
                    }
                },
            }
        }
    }

    def fake_run_one_manual_turn(**kwargs):
        return {
            "turn_index": kwargs["turn_index"],
            "player_input": kwargs["turn"],
            "raw_result": {
                "ok": True,
                "narration": "Partial state returned.",
                "turn_contract": {"player_action": kwargs["turn"]},
                "session": {
                    "simulation_state": {
                        "memory_state": {},
                        "presentation_state": {},
                    }
                },
            },
            "raw_narration": "Partial state returned.",
            "raw_turn_contract": {"player_action": kwargs["turn"]},
        }

    def fake_load_session(session_id):
        return session_holder["session"]

    def fake_save_session(session_id, session):
        session_holder["session"] = session

    monkeypatch.setattr(manual_turn_driver, "_run_one_manual_turn", fake_run_one_manual_turn)
    monkeypatch.setattr(manual_turn_driver, "load_autoplay_manual_session", fake_load_session)
    monkeypatch.setattr(manual_turn_driver, "_save_manual_session_for_test", fake_save_session)
    monkeypatch.setattr(manual_turn_driver, "_save_through_app_session_service", lambda session: None)

    result = run_autoplay_manual_turn(
        session_id="autoplay_partial_state_test",
        player_input="I observe.",
        turn_index=1,
    )

    assert result["simulation_state"]["story_arc_state"]["arcs"]["arc:x"]["stage"] == "start"
    assert result["simulation_state"]["story_arc_milestone_state"]["arcs"]["arc:x"]["milestones"][0]["status"] == "active"
    assert "memory_state" in result["simulation_state"]


def test_run_autoplay_manual_turn_captures_pre_turn_state_before_destructive_partial_write(monkeypatch):
    from tests.rpg.autoplay import manual_turn_driver

    session_holder = {
        "session": {
            "simulation_state": {
                "campaign_journal_state": {
                    "entries": [{"entry_id": "journal:already_known"}]
                },
                "story_arc_milestone_state": {
                    "arcs": {
                        "arc:x": {
                            "milestones": [
                                {"milestone_id": "milestone:x", "status": "completed"}
                            ]
                        }
                    }
                },
            }
        }
    }

    def fake_load_session(session_id):
        return session_holder["session"]

    def fake_save_session(session_id, session):
        session_holder["session"] = session

    def fake_run_one_manual_turn(**kwargs):
        # Simulate apply_turn destructively replacing the saved manual session
        # with a partial state before run_autoplay_manual_turn extracts result.
        session_holder["session"] = {
            "simulation_state": {
                "memory_state": {},
                "presentation_state": {},
            }
        }
        return {
            "turn_index": kwargs["turn_index"],
            "player_input": kwargs["turn"],
            "raw_result": {
                "ok": True,
                "narration": "Partial state returned.",
                "turn_contract": {"player_action": kwargs["turn"]},
                "session": {
                    "simulation_state": {
                        "memory_state": {},
                        "presentation_state": {},
                    }
                },
            },
            "raw_narration": "Partial state returned.",
            "raw_turn_contract": {"player_action": kwargs["turn"]},
        }

    monkeypatch.setattr(manual_turn_driver, "load_autoplay_manual_session", fake_load_session)
    monkeypatch.setattr(manual_turn_driver, "_save_manual_session_for_test", fake_save_session)
    monkeypatch.setattr(manual_turn_driver, "_save_through_app_session_service", lambda session: None)
    monkeypatch.setattr(manual_turn_driver, "_run_one_manual_turn", fake_run_one_manual_turn)

    result = run_autoplay_manual_turn(
        session_id="autoplay_destructive_partial_state_test",
        player_input="I observe.",
        turn_index=1,
    )

    assert result["simulation_state"]["campaign_journal_state"]["entries"][0]["entry_id"] == "journal:already_known"
    milestone = result["simulation_state"]["story_arc_milestone_state"]["arcs"]["arc:x"]["milestones"][0]
    assert milestone["status"] == "completed"
    assert "memory_state" in result["simulation_state"]


def test_merge_preserves_journal_entries_when_returned_root_has_empty_entries():
    before = {
        "campaign_journal_state": {
            "entries": [
                {"entry_id": "journal:one", "title": "One"},
                {"entry_id": "journal:two", "title": "Two"},
            ]
        }
    }
    returned = {
        "campaign_journal_state": {
            "entries": []
        }
    }

    merged = merge_autoplay_simulation_state(
        before_state=before,
        returned_state=returned,
    )

    assert [row["entry_id"] for row in merged["campaign_journal_state"]["entries"]] == [
        "journal:one",
        "journal:two",
    ]


def test_merge_preserves_milestones_when_returned_arcs_empty():
    before = {
        "story_arc_milestone_state": {
            "arcs": {
                "arc:witness_search": {
                    "milestones": [
                        {"milestone_id": "milestone:find_witness", "status": "completed"},
                        {"milestone_id": "milestone:pursue_bandit_trail", "status": "completed"},
                    ]
                }
            }
        }
    }
    returned = {
        "story_arc_milestone_state": {
            "arcs": {}
        }
    }

    merged = merge_autoplay_simulation_state(
        before_state=before,
        returned_state=returned,
    )

    milestones = merged["story_arc_milestone_state"]["arcs"]["arc:witness_search"]["milestones"]
    assert [row["milestone_id"] for row in milestones] == [
        "milestone:find_witness",
        "milestone:pursue_bandit_trail",
    ]


def test_merge_updates_existing_milestone_without_dropping_others():
    before = {
        "story_arc_milestone_state": {
            "arcs": {
                "arc:witness_search": {
                    "milestones": [
                        {"milestone_id": "milestone:find_witness", "status": "active"},
                        {"milestone_id": "milestone:pursue_bandit_trail", "status": "active"},
                    ]
                }
            }
        }
    }
    returned = {
        "story_arc_milestone_state": {
            "arcs": {
                "arc:witness_search": {
                    "milestones": [
                        {"milestone_id": "milestone:find_witness", "status": "completed"},
                    ]
                }
            }
        }
    }

    merged = merge_autoplay_simulation_state(
        before_state=before,
        returned_state=returned,
    )

    milestones = {
        row["milestone_id"]: row
        for row in merged["story_arc_milestone_state"]["arcs"]["arc:witness_search"]["milestones"]
    }
    assert milestones["milestone:find_witness"]["status"] == "completed"
    assert milestones["milestone:pursue_bandit_trail"]["status"] == "active"


def test_merge_preserves_story_events_when_returned_queue_empty():
    before = {
        "story_event_queue_state": {
            "queue": [
                {"event_id": "event:one", "title": "One"},
            ]
        }
    }
    returned = {
        "story_event_queue_state": {
            "queue": []
        }
    }

    merged = merge_autoplay_simulation_state(
        before_state=before,
        returned_state=returned,
    )

    assert merged["story_event_queue_state"]["queue"][0]["event_id"] == "event:one"