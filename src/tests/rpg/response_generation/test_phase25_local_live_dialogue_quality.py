from __future__ import annotations

import pytest

from app.rpg.local_dialogue_quality import (
    build_live_dialogue_plan,
    evaluate_live_dialogue_payloads,
    run_live_dialogue_quality,
)


def _payload_for_case(case) -> dict:
    return {
        "ok": True,
        "contract_version": "rpg_turn_response_v2",
        "interaction_id": f"interaction:{case.case_id}",
        "interaction_seq": 1,
        "visible_response": case.visible,
        "result": {
            "llm_called": True,
            "timing": {"provider_ms": 700.0},
        },
        "state": {"changed_domains": ["conversation"]},
    }


def test_live_dialogue_plan_covers_all_accepted_matrix_categories() -> None:
    plan = build_live_dialogue_plan()

    assert len(plan) >= 30
    assert all(case.should_accept for case in plan)
    assert {
        "emotional_disclosure",
        "hostile_noncombat",
        "private_secret_probe",
        "absent_npc",
        "group_conversation",
        "low_trust",
        "high_trust",
        "follow_up_reference",
        "multi_turn_repetition",
    } <= {case.category for case in plan}


def test_static_live_payload_evaluator_produces_acceptance_report_without_network() -> None:
    plan = build_live_dialogue_plan()
    report = evaluate_live_dialogue_payloads(plan, [_payload_for_case(case) for case in plan])

    assert report["ok"] is True, report
    assert report["accepted_case_count"] >= 30
    assert report["provider_call_failures"] == []
    assert report["structural_failures"] == []
    assert report["metrics"]["correct_speaker_rate"] == 1.0
    assert report["metrics"]["private_leak_rate"] == 0.0


def test_live_dialogue_runner_is_blocked_in_ci_before_network_access() -> None:
    with pytest.raises(RuntimeError, match="must not run in CI"):
        run_live_dialogue_quality(
            base_url="http://127.0.0.1:1",
            session_id="session:test",
            env={"CI": "true", "OMNIX_RPG_LIVE_SMOKE": "1"},
        )


def test_live_dialogue_evaluator_rejects_missing_provider_call_evidence() -> None:
    plan = build_live_dialogue_plan()
    payloads = [_payload_for_case(case) for case in plan]
    payloads[0]["result"].pop("llm_called")

    report = evaluate_live_dialogue_payloads(plan, payloads)

    assert report["ok"] is False
    assert "one_or_more_dialogue_turns_did_not_use_exactly_one_provider_call" in report["failures"]
    assert plan[0].case_id in report["provider_call_failures"]
