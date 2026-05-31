from pathlib import Path

from tests.rpg.autoplay.campaign_report import (
    build_campaign_report_model,
    build_chapter_status,
    build_story_so_far_paragraph,
    classify_dialogue_source,
    compute_dialogue_coverage,
    extract_base_response_payload,
    extract_conversation_beat,
    extract_dialogue,
    extract_narration,
    extract_story_hook_display,
    render_campaign_report_html,
    write_campaign_report,
)

def test_extract_dialogue_from_raw_narration_payload():
    row = {
        "turn_result": {
            "manual_turn_summary": {
                "raw_narration_payload": {
                    "narration": "Bran leans closer.",
                    "npc": {
                        "speaker": "Bran",
                        "line": "I saw the cloaked traveler leave by the side door.",
                    },
                }
            }
        }
    }

    assert extract_narration(row) == "Bran leans closer."
    assert extract_dialogue(row) == {
        "speaker": "Bran",
        "line": "I saw the cloaked traveler leave by the side door.",
    }


def test_extract_dialogue_from_raw_npc():
    row = {
        "turn_result": {
            "manual_turn_summary": {
                "raw_npc": {
                    "speaker": "Bran",
                    "line": "Ask outside. Someone saw him pass.",
                },
                "raw_narration": "Bran wipes the counter and nods toward the door.",
            }
        }
    }

    assert extract_dialogue(row)["speaker"] == "Bran"
    assert "outside" in extract_dialogue(row)["line"]


def test_campaign_report_model_collects_core_sections():
    transcript = [
        {
            "turn_index": 1,
            "player_action": "I ask Bran about the witness.",
            "turn_result": {
                "manual_turn_summary": {
                    "raw_narration_payload": {
                        "narration": "Bran lowers his voice.",
                        "npc": {"speaker": "Bran", "line": "A cloaked traveler left moments ago."},
                    }
                },
                "simulation_state": {
                    "story_arc_state": {
                        "arcs": {
                            "arc:witness_search": {"stage": "lead_found"}
                        }
                    },
                    "story_arc_milestone_state": {
                        "arcs": {
                            "arc:witness_search": {
                                "milestones": [
                                    {"milestone_id": "milestone:find_witness", "status": "active"}
                                ]
                            }
                        }
                    },
                    "campaign_journal_state": {
                        "entries": [
                            {"entry_id": "journal:lead", "title": "Lead", "text": "A clue appears."}
                        ]
                    },
                },
            },
            "progress_delta": {"categories": ["arc_stage_changed", "journal_entry_added"]},
            "progress_quality": {"quality": "meaningful_progress"},
            "story_hook_result": {
                "fired_hooks": [{"hook_id": "hook:witness:ask_bran"}]
            },
        }
    ]

    model = build_campaign_report_model(
        transcript=transcript,
        summary={"session_id": "s", "turns_executed": 1, "ok": True},
        metrics={"progress_quality": {"meaningful_turns": 1}},
        health={"warnings": []},
    )

    assert model["story_arcs"]
    assert model["milestones"]
    assert model["journal_entries"]
    assert model["npcs"][0]["name"] == "Bran"
    assert model["hook_counts"]["hook:witness:ask_bran"] == 1


def test_campaign_report_model_prefers_summary_latest_state_and_surfaces_reconciliation():
    transcript = [
        {
            "turn_index": 1,
            "turn_result": {
                "manual_turn_summary": {
                    "simulation_state": {
                        "quest_progress": {
                            "quests": {
                                "quest:stale": {
                                    "title": "Stale",
                                    "status": "active",
                                    "objectives": [
                                        {"objective_id": "objective:stale", "status": "active", "completed": False}
                                    ],
                                }
                            }
                        }
                    }
                }
            },
        }
    ]

    summary = {
        "session_id": "s",
        "turns_executed": 1,
        "ok": True,
        "latest_state": {
            "quest_progress": {
                "quests": {
                    "quest:authoritative": {
                        "title": "Authoritative",
                        "status": "completed",
                        "completed": True,
                        "objectives": [
                            {"objective_id": "objective:authoritative", "status": "completed", "completed": True}
                        ],
                    }
                }
            }
        },
        "quest_reconciliation_summary": {"ok": True, "count": 3, "errors": []},
    }

    model = build_campaign_report_model(
        transcript=transcript,
        summary=summary,
        metrics={"progress_quality": {"meaningful_turns": 1}},
        health={"warnings": []},
    )

    assert model["latest_state_source"] == "summary.latest_state"
    assert "quest:authoritative" in model["latest_state"]["quest_progress"]["quests"]
    assert model["quest_reconciliation_summary"]["count"] == 3


