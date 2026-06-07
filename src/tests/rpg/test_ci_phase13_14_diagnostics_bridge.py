import builtins
import json
from pathlib import Path

from app.rpg.autoplay_performance_artifacts import build_autoplay_performance_summary
from tests.rpg.autoplay import turn_error_diagnostics_hook as hook
from tests.rpg.autoplay.live_performance_bridge import (
    SOURCE as BRIDGE_SOURCE,
    append_live_performance_bridge_row,
    build_live_performance_bridge_row,
)
from tests.rpg.autoplay.turn_error_diagnostics_hook import (
    SUMMARY_NAME,
    install_turn_error_diagnostics_hook,
)


def test_phase13_14_turn_error_hook_records_emitted_turn_error(tmp_path: Path):
    original = builtins.print
    try:
        hook._INSTALLED = False
        install_turn_error_diagnostics_hook(output_dir=tmp_path)
        print("[time] TURN 59 ERROR: RecursionError: maximum recursion depth exceeded")
    finally:
        builtins.print = original
        hook._INSTALLED = False

    payload = json.loads((tmp_path / SUMMARY_NAME).read_text(encoding="utf-8"))
    assert payload["event_count"] == 1
    event = payload["events"][0]
    assert event["turn_index"] == 59
    assert event["error_type"] == "RecursionError"
    assert "maximum recursion depth exceeded" in event["message"]
    assert event["stack_tail"]


def test_phase13_14_live_performance_bridge_builds_canonical_row():
    row = build_live_performance_bridge_row(
        {
            "stage_summary": {
                "manual_turn_ms": {"avg_ms": 12000, "count": 100, "max_ms": 15000},
                "state_bounds_ms": {"avg_ms": 30, "count": 100, "max_ms": 50},
                "background_enqueue_ms": {"avg_ms": 5, "count": 100, "max_ms": 10},
                "record_build_ms": {"avg_ms": 20, "count": 100, "max_ms": 60},
            }
        }
    )

    assert row["source"] == BRIDGE_SOURCE
    timing = row["performance"]["manual_turn_stage_timing"]
    assert timing["manual_turn_ms"] == 12000
    assert timing["state_snapshot_ms"] == 30
    assert timing["deferred_enqueue_ms"] == 5
    assert row["performance"]["live_manual_timing_bridge"]["manual_turn_unattributed_avg_ms"] == 11945


def test_phase13_14_performance_summary_reads_live_bridge_row():
    rows = append_live_performance_bridge_row(
        [],
        {
            "stage_summary": {
                "manual_turn_ms": {"avg_ms": 12000, "count": 100, "max_ms": 15000},
                "state_bounds_ms": {"avg_ms": 30, "count": 100, "max_ms": 50},
                "background_enqueue_ms": {"avg_ms": 5, "count": 100, "max_ms": 10},
            }
        },
    )
    summary = build_autoplay_performance_summary(rows)
    breakdown = summary["manual_turn_breakdown"]["summary"]

    assert breakdown["manual_turn_ms"]["avg_ms"] == 12000
    assert breakdown["state_snapshot_ms"]["avg_ms"] == 30
    assert breakdown["deferred_enqueue_ms"]["avg_ms"] == 5
