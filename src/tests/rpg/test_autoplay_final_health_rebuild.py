from tests.rpg.autoplay_llm_campaign import (
    _assert_final_artifact_consistency,
    _force_final_autoplay_health,
)


def test_force_final_autoplay_health_repairs_stale_quality_gate_snapshot():
    summary = {
        "ok": True,
        "turns_executed": 100,
        "requested_turns": 100,
        "runtime_errors": [],
        "warnings": [],
        "quality_gate_summary": {
            "ok": False,
            "failed_gates": ["old_stale_gate"],
        },
        "hundred_turn_evaluation": {
            "ok": True,
            "failed_gates": [],
        },
        "hundred_turn_readiness_summary": {
            "ok": True,
            "failed_gates": [],
        },
        "autoplay_health": {
            "ok": False,
            "summary_ok": False,
            "hundred_turn_evaluation_ok": False,
            "hundred_turn_readiness_ok": True,
            "warnings": ["quality_gate_summary_failed"],
        },
    }

    health = _force_final_autoplay_health(summary)

    assert health["ok"] is True
    assert health["summary_ok"] is True
    assert health["hundred_turn_evaluation_ok"] is True
    assert health["hundred_turn_readiness_ok"] is True
    assert health["failed_gate_count"] == 0
    assert health["failed_evaluation_gates"] == []
    assert health["failed_readiness_gates"] == []
    assert health["quality_gate_summary_advisory"] is True
    assert "quality_gate_summary_failed" not in health["warnings"]


def test_summary_embedded_health_matches_forced_final_health():
    summary = {
        "ok": True,
        "turns_executed": 100,
        "requested_turns": 100,
        "runtime_errors": [],
        "warnings": [],
        "quality_gate_summary": {
            "ok": False,
            "failed_gates": ["old_stale_gate"],
        },
        "hundred_turn_evaluation": {
            "ok": True,
            "failed_gates": [],
        },
        "hundred_turn_readiness_summary": {
            "ok": True,
            "failed_gates": [],
        },
        "autoplay_health": {
            "ok": False,
            "summary_ok": False,
            "hundred_turn_evaluation_ok": False,
            "hundred_turn_readiness_ok": True,
            "warnings": ["quality_gate_summary_failed"],
        },
    }

    summary["autoplay_health"] = _force_final_autoplay_health(summary)
    _assert_final_artifact_consistency(summary)

    assert summary["autoplay_health"]["ok"] is True
    assert summary["autoplay_health"]["summary_ok"] is True
    assert summary["autoplay_health"]["hundred_turn_evaluation_ok"] is True
    assert summary["autoplay_health"]["hundred_turn_readiness_ok"] is True
    assert summary["autoplay_health"]["warnings"] == []
