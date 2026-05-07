from tests.rpg.autoplay.report_sections import (
    build_campaign_calendar_and_journal,
    campaign_time_for_turn,
    summarize_npc_evolution_for_report,
    summarize_quests_for_report,
    summarize_story_beats_for_report,
    _quest_rows_from_story_arc_view,
)
from tests.rpg.autoplay.campaign_report import render_campaign_report_html
from tests.rpg.autoplay_llm_campaign import _resolve_turn_contract_for_report


def test_campaign_time_for_turn_tracks_day_phase_and_season():
    t1 = campaign_time_for_turn(turn_index=1, minutes_per_turn=30)
    t20 = campaign_time_for_turn(turn_index=20, minutes_per_turn=30)

    assert t1["year"] == 1000
    assert t1["season"] == "spring"
    assert t1["time_label"] == "00:00"
    assert t20["turn_index"] == 20
    assert t20["day_phase"] in {"morning", "afternoon", "evening", "night"}


def test_build_campaign_calendar_and_journal_creates_player_entries():
    transcript = [
        {
            "turn_index": 1,
            "player_action": "I ask Bran about the mill.",
            "combined_background_llm_result": {"narration": "Bran answers cautiously."},
        },
        {
            "turn_index": 2,
            "player_action": "I listen for rumors.",
            "combined_background_llm_result": {"narration": "The tavern quiets."},
        },
    ]

    result = build_campaign_calendar_and_journal(
        transcript,
        minutes_per_turn=30,
        journal_every_turns=2,
    )

    assert result["calendar"]["turns_tracked"] == 2
    assert result["journal"]["entry_count"] == 1
    assert "I ask Bran" in result["journal"]["entries"][0]["text"]


def test_summarize_npc_evolution_for_report_builds_cards():
    transcript = [
        {
            "turn_index": 2,
            "runtime_state": {
                "npc_evolution": {
                    "arcs": {
                        "Bran": {
                            "npc_id": "Bran",
                            "arc_stage": "trusting",
                            "axes": {"trust": 4},
                            "memories": [{"summary": "Bran remembers the player."}],
                            "future_hooks": [{"summary": "Bran may offer a rumor."}],
                            "milestones": [],
                        }
                    },
                    "signals": [
                        {"npc_id": "Bran", "kind": "memory"},
                        {"npc_id": "Bran", "kind": "future_hook"},
                    ],
                    "loaded_profiles": {
                        "Bran": {"path": "resources/data/rpg_npc_profiles/bran.json", "profile": {}}
                    },
                }
            },
            "npc_evolution_summary": {"arc_count": 1},
        }
    ]

    summary = summarize_npc_evolution_for_report(transcript)

    assert summary["npc_count"] == 1
    assert summary["cards"][0]["npc_id"] == "Bran"
    assert summary["cards"][0]["arc_stage"] == "trusting"
    assert summary["cards"][0]["signal_count"] == 2


def test_summarize_quests_for_report_from_state_and_contract():
    transcript = [
        {
            "turn_index": 1,
            "simulation_state": {
                "quest_state": {
                    "mill": {
                        "title": "Investigate the Mill",
                        "status": "active",
                        "objectives": [
                            {"summary": "Ask Bran", "completed": True},
                            {"summary": "Visit the mill", "completed": False},
                        ],
                    }
                }
            },
        },
        {
            "turn_index": 2,
            "turn_contract": {
                "quest_updates": [
                    {
                        "quest_id": "mill",
                        "title": "Investigate the Mill",
                        "status": "active",
                        "summary": "Bran mentioned old smoke near the ridge.",
                    }
                ]
            },
        },
    ]

    summary = summarize_quests_for_report(transcript)

    assert summary["quest_count"] == 1
    assert summary["active_count"] == 1
    assert summary["quests"][0]["title"] == "Investigate the Mill"
    assert "objectives complete" in summary["quests"][0]["progress"]


def test_campaign_report_places_journal_quest_and_npc_sections_before_json_details():
    html = render_campaign_report_html(
        {
            "summary": {
                "campaign_calendar_summary": {
                    "turns_tracked": 2,
                    "end": {
                        "year": 1000,
                        "season": "spring",
                        "month": 1,
                        "day": 1,
                        "time_label": "01:00",
                        "day_phase": "night",
                    },
                },
                "player_journal_summary": {
                    "entry_count": 1,
                    "entries": [
                        {
                            "entry_id": "journal:turn:2",
                            "start_turn": 1,
                            "end_turn": 2,
                            "text": "I asked Bran about the mill.",
                        }
                    ],
                },
                "quest_progress_summary": {
                    "quest_count": 0,
                    "quests": [],
                },
                "npc_evolution_report_summary": {
                    "npc_count": 1,
                    "cards": [
                        {
                            "npc_id": "Bran",
                            "arc_stage": "stable",
                            "axes": {"trust": 0},
                            "signal_count": 1,
                            "memories": [],
                            "future_hooks": [],
                            "milestones": [],
                        }
                    ],
                },
                "profile_grounded_output_summary": {},
            },
            "metrics": {},
            "transcript": [],
        }
    )

    journal_index = html.find("Campaign Calendar & Player Journal")
    quest_index = html.find("Quest Progress")
    npc_index = html.find("NPC Evolution")
    story_index = html.find("Story So Far")
    json_index = html.find("Profile-grounded output summary JSON")

    assert journal_index != -1
    assert quest_index != -1
    assert npc_index != -1
    assert story_index != -1
    assert json_index != -1
    assert journal_index < story_index
    assert quest_index < story_index
    assert npc_index < story_index
    assert journal_index < json_index
    assert quest_index < json_index
    assert npc_index < json_index
    assert 'href="#campaign-journal"' in html
    assert 'href="#quest-progress"' in html
    assert 'href="#npc-evolution"' in html

    header_journal_index = html.find('class="header-journal-link"')
    highlights_index = html.find("Report Highlights")
    assert header_journal_index != -1
    assert highlights_index != -1
    assert header_journal_index < highlights_index


