from __future__ import annotations

import json
from pathlib import Path


_FRAGMENT = (
    Path(__file__).resolve().parent
    / "autoplay_llm_campaign_parts"
    / "zzzzzzzzzz_bundle_aj_sidecar_reconciliation_and_truth_finalization.pyfrag"
)


def _load_bundle_aj_namespace(extra_globals=None):
    namespace = {"__name__": "_bundle_aj_sidecar_reconciliation_test"}
    if extra_globals:
        namespace.update(extra_globals)
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), namespace, namespace)
    return namespace


def _write_json(path: Path, payload: dict):
    path.write_bytes((json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def test_bundle_aj_prefers_unzipped_complete_sidecars_over_stale_parent_copies(tmp_path):
    namespace = _load_bundle_aj_namespace()
    parent = tmp_path
    unzipped = parent / "autoplay-campaign-results-unzipped"
    unzipped.mkdir()

    _write_json(
        parent / "one-thousand-turn-live-result-summary.json",
        {
            "format_version": "bundle_t_live_1000_result_summary_v1",
            "ok": False,
            "source": "parent_stale",
            "metrics": {"completed_turns": 0, "blocking_turn_p95_seconds": 0.0},
            "advisory_failures": ["zipped_results_artifact_present"],
        },
    )
    _write_json(
        unzipped / "one-thousand-turn-live-result-summary.json",
        {
            "format_version": "bundle_t_live_1000_result_summary_v1",
            "ok": False,
            "source": "unzipped_complete",
            "metrics": {"completed_turns": 100, "blocking_turn_p95_seconds": 9.38443},
            "advisory_failures": ["preflight_promoted_live_run"],
        },
    )

    summary = namespace["_bundle_aj_reconcile_sidecars"](parent)
    parent_live = json.loads((parent / "one-thousand-turn-live-result-summary.json").read_text(encoding="utf-8"))
    unzipped_live = json.loads((unzipped / "one-thousand-turn-live-result-summary.json").read_text(encoding="utf-8"))

    assert summary["ok"] is True
    assert parent_live["source"] == "unzipped_complete"
    assert parent_live["metrics"]["completed_turns"] == 100
    assert unzipped_live["source"] == "unzipped_complete"


def test_bundle_aj_rebuilds_missing_aggregator_dashboard_from_available_aggregator(tmp_path):
    namespace = _load_bundle_aj_namespace()
    parent = tmp_path
    unzipped = parent / "autoplay-campaign-results-unzipped"
    unzipped.mkdir()

    _write_json(
        parent / "one-thousand-turn-readiness-dashboard-summary.json",
        {
            "format_version": "bundle_p_1000_turn_readiness_dashboard_summary_v1",
            "ok": False,
            "status_label": "Missing Aggregator",
            "recommended_next_step": "write_1000_turn_readiness_aggregator_first",
        },
    )
    _write_json(
        unzipped / "one-thousand-turn-readiness-aggregator-summary.json",
        {
            "format_version": "bundle_o_1000_turn_readiness_aggregator_summary_v1",
            "ok": False,
            "ready_for_1000_turn_preflight": False,
            "ready_for_live_1000_turn_run": False,
            "required_gate_count": 9,
            "present_required_gate_count": 9,
            "passing_required_gate_count": 8,
            "failing_required_gates": ["bundle_ai_truth:dialogue_repair_rate_ok"],
            "recommended_next_step": "fix_progression_density_and_repair_rate_before_1000_turn_preflight",
        },
    )

    namespace["_bundle_aj_reconcile_sidecars"](parent)
    parent_dashboard = json.loads((parent / "one-thousand-turn-readiness-dashboard-summary.json").read_text(encoding="utf-8"))
    unzipped_dashboard = json.loads((unzipped / "one-thousand-turn-readiness-dashboard-summary.json").read_text(encoding="utf-8"))

    assert parent_dashboard["status_label"] == "Readiness Blocked"
    assert parent_dashboard["ready_for_1000_turn_preflight"] is False
    assert parent_dashboard["failing_required_gates"] == ["bundle_ai_truth:dialogue_repair_rate_ok"]
    assert unzipped_dashboard["status_label"] == "Readiness Blocked"


def test_bundle_aj_writes_truth_summary_to_parent_and_unzipped_and_patches_aggregator(tmp_path):
    def truth_builder(result_dir):
        return {
            "format_version": "bundle_ai_readiness_truth_summary_v1",
            "source": "test_truth_builder",
            "ok": False,
            "ready_for_1000_turn_preflight": False,
            "ready_for_live_1000_turn_run": False,
            "truth_blocking_gates": ["dialogue_repair_rate_ok"],
            "recommended_next_step": "fix_progression_density_and_repair_rate_before_1000_turn_preflight",
        }

    def patcher(result_dir, truth):
        path = Path(result_dir) / "one-thousand-turn-readiness-aggregator-summary.json"
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["ok"] = False
            payload["ready_for_1000_turn_preflight"] = False
            payload["ready_for_live_1000_turn_run"] = False
            payload["bundle_ai_truth_overrides_applied"] = True
            payload["bundle_ai_truth_blocking_gates"] = truth["truth_blocking_gates"]
            _write_json(path, payload)

    namespace = _load_bundle_aj_namespace({"_bundle_ai_readiness_truth": truth_builder, "_bundle_ai_patch_aggregator_with_truth": patcher})
    parent = tmp_path
    unzipped = parent / "autoplay-campaign-results-unzipped"
    unzipped.mkdir()
    for directory in (parent, unzipped):
        _write_json(
            directory / "one-thousand-turn-readiness-aggregator-summary.json",
            {"ok": True, "ready_for_1000_turn_preflight": True, "ready_for_live_1000_turn_run": True},
        )

    namespace["_bundle_aj_reconcile_sidecars"](parent)

    for directory in (parent, unzipped):
        truth = json.loads((directory / "one-thousand-turn-readiness-truth-summary.json").read_text(encoding="utf-8"))
        aggregator = json.loads((directory / "one-thousand-turn-readiness-aggregator-summary.json").read_text(encoding="utf-8"))
        assert truth["source"] == "test_truth_builder"
        assert truth["ready_for_1000_turn_preflight"] is False
        assert aggregator["bundle_ai_truth_overrides_applied"] is True
        assert aggregator["ready_for_live_1000_turn_run"] is False


def test_bundle_aj_rebuilds_release_and_artifact_index_dashboards(tmp_path):
    namespace = _load_bundle_aj_namespace()
    parent = tmp_path
    unzipped = parent / "autoplay-campaign-results-unzipped"
    unzipped.mkdir()

    _write_json(
        unzipped / "one-thousand-turn-live-result-summary.json",
        {
            "ok": False,
            "release_candidate_ready": False,
            "advisory_failures": ["preflight_promoted_live_run"],
            "checks": {"artifact_manifest_ok": True, "preflight_promoted_live_run": False},
            "metrics": {"completed_turns": 100},
            "recommended_next_step": "fix_live_1000_result_failures_before_release_candidate",
        },
    )
    _write_json(
        unzipped / "one-thousand-turn-release-candidate-artifact-index.json",
        {
            "ok": False,
            "archive_index_ready": False,
            "advisory_failures": ["required_archive_artifacts_present"],
            "missing_required_archive_artifacts": ["one-thousand-turn-release-candidate-runbook.md"],
            "archive_digest_sha256": "abc123",
            "metrics": {"tracked_file_count": 10, "present_tracked_file_count": 6, "total_present_bytes": 42},
            "recommended_next_step": "complete_release_candidate_archive_artifacts",
        },
    )

    namespace["_bundle_aj_reconcile_sidecars"](parent)

    release_dashboard = json.loads((parent / "one-thousand-turn-release-candidate-dashboard-summary.json").read_text(encoding="utf-8"))
    index_dashboard = json.loads((parent / "one-thousand-turn-release-candidate-artifact-index-dashboard-summary.json").read_text(encoding="utf-8"))
    assert release_dashboard["status_label"] == "Release Candidate Blocked"
    assert release_dashboard["check_count"] == 2
    assert release_dashboard["failing_check_count"] == 1
    assert index_dashboard["status_label"] == "Archive Index Blocked"
    assert index_dashboard["tracked_completion_percent"] == 60.0
    assert index_dashboard["missing_required_archive_artifacts"] == ["one-thousand-turn-release-candidate-runbook.md"]


def test_bundle_aj_write_text_wrapper_triggers_reconciliation(tmp_path):
    namespace = _load_bundle_aj_namespace()
    parent = tmp_path
    unzipped = parent / "autoplay-campaign-results-unzipped"
    unzipped.mkdir()
    _write_json(
        unzipped / "one-thousand-turn-live-result-summary.json",
        {"ok": False, "source": "unzipped_complete", "metrics": {"completed_turns": 100}},
    )

    (parent / "autoplay-health.json").write_text(json.dumps({"ok": True}), encoding="utf-8")

    assert (parent / "one-thousand-turn-sidecar-reconciliation-summary.json").exists()
    parent_live = json.loads((parent / "one-thousand-turn-live-result-summary.json").read_text(encoding="utf-8"))
    assert parent_live["source"] == "unzipped_complete"
