from app.rpg.objectives.handoff import apply_generic_quest_handoff


def test_generic_handoff_creates_investigate_lead_after_completed_quest():
    state = {
        "quest_progress": {
            "quests": {
                "quest:first": {
                    "title": "First Quest",
                    "status": "completed",
                    "completed": True,
                    "objectives": [
                        {"objective_id": "objective:first", "status": "completed", "completed": True}
                    ],
                }
            }
        },
        "known_leads": [
            {"name": "old mill bridge", "type": "location"}
        ],
    }

    result = apply_generic_quest_handoff(state)

    assert result["changed"] is True
    quests = state["quest_progress"]["quests"]
    assert any(quest.get("source") == "generic_quest_handoff" for quest in quests.values())
    handoff = [quest for quest in quests.values() if quest.get("source") == "generic_quest_handoff"][0]
    assert handoff["status"] == "active"
    assert "old mill bridge" in handoff["title"].lower()


def test_generic_handoff_does_not_create_when_active_quest_exists():
    state = {
        "quest_progress": {
            "quests": {
                "quest:active": {
                    "title": "Active Quest",
                    "status": "active",
                    "completed": False,
                    "objectives": [
                        {"objective_id": "objective:active", "status": "active", "completed": False}
                    ],
                },
                "quest:done": {
                    "title": "Done Quest",
                    "status": "completed",
                    "completed": True,
                },
            }
        },
        "known_leads": [{"name": "forest trail"}],
    }

    result = apply_generic_quest_handoff(state)

    assert result["changed"] is False
    assert result["reason"] == "active_quest_exists"


def test_merge_preserving_runtime_state_keeps_dialogue_and_progress_logs():
    from tests.rpg.autoplay_llm_campaign import _merge_preserving_runtime_state

    base = {
        "dialogue_state": {"recent_exchanges": [{"npc": "A"}]},
        "objective_progression_log": [{"matched": True}],
        "quest_progress": {"quests": {"quest:a": {"status": "active"}}},
    }
    overlay = {
        "scene": {"location": "New Place"}
    }

    merged = _merge_preserving_runtime_state(base, overlay)

    assert merged["dialogue_state"]["recent_exchanges"]
    assert merged["objective_progression_log"]
    assert merged["quest_progress"]["quests"]
    assert merged["scene"]["location"] == "New Place"


def test_merge_preserving_runtime_state_does_not_drop_reconciled_quest_progress():
    from tests.rpg.autoplay_llm_campaign import _merge_preserving_runtime_state

    base = {
        "quest_progress": {
            "quests": {
                "quest:a": {
                    "status": "completed",
                    "completed": True,
                    "objectives": [
                        {"objective_id": "objective:a", "completed": True, "status": "completed"}
                    ],
                }
            }
        },
        "dialogue_state": {"recent_exchanges": [{"npc": "Bran"}]},
        "objective_progression_log": [{"objective_id": "objective:a", "matched": True, "completed": True}],
        "autoplay_story_hook_state": {"fired_hooks": {"hook:x": {}}},
        "location_history": [{"location_id": "location:x"}],
    }
    overlay = {
        "quest_progress": {
            "quests": {
                "quest:a": {
                    "status": "active",
                    "completed": False,
                    "objectives": [
                        {"objective_id": "objective:a", "completed": False, "status": "active"}
                    ],
                }
            }
        }
    }

    merged = _merge_preserving_runtime_state(base, overlay)

    quest = merged["quest_progress"]["quests"]["quest:a"]
    assert quest["status"] == "completed"
    assert quest["completed"] is True
    assert merged["dialogue_state"]["recent_exchanges"]
    assert merged["location_history"]


def test_strict_progress_health_summary_reads_nested_metrics():
    from tests.rpg.autoplay_llm_campaign import _strict_progress_health_summary_from_summary

    summary = {
        "health": {
            "progress_quality": {
                "ok": False,
                "metrics": {
                    "meaningful_progress_rate": 0.25,
                    "meaningful_turns": 5,
                    "no_change_turns": 10,
                    "churn_only_turns": 3,
                },
            }
        }
    }

    result = _strict_progress_health_summary_from_summary(summary)

    assert result["ok"] is False
    assert result["meaningful_progress_rate"] == 0.25
    assert result["meaningful_turns"] == 5


def test_handoff_derives_lead_from_objective_progression_topics_when_no_explicit_leads():
    from app.rpg.objectives.handoff import apply_generic_quest_handoff

    state = {
        "quest_progress": {
            "quests": {
                "quest:first": {
                    "title": "First Quest",
                    "status": "completed",
                    "completed": True,
                    "objectives": [
                        {"objective_id": "objective:first", "completed": True, "status": "completed"}
                    ],
                }
            }
        },
        "objective_progression_log": [
            {
                "matched": True,
                "completed": True,
                "objective_id": "objective:first",
                "event": {
                    "topics": ["old bridge", "black cord", "wagon ruts"],
                    "location_name": "East Road",
                },
            }
        ],
    }

    result = apply_generic_quest_handoff(state)

    assert result["changed"] is True
    handoff_quests = [
        quest for quest in state["quest_progress"]["quests"].values()
        if quest.get("source") == "generic_quest_handoff"
    ]
    assert handoff_quests
    assert handoff_quests[0]["status"] == "active"


def test_handoff_fallback_creates_local_investigation_when_no_leads_exist():
    from app.rpg.objectives.handoff import apply_generic_quest_handoff

    state = {
        "current_location_name": "Old Shrine",
        "quest_progress": {
            "quests": {
                "quest:first": {
                    "title": "First Quest",
                    "status": "completed",
                    "completed": True,
                    "objectives": [
                        {"objective_id": "objective:first", "completed": True, "status": "completed"}
                    ],
                }
            }
        },
    }

    result = apply_generic_quest_handoff(state)

    assert result["changed"] is True
    assert state["quest_handoff_log"]
    quest = [
        quest for quest in state["quest_progress"]["quests"].values()
        if quest.get("source") == "generic_quest_handoff"
    ][0]
    assert "old shrine" in quest["title"].lower()


def test_handoff_gate_fails_completed_without_active_or_handoff():
    from tests.rpg.autoplay_llm_campaign import _final_lifecycle_quality_gates

    summary = {
        "requested_turns": 20,
        "quality_gate_summary": {"gates": {}, "ok": True},
        "quest_progress_summary": {
            "completed_count": 1,
            "active_count": 0,
        },
        "quest_handoff_summary": {
            "ok": False,
            "count": 0,
            "active_handoff_quests": [],
        },
        "strict_progress_health_summary": {"ok": True},
        "post_transition_action_quality_summary": {"ok": True},
        "objective_progression_summary": {"matched_count": 1, "ok": True},
        "repeated_affordance_loop_summary": {"ok": True},
        "final_state_field_coverage_summary": {"ok": True},
    }

    gates = _final_lifecycle_quality_gates(summary)

    assert gates["ok"] is False
    assert gates["gates"]["quest_handoff_available_after_completion_ok"] is False
    assert gates["gates"]["no_completed_without_next_objective_ok"] is False


def test_final_state_field_coverage_detects_missing_runtime_fields():
    from tests.rpg.autoplay_llm_campaign import _final_state_field_coverage_summary

    summary = _final_state_field_coverage_summary(
        {
            "quest_progress": {"quests": {}},
            "objective_progression_log": [{"matched": True}],
        }
    )

    assert summary["ok"] is False
    assert "dialogue_state" in summary["missing"]
    assert "quest_progress" in summary["present"]