from __future__ import annotations

from typing import Any

from app.rpg.session.item_autoplay_adapter import (
    attach_item_autoplay_report,
    extract_item_autoplay_state,
    summarize_item_autoplay_reports,
)


def _state() -> dict[str, Any]:
    return {
        "current_turn": 15,
        "turn_count": 15,
        "metadata": {"genre": "classic_fantasy"},
        "player": {
            "level": 1,
            "inventory": [
                {"id": "ration", "item_id": "ration", "name": "Ration", "quantity": 2, "stackable": True}
            ],
        },
        "mechanics": {
            "item_traces": [{"event": "item_used"}],
            "market_traces": [{"event": "item_transaction_applied"}],
        },
    }


def test_extract_item_autoplay_state_from_common_artifact_shapes() -> None:
    state = _state()

    assert extract_item_autoplay_state({"state": state}) == state
    assert extract_item_autoplay_state({"game": state}) == state
    assert extract_item_autoplay_state({"session": {"state": state}}) == state
    assert extract_item_autoplay_state({"turn_result": {"game": state}}) == state


def test_attach_item_autoplay_report_adds_payload_rows_and_source() -> None:
    artifact = {"turn": 15, "session": {"state": _state()}}

    result = attach_item_autoplay_report(artifact, objective_limit=3, scenario_limit=3)

    assert result is not artifact
    assert "item_autoplay_report" in result
    assert result["item_autoplay_report"]["ok"] is True
    assert result["item_autoplay_report"]["summary"]["turn"] == 15
    assert result["item_autoplay_report_rows"]
    assert "engine_item_autoplay_adapter_v1" in result["mechanics_sources"]
    assert "item_autoplay_report" not in artifact


def test_attach_item_autoplay_report_handles_missing_state() -> None:
    result = attach_item_autoplay_report({"turn": 1})

    assert result["item_autoplay_report"]["ok"] is False
    assert result["item_autoplay_report"]["error"] == "item_autoplay_state_not_found"


def test_summarize_item_autoplay_reports_rolls_up_attached_payloads() -> None:
    one = attach_item_autoplay_report({"game": _state()}, objective_limit=2, scenario_limit=2)
    two_state = _state()
    two_state["current_turn"] = 16
    two = attach_item_autoplay_report({"game": two_state}, objective_limit=2, scenario_limit=2)

    summary = summarize_item_autoplay_reports([one, two])

    assert summary["ok"] is True
    assert summary["artifact_count"] == 2
    assert summary["report_count"] == 2
    assert summary["max_coverage_score"] >= summary["min_coverage_score"]
    assert summary["objective_count"] >= 0
    assert summary["mechanics_source"] == "engine_item_autoplay_adapter_v1"
