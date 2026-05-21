from __future__ import annotations

from app.rpg.session.survival_autoplay import (
    build_survival_autoplay_context,
    build_survival_autoplay_response_metrics,
    build_survival_response_readiness_gate,
    build_survival_supply_metrics,
    choose_survival_aware_action,
    ensure_survival_starter_supply,
    list_survival_service_supply,
    list_survival_shop_supply,
    run_survival_balance_simulation,
    survival_drink_available,
    survival_food_available,
)
from tests.rpg.autoplay_llm_campaign import (
    _build_100_turn_evaluation_summary,
    _build_100_turn_readiness_summary,
)


def _state(*, hunger=0, thirst=0, fatigue=0, food=0, drink=0):
    items = []
    if food:
        items.append({"item_id": "trail_ration", "name": "Trail ration", "quantity": food, "tags": ["food", "ration"]})
    if drink:
        items.append({"item_id": "waterskin", "name": "Waterskin", "quantity": drink, "tags": ["drink", "water"]})
    return {
        "player_state": {
            "resources": {"hunger": hunger, "thirst": thirst, "fatigue": fatigue},
            "inventory_state": {"currency": {"gold": 2, "silver": 10, "copper": 10}, "items": items},
        },
        "climate_survival": {
            "survival": {"hunger": hunger, "thirst": thirst, "fatigue": fatigue, "warnings": []}
        },
    }


def test_n1241_survival_policy_prefers_inventory_relief_before_services() -> None:
    state = _state(hunger=70, thirst=80, fatigue=60, food=1, drink=1)
    context = build_survival_autoplay_context(simulation_state=state)

    selected = choose_survival_aware_action(context)

    assert selected["selected"] is True
    assert selected["action_kind"] == "drink_water"
    assert selected["command"] == "I drink Waterskin"
    assert context["survival_suggested_actions"]


def test_n1241_survival_policy_prefers_lodging_when_fatigue_is_severe_and_available() -> None:
    state = _state(hunger=10, thirst=10, fatigue=90)
    context = build_survival_autoplay_context(
        simulation_state=state,
        suggested_actions=[
            {"type": "survival_relief", "action_kind": "rest", "command": "I rest"},
            {"type": "survival_relief", "action_kind": "buy_lodging", "command": "I rent Common room cot from Bran"},
        ],
    )

    selected = choose_survival_aware_action(context)

    assert selected["selected"] is True
    assert selected["action_kind"] == "buy_lodging"


def test_n1242_balance_simulation_has_bounded_warning_rate_and_relief() -> None:
    result = run_survival_balance_simulation(100)

    assert result["turns"] == 100
    assert result["relief_action_count"] > 0
    assert result["warning_turn_rate"] < 0.75
    assert result["max_needs"]["hunger"] <= 100
    assert result["max_needs"]["thirst"] <= 100
    assert result["max_needs"]["fatigue"] <= 100


def test_n1243_starter_supply_seeds_food_water_and_survival_shop_supply_exists() -> None:
    state = {"player_state": {"inventory_state": {"items": [], "currency": {}}}}

    result = ensure_survival_starter_supply(state)

    assert result["applied"] is True
    assert survival_food_available(state) is True
    assert survival_drink_available(state) is True
    assert list_survival_shop_supply("npc:Elara")
    assert any(offer["service_kind"] == "meal" for offer in list_survival_service_supply("npc:Bran"))


def test_n1243_supply_metrics_track_food_drink_and_risk_turns() -> None:
    rows = [
        {"state": _state(hunger=20, thirst=20, fatigue=10, food=1, drink=1)},
        {"state": _state(hunger=90, thirst=95, fatigue=10, food=0, drink=0)},
    ]

    metrics = build_survival_supply_metrics(rows)

    assert metrics["food_available_turns"] == 1
    assert metrics["drink_available_turns"] == 1
    assert metrics["starvation_risk_turns"] == 1
    assert metrics["dehydration_risk_turns"] == 1


def test_n1244_response_metrics_and_advisory_gate() -> None:
    transcript = [
        {
            "needs": {"hunger": 70, "thirst": 20, "fatigue": 10},
            "survival_suggested_actions": [{"action_kind": "eat_food", "type": "survival_relief"}],
            "survival_action": {"action_kind": "eat_food", "applied": True},
        },
        {
            "needs": {"hunger": 20, "thirst": 80, "fatigue": 10},
            "survival_suggested_actions": [{"action_kind": "drink_water", "type": "survival_relief"}],
            "survival_action": {"action_kind": "drink_water", "applied": False, "blocked": True, "blocked_reason": "no_drink_item"},
        },
    ]

    metrics = build_survival_autoplay_response_metrics(transcript)
    gate = build_survival_response_readiness_gate({
        "survival_autoplay_response_metrics": metrics,
        "survival_pressure_relief_summary": {"pressure_turn_count": 2, "relief_action_count": 1},
    })

    assert metrics["survival_suggestion_seen_count"] == 2
    assert metrics["survival_suggestion_taken_count"] == 1
    assert metrics["survival_suggestion_ignored_count"] == 1
    assert metrics["high_pressure_unanswered_turn_count"] == 1
    assert gate["gate"] == "survival_response_ok"
    assert gate["advisory_only"] is True
    assert gate["ok"] is True


def test_n1244_autoplay_summary_wrappers_attach_metrics_and_advisory_gate() -> None:
    transcript = [
        {
            "needs": {"hunger": 70, "thirst": 20, "fatigue": 10},
            "survival_suggested_actions": [{"action_kind": "eat_food", "type": "survival_relief"}],
            "survival_action": {"action_kind": "eat_food", "applied": True},
        }
    ]

    summary = _build_100_turn_evaluation_summary(
        turns_executed=100,
        requested_turns=100,
        runtime_errors=[],
        warnings=[],
        transcript=transcript,
        performance_summary={"avg_turn_seconds": 1.0, "p95_turn_seconds": 2.0},
        narration_grounding_summary={"checked_count": 100, "invalid_count": 0, "provider_json_parse_failed_count": 0, "provider_invalid_count": 0},
        progress_quality_summary={"meaningful_progress_rate": 0.5, "fallback_player_action_rate": 0.0, "no_change_turns": 0},
        checkpoint_summary={"failure_count": 0},
        loop_detection_summary={"repeated_action_window_count": 0, "loop_warning_count": 0},
    )

    assert "survival_autoplay_response_metrics" in summary
    assert "survival_supply_metrics" in summary
    assert "survival_response_gate" in summary
    assert "survival-autoplay-response-metrics.json" in summary["artifact_level_summaries"]

    readiness = _build_100_turn_readiness_summary(
        summary={"scenario_progression_arc_summary": {"graph_count": 9}},
        transcript=transcript,
        requested_turns=100,
        turns_executed=100,
        runtime_errors=[],
        warnings=[],
    )
    assert "survival_response_ok" in readiness["gates"]
    assert "survival_response_ok" in readiness["advisory_gates"]
