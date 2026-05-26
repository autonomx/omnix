from __future__ import annotations

import json
from pathlib import Path


_FRAGMENT = (
    Path(__file__).resolve().parent
    / "autoplay_llm_campaign_parts"
    / "zzzzzzzzzzzzzzz_bundle_am2_summary_consistency_cleanup.pyfrag"
)


def _load_bundle_am2_namespace(extra_globals=None):
    namespace = {"__name__": "_bundle_am2_summary_consistency_cleanup_test"}
    if extra_globals:
        namespace.update(extra_globals)
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), namespace, namespace)
    return namespace


def _write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def _seed_am2_artifacts(directory: Path):
    _write_json(
        directory / "dialogue-repair-quality-summary.json",
        {
            "checked_count": 100,
            "repaired_count": 5,
            "repair_rate": 0.05,
            "raw_repaired_count_before_bundle_am": 39,
            "raw_repair_rate_before_bundle_am": 0.39,
            "scenario_graph_empty_presentation_repairs_filled": 34,
            "effective_repaired_count_after_bundle_am": 5,
            "effective_repair_rate_after_bundle_am": 0.05,
            "max_recommended_repair_rate": 0.25,
            "product_quality_ok": True,
            "ok": True,
            "warnings": ["dialogue_action_relevance_repair_rate_high"],
            "advisory_failures": ["dialogue_action_relevance_repair_rate_high"],
        },
    )
    _write_json(
        directory / "scenario-graph-presentation-fill-summary.json",
        {
            "ok": True,
            "raw_repair_rate_before_bundle_am": None,
            "effective_repair_rate_after_bundle_am": None,
            "scenario_graph_empty_presentation_repairs_filled": 0,
            "filled_node_count": 18012,
            "player_agent_spike_guard_ok": True,
            "presentation_artifact_changes": [],
        },
    )
    _write_json(directory / "player-agent-spike-guard-summary.json", {"ok": True, "metrics": {"player_agent_max_ms": 9972.182}})
    _write_json(
        directory / "one-thousand-turn-readiness-truth-summary.json",
        {
            "checks": {"dialogue_repair_rate_ok": False, "preflight_result_ok_or_not_present": False},
            "metrics": {"dialogue_repair_rate": 0.39},
            "truth_blocking_gates": ["dialogue_repair_rate_ok", "preflight_result_ok_or_not_present"],
            "ready_for_1000_turn_preflight": False,
            "ready_for_live_1000_turn_run": False,
        },
    )
    _write_json(
        directory / "one-thousand-turn-readiness-aggregator-summary.json",
        {
            "ok": False,
            "ready_for_1000_turn_preflight": False,
            "ready_for_live_1000_turn_run": False,
            "failing_required_gates": ["bundle_ai_truth:dialogue_repair_rate_ok", "bundle_ai_truth:preflight_result_ok_or_not_present"],
        },
    )