def test_campaign_report_model_surfaces_final_lifecycle_sections():
    model = build_campaign_report_model(
        transcript=[],
        summary={
            "session_id": "s",
            "turns_executed": 1,
            "ok": True,
            "latest_state": {"quest_progress": {"quests": {}}},
            "objective_progression_summary": {"ok": True, "count": 1},
            "quest_reconciliation_summary": {"ok": True, "count": 2},
            "quest_handoff_summary": {"ok": True, "count": 1},
            "final_state_field_coverage_summary": {"ok": True, "present": ["quest_progress"]},
            "strict_progress_health_summary": {"ok": True, "quest_count": 1},
            "post_transition_action_quality_summary": {"ok": True, "bandit_road": {"count": 0}},
            "repeated_affordance_loop_summary": {"ok": True, "max_streak": 1},
            "pre_turn_advisory_promotion_performance_summary": {"ok": True, "count": 1},
            "quality_gate_summary": {"ok": True, "gates": {}},
        },
        metrics={"progress_quality": {"meaningful_turns": 1}},
        health={"warnings": []},
    )

    assert model["objective_progression_summary"]["count"] == 1
    assert model["quest_handoff_summary"]["count"] == 1
    assert model["final_state_field_coverage_summary"]["ok"] is True
    assert model["strict_progress_health_summary"]["ok"] is True
    assert model["pre_turn_advisory_promotion_performance_summary"]["count"] == 1


def test_render_campaign_report_html_contains_major_sections():
    model = {
        "summary": {"session_id": "s", "turns_executed": 1, "ok": True},
        "metrics": {
            "progress_quality": {"meaningful_turns": 1},
            "performance": {"avg_turn_ms": 1.0, "stage_summary": {}, "slowest_turns": []},
        },
        "health": {"warnings": []},
        "timeline": [],
        "story_arcs": [],
        "milestones": [],
        "journal_entries": [],
        "story_events": [],
        "npcs": [],
        "player_progression": {},
        "lore": [],
        "category_counts": {},
        "hook_counts": {},
        "npc_dialogue_counts": {},
        "action_diversity": {},
        "shortcomings": [],
        "latest_state": {},
    }

    html = render_campaign_report_html(model)

    assert "Autoplay Campaign Report" in html
    assert "NPC Cast, Biography, and Growth" in html
    assert "Lore, Setting, and Director Setup" in html
    assert "Turn-by-Turn Story Timeline" in html


def test_render_campaign_report_html_contains_quest_reconciliation_stats():
    model = build_campaign_report_model(
        transcript=[],
        summary={
            "session_id": "s",
            "turns_executed": 0,
            "ok": True,
            "latest_state": {},
            "quest_reconciliation_summary": {"ok": True, "count": 4, "errors": []},
            "quality_gate_summary": {"ok": True, "gates": {}},
            "background_result_timing_summary": {},
            "performance_budget_summary": {},
        },
        metrics={
            "progress_quality": {"meaningful_turns": 0},
            "performance": {"avg_turn_ms": 1.0, "stage_summary": {}, "slowest_turns": []},
        },
        health={"warnings": []},
    )

    html = render_campaign_report_html(model)

    assert "Quest Reconciliation" in html
    assert "Reconciliation Errors" in html


def test_write_campaign_report_creates_files(tmp_path: Path):
    paths = write_campaign_report(
        output_dir=tmp_path,
        transcript=[],
        summary={"session_id": "s"},
        metrics={},
        health={},
    )

    assert Path(paths["campaign_report_html"]).exists()
    assert Path(paths["campaign_report_json"]).exists()


