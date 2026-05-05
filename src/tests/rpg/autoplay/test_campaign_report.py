from pathlib import Path

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