from __future__ import annotations

from app.rpg.session.survival_autoplay_evidence import (
    build_survival_autoplay_evidence_summary,
    render_survival_autoplay_evidence_report_section,
)
from tests.rpg.autoplay_llm_campaign import (
    _build_100_turn_evaluation_summary,
    _build_100_turn_readiness_summary,
)


def _pressure_row(turn: int = 1):
    return {
        "turn_index": turn,
        "turn_contract": {
            "climate_survival": {
                "format_version": "n1231_climate_survival_state_v1",
                "runtime_enforced": True,
                "source": "deterministic_authoritative_turn_tick",
                "survival": {"hunger": 80, "thirst": 82, "fatigue": 78, "warnings": ["hunger_high", "thirst_high", "fatigue_high"]},
            },
            "survival_suggested_actions": [
                {"type": "survival_relief", "action_kind": "drink_water", "command": "drink waterskin"},
                {"type": "survival_relief", "action_kind": "eat_food", "command": "eat ration"},
            ],
        },
    }


def _relief_row(turn: int, *, need: str, action_name: str, deltas: dict, item_id: str = ""):
    consumed = []
    if item_id:
        consumed = [{"item_id": item_id, "name": item_id.replace("_", " ").title(), "quantity_before": 1, "quantity_after": 0, "quantity_delta": -1}]
    action = {"applied": True, "action": action_name, "action_kind": action_name, "need": need, "deltas": dict(deltas), "inventory_consumed": consumed}
    return {
        "turn_index": turn,
        "turn_contract": {
            "climate_survival": {
                "format_version": "n1263_live_runtime_survival_payload_v1",
                "runtime_enforced": True,
                "source": "n1263_live_runtime_survival_projection",
                "survival": {"hunger": 45 if need == "hunger" else 80, "thirst": 47 if need == "thirst" else 82, "fatigue": 43 if need == "fatigue" else 78, "warnings": []},
                "survival_suggestions": [{"kind": "survival_relief", "need": "fatigue", "action": "rest"}] if need != "fatigue" else [],
            },
            "resource_changes": {
                "source": "n1263_live_runtime_survival_relief",
                "hunger_delta": deltas.get("hunger_delta", 0),
                "thirst_delta": deltas.get("thirst_delta", 0),
                "fatigue_delta": deltas.get("fatigue_delta", 0),
                "effect_result": {"survival_action": action},
            },
            "effect_result": {"survival_action": action},
            "survival_action": action,
        },
    }


def _rows():
    return [
        _pressure_row(1),
        _relief_row(2, need="thirst", action_name="drink_waterskin", deltas={"thirst_delta": -35}, item_id="waterskin"),
        _relief_row(3, need="hunger", action_name="eat_trail_ration", deltas={"hunger_delta": -35}, item_id="trail_ration"),
        _relief_row(4, need="fatigue", action_name="rest", deltas={"fatigue_delta": -35}),
    ]


def _rest_only_rows():
    return [
        _pressure_row(1),
        _relief_row(2, need="fatigue", action_name="rest", deltas={"fatigue_delta": -25}),
    ]


def test_n1271_builds_survival_autoplay_evidence_summary() -> None:
    summary = build_survival_autoplay_evidence_summary(_rows())
    assert summary["format_version"] == "n1271_survival_autoplay_evidence_summary_v1"
    assert summary["evidence_gate"]["ok"] is True
    assert summary["gates"]["survival_pressure_seen"] is True
    assert summary["gates"]["survival_suggestions_seen"] is True
    assert summary["gates"]["survival_relief_actions_seen"] is True
    assert summary["gates"]["survival_inventory_consumed_seen"] is True
    assert summary["gates"]["survival_response_evidence_seen"] is True
    assert summary["gates"]["survival_state_carry_forward_seen"] is True
    assert {item["item_id"] for item in summary["inventory_consumed_summary"]} == {"trail_ration", "waterskin"}


def test_n1275_rest_only_relief_satisfies_response_evidence_gate() -> None:
    summary = build_survival_autoplay_evidence_summary(_rest_only_rows())

    assert summary["evidence_gate"]["ok"] is True
    assert summary["gates"]["survival_inventory_consumed_seen"] is False
    assert summary["gates"]["survival_non_inventory_relief_seen"] is True
    assert summary["gates"]["survival_response_evidence_seen"] is True
    assert summary["non_inventory_relief_summary"] == [{"action_kind": "rest", "count": 1}]
    assert "survival_inventory_consumed_seen" not in summary["evidence_gate"]["required_gates"]


def test_n1275_missing_relief_still_fails_advisory_evidence_gate() -> None:
    summary = build_survival_autoplay_evidence_summary([_pressure_row(1)])

    assert summary["evidence_gate"]["ok"] is False
    assert "survival_relief_actions_seen" in summary["evidence_gate"]["reasons"]
    assert "survival_response_evidence_seen" in summary["evidence_gate"]["reasons"]


def test_n1271_report_section_renders_evidence_tables() -> None:
    html = render_survival_autoplay_evidence_report_section(build_survival_autoplay_evidence_summary(_rows()))
    assert "N127.1 Survival Autoplay Evidence" in html
    assert "Pressure to suggestion to response" in html
    assert "Inventory consumed" in html
    assert "Non-inventory relief" in html
    assert "waterskin" in html


def test_n1271_autoplay_evaluation_summary_attaches_artifacts_and_report_section() -> None:
    summary = _build_100_turn_evaluation_summary(
        turns_executed=100,
        requested_turns=100,
        runtime_errors=[],
        warnings=[],
        transcript=_rows(),
        performance_summary={"avg_turn_seconds": 1.0, "p95_turn_seconds": 2.0},
        narration_grounding_summary={"checked_count": 100, "invalid_count": 0, "provider_json_parse_failed_count": 0, "provider_invalid_count": 0},
        progress_quality_summary={"meaningful_progress_rate": 0.5, "fallback_player_action_rate": 0.0, "no_change_turns": 0},
        checkpoint_summary={"failure_count": 0},
        loop_detection_summary={"repeated_action_window_count": 0, "loop_warning_count": 0},
    )
    assert summary["survival_autoplay_evidence_gate"]["ok"] is True
    assert summary["artifact_level_summaries"]["survival-autoplay-evidence-summary.json"]["turn_count"] == 4
    assert summary["artifact_level_summaries"]["survival-autoplay-evidence-gate.json"]["ok"] is True
    assert any(section["id"] == "n1271-survival-autoplay-evidence" for section in summary["report_sections"])


def test_n1271_readiness_summary_adds_advisory_gate_when_missing_evidence() -> None:
    readiness = _build_100_turn_readiness_summary(
        summary={"scenario_progression_arc_summary": {"graph_count": 9}},
        transcript=[],
        requested_turns=100,
        turns_executed=100,
        runtime_errors=[],
        warnings=[],
    )
    assert readiness["gates"]["survival_autoplay_evidence_ok"] is False
    assert "survival_autoplay_evidence_ok" in readiness["advisory_gates"]
    assert readiness["survival_autoplay_evidence_gate"]["advisory_only"] is True
