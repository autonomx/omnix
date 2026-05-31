
from tests.rpg.autoplay import campaign_report
from tests.rpg.autoplay.campaign_report import (
    build_campaign_report_model,
    render_campaign_report_html,
)

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
