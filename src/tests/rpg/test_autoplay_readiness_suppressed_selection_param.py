from tests.rpg.autoplay_llm_campaign import _build_100_turn_readiness_summary


def test_readiness_accepts_suppressed_selection_guard_summary_param():
    readiness = _build_100_turn_readiness_summary(
        summary={},
        transcript=[{"turn_index": i + 1} for i in range(100)],
        requested_turns=100,
        turns_executed=100,
        runtime_errors=[],
        warnings=[],
        suppressed_selection_guard_summary={
            "ok": True,
            "checked_count": 100,
            "retargeted_count": 2,
            "no_replacement_count": 0,
            "by_action_id": {"ask_garran_to_join": 2},
        },
    )

    gate = readiness["gates"]["suppressed_selection_guard_ok"]

    assert gate["ok"] is True
    assert gate["value"]["checked_count"] == 100
    assert gate["value"]["retargeted_count"] == 2
    assert gate["value"]["no_replacement_count"] == 0