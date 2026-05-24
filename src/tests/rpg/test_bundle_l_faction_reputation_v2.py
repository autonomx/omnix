from __future__ import annotations

import json
from pathlib import Path


_FRAGMENT = (
    Path(__file__).resolve().parent
    / "autoplay_llm_campaign_parts"
    / "zz_bundle_l_faction_reputation_v2.pyfrag"
)


def _load_bundle_l_namespace():
    namespace = {"__name__": "_bundle_l_faction_reputation_v2_test"}
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), namespace, namespace)
    return namespace


def test_bundle_l_model_exposes_factions_axes_rules_and_contract():
    namespace = _load_bundle_l_namespace()
    model = namespace["_BUNDLE_L_MODEL"]

    assert model["format_version"] == "bundle_l_faction_reputation_v2_model_v1"
    assert len(model["factions"]) >= 4
    assert len(model["standing_axes"]) >= 4
    assert len(model["consequence_rules"]) >= 8
    assert namespace["_bundle_l_rule_ids_unique"](model) is True
    assert namespace["_bundle_l_rules_reference_known_factions"](model) is True
    assert model["determinism_contract"]["requires_authoritative_trigger"] is True
    assert model["determinism_contract"]["clamps_standing_to_bounds"] is True
    assert model["determinism_contract"]["cooldown_prevents_reputation_spam"] is True
    assert model["determinism_contract"]["llm_may_describe_but_not_change_standing"] is True

    for faction in model["factions"].values():
        assert faction["display_name"]
        assert faction["starting_standing"]
        assert faction["standing_bounds"]["min"] < faction["standing_bounds"]["max"]
        assert faction["access_unlocks"]
        assert faction["access_blocks"]


def test_bundle_l_gate_passes_for_valid_model():
    namespace = _load_bundle_l_namespace()
    result = namespace["_bundle_l_evaluate_faction_reputation_v2"](
        {"faction-reputation-summary.json": {"consequence_count": 3}}
    )

    assert result["format_version"] == "bundle_l_faction_reputation_v2_summary_v1"
    assert result["source"] == "bundle_l_faction_reputation_v2"
    assert result["ok"] is True
    assert result["advisory_only"] is True
    assert result["advisory_failures"] == []
    assert result["checks"]["faction_catalog_present"] is True
    assert result["checks"]["standing_axes_present"] is True
    assert result["checks"]["consequence_rules_present"] is True
    assert result["checks"]["rule_ids_unique"] is True
    assert result["checks"]["rules_reference_known_factions_and_axes"] is True
    assert result["checks"]["access_unlocks_and_blocks_present"] is True
    assert result["checks"]["determinism_contract_present"] is True
    assert result["checks"]["cooldown_contract_present"] is True
    assert result["metrics"]["existing_consequence_count"] == 3
    assert result["recommended_next_step"] == "wire_faction_reputation_v2_into_runtime"


def test_bundle_l_gate_reports_rule_reference_failures_without_raising():
    namespace = _load_bundle_l_namespace()
    model = namespace["_BUNDLE_L_MODEL"]
    original_rules = list(model["consequence_rules"])
    try:
        model["consequence_rules"] = [
            {"id": "bad_rule", "trigger": "x", "faction": "missing", "axis": "trust", "delta": 1, "cooldown_turns": 1}
        ]
        result = namespace["_bundle_l_evaluate_faction_reputation_v2"]({})
        assert result["ok"] is False
        assert "consequence_rules_present" in result["advisory_failures"]
        assert "rules_reference_known_factions_and_axes" in result["advisory_failures"]
        assert result["recommended_next_step"] == "fix_faction_reputation_v2_advisory_failures"
    finally:
        model["consequence_rules"] = original_rules


def test_bundle_l_writes_summary_when_relevant_artifact_is_exported(tmp_path):
    namespace = _load_bundle_l_namespace()
    original_write_text = namespace["_BUNDLE_L_ORIGINAL_PATH_WRITE_TEXT"]
    try:
        (tmp_path / "summary.json").write_text(json.dumps({"turn_count": 100}), encoding="utf-8")

        summary_path = tmp_path / "faction-reputation-v2-summary.json"
        assert summary_path.exists()
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        assert summary["ok"] is True
        assert summary["checks"]["faction_catalog_present"] is True
        assert summary["checks"]["determinism_contract_present"] is True
        assert summary["metrics"]["faction_count"] >= 4
    finally:
        Path.write_text = original_write_text
