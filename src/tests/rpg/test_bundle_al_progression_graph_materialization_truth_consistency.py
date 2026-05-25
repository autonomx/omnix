from __future__ import annotations

import json
from pathlib import Path


_PARTS_DIR = Path(__file__).resolve().parent / "autoplay_llm_campaign_parts"
_AE_FRAGMENT = _PARTS_DIR / "zzzz_bundle_ae_1000_progression_graph_expansion.pyfrag"
_AL_FRAGMENT = _PARTS_DIR / "zzzzzzzzzzzz_bundle_al_progression_graph_materialization_truth_consistency.pyfrag"


def _load_bundle_al_namespace(extra_globals=None):
    namespace = {"__name__": "_bundle_al_progression_graph_materialization_truth_consistency_test"}
    if extra_globals:
        namespace.update(extra_globals)
    for fragment in (_AE_FRAGMENT, _AL_FRAGMENT):
        exec(compile(fragment.read_text(encoding="utf-8"), str(fragment), "exec"), namespace, namespace)
    return namespace


def _write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def test_bundle_al_materializes_progression_graph_to_parent_and_unzipped(tmp_path):
    namespace = _load_bundle_al_namespace()
    parent = tmp_path / "result"
    unzipped = parent / "autoplay-campaign-results-unzipped"
    unzipped.mkdir(parents=True)

    result = namespace["_bundle_al_materialize_graphs"](parent)

    assert result["graph_ready"] is True
    assert result["graph_objective_edge_count"] >= 72
    assert (parent / "one-thousand-turn-progression-graph.json").exists()
    assert (parent / "one-thousand-turn-progression-graph-summary.json").exists()
    assert (unzipped / "one-thousand-turn-progression-graph.json").exists()
    assert (unzipped / "one-thousand-turn-progression-graph-summary.json").exists()
    summary = json.loads((unzipped / "one-thousand-turn-progression-graph-summary.json").read_text(encoding="utf-8"))
    assert summary["progression_graph_ready"] is True


def test_bundle_al_truth_uses_actual_dialogue_repair_rate_from_final_artifact(tmp_path):
    namespace = _load_bundle_al_namespace()
    parent = tmp_path / "result"
    unzipped = parent / "autoplay-campaign-results-unzipped"
    unzipped.mkdir(parents=True)
    _write_json(
        unzipped / "dialogue-repair-quality-summary.json",
        {
            "format_version": "dialogue_repair_quality_v1",
            "ok": True,
            "checked_count": 100,
            "repaired_count": 39,
            "repair_rate": 0.39,
            "max_recommended_repair_rate": 0.25,
            "product_quality_ok": False,
        },
    )

    truth = namespace["_bundle_al_truth_with_actual_repair"](
        unzipped,
        {
            "format_version": "bundle_ai_readiness_truth_summary_v1",
            "checks": {"dialogue_repair_rate_ok": True, "content_exhaustion_forecast_ok": True},
            "metrics": {"dialogue_repair_rate": 0.0},
            "truth_blocking_gates": [],
        },
    )

    assert truth["checks"]["dialogue_repair_rate_ok"] is False
    assert truth["metrics"]["dialogue_repair_rate"] == 0.39
    assert truth["metrics"]["max_dialogue_repair_rate"] == 0.25
    assert truth["metrics"]["dialogue_repair_repaired_count"] == 39
    assert "dialogue_repair_rate_ok" in truth["truth_blocking_gates"]
    assert truth["ready_for_1000_turn_preflight"] is False


