from __future__ import annotations

import json
from pathlib import Path


_FRAGMENT = (
    Path(__file__).resolve().parent
    / "autoplay_llm_campaign_parts"
    / "zzzz_bundle_af_preflight_quality_gate_manifest_compat.pyfrag"
)


def _load_bundle_af_namespace():
    namespace = {"__name__": "_bundle_af_preflight_quality_gate_manifest_compat_test"}
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), namespace, namespace)
    return namespace


def _write_smoke_inputs(tmp_path: Path):
    (tmp_path / "summary.json").write_text(
        json.dumps({"requested_turns": 150, "completed_turns": 150, "runtime_error_count": 0}),
        encoding="utf-8",
    )
    (tmp_path / "progress-quality-summary.json").write_text(
        json.dumps({"ok": True, "player_agent_fallback_rate": 0.10, "meaningful_progress_rate": 0.25}),
        encoding="utf-8",
    )
    (tmp_path / "performance-summary.json").write_text(
        json.dumps({"ok": True, "blocking_turn_p95_seconds": 7.5}),
        encoding="utf-8",
    )
    (tmp_path / "one-thousand-turn-progression-graph-summary.json").write_text(
        json.dumps({"ok": True, "progression_graph_ready": True}),
        encoding="utf-8",
    )


def test_bundle_af_builds_quality_gate_summary_from_smoke_artifacts(tmp_path):
    namespace = _load_bundle_af_namespace()
    _write_smoke_inputs(tmp_path)

    summary = namespace["_bundle_af_build_quality_gate_summary"](tmp_path)

    assert summary["format_version"] == "bundle_af_quality_gate_summary_compat_v1"
    assert summary["source"] == "bundle_af_preflight_quality_gate_manifest_compat"
    assert summary["ok"] is True
    assert summary["advisory_only"] is True
    assert summary["compatibility_summary"] is True
    assert summary["checks"]["run_summary_available"] is True
    assert summary["checks"]["runtime_error_budget_ok"] is True
    assert summary["checks"]["progression_graph_ready_or_not_required"] is True
    assert summary["metrics"]["requested_turns"] == 150
    assert summary["metrics"]["completed_turns"] == 150
    assert summary["metrics"]["player_agent_fallback_rate"] == 0.10
    assert summary["metrics"]["meaningful_progress_rate"] == 0.25
    assert summary["recommended_next_step"] == "review_preflight_smoke_artifacts"


def test_bundle_af_quality_gate_summary_reports_runtime_error_failures(tmp_path):
    namespace = _load_bundle_af_namespace()
    (tmp_path / "summary.json").write_text(
        json.dumps({"requested_turns": 150, "completed_turns": 149, "runtime_error_count": 1}),
        encoding="utf-8",
    )

    summary = namespace["_bundle_af_build_quality_gate_summary"](tmp_path)

    assert summary["ok"] is False
    assert "runtime_error_budget_ok" in summary["advisory_failures"]
    assert summary["recommended_next_step"] == "review_quality_gate_compat_failures"


def test_bundle_af_writes_quality_gate_summary_when_core_artifacts_are_exported(tmp_path):
    namespace = _load_bundle_af_namespace()
    original_write_text = namespace["_BUNDLE_AF_ORIGINAL_PATH_WRITE_TEXT"]
    try:
        _write_smoke_inputs(tmp_path)

        quality_path = tmp_path / "quality-gate-summary.json"
        assert quality_path.exists()
        quality = json.loads(quality_path.read_text(encoding="utf-8"))
        assert quality["ok"] is True
        assert quality["compatibility_summary"] is True
        assert quality["metrics"]["completed_turns"] == 150
    finally:
        Path.write_text = original_write_text


def test_bundle_af_stabilizes_file_for_atexit_candidates():
    namespace = _load_bundle_af_namespace()

    assert "__file__" in namespace
    assert str(namespace["__file__"]).endswith("src\\tests\\rpg\\autoplay_llm_campaign.py") or str(namespace["__file__"]).endswith("src/tests/rpg/autoplay_llm_campaign.py")
