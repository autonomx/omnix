
from tests.rpg.autoplay import campaign_report
from tests.rpg.autoplay.campaign_report import (
    build_campaign_report_model,
    build_inventory_rows,
    build_location_journey_model,
    build_player_progression_rows,
    build_story_so_far_paragraph,
    render_campaign_report_html,
)

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