def test_build_campaign_calendar_and_journal_prefers_base_runtime_journal():
    transcript = [
        {
            "turn_index": 4,
            "runtime_state": {
                "campaign_calendar": {
                    "minutes_per_turn": 60,
                    "current": {
                        "turn_index": 4,
                        "year": 1000,
                        "season": "spring",
                        "month": 1,
                        "day": 1,
                        "time_label": "03:00",
                        "day_phase": "night",
                    },
                    "history": [
                        {"turn_index": 1, "time_label": "00:00"},
                        {"turn_index": 2, "time_label": "01:00"},
                        {"turn_index": 3, "time_label": "02:00"},
                        {"turn_index": 4, "time_label": "03:00"},
                    ],
                },
                "player_journal": {
                    "entries": [
                        {
                            "entry_id": "journal:turn:4",
                            "text": "Base runtime journal entry.",
                        }
                    ]
                },
            },
        }
    ]

    result = build_campaign_calendar_and_journal(transcript)

    assert result["calendar"]["source"] == "base_runtime"
    assert result["journal"]["source"] == "base_runtime"
    assert result["journal"]["entries"][0]["text"] == "Base runtime journal entry."


def test_report_nav_has_unique_npc_labels():
    html = render_campaign_report_html(
        {
            "summary": {
                "campaign_calendar_summary": {"turns_tracked": 1, "end": {}},
                "player_journal_summary": {"entry_count": 1, "entries": []},
                "quest_progress_summary": {"quest_count": 0, "quests": []},
                "npc_evolution_report_summary": {"npc_count": 0, "cards": []},
            },
            "metrics": {},
            "transcript": [],
        }
    )

    nav_start = html.find("<nav")
    nav_end = html.find("</nav>", nav_start)
    nav = html[nav_start:nav_end]

    assert "Evolution" in nav
    assert "NPC Cast" in nav
    assert nav.count(">NPCs<") == 0


def test_quest_summary_reads_story_arc_milestones():
    rows = _quest_rows_from_story_arc_view(
        {
            "arcs": [
                {
                    "arc_id": "arc:witness_search",
                    "title": "Witness Search",
                    "status": "active",
                    "milestones": [
                        {"title": "Find the witness", "status": "active"},
                        {"title": "Report findings to Bran", "status": "active"},
                    ],
                }
            ]
        }
    )

    assert rows[0]["title"] == "Witness Search"
    assert len(rows[0]["objectives"]) == 2


def test_story_beat_summary_uses_player_action_and_narration():
    summary = summarize_story_beats_for_report(
        [
            {
                "turn_index": 1,
                "player_action": "I ask Bran about the witness.",
                "narration": "Bran lowers his voice and glances toward the door.",
                "turn_contract": {},
            }
        ]
    )

    assert summary["beat_count"] == 1
    assert "Bran" in summary["beats"][0]["summary"]


def test_report_renders_console_log_section():
    from tests.rpg.autoplay.campaign_report import render_campaign_report_html

    html = render_campaign_report_html(
        {
            "summary": {
                "campaign_calendar_summary": {"turns_tracked": 1, "end": {}},
                "player_journal_summary": {"entry_count": 1, "entries": []},
                "quest_progress_summary": {"quest_count": 0, "quests": []},
                "npc_evolution_report_summary": {"npc_count": 0, "cards": []},
                "console_log_summary": {
                    "path": "console-log.txt",
                    "line_count": 2,
                    "error_count": 1,
                    "turn_error_count": 1,
                    "warning_count": 0,
                    "turn_errors": ["TURN 1 ERROR: boom"],
                    "errors": ["TURN 1 ERROR: boom"],
                    "warnings": [],
                    "tail": ["TURN 1 ERROR: boom"],
                },
            },
            "metrics": {},
            "transcript": [],
        }
    )

    assert 'id="console-log"' in html
    assert "Console Log" in html
    assert "TURN 1 ERROR: boom" in html
    assert 'href="#console-log"' in html


def test_resolve_turn_contract_for_report_uses_nested_session_last_turn():
    resolved = _resolve_turn_contract_for_report(
        turn_result={
            "session": {
                "last_turn": {
                    "turn_contract": {
                        "turn_index": 3,
                        "player_input": "I ask Bran.",
                    }
                }
            }
        },
        base_response_payload={},
    )

    assert resolved["turn_index"] == 3
    assert resolved["player_input"] == "I ask Bran."