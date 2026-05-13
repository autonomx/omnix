from tests.rpg.autoplay_llm_campaign import _validate_final_autoplay_summary_integrity


def test_100_turn_stub_success_is_rejected():
    summary = {
        "ok": True,
        "requested_turns": 100,
        "turns_executed": 100,
        "real_turn_loop_started": False,
        "real_turn_loop_iterations": 0,
        "real_transcript_row_count": 0,
        "runtime_errors": [],
        "warnings": [],
        "hundred_turn_evaluation": {
            "ok": True,
            "gates": {},
        },
        "hundred_turn_readiness_summary": {
            "ok": True,
            "gates": {},
        },
    }

    result = _validate_final_autoplay_summary_integrity(
        summary=summary,
        requested_turns=100,
    )

    assert result["ok"] is False
    assert "final_summary_integrity:real_turn_loop_never_started" in result["runtime_errors"]
    assert any("real_turn_loop_iterations_below_requested" in e for e in result["runtime_errors"])
    assert any("transcript_rows_below_requested" in e for e in result["runtime_errors"])
    assert "final_summary_integrity:hundred_turn_evaluation_gates_empty" in result["runtime_errors"]
    assert "final_summary_integrity:hundred_turn_readiness_gates_empty" in result["runtime_errors"]