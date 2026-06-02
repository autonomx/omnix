import inspect


def _turns(count=100):
    rows = []
    for index in range(count):
        rows.append(
            {
                "turn_index": index + 1,
                "action_text": f"travel step {index % 6}",
                "location_id": f"location:{index % 5}",
                "quest_events": [{"quest_id": "quest:old_mill"}] if index % 25 == 0 else [],
                "currency_delta": {"silver": -1} if index % 20 == 0 else {},
                "journal_updates": ["new clue"] if index % 30 == 0 else [],
                "combat_event": {"encounter_id": "encounter:road"} if index == 40 else None,
            }
        )
    return rows


def test_ci_phase7_100_turn_readiness_validates_complete_advisory_run():
    from app.rpg.session import build_100_turn_readiness_result

    result = build_100_turn_readiness_result(_turns(), report_bytes=250_000, transcript_debug_bytes=500_000)

    assert result["source"] == "deterministic_phase7_100_turn_readiness_gate"
    assert result["ok"] is True
    assert result["reason"] == "phase7_100_turn_readiness_validated"
    assert result["actual_turns"] == 100
    assert result["expected_turns"] == 100
    assert result["blockers"] == []
    assert result["progress_counts"]["travel"] == 100
    assert result["progress_counts"]["quest"] > 0
    assert result["progress_counts"]["economy"] > 0
    assert result["progress_counts"]["combat"] > 0
    assert result["progress_counts"]["journal"] > 0


def test_ci_phase7_100_turn_readiness_classifies_incomplete_run_as_blocker():
    from app.rpg.session import build_100_turn_readiness_result

    result = build_100_turn_readiness_result(_turns(40), expected_turns=100)

    assert result["ok"] is False
    assert result["reason"] == "phase7_100_turn_readiness_blocked"
    assert result["blockers"] == [
        {"kind": "incomplete_turn_count", "actual": 40, "expected": 100, "source": "deterministic_phase7_100_turn_readiness_gate"}
    ]


def test_ci_phase7_100_turn_readiness_classifies_loops_as_advisory_warnings():
    from app.rpg.session import build_100_turn_readiness_result

    turns = [
        {"turn_index": index + 1, "action_text": "wait", "location_id": "location:rusty_flagon"}
        for index in range(100)
    ]
    result = build_100_turn_readiness_result(turns)
    warning_kinds = {row["kind"] for row in result["warnings"]}

    assert result["ok"] is True
    assert result["blockers"] == []
    assert "repeated_action_loop_risk" in warning_kinds
    assert "repeated_location_loop_risk" in warning_kinds
    assert "no_progress_loop_risk" in warning_kinds
    assert "no_progress_signals_detected" in warning_kinds


def test_ci_phase7_100_turn_readiness_blocks_report_growth_budget():
    from app.rpg.session import build_100_turn_readiness_result

    result = build_100_turn_readiness_result(
        _turns(20),
        expected_turns=100,
        report_bytes=2_000_000,
        transcript_debug_bytes=3_000_000,
    )
    blocker_kinds = {row["kind"] for row in result["blockers"]}

    assert result["ok"] is False
    assert "incomplete_turn_count" in blocker_kinds
    assert "report_growth_budget_exceeded" in blocker_kinds
    assert "transcript_debug_growth_budget_exceeded" in blocker_kinds
    assert result["budget_summary"]["projected_report_bytes"] == 10_000_000
    assert result["budget_summary"]["projected_transcript_debug_bytes"] == 15_000_000


def test_ci_phase7_100_turn_readiness_contract_and_exports():
    from app.rpg import session
    from app.rpg.session import turn_readiness

    readiness = session.assert_phase7_100_turn_readiness_ready()
    contract = session.build_100_turn_readiness_contract(readiness["result"])
    source = inspect.getsource(turn_readiness).lower()

    assert readiness["ok"] is True
    assert readiness["reason"] == "phase7_100_turn_readiness_gate_ready"
    assert readiness["blockers"] == []
    assert contract["source"] == "deterministic_phase7_100_turn_readiness_gate"
    assert "Readiness result: phase7_100_turn_readiness_validated" in contract["allowed_readiness_claims"]
    assert session.build_100_turn_readiness_result
    assert session.build_100_turn_readiness_contract
    assert session.assert_phase7_100_turn_readiness_ready
    assert "openai" not in source
    assert "requests." not in source
    assert "httpx" not in source
    assert "subprocess" not in source
