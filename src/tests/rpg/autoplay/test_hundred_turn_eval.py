from tests.rpg.autoplay.hundred_turn_eval import (
    summarize_action_diversity,
    summarize_hundred_turn_eval,
    summarize_long_run_warnings,
    summarize_progress_timeline,
)


def _row(turn, action="Ask Bran about the witness.", semantic="ask", target="Bran", story=True):
    return {
        "turn_index": turn,
        "player_action": action,
        "turn_contract": {
            "player_input": action,
            "semantic_action": {"type": semantic, "target": target},
            "resolved_result": {"summary": "Bran mentioned the witness." if story else ""},
        },
        "runtime_state": {
            "player_journal": {
                "entries": [{"entry_id": f"journal:turn:{turn}"}] if turn % 4 == 0 else []
            },
            "quest_progress": {
                "quests": {
                    "quest:witness_search": {
                        "title": "Witness Search",
                        "status": "active",
                    }
                }
            },
            "npc_evolution": {
                "signals": [{"signal_id": f"s{turn}"}] if story else []
            },
        },
        "combined_background_llm_result": {
            "narration": "Bran lowered his voice." if story else ""
        },
    }


def test_action_diversity_detects_repeated_semantic_target_streak():
    transcript = [_row(i, semantic="ask", target="Bran") for i in range(1, 7)]

    summary = summarize_action_diversity(transcript)

    assert summary["turns"] == 6
    assert summary["max_same_semantic_target_streak"]["streak"] == 6
    assert summary["max_same_semantic_target_streak"]["value"] == "ask:Bran"


def test_progress_timeline_computes_progress_rates():
    transcript = [_row(i, story=True) for i in range(1, 5)]

    summary = summarize_progress_timeline(transcript)

    assert summary["turns"] == 4
    assert summary["meaningful_progress_turns"] >= 1
    assert summary["story_beat_turns"] == 4
    assert summary["max_storyless_streak"] == 0


def test_progress_timeline_detects_noop_streak():
    transcript = []
    for i in range(1, 5):
        row = _row(i, story=False)
        row["turn_contract"]["resolved_result"] = {"reason": "target_not_found"}
        transcript.append(row)

    summary = summarize_progress_timeline(transcript)

    assert summary["noop_turns"] == 4
    assert summary["max_noop_streak"] == 4


def test_long_run_warnings_become_errors_in_strict_mode():
    transcript = [_row(i, semantic="ask", target="Bran", story=False) for i in range(1, 101)]
    action = summarize_action_diversity(transcript)
    progress = summarize_progress_timeline(transcript)

    warnings = summarize_long_run_warnings(
        transcript=transcript,
        action_diversity_summary=action,
        progress_timeline_summary=progress,
        console_log_summary={"turn_error_count": 0},
        manual_turn_error_summary={"error_count": 0},
        turns_for_strict_gates=100,
    )

    assert warnings["strict_100_turn_mode"] is True
    assert warnings["ok"] is False
    assert warnings["error_count"] >= 1


def test_hundred_turn_eval_smoke_mode_allows_short_runs():
    transcript = [_row(i) for i in range(1, 9)]

    summary = summarize_hundred_turn_eval(
        transcript=transcript,
        summary={
            "console_log_summary": {"turn_error_count": 0},
            "manual_turn_error_summary": {"error_count": 0},
        },
        turns_for_strict_gates=100,
    )

    assert summary["readiness"] == "smoke"
    assert summary["strict_100_turn_mode"] is False
    assert "action_diversity_summary" in summary
    assert "progress_timeline_summary" in summary