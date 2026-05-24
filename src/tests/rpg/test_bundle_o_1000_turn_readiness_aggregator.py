from __future__ import annotations

import json
from pathlib import Path


_FRAGMENT = (
    Path(__file__).resolve().parent
    / "autoplay_llm_campaign_parts"
    / "zz_bundle_o_1000_turn_readiness_aggregator.pyfrag"
)


def _load_bundle_o_namespace():
    namespace = {"__name__": "_bundle_o_1000_turn_readiness_aggregator_test"}
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), namespace, namespace)
    return namespace


def _passing_artifacts(namespace):
    return {
        gate_name: {
            "ok": True,
            "checks": {"gate_ready": True},
            "advisory_failures": [],
            "metrics": {"sample_metric": 1},
        }
        for gate_name in namespace["_BUNDLE_O_REQUIRED_GATES"]
    }


def test_bundle_o_required_gate_catalog_is_explicit():
    namespace = _load_bundle_o_namespace()
    required = namespace["_BUNDLE_O_REQUIRED_GATES"]

    assert required == {
        "dry_run_300_endurance",
        "content_depth",
        "memory_state_compression",
        "npc_agency_v2",
        "economy_resource_pressure_v2",
        "travel_location_graph_v2",
        "faction_reputation_v2",
        "encounter_lifecycle_v2",
        "story_arc_end_state_v2",
    }
    assert namespace["_BUNDLE_O_INPUT_FILES"]["story-arc-end-state-v2-summary.json"] == "story_arc_end_state_v2"
    assert namespace["_BUNDLE_O_GATE_CATEGORIES"]["story_arc_end_state_v2"] == "campaign"


def test_bundle_o_aggregator_passes_when_required_gates_pass():
    namespace = _load_bundle_o_namespace()
    artifacts = _passing_artifacts(namespace)
    artifacts["artifact_manifest_digest"] = {"ok": True, "checks": {"manifest_ok": True}}

    result = namespace["_bundle_o_evaluate_1000_turn_readiness"](artifacts)

    assert result["format_version"] == "bundle_o_1000_turn_readiness_aggregator_summary_v1"
    assert result["source"] == "bundle_o_1000_turn_readiness_aggregator"
    assert result["ok"] is True
    assert result["advisory_only"] is True
    assert result["ready_for_1000_turn_preflight"] is True
    assert result["ready_for_live_1000_turn_run"] is True
    assert result["required_gate_count"] == 9
    assert result["present_required_gate_count"] == 9
    assert result["passing_required_gate_count"] == 9
    assert result["missing_required_gates"] == []
    assert result["failing_required_gates"] == []
    assert result["total_failed_check_count"] == 0
    assert result["total_advisory_failure_count"] == 0
    assert result["recommended_next_step"] == "run_1000_turn_preflight"
    assert result["category_rollup"]["campaign"]["pass_count"] == 1


def test_bundle_o_aggregator_reports_missing_and_failing_required_gates():
    namespace = _load_bundle_o_namespace()
    artifacts = _passing_artifacts(namespace)
    artifacts.pop("content_depth")
    artifacts["memory_state_compression"] = {
        "ok": False,
        "checks": {"state_bytes_bounded": False},
        "advisory_failures": ["state_bytes_bounded"],
    }

    result = namespace["_bundle_o_evaluate_1000_turn_readiness"](artifacts)

    assert result["ok"] is False
    assert result["ready_for_1000_turn_preflight"] is False
    assert result["ready_for_live_1000_turn_run"] is False
    assert result["missing_required_gates"] == ["content_depth"]
    assert result["failing_required_gates"] == ["memory_state_compression"]
    assert result["total_failed_check_count"] == 1
    assert result["total_advisory_failure_count"] == 2
    assert result["recommended_next_step"] == "fix_required_readiness_gates_before_1000_turn_preflight"


def test_bundle_o_writes_summary_when_required_artifacts_are_exported(tmp_path):
    namespace = _load_bundle_o_namespace()
    original_write_text = namespace["_BUNDLE_O_ORIGINAL_PATH_WRITE_TEXT"]
    try:
        file_by_gate = {gate: file_name for file_name, gate in namespace["_BUNDLE_O_INPUT_FILES"].items()}
        for gate_name in namespace["_BUNDLE_O_REQUIRED_GATES"]:
            file_name = file_by_gate[gate_name]
            (tmp_path / file_name).write_text(
                json.dumps({"ok": True, "checks": {"gate_ready": True}, "advisory_failures": []}),
                encoding="utf-8",
            )

        summary_path = tmp_path / "one-thousand-turn-readiness-aggregator-summary.json"
        assert summary_path.exists()
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        assert summary["ok"] is True
        assert summary["ready_for_1000_turn_preflight"] is True
        assert summary["present_required_gate_count"] == 9
        assert summary["passing_required_gate_count"] == 9
    finally:
        Path.write_text = original_write_text
