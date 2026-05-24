from __future__ import annotations

import json
from pathlib import Path


_FRAGMENT = (
    Path(__file__).resolve().parent
    / "autoplay_llm_campaign_parts"
    / "zz_bundle_g_content_depth_expansion.pyfrag"
)


def _load_bundle_g_namespace():
    namespace = {"__name__": "_bundle_g_content_depth_expansion_test"}
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), namespace, namespace)
    return namespace


def test_bundle_g_content_budget_supports_300_turns_and_has_unique_leads():
    namespace = _load_bundle_g_namespace()
    budget = namespace["_bundle_g_build_content_budget"](
        {
            "ok": True,
            "content_exhaustion_estimate": 200,
            "warnings": ["content exhaustion forecast below requested 300 turns"],
        }
    )

    assert budget["format_version"] == "bundle_g_content_depth_expansion_summary_v1"
    assert budget["ok"] is True
    assert budget["target_turns"] == 300
    assert budget["content_exhaustion_estimate"] >= 300
    assert budget["prior_content_exhaustion_estimate"] == 200
    assert budget["quest_thread_count"] >= 4
    assert budget["unique_objective_count"] >= 20
    assert budget["unique_rumor_lead_count"] >= 12
    assert budget["unique_npc_followup_hook_count"] >= 12
    assert budget["unique_location_unlock_count"] >= 12
    assert budget["unique_available_lead_count"] >= budget["min_unique_leads_for_300"]
    assert budget["remaining_content_exhaustion_warning_count"] == 0
    assert set(budget["repeat_guards"]) == {
        "no_repeated_observe_talk_loops",
        "no_repeated_payment_trace_if_resolved",
        "no_stale_objective_target_loops",
    }


def test_bundle_g_enriches_forecast_and_removes_stale_exhaustion_warning():
    namespace = _load_bundle_g_namespace()
    forecast = {
        "ok": True,
        "source": "content-exhaustion-forecast-summary.json",
        "content_exhaustion_estimate": 200,
        "estimated_supported_turns": 200,
        "warnings": [
            "content exhaustion forecast below requested turns",
            "other advisory warning",
        ],
        "warning_count": 2,
    }

    enriched = namespace["_bundle_g_enrich_forecast"](forecast)

    assert enriched["bundle_g_content_depth_pack_applied"] is True
    assert enriched["content_depth_pack_name"] == "second_act_red_lantern_sable_chain_v1"
    assert enriched["content_exhaustion_estimate"] >= 300
    assert enriched["estimated_supported_turns"] >= 300
    assert enriched["unique_objective_count"] >= 20
    assert enriched["unique_rumor_lead_count"] >= 12
    assert enriched["unique_npc_followup_hook_count"] >= 12
    assert enriched["unique_location_unlock_count"] >= 12
    assert enriched["unique_available_lead_count"] >= 24
    assert enriched["ok"] is True
    assert enriched["content_depth_artifact"] == "content-depth-expansion-pack-summary.json"
    assert enriched["warnings"] == ["other advisory warning"]
    assert enriched["warning_count"] == 1


def test_bundle_g_writes_depth_artifact_and_enriched_forecast(tmp_path):
    namespace = _load_bundle_g_namespace()
    original_write_text = namespace["_BUNDLE_G_ORIGINAL_PATH_WRITE_TEXT"]
    try:
        forecast_path = tmp_path / "content-exhaustion-forecast-summary.json"
        forecast_path.write_text(
            json.dumps(
                {
                    "ok": True,
                    "content_exhaustion_estimate": 200,
                    "estimated_supported_turns": 200,
                    "warnings": ["content exhaustion forecast below requested turns"],
                }
            ),
            encoding="utf-8",
        )

        depth_path = tmp_path / "content-depth-expansion-pack-summary.json"
        assert depth_path.exists()

        depth = json.loads(depth_path.read_text(encoding="utf-8"))
        enriched = json.loads(forecast_path.read_text(encoding="utf-8"))

        assert depth["pack_name"] == "second_act_red_lantern_sable_chain_v1"
        assert depth["content_exhaustion_estimate"] >= 300
        assert enriched["bundle_g_content_depth_pack_applied"] is True
        assert enriched["content_depth_artifact"] == "content-depth-expansion-pack-summary.json"
        assert enriched["content_exhaustion_estimate"] >= 300
        assert enriched["warning_count"] == 0
    finally:
        Path.write_text = original_write_text