def test_bundle_al_replaces_stale_bundle_ai_truth_failures_with_current_truth(tmp_path):
    namespace = _load_bundle_al_namespace()
    result_dir = tmp_path / "result"
    result_dir.mkdir()
    _write_json(
        result_dir / "one-thousand-turn-readiness-aggregator-summary.json",
        {
            "ok": True,
            "ready_for_1000_turn_preflight": True,
            "ready_for_live_1000_turn_run": True,
            "failing_required_gates": [
                "bundle_ai_truth:dialogue_repair_rate_ok",
                "bundle_ai_truth:old_stale_gate",
                "non_truth_gate",
            ],
        },
    )
    truth = {
        "truth_blocking_gates": ["preflight_result_ok_or_not_present"],
        "recommended_next_step": "fix_truth_blocking_gates_before_1000_turn_preflight",
        "ready_for_live_1000_turn_run": False,
    }

    patched = namespace["_bundle_al_patch_aggregator_with_truth"](result_dir, truth)
    aggregator = json.loads((result_dir / "one-thousand-turn-readiness-aggregator-summary.json").read_text(encoding="utf-8"))

    assert patched is True
    assert aggregator["bundle_al_truth_source_consistency_applied"] is True
    assert aggregator["bundle_ai_truth_blocking_gates"] == ["preflight_result_ok_or_not_present"]
    assert aggregator["failing_required_gates"] == ["non_truth_gate", "bundle_ai_truth:preflight_result_ok_or_not_present"]
    assert "bundle_ai_truth:dialogue_repair_rate_ok" not in aggregator["failing_required_gates"]
    assert aggregator["ready_for_1000_turn_preflight"] is False


def test_bundle_al_patches_ak_summary_to_fail_when_graph_files_absent_and_pass_when_materialized(tmp_path):
    namespace = _load_bundle_al_namespace()
    parent = tmp_path / "result"
    unzipped = parent / "autoplay-campaign-results-unzipped"
    unzipped.mkdir(parents=True)
    for directory in (parent, unzipped):
        _write_json(
            directory / "one-thousand-turn-slim-unzipped-mirror-summary.json",
            {"ok": True, "review_artifacts_present_after": False, "progression_graph_present": False, "progression_graph_summary_present": False},
        )

    namespace["_bundle_al_patch_ak_summary"](parent)
    before = json.loads((unzipped / "one-thousand-turn-slim-unzipped-mirror-summary.json").read_text(encoding="utf-8"))
    assert before["ok"] is False
    assert "progression_graph_present" in before["advisory_failures"]

    namespace["_bundle_al_materialize_graphs"](parent)
    namespace["_bundle_al_patch_ak_summary"](parent)
    after = json.loads((unzipped / "one-thousand-turn-slim-unzipped-mirror-summary.json").read_text(encoding="utf-8"))
    assert after["ok"] is True
    assert after["progression_graph_present"] is True
    assert after["progression_graph_summary_present"] is True


def test_bundle_al_finalize_writes_graph_truth_aggregator_dashboard_and_summary(tmp_path):
    namespace = _load_bundle_al_namespace()
    parent = tmp_path / "result"
    unzipped = parent / "autoplay-campaign-results-unzipped"
    unzipped.mkdir(parents=True)
    _write_json(unzipped / "dialogue-repair-quality-summary.json", {"repair_rate": 0.39, "max_recommended_repair_rate": 0.25, "checked_count": 100, "repaired_count": 39})
    for directory in (parent, unzipped):
        _write_json(directory / "one-thousand-turn-readiness-aggregator-summary.json", {"ok": True, "ready_for_1000_turn_preflight": True, "ready_for_live_1000_turn_run": True, "failing_required_gates": []})
        _write_json(directory / "one-thousand-turn-slim-unzipped-mirror-summary.json", {"ok": True, "review_artifacts_present_after": False})

    summary = namespace["_bundle_al_finalize_materialization_and_truth"](parent)

    assert summary["ok"] is True
    assert summary["graph_paths_ok"] is True
    assert (unzipped / "one-thousand-turn-progression-graph.json").exists()
    assert (unzipped / "one-thousand-turn-progression-graph-summary.json").exists()
    truth = json.loads((unzipped / "one-thousand-turn-readiness-truth-summary.json").read_text(encoding="utf-8"))
    aggregator = json.loads((unzipped / "one-thousand-turn-readiness-aggregator-summary.json").read_text(encoding="utf-8"))
    dashboard = json.loads((unzipped / "one-thousand-turn-readiness-dashboard-summary.json").read_text(encoding="utf-8"))
    assert truth["metrics"]["dialogue_repair_rate"] == 0.39
    assert truth["checks"]["dialogue_repair_rate_ok"] is False
    assert aggregator["failing_required_gates"] == ["bundle_ai_truth:dialogue_repair_rate_ok"]
    assert dashboard["status_label"] == "Readiness Blocked"
    assert (unzipped / "one-thousand-turn-materialization-truth-consistency-summary.json").exists()
