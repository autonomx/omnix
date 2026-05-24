from __future__ import annotations

import json
from pathlib import Path


_FRAGMENT = (
    Path(__file__).resolve().parent
    / "autoplay_llm_campaign_parts"
    / "zz_bundle_n_story_arc_end_state_v2.pyfrag"
)


def _load_bundle_n_namespace():
    namespace = {"__name__": "_bundle_n_story_arc_end_state_v2_test"}
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), namespace, namespace)
    return namespace


def test_bundle_n_model_exposes_arc_lifecycle_end_state_and_contract():
    namespace = _load_bundle_n_namespace()
    model = namespace["_BUNDLE_N_MODEL"]

    assert model["format_version"] == "bundle_n_story_arc_end_state_v2_model_v1"
    assert len(model["story_arcs"]) >= 4
    assert len(model["arc_states"]) >= 6
    assert len(model["campaign_states"]) >= 6
    assert len(model["pacing_rules"]) >= 4
    assert len(model["end_state_rules"]) >= 5
    assert namespace["_bundle_n_ids_unique"](model["story_arcs"]) is True
    assert namespace["_bundle_n_ids_unique"](model["pacing_rules"]) is True
    assert namespace["_bundle_n_ids_unique"](model["end_state_rules"]) is True
    assert model["determinism_contract"]["arc_progress_requires_authoritative_signal"] is True
    assert model["determinism_contract"]["end_state_uses_structured_flags_only"] is True
    assert model["determinism_contract"]["llm_may_summarize_but_not_resolve_arcs"] is True
    assert model["determinism_contract"]["resolved_arc_becomes_archivable"] is True

    for arc in model["story_arcs"]:
        assert arc["required_signals"]
        assert arc["resolution_conditions"]
        assert arc["end_state_flags"]


def test_bundle_n_gate_passes_for_valid_model_and_bounded_counts():
    namespace = _load_bundle_n_namespace()
    result = namespace["_bundle_n_evaluate_story_arc_end_state_v2"](
        {"story-arc-summary.json": {"resolved_arc_count": 1, "active_arc_count": 3, "unresolved_blocker_count": 2}}
    )

    assert result["format_version"] == "bundle_n_story_arc_end_state_v2_summary_v1"
    assert result["source"] == "bundle_n_story_arc_end_state_v2"
    assert result["ok"] is True
    assert result["advisory_only"] is True
    assert result["advisory_failures"] == []
    assert result["checks"]["story_arc_catalog_present"] is True
    assert result["checks"]["arc_state_machine_present"] is True
    assert result["checks"]["arc_ids_unique"] is True
    assert result["checks"]["pacing_rules_present"] is True
    assert result["checks"]["end_state_rules_present"] is True
    assert result["checks"]["required_signals_present"] is True
    assert result["checks"]["resolution_conditions_present"] is True
    assert result["checks"]["end_state_flags_present"] is True
    assert result["checks"]["active_arc_count_bounded"] is True
    assert result["checks"]["unresolved_blocker_count_bounded"] is True
    assert result["checks"]["determinism_contract_present"] is True
    assert result["metrics"]["resolved_arc_count"] == 1
    assert result["recommended_next_step"] == "wire_story_arc_end_state_v2_into_runtime"


def test_bundle_n_gate_reports_unbounded_arc_counts_without_raising():
    namespace = _load_bundle_n_namespace()
    result = namespace["_bundle_n_evaluate_story_arc_end_state_v2"](
        {"story-arc-summary.json": {"active_arc_count": 99, "unresolved_blocker_count": 99}}
    )

    assert result["ok"] is False
    assert "active_arc_count_bounded" in result["advisory_failures"]
    assert "unresolved_blocker_count_bounded" in result["advisory_failures"]
    assert result["recommended_next_step"] == "fix_story_arc_end_state_v2_advisory_failures"


def test_bundle_n_writes_summary_when_relevant_artifact_is_exported(tmp_path):
    namespace = _load_bundle_n_namespace()
    original_write_text = namespace["_BUNDLE_N_ORIGINAL_PATH_WRITE_TEXT"]
    try:
        (tmp_path / "summary.json").write_text(json.dumps({"turn_count": 100}), encoding="utf-8")

        summary_path = tmp_path / "story-arc-end-state-v2-summary.json"
        assert summary_path.exists()
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        assert summary["ok"] is True
        assert summary["checks"]["story_arc_catalog_present"] is True
        assert summary["checks"]["determinism_contract_present"] is True
        assert summary["metrics"]["story_arc_count"] >= 4
    finally:
        Path.write_text = original_write_text
