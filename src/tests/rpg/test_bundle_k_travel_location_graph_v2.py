from __future__ import annotations

import json
from pathlib import Path


_FRAGMENT = (
    Path(__file__).resolve().parent
    / "autoplay_llm_campaign_parts"
    / "zz_bundle_k_travel_location_graph_v2.pyfrag"
)


def _load_bundle_k_namespace():
    namespace = {"__name__": "_bundle_k_travel_location_graph_v2_test"}
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), namespace, namespace)
    return namespace


def test_bundle_k_graph_has_locations_routes_events_and_loop_guards():
    namespace = _load_bundle_k_namespace()
    graph = namespace["_BUNDLE_K_GRAPH"]

    assert graph["format_version"] == "bundle_k_travel_location_graph_v2_model_v1"
    assert len(graph["locations"]) >= 10
    assert len(graph["routes"]) >= 12
    assert len(graph["travel_events"]) >= 5
    assert graph["loop_guards"]["max_route_repeat_window"] == 4
    assert graph["loop_guards"]["prefer_unvisited_connected_location"] is True
    assert graph["loop_guards"]["avoid_immediate_backtrack_without_new_evidence"] is True


def test_bundle_k_gate_passes_for_valid_graph():
    namespace = _load_bundle_k_namespace()
    result = namespace["_bundle_k_evaluate_travel_location_graph_v2"]({})

    assert result["format_version"] == "bundle_k_travel_location_graph_v2_summary_v1"
    assert result["source"] == "bundle_k_travel_location_graph_v2"
    assert result["ok"] is True
    assert result["advisory_only"] is True
    assert result["advisory_failures"] == []
    assert result["checks"]["location_graph_expanded"] is True
    assert result["checks"]["route_graph_expanded"] is True
    assert result["checks"]["route_endpoints_valid"] is True
    assert result["checks"]["route_costs_present"] is True
    assert result["checks"]["locked_routes_present"] is True
    assert result["checks"]["travel_event_catalog_present"] is True
    assert result["checks"]["travel_loop_guards_present"] is True
    assert result["metrics"]["location_count"] >= 10
    assert result["metrics"]["route_count"] >= 12
    assert result["metrics"]["locked_route_count"] >= 4


def test_bundle_k_writes_summary_when_result_artifact_is_exported(tmp_path):
    namespace = _load_bundle_k_namespace()
    original_write_text = namespace["_BUNDLE_K_ORIGINAL_PATH_WRITE_TEXT"]
    try:
        (tmp_path / "summary.json").write_text(json.dumps({"turn_count": 100}), encoding="utf-8")

        summary_path = tmp_path / "travel-location-graph-v2-summary.json"
        assert summary_path.exists()
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        assert summary["ok"] is True
        assert summary["checks"]["route_endpoints_valid"] is True
        assert summary["checks"]["route_costs_present"] is True
        assert summary["metrics"]["route_count"] >= 12
    finally:
        Path.write_text = original_write_text
