from pathlib import Path

from tests.rpg.autoplay.campaign_report import (
    build_campaign_report_model,
    build_story_so_far_paragraph,
    build_chapter_status,
    build_lore_setting_paragraph,
    classify_dialogue_source,
    compute_dialogue_coverage,
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
        "metrics": {"progress_quality": {"meaningful_turns": 1}},
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
    assert "NPCs Introduced" in html
    assert "Lore & Worldbuilding" in html
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