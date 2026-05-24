from __future__ import annotations

import json
from pathlib import Path


_FRAGMENT = (
    Path(__file__).resolve().parent
    / "autoplay_llm_campaign_parts"
    / "zz_bundle_j_economy_resource_pressure_v2.pyfrag"
)


def _load_bundle_j_namespace():
    namespace = {"__name__": "_bundle_j_economy_resource_pressure_v2_test"}
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), namespace, namespace)
    return namespace


def _base_economy_payload():
    return {
        "ok": True,
        "source": "economy-resource-pressure-summary.json",
        "total_earned": 22,
        "total_spent": 9,
        "unpaid_count": 1,
        "blocked_relief_count": 0,
        "survival_intervention_count": 1,
        "resource_pressure_ok": True,
    }


def test_bundle_j_service_catalog_and_merchant_refresh_are_expanded():
    namespace = _load_bundle_j_namespace()
    catalog = namespace["_BUNDLE_J_SERVICE_CATALOG"]
    merchant = namespace["_BUNDLE_J_MERCHANT_REFRESH"]
    rules = namespace["_BUNDLE_J_RESOURCE_PRESSURE_RULES"]

    service_categories = namespace["_bundle_j_service_categories"]()
    assert len(catalog["services"]) >= 10
    assert {"lodging", "meal", "drink", "travel_supply", "repair", "guide", "rumor_service"}.issubset(service_categories)
    assert len(merchant["stock_by_location"]) >= 3
    assert namespace["_bundle_j_stock_item_count"]() >= 12
    assert "scarcity_surcharge" in merchant["price_modifiers"]
    assert "faction_pressure_surcharge" in merchant["price_modifiers"]
    assert len(rules["pressure_rules"]) >= 5
    assert rules["anti_spam_policy"]["cooldown_required"] is True
    assert rules["grounding_contract"]["no_reward_payment_hallucination"] is True
    assert rules["grounding_contract"]["payments_require_authoritative_transaction"] is True


def test_bundle_j_economy_gate_passes_for_bounded_pressure():
    namespace = _load_bundle_j_namespace()
    result = namespace["_bundle_j_evaluate_economy_resource_pressure_v2"](
        {"economy-resource-pressure-summary.json": _base_economy_payload()}
    )

    assert result["format_version"] == "bundle_j_economy_resource_pressure_v2_summary_v1"
    assert result["ok"] is True
    assert result["advisory_only"] is True
    assert result["advisory_failures"] == []
    assert result["checks"]["service_catalog_expanded"] is True
    assert result["checks"]["lodging_meal_travel_repair_guide_services_present"] is True
    assert result["checks"]["merchant_refresh_rules_present"] is True
    assert result["checks"]["price_variance_rules_present"] is True
    assert result["checks"]["resource_pressure_rules_present"] is True
    assert result["checks"]["unpaid_debt_bounded"] is True
    assert result["checks"]["survival_intervention_bounded"] is True
    assert result["checks"]["repetitive_pressure_spam_bounded"] is True
    assert result["checks"]["reward_payment_grounding_contract_present"] is True
    assert result["checks"]["anti_spam_policy_present"] is True
    assert result["metrics"]["service_count"] >= 10
    assert result["metrics"]["merchant_stock_item_count"] >= 12
    assert result["recommended_next_step"] == "wire_economy_resource_pressure_v2_into_runtime"


def test_bundle_j_gate_reports_unbounded_debt_and_spam_as_advisory_failures():
    namespace = _load_bundle_j_namespace()
    payload = _base_economy_payload()
    payload["unpaid_count"] = 99
    payload["survival_intervention_count"] = 99
    payload["repetitive_pressure_event_count"] = 99

    result = namespace["_bundle_j_evaluate_economy_resource_pressure_v2"](
        {"economy-resource-pressure-summary.json": payload}
    )

    assert result["ok"] is False
    assert result["advisory_only"] is True
    assert set(result["advisory_failures"]) == {
        "unpaid_debt_bounded",
        "survival_intervention_bounded",
        "repetitive_pressure_spam_bounded",
    }
    assert result["recommended_next_step"] == "fix_economy_resource_pressure_v2_advisory_failures"


def test_bundle_j_enriches_existing_economy_sidecar(tmp_path):
    namespace = _load_bundle_j_namespace()
    original_write_text = namespace["_BUNDLE_J_ORIGINAL_PATH_WRITE_TEXT"]
    try:
        path = tmp_path / "economy-resource-pressure-summary.json"
        path.write_text(json.dumps(_base_economy_payload()), encoding="utf-8")

        enriched = json.loads(path.read_text(encoding="utf-8"))
        summary = json.loads((tmp_path / "economy-resource-pressure-v2-summary.json").read_text(encoding="utf-8"))

        assert enriched["bundle_j_economy_resource_pressure_v2_applied"] is True
        assert enriched["economy_resource_pressure_v2_artifact"] == "economy-resource-pressure-v2-summary.json"
        assert enriched["economy_resource_pressure_v2_ok"] is True
        assert enriched["service_count"] >= 10
        assert enriched["merchant_stock_item_count"] >= 12
        assert enriched["pressure_rule_count"] >= 5
        assert enriched["resource_pressure_ok"] is True
        assert enriched["reward_payment_grounding_contract_present"] is True
        assert enriched["anti_spam_policy_present"] is True
        assert summary["ok"] is True
        assert summary["metrics"]["currency_delta"] == 13
    finally:
        Path.write_text = original_write_text


def test_bundle_j_writes_summary_when_relevant_artifacts_are_exported(tmp_path):
    namespace = _load_bundle_j_namespace()
    original_write_text = namespace["_BUNDLE_J_ORIGINAL_PATH_WRITE_TEXT"]
    try:
        (tmp_path / "summary.json").write_text(json.dumps({"turn_count": 100}), encoding="utf-8")

        summary_path = tmp_path / "economy-resource-pressure-v2-summary.json"
        assert summary_path.exists()
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        assert summary["source"] == "bundle_j_economy_resource_pressure_v2"
        assert summary["ok"] is True
        assert summary["checks"]["service_catalog_expanded"] is True
        assert summary["checks"]["merchant_refresh_rules_present"] is True
        assert summary["checks"]["reward_payment_grounding_contract_present"] is True
    finally:
        Path.write_text = original_write_text


def test_bundle_j_injects_report_section_with_collapsed_raw_json(tmp_path):
    namespace = _load_bundle_j_namespace()
    original_write_text = namespace["_BUNDLE_J_ORIGINAL_PATH_WRITE_TEXT"]
    try:
        (tmp_path / "economy-resource-pressure-summary.json").write_text(
            json.dumps(_base_economy_payload()),
            encoding="utf-8",
        )
        report_path = tmp_path / "autoplay-campaign-report.html"
        report_path.write_text(
            "<html><body><h1>Autoplay Campaign Report</h1><main><p>Body</p></main></body></html>",
            encoding="utf-8",
        )
        rendered = report_path.read_text(encoding="utf-8")

        assert 'id="bundle-j-economy-resource-pressure-v2"' in rendered
        assert "Economy / Resource Pressure v2" in rendered
        assert "service_count" in rendered
        assert "reward_payment_grounding_contract_present" in rendered
        assert '<details class="bundle-j-raw-details">' in rendered
        raw_start = rendered.index('<details class="bundle-j-raw-details">')
        raw_open = rendered[raw_start : rendered.index(">", raw_start) + 1]
        assert " open" not in raw_open
        assert "<p>Body</p>" in rendered
    finally:
        Path.write_text = original_write_text
