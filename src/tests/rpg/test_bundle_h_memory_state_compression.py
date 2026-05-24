from __future__ import annotations

import json
from pathlib import Path


_FRAGMENT = (
    Path(__file__).resolve().parent
    / "autoplay_llm_campaign_parts"
    / "zz_bundle_h_memory_state_compression.pyfrag"
)


def _load_bundle_h_namespace():
    namespace = {"__name__": "_bundle_h_memory_state_compression_test"}
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), namespace, namespace)
    return namespace


def _passing_artifacts():
    return {
        "summary.json": {
            "turn_count": 100,
            "state_bytes": 1_000_000,
            "journal_raw_row_count": 20,
            "world_event_retained_row_count": 40,
            "npc_memory": {
                "npc:bran": {"memories": [{"id": f"b{i}"} for i in range(8)]},
                "npc:sera": {"memories": [{"id": f"s{i}"} for i in range(6)]},
            },
        },
        "long-run-dry-run-projection-summary.json": {
            "projected_1000_turn_state_bytes": 8_000_000,
        },
        "npc-agency-schedule-summary.json": {
            "npc_count": 2,
        },
    }


def test_bundle_h_policy_exposes_memory_aging_and_compression_rules():
    namespace = _load_bundle_h_namespace()
    policy = namespace["_BUNDLE_H_POLICY"]

    assert policy["format_version"] == "bundle_h_memory_state_compression_policy_v1"
    assert policy["recent_detail_turn_window"] == 25
    assert policy["summarize_after_turns"] == 75
    assert policy["low_importance_decay_after_turns"] == 150
    assert policy["high_importance_persist_threshold"] == 0.75
    assert "recent_memories" in policy["memory_aging_policy"]
    assert "older_memories" in policy["memory_aging_policy"]
    assert "low_importance_memories" in policy["memory_aging_policy"]
    assert "high_importance_memories" in policy["memory_aging_policy"]
    assert "locations" in policy["world_state_compression"]
    assert "npc_relationships" in policy["world_state_compression"]
    assert "quest_history" in policy["world_state_compression"]
    assert "journal" in policy["world_state_compression"]


def test_bundle_h_gate_passes_for_bounded_state_and_memory():
    namespace = _load_bundle_h_namespace()
    result = namespace["_bundle_h_evaluate_memory_state_compression"](_passing_artifacts())

    assert result["format_version"] == "bundle_h_memory_state_compression_summary_v1"
    assert result["ok"] is True
    assert result["advisory_only"] is True
    assert result["target_turns"] == 1000
    assert result["advisory_failures"] == []
    assert result["checks"]["state_bytes_bounded"] is True
    assert result["checks"]["projected_1000_state_bytes_bounded"] is True
    assert result["checks"]["npc_memory_rows_per_npc_bounded"] is True
    assert result["checks"]["journal_raw_rows_bounded"] is True
    assert result["checks"]["world_event_rows_bounded"] is True
    assert result["checks"]["memory_aging_policy_present"] is True
    assert result["checks"]["world_state_compression_policy_present"] is True
    assert result["recommended_next_step"] == "ready_for_1000_turn_preflight"


def test_bundle_h_gate_reports_advisory_failures_for_unbounded_growth():
    namespace = _load_bundle_h_namespace()
    artifacts = _passing_artifacts()
    artifacts["summary.json"]["state_bytes"] = 99_000_000
    artifacts["summary.json"]["journal_raw_row_count"] = 999
    artifacts["summary.json"]["world_event_retained_row_count"] = 999
    artifacts["summary.json"]["npc_memory"] = {
        "npc:bran": {"memories": [{"id": f"b{i}"} for i in range(100)]}
    }
    artifacts["long-run-dry-run-projection-summary.json"]["projected_1000_turn_state_bytes"] = 99_000_000

    result = namespace["_bundle_h_evaluate_memory_state_compression"](artifacts)

    assert result["ok"] is False
    assert result["advisory_only"] is True
    assert set(result["advisory_failures"]) == {
        "state_bytes_bounded",
        "projected_1000_state_bytes_bounded",
        "npc_memory_rows_per_npc_bounded",
        "journal_raw_rows_bounded",
        "world_event_rows_bounded",
    }
    assert result["recommended_next_step"] == "apply_memory_state_compression_before_1000_turn_preflight"


def test_bundle_h_writes_summary_when_relevant_artifacts_are_exported(tmp_path):
    namespace = _load_bundle_h_namespace()
    original_write_text = namespace["_BUNDLE_H_ORIGINAL_PATH_WRITE_TEXT"]
    try:
        for file_name, payload in _passing_artifacts().items():
            (tmp_path / file_name).write_text(json.dumps(payload), encoding="utf-8")

        summary_path = tmp_path / "memory-state-compression-summary.json"
        assert summary_path.exists()
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        assert summary["source"] == "bundle_h_memory_state_compression"
        assert summary["ok"] is True
        assert summary["checks"]["memory_aging_policy_present"] is True
        assert summary["checks"]["world_state_compression_policy_present"] is True
    finally:
        Path.write_text = original_write_text


def test_bundle_h_injects_report_section_with_collapsed_raw_json(tmp_path):
    namespace = _load_bundle_h_namespace()
    original_write_text = namespace["_BUNDLE_H_ORIGINAL_PATH_WRITE_TEXT"]
    try:
        for file_name, payload in _passing_artifacts().items():
            (tmp_path / file_name).write_text(json.dumps(payload), encoding="utf-8")

        report_path = tmp_path / "autoplay-campaign-report.html"
        report_path.write_text(
            "<html><body><h1>Autoplay Campaign Report</h1><main><p>Body</p></main></body></html>",
            encoding="utf-8",
        )
        rendered = report_path.read_text(encoding="utf-8")

        assert 'id="bundle-h-memory-state-compression"' in rendered
        assert "Memory / State Compression" in rendered
        assert "projected_1000_turn_state_bytes" in rendered
        assert "npc_memory_rows_per_npc_bounded" in rendered
        assert '<details class="bundle-h-raw-details">' in rendered
        raw_start = rendered.index('<details class="bundle-h-raw-details">')
        raw_open = rendered[raw_start : rendered.index(">", raw_start) + 1]
        assert " open" not in raw_open
        assert "<p>Body</p>" in rendered
    finally:
        Path.write_text = original_write_text
