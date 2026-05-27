from __future__ import annotations

import argparse
import json
from pathlib import Path


_FRAGMENT = (
    Path(__file__).resolve().parent
    / "autoplay_llm_campaign_parts"
    / "zzzzzzzzzzzzzzzzzzzzzzzzz_bundle_aq_readiness_report_projection_reconciliation.pyfrag"
)


def _load_bundle_aq_namespace(extra_globals=None):
    namespace = {"__name__": "_bundle_aq_readiness_report_projection_reconciliation_test"}
    if extra_globals:
        namespace.update(extra_globals)
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), namespace, namespace)
    return namespace


def _write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _seed_aq_case(parent: Path):
    unzipped = parent / "autoplay-campaign-results-unzipped"
    unzipped.mkdir(parents=True)
    for directory in (parent, unzipped):
        _write_json(directory / "content-exhaustion-forecast-summary.json", {"ok": True, "advisory_ok": True, "classification": "graph_capacity_sufficient", "turns_until_content_exhaustion_estimate": 3834, "source": "bundle_ap"})
        _write_json(directory / "npc-agency-schedule-summary.json", {"ok": True, "advisory_ok": True, "npc_count": 4, "schedule_event_count": 16, "bounded_action_count": 12, "source": "bundle_ap"})
        _write_json(directory / "economy-resource-pressure-summary.json", {"ok": True, "advisory_ok": True, "service_count": 13, "pressure_rule_count": 5, "merchant_stock_item_count": 12, "source": "bundle_ap"})
        _write_json(directory / "artifact-manifest.json", {"ok": True, "nonfatal_finalization_recovered_manifest_tolerance": True, "checks": {"artifact_export_invariant_tolerated": True}})
        _write_json(directory / "essential-mirror-consistency-summary.json", {"ok": True, "artifact_manifest_valid": True, "missing_core_files": []})
        _write_json(directory / "autoplay-health.json", {"ok": True})
        _write_json(
            directory / "readiness-report-projection-summary.json",
            {
                "ok": False,
                "advisory_ok": False,
                "checks": {
                    "all_report_sections_ok": False,
                    "manifest_final_write_after_sidecars_ok": False,
                },
                "failed_checks": [
                    "all_report_sections_ok",
                    "manifest_final_write_after_sidecars",
                    "readiness_ok",
                    "all_sections_manifest_embedded",
                ],
                "sections": [
                    {"id": "content-exhaustion-forecast", "ok": False, "artifact_ok": False, "advisory_ok": False, "manifest_embedded": False, "summary": {}},
                    {"id": "npc-agency-schedule", "ok": False, "artifact_ok": False, "advisory_ok": False, "manifest_embedded": False, "summary": {}},
                    {"id": "economy-resource-pressure", "ok": False, "artifact_ok": False, "advisory_ok": False, "manifest_embedded": False, "summary": {}},
                    {"id": "long-run-dry-run-projection", "ok": False, "artifact_ok": False, "advisory_ok": True, "summary": {"advisory_ok": True}},
                    {"id": "survival-exit-criteria", "ok": False, "artifact_ok": False, "advisory_ok": False, "summary": {}},
                ],
            },
        )


def test_bundle_aq_reconciles_report_projection_sections_and_keeps_survival_blocker(tmp_path):
    namespace = _load_bundle_aq_namespace()
    parent = tmp_path / "autoplay-output"
    _seed_aq_case(parent)

    result = namespace["_bundle_aq_finalize_output_dir"](str(parent))

    assert result["ok"] is True
    unzipped = parent / "autoplay-campaign-results-unzipped"
    report = json.loads((unzipped / "readiness-report-projection-summary.json").read_text(encoding="utf-8"))
    sections = {section["id"]: section for section in report["sections"]}
    assert sections["content-exhaustion-forecast"]["ok"] is True
    assert sections["npc-agency-schedule"]["ok"] is True
    assert sections["economy-resource-pressure"]["ok"] is True
    assert sections["long-run-dry-run-projection"]["ok"] is True
    assert sections["long-run-dry-run-projection"]["advisory_only"] is True
    assert sections["survival-exit-criteria"]["ok"] is False
    assert sections["survival-exit-criteria"]["bundle_aq_real_remaining_gameplay_blocker"] is True
    assert report["remaining_real_gameplay_blockers"] == ["survival-exit-criteria"]
    assert "manifest_final_write_after_sidecars" not in report["failed_checks"]
    assert "all_sections_manifest_embedded" not in report["failed_checks"]
    assert "survival-exit-criteria" in report["failed_checks"]
    assert "all_report_sections_ok" in report["failed_checks"]


