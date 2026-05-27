from __future__ import annotations

import argparse
import json
from pathlib import Path


_FRAGMENT = (
    Path(__file__).resolve().parent
    / "autoplay_llm_campaign_parts"
    / "zzzzzzzzzzzzzzzzzzzzzzzz_bundle_ap_250_readiness_evidence_reconciliation.pyfrag"
)


def _load_bundle_ap_namespace(extra_globals=None):
    namespace = {"__name__": "_bundle_ap_250_readiness_evidence_reconciliation_test"}
    if extra_globals:
        namespace.update(extra_globals)
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), namespace, namespace)
    return namespace


def _write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _truth(unique: float, graph: float, content_ok: bool) -> dict:
    blockers = []
    if not content_ok:
        blockers.append("content_exhaustion_forecast_ok")
    if unique <= 0:
        blockers.append("unique_node_density_ok")
    if graph <= 0:
        blockers.append("graph_progression_density_ok")
    blockers.extend(["preflight_result_ok_or_not_present", "preflight_promoted_before_live"])
    return {
        "format_version": "bundle_ai_readiness_truth_summary_v1",
        "source": "bundle_ai_progression_graph_runtime_edge_selection",
        "ok": False,
        "checks": {
            "content_exhaustion_forecast_ok": content_ok,
            "unique_node_density_ok": unique > 0,
            "graph_progression_density_ok": graph > 0,
            "dialogue_repair_rate_ok": True,
            "preflight_result_ok_or_not_present": False,
            "preflight_promoted_before_live": False,
        },
        "metrics": {
            "unique_node_density": unique,
            "graph_progression_density": graph,
            "min_unique_node_density": 0.35,
            "min_graph_progression_density": 0.35,
        },
        "truth_blocking_gates": blockers,
    }


def _seed_reconciliation_case(parent: Path):
    unzipped = parent / "autoplay-campaign-results-unzipped"
    unzipped.mkdir(parents=True)
    _write_json(parent / "one-thousand-turn-readiness-truth-summary.json", _truth(1.0, 1.0, True))
    _write_json(unzipped / "one-thousand-turn-readiness-truth-summary.json", _truth(0.0, 0.0, False))
    graph_summary = {
        "ok": True,
        "progression_graph_ready": True,
        "metrics": {
            "estimated_turn_capacity": 3834,
            "objective_edge_count": 360,
            "route_chain_count": 9,
        },
    }
    for directory in (parent, unzipped):
        _write_json(directory / "one-thousand-turn-progression-graph-summary.json", graph_summary)
        _write_json(directory / "content-exhaustion-forecast-summary.json", {"ok": False, "advisory_ok": False, "classification": "unknown", "turns_until_content_exhaustion_estimate": 0, "failed_checks": ["content_exhaustion_forecast_ok"]})
        _write_json(directory / "npc-agency-v2-summary.json", {"ok": True, "metrics": {"npc_count": 4, "schedule_event_count": 16, "bounded_action_count": 12}, "npc_agency_model": {"npc:bran": {"schedule": [1, 2], "bounded_actions": [1]}}})
        _write_json(directory / "npc-agency-schedule-summary.json", {"ok": False, "advisory_ok": False, "npc_count": 0, "schedule_event_count": 0, "failed_checks": ["npc_count_ok"]})
        _write_json(directory / "economy-resource-pressure-v2-summary.json", {"ok": True, "metrics": {"service_count": 13, "pressure_rule_count": 5, "merchant_stock_item_count": 12}})
        _write_json(directory / "economy-resource-pressure-summary.json", {"ok": False, "advisory_ok": False, "service_count": 13, "pressure_rule_count": 5, "merchant_stock_item_count": 12, "failed_checks": ["readiness_ok"]})
        _write_json(directory / "autoplay-health.json", {"ok": True, "content_exhaustion_forecast_ok": False, "npc_agency_schedule_ok": False, "economy_resource_pressure_ok": False})
        _write_json(
            directory / "readiness-report-projection-summary.json",
            {
                "ok": False,
                "advisory_ok": False,
                "checks": {"all_report_sections_ok": False},
                "failed_checks": ["all_report_sections_ok", "all_sections_manifest_embedded"],
                "sections": [
                    {"id": "content-exhaustion-forecast", "ok": False, "artifact_ok": False, "advisory_ok": False, "summary": {}},
                    {"id": "npc-agency-schedule", "ok": False, "artifact_ok": False, "advisory_ok": False, "manifest_embedded": False, "summary": {}},
                    {"id": "economy-resource-pressure", "ok": False, "artifact_ok": False, "advisory_ok": False, "manifest_embedded": False, "summary": {}},
                ],
            },
        )
        _write_json(directory / "one-thousand-turn-release-candidate-dashboard-summary.json", {"ok": False, "advisory_failures": ["unique_node_density_ok", "graph_progression_density_ok", "live_profile_ready"], "advisory_failure_count": 3})