def test_bundle_am2_rewrites_stale_presentation_summary_from_repair_source(tmp_path):
    namespace = _load_bundle_am2_namespace()
    result_dir = tmp_path / "result"
    result_dir.mkdir()
    _seed_am2_artifacts(result_dir)

    result = namespace["_bundle_am2_cleanup_dir"](result_dir)
    repair = json.loads((result_dir / "dialogue-repair-quality-summary.json").read_text(encoding="utf-8"))
    summary = json.loads((result_dir / "scenario-graph-presentation-fill-summary.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert repair["warnings"] == []
    assert repair["advisory_failures"] == []
    assert repair["repair_rate"] == 0.05
    assert summary["raw_repair_rate_before_bundle_am"] == 0.39
    assert summary["effective_repair_rate_after_bundle_am"] == 0.05
    assert summary["scenario_graph_empty_presentation_repairs_filled"] == 34
    assert summary["repair_gate_ok_after_bundle_am"] is True
    assert summary["player_agent_spike_guard_ok"] is True
    assert summary["bundle_am2_summary_consistency_applied"] is True


def test_bundle_am2_updates_truth_and_removes_dialogue_repair_blocker(tmp_path):
    namespace = _load_bundle_am2_namespace()
    result_dir = tmp_path / "result"
    result_dir.mkdir()
    _seed_am2_artifacts(result_dir)

    namespace["_bundle_am2_cleanup_dir"](result_dir)
    truth = json.loads((result_dir / "one-thousand-turn-readiness-truth-summary.json").read_text(encoding="utf-8"))
    aggregator = json.loads((result_dir / "one-thousand-turn-readiness-aggregator-summary.json").read_text(encoding="utf-8"))
    dashboard = json.loads((result_dir / "one-thousand-turn-readiness-dashboard-summary.json").read_text(encoding="utf-8"))

    assert truth["checks"]["dialogue_repair_rate_ok"] is True
    assert truth["metrics"]["dialogue_repair_rate"] == 0.05
    assert truth["metrics"]["raw_dialogue_repair_rate_before_bundle_am"] == 0.39
    assert "dialogue_repair_rate_ok" not in truth["truth_blocking_gates"]
    assert aggregator["failing_required_gates"] == ["bundle_ai_truth:preflight_result_ok_or_not_present"]
    assert dashboard["status_label"] == "Readiness Blocked"


def test_bundle_am2_finalizes_parent_and_unzipped_consistently(tmp_path):
    namespace = _load_bundle_am2_namespace()
    parent = tmp_path / "autoplay-output"
    unzipped = parent / "autoplay-campaign-results-unzipped"
    for directory in (parent, unzipped):
        directory.mkdir(parents=True, exist_ok=True)
        _seed_am2_artifacts(directory)

    result = namespace["_bundle_am2_finalize"](parent)

    assert result["ok"] is True
    for directory in (parent, unzipped):
        repair = json.loads((directory / "dialogue-repair-quality-summary.json").read_text(encoding="utf-8"))
        presentation = json.loads((directory / "scenario-graph-presentation-fill-summary.json").read_text(encoding="utf-8"))
        cleanup = json.loads((directory / "scenario-graph-presentation-fill-consistency-cleanup-summary.json").read_text(encoding="utf-8"))
        assert repair["warnings"] == []
        assert presentation["effective_repair_rate_after_bundle_am"] == 0.05
        assert cleanup["ok"] is True


def test_bundle_am2_export_summary_marks_consistency_applied(tmp_path):
    namespace = _load_bundle_am2_namespace()
    parent = tmp_path / "autoplay-output"
    unzipped = parent / "autoplay-campaign-results-unzipped"
    for directory in (parent, unzipped):
        directory.mkdir(parents=True, exist_ok=True)
        _seed_am2_artifacts(directory)
    _write_json(unzipped / "scenario-graph-presentation-fill-export-summary.json", {"ok": True, "presentation_summary_present": True})

    namespace["_bundle_am2_finalize"](parent)
    export = json.loads((unzipped / "scenario-graph-presentation-fill-export-summary.json").read_text(encoding="utf-8"))

    assert export["ok"] is True
    assert export["presentation_summary_present"] is True
    assert export["bundle_am2_summary_consistency_applied"] is True
    assert export["copied_file_count_after_bundle_am2"] >= 1


def test_bundle_am2_manifest_finalizer_runs_pre_and_post_finalize(tmp_path):
    parent = tmp_path / "autoplay-output"
    unzipped = parent / "autoplay-campaign-results-unzipped"
    for directory in (parent, unzipped):
        directory.mkdir(parents=True, exist_ok=True)
        _seed_am2_artifacts(directory)

    def hard_finalizer():
        return {"ok": True, "hard_finalized": True}

    namespace = _load_bundle_am2_namespace({"_manifest_hard_finalize_latest": hard_finalizer, "RESULT_DIR_FOR_TEST": str(parent)})
    result = namespace["_manifest_hard_finalize_latest"]()

    assert result["ok"] is True
    assert namespace["BUNDLE_AM2_PREFINALIZE_RESULT"]["root_count"] >= 1
    assert namespace["BUNDLE_AM2_POSTFINALIZE_RESULT"]["root_count"] >= 1
    presentation = json.loads((unzipped / "scenario-graph-presentation-fill-summary.json").read_text(encoding="utf-8"))
    assert presentation["effective_repair_rate_after_bundle_am"] == 0.05


def test_bundle_am2_write_text_wrapper_triggers_cleanup(tmp_path):
    _load_bundle_am2_namespace()
    parent = tmp_path / "autoplay-output"
    unzipped = parent / "autoplay-campaign-results-unzipped"
    for directory in (parent, unzipped):
        directory.mkdir(parents=True, exist_ok=True)
        _seed_am2_artifacts(directory)

    (unzipped / "quality-gate-summary.json").write_text(json.dumps({"ok": True}), encoding="utf-8")

    presentation = json.loads((unzipped / "scenario-graph-presentation-fill-summary.json").read_text(encoding="utf-8"))
    repair = json.loads((unzipped / "dialogue-repair-quality-summary.json").read_text(encoding="utf-8"))
    assert presentation["effective_repair_rate_after_bundle_am"] == 0.05
    assert repair["warnings"] == []
