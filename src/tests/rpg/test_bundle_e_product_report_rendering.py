from __future__ import annotations

import json
from pathlib import Path


_FRAGMENT = (
    Path(__file__).resolve().parent
    / "autoplay_llm_campaign_parts"
    / "zz_bundle_e_product_report_rendering.pyfrag"
)


def _load_bundle_e_namespace():
    namespace = {"__name__": "_bundle_e_product_report_rendering_test"}
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), namespace, namespace)
    return namespace


def _write_bundle_e_artifacts(result_dir: Path) -> None:
    payloads = {
        "survival-exit-criteria-summary.json": {
            "ok": True,
            "source": "survival-exit-criteria-summary.json",
            "turn_count": 100,
            "completed_turns": 100,
            "hard_failure_count": 0,
        },
        "transcript-payload-budget-summary.json": {
            "ok": True,
            "source": "transcript-payload-budget-summary.json",
            "total_bytes": 12000,
            "projected_1000_turn_bytes": 120000,
            "budget_ok": True,
        },
        "long-run-dry-run-projection-summary.json": {
            "ok": True,
            "source": "long-run-dry-run-projection-summary.json",
            "projected_turns": 300,
            "ready_for_300_turns": True,
        },
        "content-exhaustion-forecast-summary.json": {
            "ok": True,
            "source": "content-exhaustion-forecast-summary.json",
            "content_exhaustion_estimate": 300,
            "warning_count": 0,
        },
        "npc-agency-schedule-summary.json": {
            "ok": True,
            "source": "npc-agency-schedule-summary.json",
            "npc_count": 4,
            "agency_event_count": 7,
        },
        "economy-resource-pressure-summary.json": {
            "ok": True,
            "source": "economy-resource-pressure-summary.json",
            "total_earned": 12,
            "total_spent": 4,
            "resource_pressure_ok": True,
        },
        "artifact-manifest-digest.json": {
            "ok": True,
            "source": "bundle_d3_artifact_manifest_digest",
            "manifest_byte_size": 1993633,
            "manifest_sha256": "abc123",
            "embedded_artifact_count": 8,
            "zip_manifest_valid_count": 1,
            "invariant_ok": True,
        },
    }
    for file_name, payload in payloads.items():
        (result_dir / file_name).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_bundle_e_decorator_injects_product_sections_and_digest(tmp_path):
    namespace = _load_bundle_e_namespace()
    original_write_text = namespace["_BUNDLE_E_ORIGINAL_PATH_WRITE_TEXT"]
    try:
        _write_bundle_e_artifacts(tmp_path)
        report = tmp_path / "autoplay-campaign-report.html"

        report.write_text(
            "<html><body><h1>Autoplay Campaign Report</h1><p>Existing report body.</p></body></html>",
            encoding="utf-8",
        )

        rendered = report.read_text(encoding="utf-8")
        assert 'id="bundle-e-product-reporting"' in rendered
        assert "Artifact Manifest Digest" in rendered
        assert "manifest_byte_size" in rendered
        assert "manifest_sha256" in rendered
        assert "embedded_artifact_count" in rendered
        assert "zip_manifest_valid_count" in rendered
        assert "invariant_ok" in rendered

        for title in (
            "Survival Exit Criteria",
            "Transcript Payload Budget",
            "Long-Run Dry-Run Projection",
            "Content Exhaustion Forecast",
            "NPC Agency / Schedule Evidence",
            "Economy / Resource Pressure",
        ):
            assert title in rendered

        assert '<nav class="bundle-e-nav"' in rendered
        assert '<details class="bundle-e-raw-details">' in rendered
        assert "Raw JSON details" in rendered
        assert "Existing report body." in rendered
    finally:
        Path.write_text = original_write_text


def test_bundle_e_raw_json_is_collapsed_by_default(tmp_path):
    namespace = _load_bundle_e_namespace()
    try:
        _write_bundle_e_artifacts(tmp_path)
        injector = namespace["_bundle_e_inject_product_sections_into_html"]
        rendered = injector(
            tmp_path / "autoplay-campaign-report.html",
            "<html><body><h1>Campaign Chronicle</h1></body></html>",
        )

        raw_start = rendered.index('<details class="bundle-e-raw-details">')
        raw_end = rendered.index("</details>", raw_start)
        raw_details_opening_tag = rendered[raw_start : rendered.index(">", raw_start) + 1]
        raw_details_html = rendered[raw_start:raw_end]

        assert " open" not in raw_details_opening_tag
        assert '<pre class="bundle-e-raw-json">' in raw_details_html
        assert 'survival-exit-criteria-summary.json' in rendered
    finally:
        Path.write_text = namespace["_BUNDLE_E_ORIGINAL_PATH_WRITE_TEXT"]
