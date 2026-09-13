from __future__ import annotations

from app.rpg.session.item_state_maintenance import (
    build_item_state_maintenance_plan,
    run_item_state_maintenance,
)


def _trace(index: int) -> dict[str, object]:
    return {"event": "trace", "index": index}


def _state() -> dict[str, object]:
    return {
        "player": {
            "currency": {"silver": 1, "copper": 2},
            "inventory": [
                {"item_id": "trail_ration", "name": "Trail Ration", "quantity": 2, "stackable": True, "item_type": "consumable"},
                {"material_id": "cloth", "name": "Cloth", "quantity": 3, "stackable": True, "item_type": "crafting_material"},
            ],
            "equipment": {},
        },
        "crafting": {"known_recipes": ["torch"]},
        "mechanics": {
            "item_traces": [_trace(index) for index in range(4)],
            "market_traces": [_trace(index) for index in range(3)],
        },
    }


def test_build_item_state_maintenance_plan_is_dry_run() -> None:
    state = _state()

    plan = build_item_state_maintenance_plan(state, bucket_limit=2, include_report=True)

    assert plan["ok"] is True
    assert plan["actions"] == ["audit", "compact", "report"]
    assert plan["summary"]["compaction_dropped"] == 3
    assert len(state["mechanics"]["item_traces"]) == 4
    assert "item_state_maintenance_traces" not in state["mechanics"]


def test_run_item_state_maintenance_records_audit_compaction_and_summary_trace() -> None:
    state = _state()

    result = run_item_state_maintenance(state, bucket_limit=2, record_report=False)

    assert result["ok"] is True
    assert result["summary"]["compacted"] is True
    assert result["summary"]["compaction_dropped"] >= 3
    assert result["trace"]["event"] == "item_state_maintained"
    assert "compact" in result["trace"]["actions"]
    assert state["mechanics"]["item_state_audit_traces"][0]["event"] == "item_state_audited"
    assert state["mechanics"]["item_state_compaction_traces"][0]["event"] == "item_state_compacted"
    assert state["mechanics"]["item_state_maintenance_traces"][0] == result["trace"]
    assert state["mechanics"]["item_traces"][0] == result["trace"]
    assert len(state["mechanics"]["market_traces"]) == 2


def test_run_item_state_maintenance_can_record_report_snapshot() -> None:
    state = _state()

    result = run_item_state_maintenance(state, bucket_limit=10, record_report=True)

    assert result["summary"]["report_recorded"] is True
    assert result["report"]["ok"] is True
    assert state["mechanics"]["item_report_sections"][0]["title"] == "Item System Coverage"
    assert state["mechanics"]["item_report_session_traces"][0]["session_source"] == "maintenance"
    assert "report" in result["trace"]["actions"]


def test_run_item_state_maintenance_reports_invalid_state_without_compaction_noise() -> None:
    state = {
        "player": {
            "currency": {"copper": -1},
            "inventory": [{"name": "Bent Token", "quantity": -2}],
        },
        "mechanics": {"item_traces": []},
    }

    result = run_item_state_maintenance(state, bucket_limit=10, record_compaction=False)

    assert result["ok"] is False
    assert result["summary"]["audit_severity"] == "error"
    assert result["compaction"] is None
    assert "item_state_compaction_traces" not in state["mechanics"]
    assert state["mechanics"]["item_state_maintenance_traces"][0] == result["trace"]
