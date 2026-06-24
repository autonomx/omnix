from __future__ import annotations

from app.rpg.performance_paths import (
    LatencySample,
    blocking_tasks,
    classify_turn_task,
    deferred_tasks,
    fast_action_response,
    is_fast_deterministic_action,
    performance_report,
)


def test_known_tasks_use_configured_classes() -> None:
    assert classify_turn_task("intent_classification").path_class == "must_block"
    assert classify_turn_task("memory_summary").path_class == "can_defer"
    assert classify_turn_task("unknown").reason == "unknown_tasks_block"


def test_fast_actions_skip_heavy_llm() -> None:
    assert is_fast_deterministic_action("inventory") is True
    assert fast_action_response("inventory")["requires_heavy_llm"] is False
    assert fast_action_response("attack")["requires_heavy_llm"] is True


def test_blocking_and_deferred_task_lists() -> None:
    decisions = [classify_turn_task("simulation_resolution"), classify_turn_task("journal_recap")]

    assert blocking_tasks(decisions) == ("simulation_resolution",)
    assert deferred_tasks(decisions) == ("journal_recap",)


def test_performance_report_groups_latency() -> None:
    payload = performance_report(
        [LatencySample("intent", 10.0, "must_block"), LatencySample("audit", 5.0, "can_defer")]
    )

    assert payload["sample_count"] == 2
    assert payload["total_latency_ms"] == 15.0
    assert payload["blocking_latency_ms"] == 10.0