def test_extract_dialogue_from_story_hook_display():
    row = {
        "story_hook_result": {
            "display": {
                "narration": "Bran lowers his voice.",
                "npc": {
                    "speaker": "Bran",
                    "line": "A cloaked traveler left not long ago.",
                },
            }
        }
    }

    assert extract_story_hook_display(row)["npc"]["speaker"] == "Bran"
    assert extract_narration(row) == "Bran lowers his voice."
    assert extract_dialogue(row)["line"] == "A cloaked traveler left not long ago."


def test_extract_conversation_beat_from_raw_result():
    row = {
        "turn_result": {
            "manual_turn_summary": {
                "raw_result": {
                    "conversation_result": {
                        "beat": {
                            "speaker_name": "Bran",
                            "line": "The room has been busier than usual tonight.",
                        }
                    }
                }
            }
        }
    }

    assert extract_conversation_beat(row) == {
        "speaker": "Bran",
        "line": "The room has been busier than usual tonight.",
    }
    assert extract_dialogue(row)["speaker"] == "Bran"


def test_story_so_far_paragraph_mentions_completed_objectives():
    model = {
        "timeline": [{"turn_index": 1}],
        "milestones": [
            {"status": "completed", "title": "Find the witness"},
            {"status": "completed", "title": "Pursue the bandit trail"},
            {"status": "completed", "title": "Witness Found"},
        ],
        "journal_entries": [],
    }

    paragraph = build_story_so_far_paragraph(model)

    assert "Find the witness" in paragraph
    assert "Pursue the bandit trail" in paragraph
    assert "Witness Found" in paragraph


def test_story_so_far_paragraph_does_not_expose_hook_ids():
    model = {
        "timeline": [
            {
                "turn_index": 1,
                "fired_hooks": [
                    {
                        "hook_id": "hook:witness:ask_bran",
                        "story_summary": "Bran reveals the first witness lead.",
                    }
                ],
            }
        ],
        "milestones": [],
        "journal_entries": [],
        "hook_counts": {"hook:witness:ask_bran": 1},
    }

    paragraph = build_story_so_far_paragraph(model)

    assert "Bran reveals the first witness lead" in paragraph
    assert "hook:witness" not in paragraph


def test_campaign_report_shortcomings_flag_fallback_player_agent():
    model = build_campaign_report_model(
        transcript=[],
        summary={"session_id": "s"},
        metrics={
            "player_agent_exception_count": 20,
            "fallback_player_action_rate": 1.0,
            "fallback_player_actions": 20,
        },
        health={"warnings": []},
    )

    text = " ".join(model["shortcomings"])

    assert "Player-agent exceptions" in text
    assert "Fallback player action rate" in text


def test_dialogue_coverage_detects_social_turn_missing_npc_response():
    timeline = [
        {
            "turn_index": 1,
            "player_action": "I ask Bran about the witness.",
            "social_action": True,
            "npc": {},
            "missing_npc_response": True,
            "dialogue_source": "none",
            "echoed_narration": True,
            "narration": "I ask Bran about the witness.",
        },
        {
            "turn_index": 2,
            "player_action": "I inspect the tavern.",
            "social_action": False,
            "npc": {"speaker": "Mira", "line": "I saw someone leave."},
            "missing_npc_response": False,
            "dialogue_source": "story_hook_display",
            "echoed_narration": False,
        },
    ]

    coverage = compute_dialogue_coverage(timeline)

    assert coverage["social_turn_missing_npc_response_count"] == 1
    assert coverage["hook_dialogue_turn_count"] == 1
    assert coverage["echoed_narration_turn_count"] == 1


def test_classify_dialogue_source_prefers_story_hook_display():
    row = {
        "story_hook_result": {
            "display": {
                "npc": {"speaker": "Bran", "line": "Take the road carefully."}
            }
        }
    }

    assert classify_dialogue_source(row) == "story_hook_display"


