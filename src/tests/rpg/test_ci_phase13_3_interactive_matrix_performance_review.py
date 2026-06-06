import json
from pathlib import Path

from app.rpg.interactive_matrix_performance_review import (
    REVIEW_HTML_NAME,
    REVIEW_JSON_NAME,
    build_interactive_matrix_performance_review,
    write_interactive_matrix_performance_review,
    write_interactive_matrix_performance_review_from_file,
)


def _matrix_performance_payload():
    return {
        "format_version": "interactive_intent_matrix_performance_v1",
        "scenario_count": 8,
        "avg_turn_seconds": 3.1433,
        "p95_turn_seconds": 6.3558,
        "max_turn_seconds": 7.4521,
        "phase_totals_seconds": {
            "runtime_apply_turn_seconds": 71.618,
            "turn_total_seconds": 72.2967,
            "commerce_repair_seconds": 0.1649,
        },
        "scenarios": [
            {"scenario_id": "combat_basic_attack", "completed_turns": 5, "avg_turn_seconds": 0.1011, "max_turn_seconds": 0.1216, "slow_turn_count": 0},
            {"scenario_id": "travel_route_choice", "completed_turns": 2, "avg_turn_seconds": 0.09, "max_turn_seconds": 0.12, "slow_turn_count": 0},
            {"scenario_id": "survival_food_and_water", "completed_turns": 3, "avg_turn_seconds": 0.11, "max_turn_seconds": 0.12, "slow_turn_count": 0},
            {"scenario_id": "npc_dialogue_persona", "completed_turns": 2, "avg_turn_seconds": 4.66, "max_turn_seconds": 4.8, "slow_turn_count": 0},
            {"scenario_id": "quest_no_backed_state", "completed_turns": 2, "avg_turn_seconds": 4.82, "max_turn_seconds": 5.23, "slow_turn_count": 0},
            {"scenario_id": "party_companion_recruitment", "completed_turns": 3, "avg_turn_seconds": 5.47, "max_turn_seconds": 6.38, "slow_turn_count": 0},
            {"scenario_id": "commerce_food_purchase", "completed_turns": 4, "avg_turn_seconds": 5.79, "max_turn_seconds": 6.17, "slow_turn_count": 0},
            {"scenario_id": "rumor_news_no_backed_state", "completed_turns": 2, "avg_turn_seconds": 6.36, "max_turn_seconds": 7.45, "slow_turn_count": 0},
        ],
    }


def test_phase13_3_review_flags_provider_backed_matrix_latency():
    review = build_interactive_matrix_performance_review(
        _matrix_performance_payload(),
        evidence_name="interactive-intent-matrix(36).zip",
    )

    assert review["advisory_only"] is True
    assert review["metrics"]["scenario_count"] == 8
    assert review["metrics"]["avg_turn_seconds"] == 3.1433
    assert review["metrics"]["runtime_apply_share"] == 0.9906
    assert review["metrics"]["deterministic_avg_turn_seconds"] == 0.1004
    assert review["metrics"]["provider_backed_avg_turn_seconds"] == 5.42
    assert "provider_backed_avg_turn_seconds_above_target" in review["warnings"]
    assert "runtime_apply_share_dominates_turn_time" in review["warnings"]
    assert review["recommended_next_target"] == "bounded_latency_reduction_for_provider_backed_intent_paths"
    assert review["slowest_scenarios"][0]["scenario_id"] == "rumor_news_no_backed_state"


def test_phase13_3_review_writes_json_and_html(tmp_path: Path):
    result = write_interactive_matrix_performance_review(
        tmp_path,
        _matrix_performance_payload(),
        evidence_name="interactive-intent-matrix(36).zip",
    )

    assert result["ok"] is True
    json_path = Path(result["json_path"])
    html_path = Path(result["html_path"])
    assert json_path.name == REVIEW_JSON_NAME
    assert html_path.name == REVIEW_HTML_NAME
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["evidence_name"] == "interactive-intent-matrix(36).zip"
    assert "provider_backed_avg_turn_seconds_above_target" in payload["warnings"]
    assert "Interactive Matrix Performance Review" in html_path.read_text(encoding="utf-8")


def test_phase13_3_review_can_be_built_from_existing_performance_file(tmp_path: Path):
    source = tmp_path / "interactive-intent-matrix-performance.json"
    source.write_text(json.dumps(_matrix_performance_payload()), encoding="utf-8")

    result = write_interactive_matrix_performance_review_from_file(
        source,
        evidence_name="interactive-intent-matrix(36).zip",
    )

    assert result["ok"] is True
    assert Path(result["json_path"]).exists()
    assert Path(result["html_path"]).exists()
