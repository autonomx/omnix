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


def _artifact(count=100):
    return {
        "turns": _turns(count),
        "report_bytes": 250_000,
        "transcript_debug_bytes": 500_000,
        "final_checkpoint_digest": "digest:phase7:final",
        "loaded_checkpoint_digest": "digest:phase7:final",
        "state_diff_source": "test_phase7_full_100_turn_certification",
    }


def test_ci_phase7_full_100_turn_certification_passes_complete_artifact():
    from app.rpg.session import build_full_100_turn_certification_result

    result = build_full_100_turn_certification_result(_artifact())

    assert result["source"] == "deterministic_phase7_full_100_turn_certification_gate"
    assert result["ok"] is True
    assert result["reason"] == "phase7_full_100_turn_certification_passed"
    assert result["certification_status"] == "final_100_turn_certification_passed"
    assert result["actual_turns"] == 100
    assert result["expected_turns"] == 100
    assert result["blockers"] == []
    assert result["readiness_result"]["source"] == "deterministic_phase7_100_turn_readiness_gate"
    assert result["readiness_report_payload"]["source"] == "deterministic_phase7_100_turn_readiness_report_gate"
    assert result["readiness_report_payload"]["severity_counts"]["critical"] == 0
    assert result["state_diff"]["checked"] is True
    assert result["state_diff"]["blockers"] == []


def test_ci_phase7_full_100_turn_certification_blocks_wrong_turn_count():
    from app.rpg.session import build_full_100_turn_certification_result

    result = build_full_100_turn_certification_result(_artifact(99))
    blocker_kinds = {row["kind"] for row in result["blockers"]}

    assert result["ok"] is False
    assert result["reason"] == "phase7_full_100_turn_certification_blocked"
    assert result["certification_status"] == "final_100_turn_certification_blocked"
    assert "artifact_turn_count_not_exact" in blocker_kinds
    assert "readiness_critical_blocker" in blocker_kinds


def test_ci_phase7_full_100_turn_certification_blocks_readiness_critical_budget():
    from app.rpg.session import build_full_100_turn_certification_result

    artifact = _artifact()
    artifact["report_bytes"] = 6_000_000
    result = build_full_100_turn_certification_result(artifact)
    blockers = result["blockers"]

    assert result["ok"] is False
    assert any(row["kind"] == "readiness_critical_blocker" for row in blockers)
    assert any(row.get("blocker") == "report_growth_budget_exceeded" for row in blockers)


def test_ci_phase7_full_100_turn_certification_blocks_state_digest_mismatch():
    from app.rpg.session import build_full_100_turn_certification_result

    artifact = _artifact()
    artifact["loaded_checkpoint_digest"] = "digest:phase7:loaded-drift"
    result = build_full_100_turn_certification_result(artifact)

    assert result["ok"] is False
    assert result["state_diff"]["checked"] is True
    assert result["state_diff"]["blockers"] == [
        {
            "kind": "final_vs_loaded_checkpoint_digest_mismatch",
            "source": "test_phase7_full_100_turn_certification",
        }
    ]


def test_ci_phase7_full_100_turn_certification_contract_exports_and_provider_free_source():
    from app.rpg import session
    from app.rpg.session import turn_certification

    readiness = session.assert_phase7_full_100_turn_certification_ready()
    contract = session.build_full_100_turn_certification_contract(readiness["result"])
    source = inspect.getsource(turn_certification).lower()

    assert readiness["ok"] is True
    assert readiness["reason"] == "phase7_full_100_turn_certification_gate_ready"
    assert readiness["blockers"] == []
    assert contract["source"] == "deterministic_phase7_full_100_turn_certification_gate"
    assert "Do not certify fewer or more than the expected 100 turns." in contract["forbidden_certification_claims"]
    assert session.build_full_100_turn_certification_result
    assert session.build_full_100_turn_certification_contract
    assert session.assert_phase7_full_100_turn_certification_ready
    assert "openai" not in source
    assert "requests." not in source
    assert "httpx" not in source
    assert "subprocess" not in source
