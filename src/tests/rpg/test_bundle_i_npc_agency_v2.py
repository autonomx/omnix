from __future__ import annotations

import json
from pathlib import Path


_FRAGMENT = (
    Path(__file__).resolve().parent
    / "autoplay_llm_campaign_parts"
    / "zz_bundle_i_npc_agency_v2.pyfrag"
)


def _load_bundle_i_namespace():
    namespace = {"__name__": "_bundle_i_npc_agency_v2_test"}
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), namespace, namespace)
    return namespace


def _base_agency_payload():
    return {
        "ok": True,
        "source": "npc-agency-schedule-summary.json",
        "npc_count": 2,
        "agency_event_count": 2,
    }


def test_bundle_i_model_exposes_schedules_goals_and_bounded_actions():
    namespace = _load_bundle_i_namespace()
    model = namespace["_BUNDLE_I_NPC_AGENCY_MODEL"]
    allowed = set(namespace["_BUNDLE_I_ALLOWED_ACTION_TYPES"])

    assert model["format_version"] == "bundle_i_npc_agency_v2_model_v1"
    assert len(model["npcs"]) >= 4
    assert namespace["_bundle_i_model_schedule_entry_count"](model) >= len(model["npcs"]) * 4
    assert namespace["_bundle_i_model_goal_count"](model) == len(model["npcs"])
    assert namespace["_bundle_i_model_bounded_action_count"](model) >= len(model["npcs"]) * 3
    assert namespace["_bundle_i_model_action_types"](model).issubset(allowed)

    for npc in model["npcs"].values():
        assert npc["schedule"]
        assert npc["goal_state"]["short_term_goal"]
        assert npc["goal_state"]["pressure"]
        assert npc["bounded_actions"]
        assert npc["interruption_rules"]


def test_bundle_i_agency_gate_passes_with_projected_events():
    namespace = _load_bundle_i_namespace()
    result = namespace["_bundle_i_evaluate_npc_agency_v2"](
        {"npc-agency-schedule-summary.json": _base_agency_payload()}
    )

    assert result["format_version"] == "bundle_i_npc_agency_v2_summary_v1"
    assert result["ok"] is True
    assert result["advisory_only"] is True
    assert result["advisory_failures"] == []
    assert result["checks"]["schedule_model_present"] is True
    assert result["checks"]["goal_state_present"] is True
    assert result["checks"]["bounded_action_catalog_present"] is True
    assert result["checks"]["only_allowed_bounded_actions"] is True
    assert result["checks"]["meaningful_agency_events_available"] is True
    assert result["checks"]["inspector_projection_available"] is True
    assert result["checks"]["no_environment_memory_pollution_contract"] is True
    assert result["metrics"]["npc_count"] >= 4
    assert result["metrics"]["meaningful_agency_event_count"] >= 6
    assert result["projected_agency_events"]
    assert result["recommended_next_step"] == "wire_npc_agency_v2_into_runtime"


def test_bundle_i_enriches_existing_npc_agency_sidecar(tmp_path):
    namespace = _load_bundle_i_namespace()
    original_write_text = namespace["_BUNDLE_I_ORIGINAL_PATH_WRITE_TEXT"]
    try:
        path = tmp_path / "npc-agency-schedule-summary.json"
        path.write_text(json.dumps(_base_agency_payload()), encoding="utf-8")

        enriched = json.loads(path.read_text(encoding="utf-8"))
        summary = json.loads((tmp_path / "npc-agency-v2-summary.json").read_text(encoding="utf-8"))

        assert enriched["bundle_i_npc_agency_v2_applied"] is True
        assert enriched["npc_agency_v2_artifact"] == "npc-agency-v2-summary.json"
        assert enriched["npc_agency_v2_ok"] is True
        assert enriched["schedule_model_npc_count"] >= 4
        assert enriched["schedule_entry_count"] >= 16
        assert enriched["goal_state_count"] >= 4
        assert enriched["bounded_action_count"] >= 12
        assert enriched["meaningful_agency_event_count"] >= 6
        assert summary["ok"] is True
        assert summary["metrics"]["projected_agency_event_count"] >= 6
    finally:
        Path.write_text = original_write_text


def test_bundle_i_writes_summary_when_relevant_artifacts_are_exported(tmp_path):
    namespace = _load_bundle_i_namespace()
    original_write_text = namespace["_BUNDLE_I_ORIGINAL_PATH_WRITE_TEXT"]
    try:
        (tmp_path / "summary.json").write_text(json.dumps({"turn_count": 100}), encoding="utf-8")

        summary_path = tmp_path / "npc-agency-v2-summary.json"
        assert summary_path.exists()
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        assert summary["source"] == "bundle_i_npc_agency_v2"
        assert summary["ok"] is True
        assert summary["checks"]["schedule_model_present"] is True
        assert summary["checks"]["goal_state_present"] is True
        assert summary["checks"]["bounded_action_catalog_present"] is True
    finally:
        Path.write_text = original_write_text


def test_bundle_i_injects_report_section_with_collapsed_raw_json(tmp_path):
    namespace = _load_bundle_i_namespace()
    original_write_text = namespace["_BUNDLE_I_ORIGINAL_PATH_WRITE_TEXT"]
    try:
        (tmp_path / "npc-agency-schedule-summary.json").write_text(
            json.dumps(_base_agency_payload()),
            encoding="utf-8",
        )
        report_path = tmp_path / "autoplay-campaign-report.html"
        report_path.write_text(
            "<html><body><h1>Autoplay Campaign Report</h1><main><p>Body</p></main></body></html>",
            encoding="utf-8",
        )
        rendered = report_path.read_text(encoding="utf-8")

        assert 'id="bundle-i-npc-agency-v2"' in rendered
        assert "NPC Agency v2: Schedules, Goals, Consequences" in rendered
        assert "schedule_entry_count" in rendered
        assert "meaningful_agency_events_available" in rendered
        assert '<details class="bundle-i-raw-details">' in rendered
        raw_start = rendered.index('<details class="bundle-i-raw-details">')
        raw_open = rendered[raw_start : rendered.index(">", raw_start) + 1]
        assert " open" not in raw_open
        assert "<p>Body</p>" in rendered
    finally:
        Path.write_text = original_write_text
