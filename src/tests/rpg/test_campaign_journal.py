from app.rpg.campaign_journal_runtime import (
    advance_campaign_journal_for_turn,
    campaign_time_for_turn,
    _clean_journal_text,
    _looks_malformed_journal_fragment,
    _journal_text,
    summarize_campaign_calendar,
    summarize_player_journal,
)


def test_campaign_time_for_turn_tracks_phase_and_date():
    first = campaign_time_for_turn(turn_index=1, minutes_per_turn=60)
    eighth = campaign_time_for_turn(turn_index=8, minutes_per_turn=60)

    assert first["time_label"] == "00:00"
    assert first["day_phase"] == "night"
    assert eighth["time_label"] == "07:00"
    assert eighth["day_phase"] == "morning"
    assert eighth["season"] == "spring"


def test_advance_campaign_journal_writes_entry_every_n_turns():
    runtime_state = {}
    for turn in range(1, 5):
        runtime_state = advance_campaign_journal_for_turn(
            runtime_state=runtime_state,
            turn_index=turn,
            player_input=f"I do thing {turn}",
            turn_contract={
                "turn_index": turn,
                "player_input": f"I do thing {turn}",
                "resolved_result": {"summary": f"Result {turn}"},
            },
            journal_every_turns=4,
            minutes_per_turn=60,
        )

    journal = summarize_player_journal(runtime_state)
    calendar = summarize_campaign_calendar(runtime_state)

    assert calendar["turns_tracked"] == 4
    assert journal["entry_count"] == 1
    assert journal["entries"][0]["entry_id"] == "journal:turn:4"
    assert "I do thing 1" in journal["entries"][0]["text"]
    assert "Result" in journal["entries"][0]["text"]


def test_advance_campaign_journal_is_idempotent_for_same_turn_entry():
    runtime_state = {}
    for _ in range(2):
        runtime_state = advance_campaign_journal_for_turn(
            runtime_state=runtime_state,
            turn_index=4,
            player_input="I ask Bran.",
            turn_contract={
                "turn_index": 4,
                "player_input": "I ask Bran.",
                "resolved_result": {"summary": "Bran answers."},
            },
            journal_every_turns=4,
        )

    journal = summarize_player_journal(runtime_state)
    assert journal["entry_count"] == 1


def test_campaign_journal_history_accumulates_across_turns():
    runtime_state = {}
    for turn in range(1, 9):
        runtime_state = advance_campaign_journal_for_turn(
            runtime_state=runtime_state,
            turn_index=turn,
            player_input=f"I act on turn {turn}",
            turn_contract={
                "turn_index": turn,
                "player_input": f"I act on turn {turn}",
                "resolved_result": {"summary": f"Result {turn}"},
            },
            journal_every_turns=4,
            minutes_per_turn=60,
        )

    calendar = summarize_campaign_calendar(runtime_state)
    journal = summarize_player_journal(runtime_state)

    assert calendar["turns_tracked"] == 8
    assert calendar["end"]["turn_index"] == 8
    assert journal["entry_count"] == 2
    assert journal["entries"][0]["entry_id"] == "journal:turn:4"
    assert journal["entries"][1]["entry_id"] == "journal:turn:8"


def test_clean_journal_text_filters_internal_codes():
    assert _clean_journal_text("target_not_found") == ""
    assert _clean_journal_text("no_supported_semantic_action_detected") == ""
    assert _clean_journal_text("Bran answered despite target_not_found debug noise.") == "Bran answered despite debug noise."


def test_advance_campaign_journal_prefers_narration_over_internal_result_codes():
    runtime_state = {}
    for turn in range(1, 5):
        runtime_state = advance_campaign_journal_for_turn(
            runtime_state=runtime_state,
            turn_index=turn,
            player_input=f"I ask Bran about clue {turn}",
            turn_contract={
                "turn_index": turn,
                "player_input": f"I ask Bran about clue {turn}",
                "resolved_result": {"summary": "target_not_found"},
            },
            turn_result={
                "narration_payload": {
                    "narration": "Bran lowers his voice and points toward the road.",
                    "npc": {"speaker": "Bran", "line": "Look for the witness by the old mile marker."},
                }
            },
            journal_every_turns=4,
        )

    journal = summarize_player_journal(runtime_state)
    text = journal["entries"][0]["text"]

    assert "target_not_found" not in text
    assert "Bran lowers his voice" in text


def test_journal_text_normalizes_punctuation_and_sections():
    text = _journal_text(
        [
            "Ask Bran about the witness.",
            "Ask Bran about the witness.",
            "Look around town..",
        ],
        [
            "Bran mentioned strange lights near the woods..",
            "Find the witness.",
        ],
    )

    assert "town.." not in text
    assert ".." not in text
    assert "What I did:" in text
    assert "What I learned:" in text
    assert "Next:" in text
    assert text.count("Ask Bran about the witness") == 2


def test_journal_text_includes_active_quest_objectives_in_next_section():
    runtime_state = {
        "quest_progress": {
            "quests": {
                "quest:witness_search": {
                    "title": "Witness Search",
                    "objectives": [
                        {"summary": "Find the witness", "completed": False, "status": "active"},
                        {"summary": "Report findings to Bran", "completed": False, "status": "active"},
                    ],
                }
            }
        }
    }
    text = _journal_text(
        ["Ask Bran about the witness."],
        ["Bran mentioned the road."],
        runtime_state=runtime_state,
    )

    assert "Next:" in text
    assert "Witness Search" in text
    assert "Find the witness" in text
    assert "Report findings to Bran" in text


def test_journal_filters_malformed_action_fragments():
    assert _looks_malformed_journal_fragment(".gold? Or trouble, indeed.") is True
    assert _clean_journal_text(".gold? Or trouble, indeed.") == ""
    assert _clean_journal_text("Tell me something concrete about the witness.") != ""


def test_journal_prefers_narration_as_learned_and_changed_text():
    runtime_state = {}
    for turn in range(1, 5):
        runtime_state = advance_campaign_journal_for_turn(
            runtime_state=runtime_state,
            turn_index=turn,
            player_input=f"Ask Bran about the witness {turn}.",
            turn_contract={
                "turn_index": turn,
                "player_input": f"Ask Bran about the witness {turn}.",
                "resolved_result": {"summary": "target_not_found"},
            },
            turn_result={
                "narration_payload": {
                    "narration": "Bran lowered his voice and warned that someone saw strange lights near the woods.",
                    "npc": {"speaker": "Bran", "line": "Find the witness before the trail goes cold."},
                }
            },
            journal_every_turns=4,
        )

    text = summarize_player_journal(runtime_state)["entries"][0]["text"]

    assert "What I learned:" in text
    assert "strange lights near the woods" in text
    assert "target_not_found" not in text