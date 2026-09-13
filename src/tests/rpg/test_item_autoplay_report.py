from __future__ import annotations

from typing import Any

from app.rpg.session.item_autoplay_report import (
    build_item_autoplay_report_payload,
    build_item_autoplay_report_rows,
)


def _state() -> dict[str, Any]:
    return {
        "current_turn": 12,
        "turn_count": 12,
        "metadata": {"genre": "classic_fantasy"},
        "player": {
            "level": 1,
            "inventory": [
                {
                    "id": "ration",
                    "item_id": "ration",
                    "name": "Ration",
                    "quantity": 2,
                    "stackable": True,
                    "tags": ["food"],
                },
                {
                    "id": "utility_baton",
                    "item_id": "utility_baton",
                    "name": "Utility Baton",
                    "quantity": 1,
                    "slot": "tool",
                    "tags": ["tool"],
                },
            ],
        },
        "mechanics": {
            "item_traces": [
                {"event": "item_used"},
                {"event": "merchant_catalog_built"},
            ],
            "market_traces": [{"event": "item_transaction_applied"}],
            "item_report_sections": [{"title": "Item Coverage"}],
        },
    }


def test_build_item_autoplay_report_payload_summarizes_coverage_and_traces() -> None:
    payload = build_item_autoplay_report_payload(_state(), objective_limit=4, scenario_limit=4)

    assert payload["ok"] is True
    assert payload["mechanics_source"] == "engine_item_autoplay_report_v1"
    summary = payload["summary"]
    assert summary["turn"] == 12
    assert "coverage_score" in summary
    assert summary["objective_count"] <= 4
    assert summary["scenario_step_count"] <= 4
    assert summary["trace_counts"]["item_traces"] == 2
    assert summary["trace_counts"]["market_traces"] == 1
    assert summary["recent_trace_events"] == ["item_used", "merchant_catalog_built"]
    assert payload["report"]["ok"] is True
    assert payload["diagnostics"]["ok"] is True
    assert isinstance(payload["objectives"], list)
    assert payload["scenario"]["ok"] is True


def test_build_item_autoplay_report_rows_returns_compact_strings() -> None:
    payload = build_item_autoplay_report_payload(_state(), objective_limit=3, scenario_limit=3)

    rows = build_item_autoplay_report_rows(payload)

    labels = [row["label"] for row in rows]
    assert "Coverage score" in labels
    assert "Objectives" in labels
    assert "Trace buckets" in labels
    trace_row = next(row for row in rows if row["label"] == "Trace buckets")
    assert "item_traces:2" in trace_row["value"]
    assert all(isinstance(row["value"], str) for row in rows)


def test_build_item_autoplay_report_payload_handles_empty_state() -> None:
    payload = build_item_autoplay_report_payload({}, objective_limit=2, scenario_limit=2)

    assert payload["ok"] is True
    assert payload["summary"]["turn"] == 0
    assert payload["summary"]["trace_counts"] == {}
    assert payload["summary"]["recent_trace_events"] == []
