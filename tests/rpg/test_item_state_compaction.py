from __future__ import annotations

from app.rpg.session.item_state_compaction import (
    MECHANICS_SOURCE,
    apply_item_state_compaction,
    build_item_state_compaction,
)


def _trace(index: int) -> dict[str, object]:
    return {"event": "trace", "index": index}


def test_build_item_state_compaction_reports_over_limit_buckets_without_mutating_state() -> None:
    state = {"mechanics": {"item_traces": [_trace(index) for index in range(5)]}}

    plan = build_item_state_compaction(state, bucket_limit=2)

    assert plan["changed"] is True
    assert plan["summary"]["total_dropped"] == 3
    assert plan["buckets"] == [
        {"bucket": "item_traces", "before": 5, "after": 2, "dropped": 3, "changed": True}
    ]
    assert len(state["mechanics"]["item_traces"]) == 5


def test_apply_item_state_compaction_trims_newest_entries_and_records_trace() -> None:
    state = {
        "mechanics": {
            "item_traces": [_trace(index) for index in range(5)],
            "crafting_traces": [_trace(index) for index in range(4)],
        }
    }

    result = apply_item_state_compaction(state, bucket_limit=2)

    assert result["ok"] is True
    assert result["changed"] is True
    assert result["summary"]["total_dropped"] == 5
    assert state["mechanics"]["crafting_traces"] == [_trace(0), _trace(1)]
    assert state["mechanics"]["item_traces"][0]["event"] == "item_state_compacted"
    assert state["mechanics"]["item_traces"][1:] == [_trace(0), _trace(1)]
    trace = state["mechanics"]["item_state_compaction_traces"][0]
    assert trace["mechanics_source"] == MECHANICS_SOURCE
    assert trace["total_before"] == 9
    assert trace["total_after"] == 4
    assert trace["total_dropped"] == 5
    assert {bucket["bucket"] for bucket in trace["changed_buckets"]} == {"item_traces", "crafting_traces"}


def test_apply_item_state_compaction_detects_invalid_trace_buckets() -> None:
    state = {"mechanics": {"item_traces": {"not": "a-list"}}}

    result = apply_item_state_compaction(state, bucket_limit=2)

    assert result["ok"] is False
    assert result["invalid_buckets"] == [
        {"bucket": "item_traces", "reason": "not_list", "value_type": "dict"}
    ]
    assert state["mechanics"]["item_traces"][0]["event"] == "item_state_compacted"
    assert state["mechanics"]["item_state_compaction_traces"][0]["invalid_buckets"] == result["invalid_buckets"]


def test_apply_item_state_compaction_can_skip_trace_recording() -> None:
    state = {"mechanics": {"item_traces": [_trace(index) for index in range(3)]}}

    result = apply_item_state_compaction(state, bucket_limit=1, record_trace=False)

    assert result["changed"] is True
    assert state["mechanics"]["item_traces"] == [_trace(0)]
    assert "item_state_compaction_traces" not in state["mechanics"]


def test_build_item_state_compaction_can_include_unchanged_buckets() -> None:
    state = {"mechanics": {"item_traces": [_trace(0)]}}

    plan = build_item_state_compaction(state, bucket_limit=5, include_unchanged=True)

    assert plan["changed"] is False
    item_trace_summary = next(bucket for bucket in plan["buckets"] if bucket["bucket"] == "item_traces")
    assert item_trace_summary == {"bucket": "item_traces", "before": 1, "after": 1, "dropped": 0, "changed": False}
