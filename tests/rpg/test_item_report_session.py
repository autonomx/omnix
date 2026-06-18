from __future__ import annotations

from app.rpg.session.item_report_session import build_item_report_for_session, record_item_report_for_session


def _state() -> dict[str, object]:
    return {
        "current_turn": 9,
        "player": {
            "inventory": [
                {
                    "item_id": "ration",
                    "name": "Trail ration",
                    "item_type": "consumable",
                    "quantity": 2,
                    "value": {"copper": 4},
                },
                {
                    "item_id": "iron",
                    "name": "Iron scrap",
                    "item_type": "crafting_material",
                    "material_id": "iron",
                    "quantity": 3,
                    "stackable": True,
                },
            ]
        },
        "crafting": {"known_recipes": ["torch_basic"]},
        "mechanics": {
            "salvage_traces": [{"event": "item_salvaged"}],
            "crafting_traces": [{"event": "item_crafted"}],
            "market_traces": [{"event": "market_transaction_applied"}],
        },
    }


def test_build_item_report_for_session_does_not_mutate_mechanics() -> None:
    state = _state()

    result = build_item_report_for_session(state, source="autoplay")

    assert result["ok"] is True
    assert result["summary"]["item_count"] == 2
    assert result["mechanics_trace"]["session_event"] == "item_report_session_recorded"
    assert result["mechanics_trace"]["session_source"] == "autoplay"
    assert result["mechanics_trace"]["turn"] == 9
    assert result["mechanics_trace"]["mechanics_source"] == "engine_item_report_session_v1"
    assert "item_report_sections" not in state["mechanics"]
    assert "item_traces" not in state["mechanics"]


def test_record_item_report_for_session_prepends_section_and_traces() -> None:
    state = _state()
    state["mechanics"]["item_report_sections"] = [{"old": True}]
    state["mechanics"]["item_traces"] = [{"event": "old_item_trace"}]

    result = record_item_report_for_session(state, source="campaign_report")

    assert result["ok"] is True
    assert result["detail"].startswith("Item report recorded 2 item(s)")
    assert state["mechanics"]["item_report_sections"][0] == result["section"]
    assert state["mechanics"]["item_report_sections"][1] == {"old": True}
    assert state["mechanics"]["item_report_session_traces"][0] == result["mechanics_trace"]
    assert state["mechanics"]["item_traces"][0] == result["mechanics_trace"]
    assert state["mechanics"]["item_traces"][1] == {"event": "old_item_trace"}
    assert result["section"]["mechanics_source"] == "engine_item_report_session_v1"
    assert result["section"]["trace"]["session_source"] == "campaign_report"
