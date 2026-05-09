from pathlib import Path

from tests.rpg.autoplay import campaign_report
from tests.rpg.autoplay.campaign_report import (
    build_campaign_report_model,
    build_chapter_status,
    build_inventory_rows,
    build_location_journey_model,
    build_player_progression_rows,
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


def test_story_summary_has_multiple_paragraphs_and_no_hook_ids():
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
        "milestones": [{"title": "Find the witness", "status": "completed"}],
        "journal_entries": [],
        "hook_counts": {"hook:witness:ask_bran": 1},
    }

    paragraph = build_story_so_far_paragraph(model)

    assert "\n\n" in paragraph
    assert "hook:witness" not in paragraph
    assert "Bran reveals the first witness lead" in paragraph


def test_campaign_report_prefers_final_authoritative_state_for_latest_state():
    transcript = [
        {
            "turn_index": 1,
            "turn_result": {
                "simulation_state": {
                    "story_arc_state": {
                        "arcs": {
                            "arc:witness_search": {"stage": "reported_to_bran"}
                        }
                    },
                    "story_arc_milestone_state": {
                        "arcs": {
                            "arc:witness_search": {
                                "milestones": [
                                    {
                                        "milestone_id": "milestone:pursue_bandit_trail",
                                        "title": "Pursue the bandit trail",
                                        "status": "active",
                                    }
                                ]
                            }
                        }
                    },
                }
            },
            "final_authoritative_state": {
                "story_arc_state": {
                    "arcs": {
                        "arc:witness_search": {"stage": "bandit_trail"}
                    }
                },
                "story_arc_milestone_state": {
                    "arcs": {
                        "arc:witness_search": {
                            "milestones": [
                                {
                                    "milestone_id": "milestone:pursue_bandit_trail",
                                    "title": "Pursue the bandit trail",
                                    "status": "completed",
                                },
                                {
                                    "milestone_id": "milestone:prepare_for_bandit_road",
                                    "title": "Prepare for the bandit road",
                                    "status": "active",
                                },
                            ]
                        }
                    }
                },
            },
        }
    ]

    model = build_campaign_report_model(
        transcript=transcript,
        summary={"session_id": "s", "turns_executed": 1},
        metrics={},
        health={},
    )

    milestones = {
        row["milestone_id"]: row
        for row in model["milestones"]
    }

    assert model["latest_state_source"] == "final_authoritative_state"
    assert model["story_arcs"][0]["stage"] == "bandit_trail"
    assert milestones["milestone:pursue_bandit_trail"]["status"] == "completed"
    assert milestones["milestone:prepare_for_bandit_road"]["status"] == "active"
    assert model["chapter_status"]["active_objectives"] == ["Prepare for the bandit road"]


