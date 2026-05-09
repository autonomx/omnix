from app.rpg.campaign_state.authority_commit import commit_campaign_state


def test_commit_reconciles_objective_hooks_into_canonical_quest_progress():
    state = {
        "quest_progress": {
            "quests": {
                "quest:witness_search": {
                    "quest_id": "quest:witness_search",
                    "title": "Witness Search",
                    "status": "active",
                    "completed": False,
                    "objectives": [
                        {
                            "objective_id": "objective:find_witness",
                            "summary": "Find the witness near the tavern.",
                            "status": "active",
                            "completed": False,
                        },
                        {
                            "objective_id": "objective:report_to_bran",
                            "summary": "Report the witness findings to Bran.",
                            "status": "active",
                            "completed": False,
                        },
                    ],
                }
            }
        },
        "autoplay_story_hook_state": {
            "fired_hooks": {
                "hook:objective:find_witness:completed": {
                    "summary": "Find the witness near the tavern completed.",
                    "completed": True,
                },
                "hook:objective:report_to_bran:completed": {
                    "summary": "Report the witness findings to Bran completed.",
                    "completed": True,
                },
            }
        },
        "current_location_name": "East Road",
    }

    result = commit_campaign_state(state, phase="turn")

    assert result["ok"] is True
    quest = result["state"]["quest_progress"]["quests"]["quest:witness_search"]
    assert quest["status"] == "completed"
    assert quest["completed"] is True
    assert all(obj["completed"] for obj in quest["objectives"])


def test_commit_creates_generic_handoff_after_completed_quest_with_no_active_quest():
    state = {
        "quest_progress": {
            "quests": {
                "quest:first": {
                    "quest_id": "quest:first",
                    "title": "First Quest",
                    "status": "completed",
                    "completed": True,
                    "objectives": [
                        {
                            "objective_id": "objective:first",
                            "summary": "Find the clue.",
                            "status": "completed",
                            "completed": True,
                        }
                    ],
                }
            }
        },
        "objective_progression_log": [
            {
                "objective_id": "objective:first",
                "matched": True,
                "completed": True,
                "summary": "Find the clue completed near the old bridge.",
                "event": {"topics": ["old bridge", "wagon ruts"]},
            }
        ],
        "current_location_name": "Old Road",
    }

    result = commit_campaign_state(state, phase="turn")

    quests = result["state"]["quest_progress"]["quests"]
    handoff_quests = [
        quest for quest in quests.values()
        if quest.get("source") == "campaign_state_authority_commit"
    ]
    assert handoff_quests
    assert handoff_quests[0]["status"] == "active"
    assert result["summary"]["handoff_summary"]["changed"] is True


def test_commit_marks_stale_state_red_when_completed_without_next_and_no_leads_impossible_case():
    state = {
        "quest_progress": {
            "quests": {
                "quest:first": {
                    "quest_id": "quest:first",
                    "title": "First Quest",
                    "status": "completed",
                    "completed": True,
                    "objectives": [
                        {"objective_id": "objective:first", "summary": "Done.", "completed": True, "status": "completed"}
                    ],
                }
            }
        }
    }

    result = commit_campaign_state(state, phase="turn")

    assert result["summary"]["stale_state_summary"]["completed_without_next_objective"] is False
    assert result["summary"]["handoff_summary"]["changed"] is True


def test_commit_per_turn_is_bounded_for_small_state():
    state = {
        "quest_progress": {
            "quests": {
                "quest:test": {
                    "status": "active",
                    "objectives": [
                        {"objective_id": "objective:test", "summary": "Inspect the clue.", "status": "active"}
                    ],
                }
            }
        }
    }

    result = commit_campaign_state(state, phase="turn", performance_budget_ms=25)

    assert result["summary"]["performance"]["elapsed_ms"] <= 25


def test_commit_prefers_hook_lead_over_recent_repeated_action_lead():
    state = {
        "quest_progress": {
            "quests": {
                "quest:first": {
                    "quest_id": "quest:first",
                    "title": "First Quest",
                    "status": "completed",
                    "completed": True,
                    "objectives": [
                        {
                            "objective_id": "objective:first",
                            "summary": "Find the clue.",
                            "status": "completed",
                            "completed": True,
                        }
                    ],
                }
            }
        },
        "autoplay_story_hook_state": {
            "fired_hooks": {
                "hook:lead:next_location": {
                    "summary": "The trail points toward the old mill bridge.",
                }
            }
        },
        "current_location_name": "Road Outside Tavern",
    }

    transcript_tail = [
        {
            "turn": 1,
            "player_action": "I inspect the road outside the tavern for fresh tracks, wagon ruts, black cord, torn cloth, ambush signs, or bridge markings.",
        }
    ] * 5

    result = commit_campaign_state(
        state,
        transcript_tail=transcript_tail,
        phase="turn",
    )

    handoff = result["summary"]["handoff_summary"]
    assert handoff["changed"] is True
    quest = [
        q for q in result["state"]["quest_progress"]["quests"].values()
        if q.get("source") == "campaign_state_authority_commit"
    ][0]
    assert "old mill bridge" in quest["title"].lower()


