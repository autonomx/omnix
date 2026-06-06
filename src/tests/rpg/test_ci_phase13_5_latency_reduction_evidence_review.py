import json
from pathlib import Path

from app.rpg.latency_reduction_evidence_review import (
    REVIEW_JSON_NAME,
    build_latency_reduction_evidence_review,
    write_latency_reduction_evidence_review,
)


def _payload(provider_avg: float, *, enabled: bool = True):
    return {
        "scenario_count": 8,
        "p95_turn_seconds": 5.5,
        "max_turn_seconds": 6.4,
        "phase13_4_latency_reduction": {
            "enabled": enabled,
            "source": "phase13_4_provider_backed_intent_fast_path_v1",
            "bounded_target": "provider_backed_intent_paths",
        },
        "scenarios": [
            {"scenario_id": "combat_basic_attack", "completed_turns": 5, "avg_turn_seconds": 0.1},
            {"scenario_id": "travel_route_choice", "completed_turns": 2, "avg_turn_seconds": 0.1},
            {"scenario_id": "survival_food_and_water", "completed_turns": 3, "avg_turn_seconds": 0.1},
            {"scenario_id": "npc_dialogue_persona", "completed_turns": 2, "avg_turn_seconds": provider_avg},
            {"scenario_id": "quest_no_backed_state", "completed_turns": 2, "avg_turn_seconds": provider_avg},
            {"scenario_id": "party_companion_recruitment", "completed_turns": 3, "avg_turn_seconds": provider_avg},
            {"scenario_id": "commerce_food_purchase", "completed_turns": 4, "avg_turn_seconds": provider_avg},
            {"scenario_id": "rumor_news_no_backed_state", "completed_turns": 2, "avg_turn_seconds": provider_avg},
        ],
    }


def test_phase13_5_review_confirms_provider_backed_improvement():
    review = build_latency_reduction_evidence_review(
        _payload(3.8),
        evidence_name="latency-reduced-interactive-intent-matrix.zip",
    )

    assert review["ok"] is True
    assert review["advisory_only"] is True
    assert review["metrics"]["provider_backed_avg_turn_seconds"] == 3.8
    assert review["metrics"]["deterministic_fast_path_avg_turn_seconds"] == 0.1
    assert review["metrics"]["provider_backed_improvement_ratio"] > 0.15
    assert review["warnings"] == []
    assert review["recommended_next_target"] == "promote_or_repeat_latency_reduction_with_live_evidence"


def test_phase13_5_review_blocks_missing_runner_or_low_improvement():
    missing_runner = build_latency_reduction_evidence_review(_payload(3.8, enabled=False))
    assert missing_runner["ok"] is False
    assert "latency_reduction_runner_not_confirmed" in missing_runner["warnings"]

    weak = build_latency_reduction_evidence_review(_payload(5.2))
    assert weak["ok"] is False
    assert "provider_backed_improvement_below_target" in weak["warnings"]
    assert weak["recommended_next_target"] == "phase13_6_follow_up_provider_backed_latency_target"


def test_phase13_5_review_writes_json(tmp_path: Path):
    result = write_latency_reduction_evidence_review(tmp_path, _payload(3.8))

    assert result["ok"] is True
    path = Path(result["json_path"])
    assert path.name == REVIEW_JSON_NAME
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["source"] == "phase13_5_latency_reduction_evidence_review_v1"
