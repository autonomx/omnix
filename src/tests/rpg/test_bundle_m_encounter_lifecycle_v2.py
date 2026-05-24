from __future__ import annotations

import json
from pathlib import Path


_FRAGMENT = (
    Path(__file__).resolve().parent
    / "autoplay_llm_campaign_parts"
    / "zz_bundle_m_encounter_lifecycle_v2.pyfrag"
)


def _load_bundle_m_namespace():
    namespace = {"__name__": "_bundle_m_encounter_lifecycle_v2_test"}
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), namespace, namespace)
    return namespace


def test_bundle_m_model_exposes_lifecycle_actions_rules_and_contract():
    namespace = _load_bundle_m_namespace()
    model = namespace["_BUNDLE_M_MODEL"]

    assert model["format_version"] == "bundle_m_encounter_lifecycle_v2_model_v1"
    assert len(model["participant_roles"]) >= 5
    assert len(model["round_phases"]) >= 7
    assert len(model["action_catalog"]) >= 8
    assert len(model["resolution_rules"]) >= 5
    assert len(model["outcome_states"]) >= 5
    assert len(model["recovery_hooks"]) >= 5
    assert namespace["_bundle_m_rule_ids_unique"](model["action_catalog"]) is True
    assert namespace["_bundle_m_rule_ids_unique"](model["resolution_rules"]) is True
    assert model["determinism_contract"]["authoritative_state_required"] is True
    assert model["determinism_contract"]["stable_participant_order"] is True
    assert model["determinism_contract"]["single_resolution_per_round"] is True
    assert model["determinism_contract"]["llm_may_describe_but_not_change_outcome"] is True
    assert model["determinism_contract"]["bounded_recovery_hooks"] is True


def test_bundle_m_gate_passes_for_valid_model():
    namespace = _load_bundle_m_namespace()
    result = namespace["_bundle_m_evaluate_encounter_lifecycle_v2"](
        {"encounter-lifecycle-summary.json": {"encounter_count": 2}}
    )

    assert result["format_version"] == "bundle_m_encounter_lifecycle_v2_summary_v1"
    assert result["source"] == "bundle_m_encounter_lifecycle_v2"
    assert result["ok"] is True
    assert result["advisory_only"] is True
    assert result["advisory_failures"] == []
    assert result["checks"]["participant_roles_present"] is True
    assert result["checks"]["round_phases_present"] is True
    assert result["checks"]["action_catalog_present"] is True
    assert result["checks"]["action_ids_unique"] is True
    assert result["checks"]["resolution_rules_present"] is True
    assert result["checks"]["resolution_rule_ids_unique"] is True
    assert result["checks"]["outcome_states_present"] is True
    assert result["checks"]["recovery_hooks_present"] is True
    assert result["checks"]["determinism_contract_present"] is True
    assert result["checks"]["single_resolution_contract_present"] is True
    assert result["metrics"]["existing_encounter_count"] == 2
    assert result["recommended_next_step"] == "wire_encounter_lifecycle_v2_into_runtime"


def test_bundle_m_gate_reports_duplicate_action_ids_without_raising():
    namespace = _load_bundle_m_namespace()
    model = namespace["_BUNDLE_M_MODEL"]
    original_actions = list(model["action_catalog"])
    try:
        model["action_catalog"] = [
            {"id": "duplicate", "phase": "choose", "bounded": True},
            {"id": "duplicate", "phase": "choose", "bounded": True},
        ]
        result = namespace["_bundle_m_evaluate_encounter_lifecycle_v2"]({})
        assert result["ok"] is False
        assert "action_catalog_present" in result["advisory_failures"]
        assert "action_ids_unique" in result["advisory_failures"]
        assert result["recommended_next_step"] == "fix_encounter_lifecycle_v2_advisory_failures"
    finally:
        model["action_catalog"] = original_actions


def test_bundle_m_writes_summary_when_relevant_artifact_is_exported(tmp_path):
    namespace = _load_bundle_m_namespace()
    original_write_text = namespace["_BUNDLE_M_ORIGINAL_PATH_WRITE_TEXT"]
    try:
        (tmp_path / "summary.json").write_text(json.dumps({"turn_count": 100}), encoding="utf-8")

        summary_path = tmp_path / "encounter-lifecycle-v2-summary.json"
        assert summary_path.exists()
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        assert summary["ok"] is True
        assert summary["checks"]["round_phases_present"] is True
        assert summary["checks"]["determinism_contract_present"] is True
        assert summary["metrics"]["action_count"] >= 8
    finally:
        Path.write_text = original_write_text