def test_handoff_quest_not_completed_by_same_commit_evidence():
    state = {
        "quest_progress": {
            "quests": {
                "quest:first": {
                    "quest_id": "quest:first",
                    "title": "First Quest",
                    "status": "active",
                    "completed": False,
                    "objectives": [
                        {
                            "objective_id": "objective:first",
                            "summary": "Find the witness trail.",
                            "status": "active",
                            "completed": False,
                        }
                    ],
                }
            }
        },
        "objective_progression_log": [
            {
                "objective_id": "objective:first",
                "matched": True,
                "completed": True,
                "summary": "Find the witness trail completed.",
                "event": {"topics": ["witness trail", "old bridge"]},
            }
        ],
        "autoplay_story_hook_state": {
            "fired_hooks": {
                "hook:lead:next_location": {
                    "summary": "The witness trail now points toward the old bridge.",
                }
            }
        },
        "current_location_name": "Road Outside Tavern",
    }

    result = commit_campaign_state(state, phase="turn")

    quests = result["state"]["quest_progress"]["quests"]
    handoff_quests = [
        quest for quest in quests.values()
        if quest.get("source") == "campaign_state_authority_commit"
    ]
    assert handoff_quests
    handoff = handoff_quests[0]
    assert handoff["status"] == "active"


def test_generic_handoff_suppressed_when_scenario_progression_graph_active():
    state = {
        "progression_completed_nodes": {"ask_bran_about_tension": {}},
        "progression_facts": {"fact:witness_left_side_door": {}},
        "quest_progress": {
            "quests": {
                "quest:first": {
                    "quest_id": "quest:first",
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

    result = commit_campaign_state(state, phase="turn")

    assert result["summary"]["handoff_summary"]["reason"] == "suppressed_by_scenario_progression_graph"


def test_forward_looking_hook_lead_beats_reported_completion_hook():
    state = {
        "quest_progress": {
            "quests": {
                "quest:first": {
                    "quest_id": "quest:first",
                    "title": "First Quest",
                    "status": "completed",
                    "completed": True,
                    "objectives": [
                        {
                            "objective_id": "objective:first",
                            "summary": "Report findings.",
                            "status": "completed",
                            "completed": True,
                        }
                    ],
                }
            }
        },
        "autoplay_story_hook_state": {
            "fired_hooks": {
                "hook:objective:report:completed": {
                    "summary": "The witness trail findings were reported to Bran.",
                    "completed": True,
                },
                "hook:lead:bandit_road": {
                    "summary": "The witness trail now points toward the Bandit Road.",
                },
            }
        },
        "current_location_name": "Road Outside Tavern",
    }

    result = commit_campaign_state(state, phase="turn")

    handoff_quests = [
        quest for quest in result["state"]["quest_progress"]["quests"].values()
        if quest.get("source") == "campaign_state_authority_commit"
    ]
    assert handoff_quests
    assert "bandit road" in handoff_quests[0]["title"].lower()
    assert "reported to bran" not in handoff_quests[0]["title"].lower()


def test_handoff_guard_allows_future_evidence_to_complete_handoff():
    state = {
        "quest_progress": {
            "quests": {
                "quest:first": {
                    "quest_id": "quest:first",
                    "title": "First Quest",
                    "status": "completed",
                    "completed": True,
                    "objectives": [
                        {"objective_id": "objective:first", "summary": "Done.", "completed": True, "status": "completed"}
                    ],
                }
            }
        },
        "autoplay_story_hook_state": {
            "fired_hooks": {
                "hook:lead:bridge": {
                    "summary": "The trail now points toward the old bridge.",
                }
            }
        },
        "current_location_name": "Road",
    }

    first = commit_campaign_state(state, phase="turn")
    handoff_quest = [
        quest for quest in first["state"]["quest_progress"]["quests"].values()
        if quest.get("source") == "campaign_state_authority_commit"
    ][0]
    handoff_obj = handoff_quest["objectives"][0]
    assert handoff_obj["completed"] is False

    state.setdefault("objective_progression_log", []).append(
        {
            "objective_id": handoff_obj["objective_id"],
            "matched": True,
            "completed": True,
            "summary": handoff_obj["summary"],
            "turn": int(handoff_obj.get("activated_after_turn") or 0) + 1,
            "generation": int(handoff_obj.get("created_commit_sequence") or 0) + 1,
        }
    )

    second = commit_campaign_state(state, phase="turn")
    handoff_quest = second["state"]["quest_progress"]["quests"][handoff_quest["quest_id"]]
    assert handoff_quest["objectives"][0]["completed"] is True


def test_low_information_lead_labels_are_rejected():
    from app.rpg.campaign_state.authority_commit import (
        _candidate_lead_phrases_from_text,
        _is_low_information_lead_label,
    )

    assert _is_low_information_lead_label("toward") is True
    assert _is_low_information_lead_label("the clue") is True
    assert _is_low_information_lead_label("the evidence") is True
    assert _is_low_information_lead_label("the ruined observatory") is False
    assert _is_low_information_lead_label("Captain Mara") is False

    phrases = _candidate_lead_phrases_from_text("The trail now points toward the ruined observatory.")
    assert "toward" not in [p.lower() for p in phrases]
    assert any("ruined observatory" in p.lower() for p in phrases)


def test_handoff_uses_specific_multitoken_lead_not_direction_word():
    from app.rpg.campaign_state.authority_commit import commit_campaign_state

    state = {
        "quest_progress": {
            "quests": {
                "quest:first": {
                    "quest_id": "quest:first",
                    "title": "First Quest",
                    "status": "completed",
                    "completed": True,
                    "objectives": [
                        {
                            "objective_id": "objective:first",
                            "summary": "Finish the first lead.",
                            "status": "completed",
                            "completed": True,
                        }
                    ],
                }
            }
        },
        "autoplay_story_hook_state": {
            "fired_hooks": {
                "hook:lead:next": {
                    "summary": "The trail now points toward the ruined observatory.",
                }
            }
        },
    }

    result = commit_campaign_state(state, phase="turn")
    handoff = [
        quest for quest in result["state"]["quest_progress"]["quests"].values()
        if quest.get("source") == "campaign_state_authority_commit"
    ][0]

    assert "toward" != handoff["lead"]["name"].lower()
    assert "ruined observatory" in handoff["title"].lower()
    assert handoff["objectives"][0]["semantic_action_templates"]


def test_handoff_progresses_after_two_distinct_future_semantic_actions():
    from app.rpg.campaign_state.authority_commit import commit_campaign_state

    state = {
        "quest_progress": {
            "quests": {
                "quest:first": {
                    "quest_id": "quest:first",
                    "title": "First Quest",
                    "status": "completed",
                    "completed": True,
                    "objectives": [
                        {"objective_id": "objective:first", "summary": "Done.", "completed": True, "status": "completed"}
                    ],
                }
            }
        },
        "autoplay_story_hook_state": {
            "fired_hooks": {
                "hook:lead:next": {
                    "summary": "The clue points toward the ruined observatory.",
                }
            }
        },
    }

    first = commit_campaign_state(state, phase="turn", turn_record={"turn": 1})
    handoff = [
        quest for quest in first["state"]["quest_progress"]["quests"].values()
        if quest.get("source") == "campaign_state_authority_commit"
    ][0]
    assert handoff["status"] == "active"

    second = commit_campaign_state(
        first["state"],
        phase="turn",
        turn_record={
            "turn": 2,
            "player_action": "I ask nearby people what they know about the ruined observatory.",
        },
    )
    handoff = second["state"]["quest_progress"]["quests"][handoff["quest_id"]]
    assert handoff["objectives"][0]["handoff_progress_count"] == 1
    assert handoff["objectives"][0]["completed"] is False

    third = commit_campaign_state(
        second["state"],
        phase="turn",
        turn_record={
            "turn": 3,
            "player_action": "I inspect evidence connected to the ruined observatory, looking for concrete next steps.",
        },
    )
    handoff = third["state"]["quest_progress"]["quests"][handoff["quest_id"]]
    assert handoff["objectives"][0]["completed"] is True
    assert handoff["completed"] is True


def test_campaign_commit_preserves_scenario_progression_graph_quest_state():
    from app.rpg.campaign_state.authority_commit import commit_campaign_state

    state = {
        "progression_completed_nodes": {"report_findings_to_bran": {}},
        "scenario_progression_quest_state": {
            "quest:warn_wagon": {
                "quest_id": "quest:warn_wagon",
                "title": "Warn the Wagon",
                "status": "active",
                "completed": False,
                "source": "scenario_progression_graph",
                "objectives": [
                    {"objective_id": "objective:warn_garran", "status": "active", "completed": False}
                ],
            }
        },
        "quest_progress": {
            "quests": {
                "quest:witness_search": {
                    "quest_id": "quest:witness_search",
                    "status": "completed",
                    "completed": True,
                    "objectives": [
                        {"objective_id": "objective:find_witness", "status": "completed", "completed": True}
                    ],
                }
            }
        },
    }

    result = commit_campaign_state(state, phase="turn")

    quests = result["state"]["quest_progress"]["quests"]
    assert "quest:warn_wagon" in quests
    assert quests["quest:warn_wagon"]["status"] == "active"