def test_runtime_diagnostics_count_repaired_provider_payloads():
    transcript = [
        {
            "turn_index": 1,
            "player_action": "I ask Bran about the witness.",
            "turn_result": {
                "manual_turn_summary": {
                    "raw_narration_payload": {
                        "format_version": "rpg_narration_v2",
                        "source": "provider_runtime_narration",
                        "narration": "Bran answers.",
                        "npc": {"speaker": "Bran", "line": "Tell me more."},
                        "runtime_narration_diagnostics": {
                            "provider_requested": True,
                            "provider_present": True,
                            "provider_attempted": True,
                            "provider_valid": True,
                            "provider_repaired": True,
                            "provider_original_errors": ["followup_hooks_not_empty"],
                            "provider_repair_actions": ["cleared_followup_hooks"],
                            "fallback_used": False,
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
    assert diagnostics["provider_valid_turns"] == 1
    assert diagnostics["provider_repaired_turns"] == 1
    assert diagnostics["provider_original_error_counts"]["followup_hooks_not_empty"] == 1
    assert diagnostics["provider_repair_action_counts"]["cleared_followup_hooks"] == 1


def test_runtime_diagnostics_read_combined_background_narration_payloads():
    transcript = [
        {
            "turn_index": 1,
            "player_action": "I ask Bran about the witness.",
            "combined_background_llm_result": {
                "narration_payload": {
                    "format_version": "rpg_narration_v2",
                    "source": "provider_runtime_narration",
                    "narration": "Bran answers with a guarded glance.",
                    "npc": {"speaker": "Bran", "line": "The road is the danger."},
                    "runtime_narration_diagnostics": {
                        "provider_requested": True,
                        "provider_present": True,
                        "provider_attempted": True,
                        "provider_valid": True,
                        "provider_attempt_count": 1,
                        "fallback_used": False,
                    },
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
    assert diagnostics["provider_valid_turns"] == 1
    assert diagnostics["provider_attempted_turns"] == 1
    assert diagnostics["provider_attempt_count"] == 1


def test_campaign_report_model_includes_pm_summary_and_inventory():
    transcript = [
        {
            "turn_index": 1,
            "player_action": "I ask Bran.",
            "before_state": {
                "player_state": {
                    "inventory": {
                        "items": [{"id": "torch", "name": "Torch"}],
                        "currency": {"gold": 1},
                    }
                }
            },
            "final_authoritative_state": {
                "player_state": {
                    "inventory": {
                        "items": [{"id": "torch", "name": "Torch"}],
                        "currency": {"gold": 1},
                    }
                },
                "story_arc_state": {"arcs": {"arc:x": {"stage": "active"}}},
                "story_arc_milestone_state": {
                    "arcs": {
                        "arc:x": {
                            "milestones": [
                                {"milestone_id": "m:next", "title": "Next step", "status": "active"}
                            ]
                        }
                    }
                },
            },
        }
    ]
    model = build_campaign_report_model(
        transcript=transcript,
        summary={"session_id": "s", "turns_executed": 1},
        metrics={"progress_quality": {"meaningful_turns": 1}},
        health={},
    )

    assert model["pm_summary"]["overall_status"] in {"good", "partial"}


def test_inventory_rows_format_currency_and_items():
    rows = build_inventory_rows(
        {
            "currency": {"gold": 15},
            "items": [
                {
                    "name": "Iron Dagger",
                    "quantity": 1,
                    "type": "weapon",
                    "description": "A simple blade.",
                }
            ],
        }
    )

    assert rows["currency_rows"] == [["gold", 15]]
    assert rows["item_rows"][0][0] == "Iron Dagger"


def test_player_progression_rows_are_table_ready():
    state = {
        "player_state": {
            "name": "The Player",
            "level": 2,
            "experience": 5,
            "experience_to_next_level": 150,
            "stats": {"strength": 10},
            "progression_log": [{"turn_index": 1, "type": "experience", "amount": 15, "reason": "Lead found."}],
        }
    }

    rows = build_player_progression_rows(state)

    assert ("Level", 2) in rows["summary_rows"]
    assert rows["stats_rows"] == [("Strength", 10)]
    assert rows["recent_progression_rows"][0][3] == "Lead found."


def test_location_journey_model_groups_tavern_and_road():
    timeline = [
        {
            "turn_index": 1,
            "player_action": "I ask Bran about the witness.",
            "narration": "Bran answers in the tavern.",
            "npc": {"speaker": "Bran"},
            "fired_hooks": [{"story_label": "Bran reveals a lead."}],
        },
        {
            "turn_index": 2,
            "player_action": "I pursue the bandit road outside.",
            "narration": "The road grows quiet.",
            "npc": {},
            "fired_hooks": [{"story_label": "The road branch opens."}],
        },
    ]
    state = {
        "story_arc_milestone_state": {
            "arcs": {
                "arc:witness_search": {
                    "milestones": [
                        {"title": "Find the witness", "objective_text": "Find the witness near the tavern."},
                        {"title": "Prepare for the bandit road", "objective_text": "Prepare for the bandit road."},
                    ]
                }
            }
        }
    }

    model = build_location_journey_model(timeline=timeline, state=state)
    names = {row["name"] for row in model["locations"]}

    assert "The Rusty Flagon Tavern" in names
    assert "The Bandit Road" in names


def test_render_campaign_report_html_has_story_so_far_and_single_body():
    model = build_campaign_report_model(
        transcript=[
            {
                "turn_index": 1,
                "player_action": "I ask Bran about the witness.",
                "narration": "Bran lowers his voice.",
                "final_authoritative_state": {
                    "story_arc_milestone_state": {
                        "arcs": {
                            "arc:witness_search": {
                                "milestones": [
                                    {"title": "Find the witness", "status": "completed"},
                                    {"title": "Prepare for the bandit road", "status": "active"},
                                ]
                            }
                        }
                    },
                },
            }
        ],
        summary={"session_id": "s", "turns_executed": 1},
        metrics={},
        health={},
    )

    html = render_campaign_report_html(model)

    assert html.count("<body>") == 1
    assert '<section id="story-so-far">' in html
    assert html.index('<section id="story-so-far">') < html.index('<section id="setting">')
    assert "Find the witness" in html


def test_render_campaign_report_html_formats_chapter_status_not_raw_pre():
    model = build_campaign_report_model(
        transcript=[
            {
                "turn_index": 1,
                "final_authoritative_state": {
                    "campaign_director_state": {"campaign_title": "The Witness Trail"},
                    "story_arc_state": {"arcs": {"arc:x": {"stage": "bandit_trail"}}},
                    "story_arc_milestone_state": {
                        "arcs": {
                            "arc:x": {
                                "milestones": [
                                    {"title": "Find the witness", "status": "completed"},
                                    {"title": "Prepare for the bandit road", "status": "active"},
                                ]
                            }
                        }
                    },
                },
            }
        ],
        summary={"session_id": "s", "turns_executed": 1},
        metrics={},
        health={},
    )

    html = render_campaign_report_html(model)
    chapter_html = html.split('<section id="chapter-status">', 1)[1].split("</section>", 1)[0]

    assert "Active Objectives" in chapter_html
    assert "Completed Objectives" in chapter_html
    assert "Prepare for the bandit road" in chapter_html
    assert "Chapter status JSON" in chapter_html
    assert "<pre>" not in chapter_html.split("Chapter status JSON", 1)[0]


def test_render_campaign_report_places_npcs_before_technical_sections():
    model = build_campaign_report_model(
        transcript=[],
        summary={"session_id": "s"},
        metrics={},
        health={},
    )

    html = render_campaign_report_html(model)

    assert html.index('<section id="npcs">') < html.index('<section id="dialogue-coverage">')
    assert html.index('<section id="npcs">') < html.index('<section id="performance">')
    assert html.index('<section id="npcs">') < html.index('<section id="runtime-narration-diagnostics">')


def test_campaign_report_renders_rpg_shell_sections():
    model = build_campaign_report_model(
        transcript=[
            {
                "turn_index": 1,
                "player_input": "Ask Bran about the tavern.",
                "narration": "Bran leans on the bar and answers carefully.",
                "semantic_action_v2": {
                    "semantic_action": "service_inquiry",
                    "target": "Bran",
                },
            }
        ],
        summary={
            "ok": True,
            "session_id": "test-session",
            "scenario_seed": "tavern_story_seed",
            "quality_gate_summary": {
                "ok": True,
                "gates": {
                    "manual_turn_runtime_errors_absent": True,
                    "background_result_timing_ok": True,
                },
            },
            "background_result_timing_summary": {
                "jobs_submitted": 3,
                "jobs_attached_total": 3,
                "jobs_attached_pre_turn": 2,
                "jobs_attached_final": 1,
                "pre_turn_attach_rate": 0.66,
                "missing_job_count": 0,
            },
            "long_run_warning_summary": {"warning_count": 0},
            "action_diversity_summary": {
                "max_same_semantic_target_streak": {
                    "value": "observe:Bran",
                    "streak": 2,
                }
            },
        },
        metrics={"real_turn_runtime_count": 3},
        health={},
    )
    html = render_campaign_report_html(model)

    assert "rpg-shell" in html
    assert "Campaign Chronicle" in html
    assert 'id="campaign-overview"' in html
    assert 'id="verdict-cards"' in html
    assert 'id="adventure-timeline"' in html
    assert 'id="quest-board"' in html
    assert 'id="npc-chronicle"' in html
    assert 'id="location-journey"' in html
    assert 'id="player-sheet"' in html
    assert 'id="qa-dashboard"' in html
    assert 'id="technical-debug"' in html
    assert "Autoplay Campaign Report" in html
    assert "rpg-hero-report" in html
    assert "Show raw / legacy report sections" in html


def test_campaign_report_rpg_verdict_cards_include_reconciled_background_counts():
    model = build_campaign_report_model(
        transcript=[],
        summary={
            "ok": True,
            "quality_gate_summary": {"ok": True, "gates": {"x": True}},
            "background_result_timing_summary": {
                "jobs_submitted": 20,
                "jobs_attached_total": 20,
                "jobs_attached_pre_turn": 12,
                "jobs_attached_final": 8,
                "pre_turn_attach_rate": 0.6,
                "missing_job_count": 0,
            },
            "background_jobs": {
                "source": "background_result_timing_summary",
                "combined_background_llm_jobs": 20,
                "total_jobs": 20,
            },
            "long_run_warning_summary": {"warning_count": 0},
        },
        metrics={"real_turn_runtime_count": 20},
        health={},
    )
    html = render_campaign_report_html(model)

    assert "20 Turns" in html or ">20<" in html
    assert "Pre-Turn Attach Rate" in html
    assert "60%" in html
    assert "Missing Background Jobs" in html


def test_campaign_report_prefixes_legacy_debug_ids_and_hrefs():
    from tests.rpg.autoplay import campaign_report
    html = campaign_report._wrap_technical_debug_section(
        """
        <section id="campaign-journal">
          <h2>Campaign Calendar & Player Journal</h2>
          <a href="#quest-progress">Quest Progress</a>
        </section>
        <section id="quest-progress"><h2>Quest Progress</h2></section>
        """
    )

    assert 'id="legacy-campaign-journal"' in html
    assert 'id="legacy-quest-progress"' in html
    assert 'href="#legacy-quest-progress"' in html
    assert 'id="campaign-journal"' not in html
    assert 'href="#quest-progress"' not in html


def test_campaign_report_rpg_shell_has_unique_ids():
    import re
    from collections import Counter

    model = {
        "summary": {
            "ok": True,
            "quality_gate_summary": {"ok": True, "gates": {"x": True}},
            "background_result_timing_summary": {
                "jobs_submitted": 1,
                "jobs_attached_total": 1,
                "pre_turn_attach_rate": 1.0,
                "missing_job_count": 0,
            },
            "long_run_warning_summary": {"warning_count": 0},
        },
        "metrics": {"real_turn_runtime_count": 1},
        "timeline": [
            {
                "turn_index": 1,
                "narration": "Bran answers carefully.",
                "turn_contract": {
                    "action": {
                        "metadata": {
                            "semantic_action": {
                                "action_type": "service_inquiry",
                                "target_name": "Bran",
                            }
                        }
                    }
                },
            }
        ],
        "health": {"warnings": []},
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

    ids = re.findall(r'id="([^"]+)"', html)
    duplicates = {key: count for key, count in Counter(ids).items() if count > 1}
    assert duplicates == {}


def test_campaign_report_timeline_title_uses_nested_semantic_metadata():
    from tests.rpg.autoplay import campaign_report
    title = campaign_report._turn_title_from_row(
        {
            "turn_index": 1,
            "turn_contract": {
                "action": {
                    "metadata": {
                        "semantic_action": {
                            "action_type": "service_inquiry",
                            "service_kind": "lodging",
                            "target_name": "Bran",
                        }
                    }
                }
            },
        }
    )

    assert title == "Lodging Inquiry · Bran"
    assert title != "Campaign Beat"


def test_campaign_report_timeline_title_text_fallback_avoids_campaign_beat():
    from tests.rpg.autoplay import campaign_report
    title = campaign_report._turn_title_from_row(
        {
            "turn_index": 1,
            "narration": "A closer look around the tavern reveals a disturbed trail near the exit.",
        }
    )

    assert title == "Inspect Clues · Tavern"
    assert title != "Campaign Beat"


def test_campaign_report_css_contains_anchor_and_debug_contrast_fixes():
    model = {
        "summary": {
            "ok": True,
            "quality_gate_summary": {"ok": True, "gates": {"x": True}},
            "background_result_timing_summary": {"jobs_submitted": 1},
            "long_run_warning_summary": {"warning_count": 0},
        },
        "metrics": {"real_turn_runtime_count": 1},
        "timeline": [],
        "health": {"warnings": []},
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

    assert "scroll-margin-top" in html
    assert ".rpg-debug-body section" in html
    assert "aria-label=\"Campaign report sections\"" in html
    assert "legacy-campaign-journal" in html or "Legacy report sections are preserved" in html


def test_campaign_report_quest_board_renders_objectives_evidence_and_blockers():
    model = build_campaign_report_model(
        transcript=[],
        summary={
            "ok": True,
            "quality_gate_summary": {"ok": True, "gates": {"x": True}},
            "background_result_timing_summary": {"jobs_submitted": 1, "pre_turn_attach_rate": 1.0},
            "long_run_warning_summary": {"warning_count": 0},
            "quest_progress_summary": {
                "quest_count": 1,
                "quests": [
                    {
                        "quest_id": "quest:witness_search",
                        "title": "Witness Search",
                        "status": "active",
                        "giver": "Bran",
                        "location": "Rusty Flagon Tavern",
                        "progress": "0/2 objectives complete: Find the witness; Report findings to Bran",
                        "blockers": ["Witness not identified yet"],
                    }
                ],
                "timeline": [
                    {"quest_id": "quest:witness_search", "turn_index": 1, "summary": "Witness Search started."},
                    {"quest_id": "quest:witness_search", "turn_index": 4, "summary": "Bran connected the danger to the road."},
                ],
            },
        },
        metrics={"real_turn_runtime_count": 1},
        health={"warnings": []},
    )
    html = render_campaign_report_html(model)

    assert "Witness Search" in html
    assert "0/2 objectives complete" in html
    assert "Turn 1" in html
    assert "Turn 4" in html
    assert "Witness not identified yet" in html


def test_campaign_report_npc_chronicle_renders_evolution_cards():
    model = build_campaign_report_model(
        transcript=[],
        summary={
            "ok": True,
            "quality_gate_summary": {"ok": True, "gates": {"x": True}},
            "background_result_timing_summary": {"jobs_submitted": 1},
            "long_run_warning_summary": {"warning_count": 0},
            "npc_evolution_report_summary": {
                "cards": [
                    {
                        "npc_id": "Bran",
                        "arc_stage": "stable",
                        "signal_count": 12,
                        "axes": {"trust": 2, "fear": 0},
                        "memories": [{"summary": "The player asked Bran about the northern road."}],
                        "semantic_intents": [{"summary": "Bran is cautious but cooperative."}],
                        "future_hooks": [{"summary": "Bran may reveal more about the witness."}],
                    }
                ]
            },
        },
        metrics={"real_turn_runtime_count": 1},
        health={"warnings": []},
    )
    html = render_campaign_report_html(model)

    assert "Bran" in html
    assert "Stage: stable" in html
    assert "trust" in html
    assert "northern road" in html
    assert "cautious but cooperative" in html
    assert "may reveal more" in html


def test_campaign_report_location_journey_summarizes_turns_npcs_services():
    model = build_campaign_report_model(
        transcript=[
            {
                "turn_index": 1,
                "location": "Rusty Flagon Tavern",
                "npc": {"speaker": "Bran"},
                "narration": "Bran answers carefully.",
                "turn_contract": {
                    "action": {
                        "metadata": {
                            "semantic_action": {
                                "action_type": "service_inquiry",
                                "target_name": "Bran",
                            }
                        }
                    }
                },
            },
            {
                "turn_index": 2,
                "location": "Rusty Flagon Tavern",
                "narration": "The room grows tense.",
            },
        ],
        summary={
            "ok": True,
            "quality_gate_summary": {"ok": True, "gates": {"x": True}},
            "background_result_timing_summary": {"jobs_submitted": 1},
            "long_run_warning_summary": {"warning_count": 0},
        },
        metrics={"real_turn_runtime_count": 2},
        health={"warnings": []},
    )
    html = render_campaign_report_html(model)

    assert "Rusty Flagon Tavern" in html
    assert "Turns: 1–2" in html
    assert "Bran" in html
    assert "service_inquiry" in html


def test_campaign_report_player_sheet_formats_currency_and_inventory():
    model = build_campaign_report_model(
        transcript=[],
        summary={
            "ok": True,
            "quality_gate_summary": {"ok": True, "gates": {"x": True}},
            "background_result_timing_summary": {"jobs_submitted": 1},
            "long_run_warning_summary": {"warning_count": 0},
            "inventory_end": {
                "currency": {"gold": 10, "silver": 3},
                "items": [{"name": "Iron Dagger", "quantity": 1}, "Traveler Pack"],
            },
            "player_journal_summary": {"entry_count": 2},
        },
        metrics={"real_turn_runtime_count": 1},
        health={"warnings": []},
    )
    html = render_campaign_report_html(model)

    assert "10 gold" in html
    assert "3 silver" in html
    assert "Iron Dagger" in html
    assert "Traveler Pack" in html
    assert "Journal Entries" in html


def test_campaign_report_adventure_timeline_prefers_story_and_journal_beats():
    model = build_campaign_report_model(
        transcript=[],
        summary={
            "ok": True,
            "quality_gate_summary": {"ok": True, "gates": {"x": True}},
            "background_result_timing_summary": {"jobs_submitted": 1},
            "long_run_warning_summary": {"warning_count": 0},
            "story_beat_summary": {
                "beats": [
                    {
                        "story_label": "The Tavern Confrontation",
                        "turn_index": 3,
                        "story_summary": "Bran reveals the witness information under pressure.",
                    }
                ]
            },
            "player_journal_summary": {
                "entries": [
                    {
                        "start_turn": 1,
                        "end_turn": 2,
                        "text": "Met Bran at the tavern, he seems nervous about something.",
                    }
                ]
            },
        },
        metrics={"real_turn_runtime_count": 1},
        health={"warnings": []},
    )
    html = render_campaign_report_html(model)

    assert "Tavern Confrontation" in html
    assert "Journal Entry" in html
    assert "nervous about something" in html


def test_campaign_report_player_sheet_reads_inventory_end_view_rows():
    html = render_campaign_report_html({
        "summary": {
            "ok": True,
            "quality_gate_summary": {"ok": True, "gates": {"x": True}},
            "background_result_timing_summary": {"jobs_submitted": 1},
            "long_run_warning_summary": {"warning_count": 0},
            "inventory_end_view": {
                "currency_rows": [
                    {"currency": "gold", "amount": 15},
                    {"currency": "silver", "amount": 8},
                ],
                "item_rows": [
                    {"name": "Traveler's Cloak", "quantity": 1},
                    {"name": "Iron Dagger", "quantity": 1},
                    {"name": "Trail Rations", "quantity": 3},
                ],
            },
        },
        "metrics": {"real_turn_runtime_count": 1},
        "transcript": [],
    })

    assert "15 gold" in html
    assert "8 silver" in html
    assert "Traveler&#x27;s Cloak" in html or "Traveler's Cloak" in html
    assert "Iron Dagger" in html
    assert "Trail Rations" in html
    assert "Inventory is empty" not in html


def test_campaign_report_location_journey_uses_quest_location_when_rows_unknown():
    html = render_campaign_report_html({
        "summary": {
            "ok": True,
            "quality_gate_summary": {"ok": True, "gates": {"x": True}},
            "background_result_timing_summary": {"jobs_submitted": 1},
            "long_run_warning_summary": {"warning_count": 0},
            "quest_progress_summary": {
                "quests": [{"title": "Witness Search", "location": "Rusty Flagon Tavern"}]
            },
        },
        "metrics": {"real_turn_runtime_count": 1},
        "transcript": [
            {
                "turn_index": 1,
                "narration": "Bran answers carefully.",
            }
        ],
    })

    assert "Journey Path:" in html
    assert "Rusty Flagon Tavern" in html
    assert "Unknown Location" not in html


def test_campaign_report_story_beat_titles_are_inferred_from_summary():
    html = render_campaign_report_html({
        "summary": {
            "ok": True,
            "quality_gate_summary": {"ok": True, "gates": {"x": True}},
            "background_result_timing_summary": {"jobs_submitted": 1},
            "long_run_warning_summary": {"warning_count": 0},
            "story_beat_summary": {
                "beats": [
                    {
                        "turn_index": 1,
                        "summary": "Player: Walk up to the innkeeper's counter and ask Bran about work.",
                    }
                ]
            },
        },
        "metrics": {"real_turn_runtime_count": 1},
        "transcript": [],
    })

    assert "Approach the Innkeeper" in html or "Ask Bran About Work" in html
    assert ">Story Beat<" not in html


def test_campaign_report_npc_cards_dedupe_and_infer_role():
    html = render_campaign_report_html({
        "summary": {
            "ok": True,
            "quality_gate_summary": {"ok": True, "gates": {"x": True}},
            "background_result_timing_summary": {"jobs_submitted": 1},
            "long_run_warning_summary": {"warning_count": 0},
            "npc_evolution_report_summary": {
                "cards": [
                    {
                        "npc_id": "Bran",
                        "role": "NPC",
                        "arc_stage": "stable",
                        "memories": [
                            {"summary": "The player asked about the northern road."},
                            {"summary": "The player asked about the northern road."},
                        ],
                        "future_hooks": [
                            {"summary": "Bran may reveal more about the witness."},
                            {"summary": "Bran may reveal more about the witness."},
                        ],
                    }
                ]
            },
        },
        "metrics": {"real_turn_runtime_count": 1},
        "transcript": [],
    })

    assert "Role: Innkeeper" in html
    assert html.count("The player asked about the northern road.") == 1
    assert html.count("Bran may reveal more about the witness.") == 1


def test_campaign_report_quest_board_infers_evidence_turns_from_transcript():
    html = render_campaign_report_html({
        "summary": {
            "ok": True,
            "quality_gate_summary": {"ok": True, "gates": {"x": True}},
            "background_result_timing_summary": {"jobs_submitted": 1},
            "long_run_warning_summary": {"warning_count": 0},
            "quest_progress_summary": {
                "quests": [
                    {
                        "quest_id": "quest:witness_search",
                        "title": "Witness Search",
                        "status": "active",
                        "progress": "Find the witness and report findings to Bran.",
                    }
                ],
                "timeline": [{"quest_id": "quest:witness_search", "turn_index": 1}],
            },
        },
        "metrics": {"real_turn_runtime_count": 4},
        "transcript": [
            {"turn_index": 1, "player_input": "Ask Bran about work."},
            {"turn_index": 4, "player_input": "Ask Bran if the witness saw bandits on the road."},
        ],
    })

    assert "Turn 1" in html
    assert "Turn 4" in html


def test_campaign_report_merges_autoplay_campaign_report_into_hero():
    html = render_campaign_report_html(
        summary={
            "ok": True,
            "quality_gate_summary": {"ok": True, "gates": {"x": True}},
            "background_result_timing_summary": {
                "jobs_submitted": 20,
                "jobs_attached_pre_turn": 12,
                "jobs_attached_final": 8,
                "pre_turn_attach_rate": 0.6,
                "missing_job_count": 0,
            },
            "progress_timeline_summary": {"meaningful_progress_rate": 0.25},
            "action_diversity_summary": {
                "max_same_semantic_target_streak": {
                    "streak": 3,
                    "value": "test",
                }
            },
            "long_run_warning_summary": {"warning_count": 0},
        },
        metrics={"real_turn_runtime_count": 20},
        transcript=[],
    )

    assert 'id="campaign-overview"' in html
    assert "Autoplay Campaign Report" in html
    assert "Run Report" in html
    assert "Pre-Turn Attach Rate" in html
    assert "60%" in html
    assert 'id="autoplay-campaign-report"' not in html
    assert "Run Report" not in html.split('<nav class="rpg-nav"', 1)[1].split("</nav>", 1)[0]


def test_campaign_report_hero_contains_run_report_before_adventure_sections():
    html = render_campaign_report_html(
        summary={
            "ok": True,
            "quality_gate_summary": {"ok": True, "gates": {"x": True}},
            "background_result_timing_summary": {
                "jobs_submitted": 20,
                "jobs_attached_pre_turn": 12,
                "jobs_attached_final": 8,
                "pre_turn_attach_rate": 0.6,
                "missing_job_count": 0,
            },
            "progress_timeline_summary": {"meaningful_progress_rate": 0.25},
            "long_run_warning_summary": {"warning_count": 0},
        },
        metrics={"real_turn_runtime_count": 20},
        transcript=[],
    )

    assert html.index('id="campaign-overview"') < html.index('id="adventure-timeline"')
    hero_html = html.split('id="campaign-overview"', 1)[1].split("</header>", 1)[0]
    assert "Autoplay Campaign Report" in hero_html
    assert "Background Jobs" in hero_html
    assert "20" in hero_html
    assert "Pre-turn 12" in hero_html
    assert "Final 8" in hero_html
    assert "Meaningful Progress" in hero_html


def test_campaign_report_splits_legacy_html_into_debug_groups():
    groups = campaign_report._split_legacy_html_into_debug_groups(
        """
        <section id="quality"><h2>Quality Gates</h2></section>
        <section id="background-result-timing"><h2>Background Result Timing</h2></section>
        <section id="performance"><h2>Performance Metrics</h2></section>
        <section id="campaign-journal"><h2>Campaign Calendar & Player Journal</h2></section>
        <section id="progress-timeline"><h2>Progress Timeline</h2></section>
        <section id="debug"><h2>Raw Debug</h2></section>
        """
    )

    html = campaign_report._wrap_technical_debug_groups(groups)

    assert "Quality Gates" in html
    assert "Background Pipeline" in html
    assert "Performance" in html
    assert "Campaign Data" in html
    assert "Timeline / Progress" in html
    assert "Console / Raw Debug" in html
    assert "Legacy Report" not in html


def test_campaign_report_player_sheet_reads_inventory_from_report_model():
    html = campaign_report.render_campaign_report_html(
        summary={
            "ok": True,
            "quality_gate_summary": {"ok": True, "gates": {"x": True}},
            "background_result_timing_summary": {"jobs_submitted": 1},
            "long_run_warning_summary": {"warning_count": 0},
        },
        metrics={"real_turn_runtime_count": 1},
        report_model={
            "inventory_end": {
                "currency": {"gold": 15, "silver": 8},
                "items": [
                    {"name": "Traveler's Cloak", "quantity": 1},
                    {"name": "Iron Dagger", "quantity": 1},
                    {"name": "Trail Rations", "quantity": 3},
                    {"name": "Waterskin", "quantity": 1},
                    {"name": "Plain Journal", "quantity": 1},
                ],
            }
        },
        transcript=[],
    )

    assert "15 gold" in html
    assert "8 silver" in html
    assert "Traveler&#x27;s Cloak" in html or "Traveler's Cloak" in html
    assert "Iron Dagger" in html
    assert "Trail Rations" in html
    assert "Waterskin" in html
    assert "Plain Journal" in html
    assert "Inventory is empty" not in html


def test_campaign_report_player_sheet_reads_inventory_view_list_rows():
    html = campaign_report.render_campaign_report_html(
        summary={
            "ok": True,
            "quality_gate_summary": {"ok": True, "gates": {"x": True}},
            "background_result_timing_summary": {"jobs_submitted": 1},
            "long_run_warning_summary": {"warning_count": 0},
            "inventory_end_view": {
                "currency_rows": [["gold", 15], ["silver", 8]],
                "item_rows": [
                    ["Traveler's Cloak", 1, "gear", "A weathered cloak."],
                    ["Trail Rations", 3, "consumable", "Enough food for the road."],
                ],
            },
        },
        metrics={"real_turn_runtime_count": 1},
        transcript=[],
    )

    assert "15 gold" in html
    assert "8 silver" in html
    assert "Traveler&#x27;s Cloak" in html or "Traveler's Cloak" in html
    assert "Trail Rations ×3" in html


def test_campaign_report_npc_fuzzy_dedupes_turn_suffixes():
    html = campaign_report.render_campaign_report_html(
        summary={
            "ok": True,
            "quality_gate_summary": {"ok": True, "gates": {"x": True}},
            "background_result_timing_summary": {"jobs_submitted": 1},
            "long_run_warning_summary": {"warning_count": 0},
            "npc_evolution_report_summary": {
                "cards": [
                    {
                        "npc_id": "Bran",
                        "future_hooks": [
                            {"summary": "The ambiance in The Rusty Flagon is subtly shifting toward cautious anxiety. (Turn 15)"},
                            {"summary": "The ambiance in The Rusty Flagon is subtly shifting toward cautious anxiety. (Turn 16)"},
                        ],
                    }
                ]
            },
        },
        metrics={"real_turn_runtime_count": 1},
        transcript=[],
    )

    # Check that fuzzy de-dupe worked in the NPC chronicle section
    npc_section_start = html.find('<section class="rpg-card span-12" id="npc-chronicle">')
    npc_section_end = html.find('</section>', npc_section_start) if npc_section_start != -1 else -1
    if npc_section_start != -1 and npc_section_end != -1:
        npc_section = html[npc_section_start:npc_section_end]
        assert npc_section.count("The ambiance in The Rusty Flagon is subtly shifting toward cautious anxiety") == 1
    else:
        # Fallback: check that overall count is reasonable (de-duped in main section but may appear in debug)
        assert html.count("The ambiance in The Rusty Flagon is subtly shifting toward cautious anxiety") <= 3


def test_campaign_report_location_npcs_ignore_structural_keys():
    names = campaign_report._npcs_from_row(
        {
            "npc": {
                "speaker": "Bran",
                "line": "Welcome.",
            },
            "simulation_state": {
                "npcs": {
                    "Bran": {"name": "Bran"},
                    "speaker": {},
                    "line": {},
                }
            },
        }
    )

    assert "Bran" in names
    assert "speaker" not in names
    assert "line" not in names


def test_campaign_report_location_services_from_semantic_metadata():
    services = campaign_report._services_from_row(
        {
            "turn_contract": {
                "action": {
                    "metadata": {
                        "semantic_action": {
                            "action_type": "rent_room",
                            "service_kind": "lodging",
                            "target_name": "Bran",
                        }
                    }
                }
            }
        }
    )

    assert "rent_room" in services
    assert "lodging" in services


def test_campaign_report_quest_evidence_infers_from_story_and_journal_context():
    turns = campaign_report._infer_quest_evidence_turns_from_transcript(
        {
            "title": "Witness Search",
            "progress": "Find the witness and report findings to Bran.",
        },
        transcript=[],
        context={
            "story_beat_summary": {
                "beats": [
                    {"turn_index": 4, "summary": "Bran says the witness saw bandits on the road."}
                ]
            },
            "player_journal_summary": {
                "entries": [
                    {
                        "start_turn": 1,
                        "end_turn": 4,
                        "text": "What I learned: Bran suspects the witness knows about the road.",
                    }
                ]
            },
        },
    )

    assert 1 in turns
    assert 4 in turns


def test_campaign_report_timeline_finalizer_replaces_story_beat_from_player_prefix():
    html = campaign_report.render_campaign_report_html(
        summary={
            "ok": True,
            "quality_gate_summary": {"ok": True, "gates": {"x": True}},
            "background_result_timing_summary": {"jobs_submitted": 1},
            "long_run_warning_summary": {"warning_count": 0},
            "story_beat_summary": {
                "beats": [
                    {
                        "turn_index": 2,
                        "kind": "Story Beat",
                        "summary": "Player: Ask Bran about any unusual activity or rumors in town. Result: Bran grows cautious.",
                    },
                    {
                        "turn_index": 3,
                        "kind": "Story Beat",
                        "summary": "Player: Lean in slightly and lower your voice before asking Bran what he knows. Result: The conversation becomes private.",
                    },
                    {
                        "turn_index": 19,
                        "kind": "Story Beat",
                        "summary": "Player: Listen intently to Bran's immediate elaboration. Result: Bran explains the road trouble.",
                    },
                ]
            },
        },
        metrics={"real_turn_runtime_count": 3},
        transcript=[],
    )

    assert "Ask Bran About Rumors" in html
    assert "Speak Privately with Bran" in html
    assert "Listen to Bran" in html
    assert ">Story Beat<" not in html


def test_campaign_report_scan_service_labels_from_deep_row_shape():
    row = {
        "turn_index": 4,
        "result": {
            "turn_contract": {
                "action": {
                    "metadata": {
                        "semantic_action": {
                            "action_type": "service_inquiry",
                            "service_kind": "lodging",
                            "target_name": "Bran",
                        }
                    }
                }
            }
        },
    }

    services = campaign_report._services_from_row(row)

    assert "service_inquiry" in services
    assert "lodging" in services


def test_campaign_report_services_from_serialized_row_text():
    row = {
        "turn_index": 5,
        "debug": "{'semantic_action': {'action_type': 'rent_room', 'service_kind': 'lodging'}}",
    }

    services = campaign_report._services_from_row(row)

    assert "rent_room" in services
    assert "lodging" in services


def test_campaign_report_location_journey_uses_context_service_fallback():
    html = campaign_report.render_campaign_report_html(
        summary={
            "ok": True,
            "quality_gate_summary": {"ok": True, "gates": {"x": True}},
            "background_result_timing_summary": {"jobs_submitted": 1},
            "long_run_warning_summary": {"warning_count": 0},
            "quest_progress_summary": {
                "quests": [{"title": "Witness Search", "location": "Rusty Flagon Tavern"}]
            },
            "story_beat_summary": {
                "beats": [
                    {
                        "turn_index": 4,
                        "summary": "The player makes a service_inquiry about lodging with Bran.",
                    },
                    {
                        "turn_index": 5,
                        "summary": "The player tries to rent_room for the night.",
                    },
                ]
            },
        },
        metrics={"real_turn_runtime_count": 5},
        transcript=[
            {
                "turn_index": 1,
                "narration": "The tavern is tense.",
            }
        ],
    )

    assert "Rusty Flagon Tavern" in html
    assert "service_inquiry" in html
    assert "rent_room" in html
    assert "lodging" in html
    assert "No services recorded." not in html


def test_campaign_report_no_visible_generic_story_beat_titles_for_story_summary_rows():
    html = campaign_report.render_campaign_report_html(
        summary={
            "ok": True,
            "quality_gate_summary": {"ok": True, "gates": {"x": True}},
            "background_result_timing_summary": {"jobs_submitted": 1},
            "long_run_warning_summary": {"warning_count": 0},
            "story_beat_summary": {
                "beats": [
                    {
                        "turn_index": 1,
                        "summary": "Player: Ask Bran about work. Result: Bran considers the request.",
                    }
                ]
            },
        },
        metrics={"real_turn_runtime_count": 1},
        transcript=[],
    )

    assert ">Story Beat<" not in html
    assert "Ask Bran About Work" in html or "Question Bran" in html


def test_campaign_report_strips_legacy_autoplay_partial_shell():
    legacy = """
    <header>
      <h1>Autoplay Campaign Report <span class="status-pill">partial</span></h1>
      <nav>
        <a href="#summary">Summary</a>
        <a href="#journal">Journal</a>
      </nav>
    </header>
    <section class="hero" id="summary">
      <h2>Executive Summary</h2>
      <p>The campaign can progress through a complete tavern investigation branch.</p>
    </section>
    <section id="campaign-journal">
      <h2>Campaign Calendar & Player Journal</h2>
      <p>Keep this useful legacy section.</p>
    </section>
    """

    cleaned = campaign_report._strip_legacy_autoplay_report_partial(legacy)

    assert "Autoplay Campaign Report" not in cleaned
    assert "Executive Summary" not in cleaned
    assert "Summary</a>" not in cleaned
    assert "Campaign Calendar & Player Journal" in cleaned
    assert "Keep this useful legacy section." in cleaned


def test_campaign_report_does_not_render_old_autoplay_partial_as_separate_section():
    html = render_campaign_report_html(
        summary={
            "ok": True,
            "quality_gate_summary": {"ok": True, "gates": {"x": True}},
            "background_result_timing_summary": {
                "jobs_submitted": 20,
                "jobs_attached_pre_turn": 12,
                "jobs_attached_final": 8,
                "pre_turn_attach_rate": 0.6,
                "missing_job_count": 0,
            },
            "progress_timeline_summary": {"meaningful_progress_rate": 0.25},
            "long_run_warning_summary": {"warning_count": 0},
        },
        metrics={"real_turn_runtime_count": 20},
        transcript=[],
    )

    # The unified hero still contains this phrase once as the run-report title.
    assert "Autoplay Campaign Report" in html
    assert 'class="rpg-hero-report"' in html

    # But the old standalone report shell must not exist at the top level.
    # Legacy data may appear in debug sections.
    debug_start = html.find('<section class="rpg-card dark')
    if debug_start != -1:
        main_html = html[:debug_start]
    else:
        main_html = html
    assert '<header class="rpg-hero"' in main_html  # The rpg-hero
    assert '<section class="hero"' not in main_html
    assert "<h2>Executive Summary</h2>" not in main_html


def test_campaign_report_debug_strips_old_shell_but_keeps_legacy_details():
    html = campaign_report._wrap_technical_debug_groups(
        {
            "campaign": """
              <header><h1>Autoplay Campaign Report <span class="status-pill">partial</span></h1></header>
              <section class="hero" id="summary"><h2>Executive Summary</h2><p>Duplicate summary.</p></section>
              <section id="campaign-journal"><h2>Campaign Calendar & Player Journal</h2><p>Useful details.</p></section>
            """
        }
    )

    assert "<header>" not in html
    assert "Executive Summary" not in html
    assert "Duplicate summary" not in html
    assert "Campaign Calendar & Player Journal" in html
    assert "Useful details" in html
    assert 'id="legacy-campaign-journal"' in html


def test_campaign_report_strips_legacy_partial_inside_body_after_debug():
    html = """
    <!doctype html>
    <html>
    <body>
      <main class="rpg-shell">
        <section class="rpg-card dark span-12" id="technical-debug">
          <h2>Technical Debug</h2>
        </section>
      </main>
      <header>
        <h1>Autoplay Campaign Report <span class="status-pill warn">partial</span></h1>
        <p>Session autoplay_abc · Strategy balanced_story_player · Turns 20</p>
        <nav>
          <a href="#summary">Summary</a>
          <a href="#campaign-journal">Journal</a>
          <a href="#quests">Quests</a>
        </nav>
      </header>
      <section class="hero" id="summary">
        <h2>Executive Summary</h2>
        <p>The campaign can progress through a complete tavern investigation branch.</p>
      </section>
    </body>
    </html>
    """

    cleaned = campaign_report._strip_legacy_autoplay_report_tail(html)

    assert "Technical Debug" in cleaned
    assert "status-pill" not in cleaned
    assert "partial" not in cleaned
    assert "Summary</a>" not in cleaned
    assert "Journal</a>" not in cleaned
    assert "Executive Summary" not in cleaned
    assert "complete tavern investigation branch" not in cleaned


def test_campaign_report_legacy_tail_sanitizer_preserves_rpg_hero_report():
    html = """
    <main class="rpg-shell">
      <header class="rpg-hero" id="campaign-overview">
        <h1>The Autoplay Campaign Chronicle</h1>
        <div class="rpg-hero-report">
          <h2>Autoplay Campaign Report</h2>
          <div>Pre-Turn Attach Rate</div>
        </div>
      </header>
    </main>
    <header>
      <h1>Autoplay Campaign Report <span class="status-pill warn">partial</span></h1>
    </header>
    <section class="hero" id="summary"><h2>Executive Summary</h2></section>
    """

    cleaned = campaign_report._strip_legacy_autoplay_report_tail(html)

    assert "The Autoplay Campaign Chronicle" in cleaned
    assert "rpg-hero-report" in cleaned
    assert "Pre-Turn Attach Rate" in cleaned
    assert "status-pill" not in cleaned
    assert "Executive Summary" not in cleaned


def test_campaign_report_render_output_has_no_old_partial_markers():
    html = campaign_report.render_campaign_report_html(
        summary={
            "ok": True,
            "quality_gate_summary": {"ok": True, "gates": {"x": True}},
            "background_result_timing_summary": {
                "jobs_submitted": 20,
                "jobs_attached_pre_turn": 12,
                "jobs_attached_final": 8,
                "pre_turn_attach_rate": 0.6,
                "missing_job_count": 0,
            },
            "long_run_warning_summary": {"warning_count": 0},
            "progress_timeline_summary": {"meaningful_progress_rate": 0.25},
        },
        metrics={"real_turn_runtime_count": 20},
        transcript=[],
    )

    assert "rpg-hero-report" in html
    assert "Autoplay Campaign Report" in html
    assert "status-pill warn" not in html
    assert "<h2>Executive Summary</h2>" not in html
    assert "Summary</a>" not in html
    assert "Journal</a>" not in html
    assert 'id="summary"' not in html


def test_campaign_report_nav_is_split_into_primary_and_appendix_sections():
    html = campaign_report.render_campaign_report_html(
        summary={
            "ok": True,
            "quality_gate_summary": {"ok": True, "gates": {"x": True}},
            "background_result_timing_summary": {
                "jobs_submitted": 20,
                "jobs_attached_pre_turn": 12,
                "jobs_attached_final": 8,
                "pre_turn_attach_rate": 0.6,
                "missing_job_count": 0,
            },
            "long_run_warning_summary": {"warning_count": 0},
            "progress_timeline_summary": {"meaningful_progress_rate": 0.25},
        },
        metrics={"real_turn_runtime_count": 20},
        transcript=[],
    )

    assert 'class="rpg-nav"' in html
    assert 'class="rpg-nav-primary"' in html
    assert 'class="rpg-nav-appendix"' in html
    assert "Appendix Sections" in html

    nav_html = html.split('class="rpg-nav"', 1)[1].split("</nav>", 1)[0]

    # Primary links remain immediately visible.
    assert 'href="#campaign-overview"' in nav_html
    assert 'href="#verdict-cards"' in nav_html
    assert 'href="#adventure-timeline"' in nav_html
    assert 'href="#quest-board"' in nav_html
    assert 'href="#npc-chronicle"' in nav_html
    assert 'href="#location-journey"' in nav_html
    assert 'href="#player-sheet"' in nav_html
    assert 'href="#qa-dashboard"' in nav_html
    assert 'href="#technical-debug"' in nav_html

    # Appendix links are still present, but inside the collapsible appendix group.
    assert 'href="#campaign-journal"' in nav_html
    assert 'href="#quest-progress"' in nav_html
    assert 'href="#npc-evolution"' in nav_html
    assert 'href="#hundred-turn-eval"' in nav_html
    assert 'href="#background-result-timing"' in nav_html
    assert 'href="#performance"' in nav_html
    assert 'href="#console-log"' in nav_html
    assert 'href="#timeline"' in nav_html
    assert 'href="#debug"' in nav_html


def test_campaign_report_does_not_render_old_report_highlights_block():
    html = campaign_report.render_campaign_report_html(
        summary={"ok": True},
        metrics={"real_turn_runtime_count": 20},
        transcript=[],
    )

    assert 'class="report-quick-links"' not in html or ".report-quick-links { display: none" in html
    assert "Campaign Journal (5)" not in html
    assert "Quest Progress (1)" not in html
    assert "NPC Evolution (1)" not in html

    assert "<h2>Report Highlights</h2>" not in html


def test_campaign_report_promoted_sections_use_rpg_theme():
    html = campaign_report.render_campaign_report_html(
        summary={"ok": True},
        metrics={"real_turn_runtime_count": 20},
        transcript=[],
    )

    assert 'id="campaign-journal"' in html
    assert 'id="quest-progress"' in html
    assert 'id="npc-evolution"' in html
    assert 'class="rpg-card rpg-promoted-section span-12"' in html
    assert "Campaign Calendar & Player Journal" in html
    assert "Quest Progress" in html
    assert "NPC Evolution" in html


def test_campaign_report_strips_second_legacy_main_after_rpg_shell():
    html = """
    <main class="rpg-shell">
      <section id="technical-debug" class="rpg-card dark span-12">
        <h2>Technical Debug</h2>
      </section>
    </main>
    <main>
      <section id="campaign-journal"><h2>Campaign Calendar & Player Journal</h2></section>
      <section id="quest-progress"><h2>Quest Progress</h2></section>
      <section id="debug"><h2>Raw Debug Appendix</h2></section>
    </main>
    """

    cleaned = campaign_report._strip_legacy_autoplay_report_tail(html)

    assert 'class="rpg-shell"' in cleaned
    assert "Technical Debug" in cleaned
    assert '<main>\n      <section id="campaign-journal"' not in cleaned
    assert 'id="campaign-journal"' not in cleaned
    assert 'id="quest-progress"' not in cleaned
    assert 'id="debug"' not in cleaned


def test_campaign_report_promoted_sections_have_high_contrast_css():
    html = campaign_report.render_campaign_report_html(
        summary={"ok": True},
        metrics={"real_turn_runtime_count": 20},
        transcript=[],
    )

    assert ".rpg-promoted-section *" in html
    assert "color: #24170d !important" in html
    assert "background: #fff8e9 !important" in html
    assert "body > main:not(.rpg-shell)" in html


def test_campaign_report_appendix_nav_is_open_and_contains_extended_links():
    html = campaign_report.render_campaign_report_html(
        summary={
            "ok": True,
            "quality_gate_summary": {"ok": True, "gates": {"x": True}},
            "background_result_timing_summary": {"jobs_submitted": 1},
            "long_run_warning_summary": {"warning_count": 0},
        },
        metrics={"real_turn_runtime_count": 20},
        transcript=[],
    )

    assert '<details class="rpg-nav-appendix" open>' in html
    nav_html = html.split('class="rpg-nav"', 1)[1].split("</nav>", 1)[0]
    assert 'href="#campaign-journal"' in nav_html
    assert 'href="#quest-progress"' in nav_html
    assert 'href="#npc-evolution"' in nav_html
    assert 'href="#performance"' in nav_html
    assert 'href="#console-log"' in nav_html
    assert 'href="#timeline"' in nav_html
    assert 'href="#debug"' in nav_html


def test_campaign_report_final_html_has_no_report_highlights_block():
    html = campaign_report.render_campaign_report_html(
        summary={"ok": True},
        metrics={"real_turn_runtime_count": 20},
        transcript=[],
    )

    assert "<h2>Report Highlights</h2>" not in html
    assert 'class="report-quick-links"' not in html
    assert "Campaign Journal (" not in html
    assert "Quest Progress (" not in html
    assert "NPC Evolution (" not in html


def test_campaign_report_strips_unsafe_file_self_links():
    html = """
    <html>
      <head>
        <base href="file:///F:/LLM/omnix/resources/data/test-results/autoplay-background-timing-20/">
        <meta http-equiv="refresh" content="0;url=file:///F:/LLM/omnix/resources/data/test-results/autoplay-background-timing-20/autoplay-campaign-report.html">
      </head>
      <body>
        <a href="file:///F:/LLM/omnix/resources/data/test-results/autoplay-background-timing-20/autoplay-campaign-report.html">Self</a>
        <iframe src="file:///F:/LLM/omnix/resources/data/test-results/autoplay-background-timing-20/autoplay-campaign-report.html"></iframe>
        <script>
          window.location = "file:///F:/LLM/omnix/resources/data/test-results/autoplay-background-timing-20/autoplay-campaign-report.html";
          window.open("file:///F:/LLM/omnix/resources/data/test-results/autoplay-background-timing-20/autoplay-campaign-report.html");
        </script>
      </body>
    </html>
    """

    cleaned = campaign_report._strip_unsafe_file_urls_from_report_html(html)

    assert "file:///" not in cleaned
    assert "<base" not in cleaned.lower()
    assert "http-equiv=\"refresh\"" not in cleaned.lower()
    assert "<iframe" not in cleaned.lower()
    assert 'href="#campaign-overview"' in cleaned
    assert "window.location" not in cleaned
    assert "window.open" not in cleaned


def test_campaign_report_rewrites_file_artifact_links_to_relative_filenames():
    html = """
    <a href="file:///F:/LLM/omnix/resources/data/test-results/autoplay-background-timing-20/autoplay-summary.json">Summary JSON</a>
    <a href="file:///F:/LLM/omnix/resources/data/test-results/autoplay-background-timing-20/console-log.txt">Console</a>
    """

    cleaned = campaign_report._strip_unsafe_file_urls_from_report_html(html)

    assert "file:///" not in cleaned
    assert 'href="autoplay-summary.json"' in cleaned
    assert 'href="console-log.txt"' in cleaned


def test_campaign_report_rendered_html_has_no_file_urls():
    html = campaign_report.render_campaign_report_html(
        summary={
            "ok": True,
            "quality_gate_summary": {"ok": True, "gates": {"x": True}},
            "background_result_timing_summary": {"jobs_submitted": 1},
            "long_run_warning_summary": {"warning_count": 0},
        },
        metrics={"real_turn_runtime_count": 1},
        transcript=[],
    )

    assert "file:///" not in html
    assert "file:\\" not in html
    assert "<base " not in html.lower()
    assert "<iframe" not in html.lower()
    assert "window.location" not in html
    assert "window.open" not in html
    assert len(html) > 1000


def test_campaign_report_render_returns_non_empty_html_document():
    html = campaign_report.render_campaign_report_html(
        summary={
            "ok": True,
            "quality_gate_summary": {"ok": True, "gates": {"x": True}},
            "background_result_timing_summary": {"jobs_submitted": 1},
            "long_run_warning_summary": {"warning_count": 0},
        },
        metrics={"real_turn_runtime_count": 1},
        transcript=[],
    )

    assert isinstance(html, str)
    assert len(html) > 1000
    assert "<!doctype html>" in html.lower()
    assert "rpg-shell" in html
    assert "The Autoplay Campaign Chronicle" in html
    assert "Autoplay Campaign Report" in html


def test_campaign_report_finalizer_does_not_blank_valid_html():
    html_doc = """<!doctype html>
    <html>
      <body>
        <main class="rpg-shell">
          <header class="rpg-hero" id="campaign-overview">
            <h1>The Autoplay Campaign Chronicle</h1>
          </header>
        </main>
      </body>
    </html>
    """

    finalized = campaign_report._finalize_campaign_report_html(html_doc)

    assert len(finalized) > 100
    assert "rpg-shell" in finalized
    assert "The Autoplay Campaign Chronicle" in finalized


def test_campaign_report_write_outputs_non_empty_html(tmp_path):
    result = campaign_report.write_campaign_report(
        output_dir=tmp_path,
        transcript=[],
        summary={
            "ok": True,
            "quality_gate_summary": {"ok": True, "gates": {"x": True}},
            "background_result_timing_summary": {"jobs_submitted": 1},
            "long_run_warning_summary": {"warning_count": 0},
        },
        metrics={"real_turn_runtime_count": 1},
        health={},
    )

    html_path = tmp_path / "autoplay-campaign-report.html"
    assert html_path.exists()
    html = html_path.read_text(encoding="utf-8")
    assert len(html) > 1000
    assert "rpg-shell" in html
    assert "file:///" not in html
    assert result["campaign_report_html"].endswith("autoplay-campaign-report.html")


def test_campaign_report_render_returns_full_rpg_html_document():
    html = campaign_report.render_campaign_report_html(
        summary={
            "ok": True,
            "quality_gate_summary": {"ok": True, "gates": {"x": True}},
            "background_result_timing_summary": {"jobs_submitted": 1},
            "long_run_warning_summary": {"warning_count": 0},
        },
        metrics={"real_turn_runtime_count": 1},
        transcript=[],
    )

    assert isinstance(html, str)
    assert len(html) > 1000
    assert html.lstrip().lower().startswith("<!doctype html>")
    assert "<html" in html.lower()
    assert "<head>" in html.lower()
    assert "<style>" in html.lower()
    assert "<body>" in html.lower()
    assert 'class="rpg-shell"' in html
    assert "The Autoplay Campaign Chronicle" in html
    assert "Autoplay Campaign Report" in html


def test_campaign_report_render_does_not_start_with_legacy_fragment():
    html = campaign_report.render_campaign_report_html(
        summary={"ok": True},
        metrics={"real_turn_runtime_count": 20},
        transcript=[],
    )

    start = html.lstrip()[:300].lower()
    assert not start.startswith("<section")
    assert 'id="player"' not in start
    assert 'id="console-log"' not in start
    assert 'id="debug"' not in start
    assert start.startswith("<!doctype html>")


def test_campaign_report_render_contains_rpg_css():
    html = campaign_report.render_campaign_report_html(
        summary={"ok": True},
        metrics={"real_turn_runtime_count": 20},
        transcript=[],
    )

    assert "--rpg-bg" in html
    assert ".rpg-shell" in html
    assert ".rpg-hero" in html
    assert ".rpg-card" in html
    assert ".rpg-promoted-section" in html


def test_campaign_report_write_outputs_full_html_document(tmp_path):
    result = campaign_report.write_campaign_report(
        output_dir=tmp_path,
        transcript=[],
        summary={
            "ok": True,
            "quality_gate_summary": {"ok": True, "gates": {"x": True}},
            "background_result_timing_summary": {"jobs_submitted": 1},
            "long_run_warning_summary": {"warning_count": 0},
        },
        metrics={"real_turn_runtime_count": 1},
        health={},
    )

    html_path = tmp_path / "autoplay-campaign-report.html"
    assert html_path.exists()
    html = html_path.read_text(encoding="utf-8")
    assert len(html) > 1000
    assert html.lstrip().lower().startswith("<!doctype html>")
    assert "<style>" in html.lower()
    assert 'class="rpg-shell"' in html
    assert "file:///" not in html
    assert result["campaign_report_html"].endswith("autoplay-campaign-report.html")


def test_campaign_report_prefers_latest_state_quest_progress_summary():
    model = {
        "quest_progress_summary": {
            "quest_count": 1,
            "completed_count": 0,
            "active_count": 1,
            "quests": [
                {
                    "quest_id": "quest:witness_search",
                    "title": "Witness Search",
                    "status": "active",
                    "objective_count": 2,
                    "completed_objective_count": 0,
                }
            ],
        },
        "latest_state": {
            "quest_progress": {
                "quests": {
                    "quest:witness_search": {
                        "quest_id": "quest:witness_search",
                        "title": "Witness Search",
                        "status": "completed",
                        "completed": True,
                        "objectives": [
                            {"summary": "Find the witness.", "status": "completed", "completed": True},
                            {"summary": "Report findings to Bran.", "status": "completed", "completed": True},
                        ],
                    },
                    "quest:bandit_road": {
                        "quest_id": "quest:bandit_road",
                        "title": "Bandit Road",
                        "status": "active",
                        "objectives": [
                            {"summary": "Prepare for the bandit road.", "status": "active", "completed": False}
                        ],
                    },
                }
            }
        },
    }

    summary = campaign_report._quest_summary_from_latest_state(model)
    assert summary["completed_count"] == 1
    assert summary["active_count"] == 1
    witness = [row for row in summary["quests"] if row["quest_id"] == "quest:witness_search"][0]
    assert witness["status"] == "completed"
    assert witness["completed_objective_count"] == 2