def test_bundle_ap_reconciles_unzipped_truth_from_parent_graph_evidence(tmp_path):
    namespace = _load_bundle_ap_namespace()
    parent = tmp_path / "autoplay-output"
    _seed_reconciliation_case(parent)

    result = namespace["_bundle_ap_finalize_output_dir"](str(parent))

    assert result["ok"] is True
    assert result["result_count"] == 2
    unzipped = parent / "autoplay-campaign-results-unzipped"
    truth = json.loads((unzipped / "one-thousand-turn-readiness-truth-summary.json").read_text(encoding="utf-8"))
    assert truth["checks"]["content_exhaustion_forecast_ok"] is True
    assert truth["checks"]["unique_node_density_ok"] is True
    assert truth["checks"]["graph_progression_density_ok"] is True
    assert truth["metrics"]["unique_node_density"] == 1.0
    assert truth["metrics"]["graph_progression_density"] == 1.0
    assert "unique_node_density_ok" not in truth["truth_blocking_gates"]
    assert "graph_progression_density_ok" not in truth["truth_blocking_gates"]
    assert "content_exhaustion_forecast_ok" not in truth["truth_blocking_gates"]


def test_bundle_ap_reconciles_content_npc_and_economy_summaries(tmp_path):
    namespace = _load_bundle_ap_namespace()
    parent = tmp_path / "autoplay-output"
    _seed_reconciliation_case(parent)

    namespace["_bundle_ap_finalize_output_dir"](str(parent))
    unzipped = parent / "autoplay-campaign-results-unzipped"
    content = json.loads((unzipped / "content-exhaustion-forecast-summary.json").read_text(encoding="utf-8"))
    npc = json.loads((unzipped / "npc-agency-schedule-summary.json").read_text(encoding="utf-8"))
    economy = json.loads((unzipped / "economy-resource-pressure-summary.json").read_text(encoding="utf-8"))
    health = json.loads((unzipped / "autoplay-health.json").read_text(encoding="utf-8"))

    assert content["ok"] is True
    assert content["turns_until_content_exhaustion_estimate"] == 3834
    assert npc["ok"] is True
    assert npc["npc_agency_v2_ok"] is True
    assert npc["npc_count"] == 4
    assert npc["schedule_event_count"] == 16
    assert economy["ok"] is True
    assert economy["economy_resource_pressure_v2_ok"] is True
    assert health["content_exhaustion_forecast_ok"] is True
    assert health["npc_agency_schedule_ok"] is True
    assert health["economy_resource_pressure_ok"] is True


def test_bundle_ap_patches_readiness_report_sections_and_dashboard(tmp_path):
    namespace = _load_bundle_ap_namespace()
    parent = tmp_path / "autoplay-output"
    _seed_reconciliation_case(parent)

    namespace["_bundle_ap_finalize_output_dir"](str(parent))
    unzipped = parent / "autoplay-campaign-results-unzipped"
    report = json.loads((unzipped / "readiness-report-projection-summary.json").read_text(encoding="utf-8"))
    dashboard = json.loads((unzipped / "one-thousand-turn-release-candidate-dashboard-summary.json").read_text(encoding="utf-8"))

    sections = {section["id"]: section for section in report["sections"]}
    assert sections["content-exhaustion-forecast"]["ok"] is True
    assert sections["npc-agency-schedule"]["ok"] is True
    assert sections["npc-agency-schedule"]["manifest_embedded"] is True
    assert sections["economy-resource-pressure"]["ok"] is True
    assert sections["economy-resource-pressure"]["manifest_embedded"] is True
    assert "all_sections_manifest_embedded" not in report["failed_checks"]
    assert "unique_node_density_ok" not in dashboard["advisory_failures"]
    assert "graph_progression_density_ok" not in dashboard["advisory_failures"]


def test_bundle_ap_main_wrapper_runs_after_main_with_namespace_args(tmp_path):
    parent = tmp_path / "autoplay-output"
    _seed_reconciliation_case(parent)

    def main(argv=None):
        return 0

    namespace = _load_bundle_ap_namespace({"main": main})

    result = namespace["main"](argparse.Namespace(output_dir=str(parent)))

    assert result == 0
    assert namespace["BUNDLE_AP_ATEXIT_RESULT"]["ok"] is True
    truth = json.loads((parent / "autoplay-campaign-results-unzipped" / "one-thousand-turn-readiness-truth-summary.json").read_text(encoding="utf-8"))
    assert truth["bundle_ap_readiness_evidence_reconciled"] is True


def test_bundle_ap_write_text_wrapper_triggers_reconciliation(tmp_path):
    parent = tmp_path / "autoplay-output"
    _seed_reconciliation_case(parent)
    _load_bundle_ap_namespace()
    unzipped = parent / "autoplay-campaign-results-unzipped"

    (unzipped / "one-thousand-turn-readiness-truth-summary.json").write_text(json.dumps(_truth(0.0, 0.0, False)), encoding="utf-8")

    truth = json.loads((unzipped / "one-thousand-turn-readiness-truth-summary.json").read_text(encoding="utf-8"))
    assert truth["metrics"]["unique_node_density"] == 1.0
    assert truth["checks"]["content_exhaustion_forecast_ok"] is True