def test_bundle_aq_all_sections_pass_when_survival_passes(tmp_path):
    namespace = _load_bundle_aq_namespace()
    parent = tmp_path / "autoplay-output"
    _seed_aq_case(parent)
    for directory in (parent, parent / "autoplay-campaign-results-unzipped"):
        report = json.loads((directory / "readiness-report-projection-summary.json").read_text(encoding="utf-8"))
        for section in report["sections"]:
            if section["id"] == "survival-exit-criteria":
                section["ok"] = True
                section["artifact_ok"] = True
                section["advisory_ok"] = True
        _write_json(directory / "readiness-report-projection-summary.json", report)

    namespace["_bundle_aq_finalize_output_dir"](str(parent))
    report = json.loads((parent / "autoplay-campaign-results-unzipped" / "readiness-report-projection-summary.json").read_text(encoding="utf-8"))

    assert report["ok"] is True
    assert report["advisory_ok"] is True
    assert report["failed_checks"] == []
    assert report["checks"]["all_report_sections_ok"] is True


def test_bundle_aq_health_is_patched_from_report_status(tmp_path):
    namespace = _load_bundle_aq_namespace()
    parent = tmp_path / "autoplay-output"
    _seed_aq_case(parent)

    namespace["_bundle_aq_finalize_output_dir"](str(parent))
    health = json.loads((parent / "autoplay-campaign-results-unzipped" / "autoplay-health.json").read_text(encoding="utf-8"))

    assert health["readiness_report_projection_ok"] is False
    assert health["readiness_report_projection_advisory_ok"] is True
    assert health["remaining_real_gameplay_blockers"] == ["survival-exit-criteria"]
    assert health["bundle_aq_readiness_report_projection_reconciled"] is True


def test_bundle_aq_main_wrapper_runs_with_namespace_args(tmp_path):
    parent = tmp_path / "autoplay-output"
    _seed_aq_case(parent)

    def main(argv=None):
        return 0

    namespace = _load_bundle_aq_namespace({"main": main})

    result = namespace["main"](argparse.Namespace(output_dir=str(parent)))

    assert result == 0
    assert namespace["BUNDLE_AQ_ATEXIT_RESULT"]["ok"] is True
    report = json.loads((parent / "autoplay-campaign-results-unzipped" / "readiness-report-projection-summary.json").read_text(encoding="utf-8"))
    assert report["bundle_aq_readiness_report_projection_reconciled"] is True


def test_bundle_aq_write_text_wrapper_triggers_projection_reconciliation(tmp_path):
    parent = tmp_path / "autoplay-output"
    _seed_aq_case(parent)
    _load_bundle_aq_namespace()
    unzipped = parent / "autoplay-campaign-results-unzipped"

    (unzipped / "readiness-report-projection-summary.json").write_text(json.dumps({"ok": False, "failed_checks": ["manifest_final_write_after_sidecars"], "sections": []}), encoding="utf-8")

    report = json.loads((unzipped / "readiness-report-projection-summary.json").read_text(encoding="utf-8"))
    assert report["bundle_aq_readiness_report_projection_reconciled"] is True
    assert "manifest_final_write_after_sidecars" not in report["failed_checks"]