def test_extract_dialogue_from_base_runtime_response():
    row = {
        "base_response_payload": {
            "source": "deterministic_base_runtime_response",
            "narration": "Bran studies the question before answering.",
            "npc": {
                "speaker": "Bran",
                "line": "Tell me exactly what you found.",
            },
        }
    }

    assert extract_base_response_payload(row)["npc"]["speaker"] == "Bran"
    assert extract_dialogue(row)["line"] == "Tell me exactly what you found."
    assert extract_narration(row) == "Bran studies the question before answering."
    assert classify_dialogue_source(row) == "base_runtime_deterministic"


def test_dialogue_coverage_counts_base_runtime_dialogue():
    timeline = [
        {
            "turn_index": 1,
            "player_action": "I ask Bran about the witness.",
            "social_action": True,
            "npc": {"speaker": "Bran", "line": "Tell me exactly what you found."},
            "missing_npc_response": False,
            "dialogue_source": "base_runtime_deterministic",
            "echoed_narration": False,
        }
    ]

    coverage = compute_dialogue_coverage(timeline)

    assert coverage["base_runtime_dialogue_turn_count"] == 1
    assert coverage["social_turn_missing_npc_response_count"] == 0


def test_report_classifies_real_runtime_provider_dialogue():
    row = {
        "turn_result": {
            "manual_turn_summary": {
                "raw_narration_payload": {
                    "format_version": "rpg_narration_v2",
                    "source": "provider_runtime_narration",
                    "narration": "Bran lowers his voice.",
                    "npc": {
                        "speaker": "Bran",
                        "line": "Tell me exactly what you found.",
                    },
                    "reward": "",
                    "followup_hooks": [],
                }
            }
        }
    }

    assert classify_dialogue_source(row) == "real_runtime_provider"


def test_story_hook_display_overrides_deterministic_runtime_fallback_in_report():
    row = {
        "turn_result": {
            "manual_turn_summary": {
                "raw_narration_payload": {
                    "format_version": "rpg_narration_v2",
                    "source": "deterministic_runtime_narration_fallback",
                    "narration": "Generic fallback narration.",
                    "npc": {
                        "speaker": "Bran",
                        "line": "Generic fallback line.",
                    },
                    "reward": "",
                    "followup_hooks": [],
                }
            }
        },
        "story_hook_result": {
            "display": {
                "narration": "Specific hook narration.",
                "npc": {
                    "speaker": "Bran",
                    "line": "Specific hook line.",
                },
            }
        },
    }

    assert classify_dialogue_source(row) == "story_hook_display"
    assert extract_dialogue(row)["line"] == "Specific hook line."
    assert extract_narration(row) == "Specific hook narration."


def test_runtime_diagnostics_are_collected_in_campaign_report_model():
    transcript = [
        {
            "turn_index": 1,
            "player_action": "I ask Bran about the witness.",
            "turn_result": {
                "manual_turn_summary": {
                    "raw_narration_payload": {
                        "format_version": "rpg_narration_v2",
                        "source": "deterministic_runtime_narration_fallback",
                        "narration": "Bran answers.",
                        "npc": {"speaker": "Bran", "line": "Tell me more."},
                        "runtime_narration_diagnostics": {
                            "provider_requested": True,
                            "provider_present": False,
                            "provider_attempted": False,
                            "provider_valid": False,
                            "provider_errors": ["provider_not_available"],
                            "fallback_used": True,
                        },
                    }
                }
            },
        }
    ]

    model = build_campaign_report_model(
        transcript=transcript,
        summary={"session_id": "s"},
        metrics={},
        health={},
    )

    diagnostics = model["runtime_narration_diagnostics"]
    assert diagnostics["fallback_used_turns"] == 1
    assert diagnostics["provider_error_counts"]["provider_not_available"] == 1


def test_chapter_status_recommends_next_objective_when_active_exists():
    state = {
        "campaign_director_state": {"campaign_title": "Test Campaign"},
        "story_arc_state": {"arcs": {"arc:x": {"stage": "bandit_trail"}}},
    }
    model_like = {
        "milestones": [
            {"title": "Find witness", "status": "completed"},
            {"title": "Prepare for the bandit road", "status": "active"},
        ]
    }

    status = build_chapter_status(state, model_like)

    assert status["active_objective_count"] == 1
    assert "can continue" in status["recommendation"]
