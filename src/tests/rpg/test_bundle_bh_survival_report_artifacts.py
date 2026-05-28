from __future__ import annotations

import json
import zipfile

from app.rpg.survival_report_artifacts import (
    SURVIVAL_METRICS_HTML_NAME,
    SURVIVAL_METRICS_JSON_NAME,
    SURVIVAL_READINESS_HTML_NAME,
    SURVIVAL_READINESS_JSON_NAME,
    SURVIVAL_SUMMARY_HTML_NAME,
    SURVIVAL_SUMMARY_JSON_NAME,
    append_survival_report_artifacts_to_zip,
    attach_survival_artifact_manifest,
    survival_metrics_artifact_payload,
    write_survival_report_artifacts,
)
from tests.rpg.autoplay.survival_report_artifacts import (
    write_survival_report_artifacts as autoplay_write_survival_report_artifacts,
)


def _rows():
    return [
        {
            "turn": 1,
            "turn_contract": {
                "survival": {"hunger": 10, "thirst": 22, "fatigue": 30},
                "survival_pressure": {"hunger": "low", "thirst": "low", "fatigue": "moderate"},
                "survival_tick_result": {
                    "applied": True,
                    "reason": "standard_turn",
                    "turn_id": "turn:1",
                },
            },
        },
        {
            "turn": 2,
            "result": {
                "survival": {"hunger": 80, "thirst": 92, "fatigue": 50},
                "survival_pressure": {"hunger": "critical", "thirst": "critical", "fatigue": "high"},
                "survival_result": {
                    "ok": False,
                    "action_category": "survival",
                    "action": "drink_water",
                    "blocked_reason": "no_water_available",
                },
            },
        },
    ]


def test_bundle_bh_builds_survival_artifact_payload() -> None:
    payload = survival_metrics_artifact_payload(_rows())

    assert payload["json_filename"] == SURVIVAL_METRICS_JSON_NAME
    assert payload["html_filename"] == SURVIVAL_METRICS_HTML_NAME
    assert payload["summary_json_filename"] == SURVIVAL_SUMMARY_JSON_NAME
    assert payload["summary_html_filename"] == SURVIVAL_SUMMARY_HTML_NAME
    assert payload["readiness_json_filename"] == SURVIVAL_READINESS_JSON_NAME
    assert payload["readiness_html_filename"] == SURVIVAL_READINESS_HTML_NAME
    assert payload["metrics"]["summary"]["passive_tick_count"] == 1
    assert payload["metrics"]["summary"]["blocked_survival_action_count"] == 1
    assert payload["compact_summary"]["format_version"] == "survival_report_polish_v1"
    assert payload["survival_readiness"]["format_version"] == "survival_readiness_v1"
    assert payload["survival_readiness"]["advisory_only"] is True
    assert "Survival Report Metrics" in payload["html_text"]
    assert "Survival Summary" in payload["summary_html_text"]
    assert "Survival Readiness" in payload["readiness_html_text"]
    metrics = json.loads(payload["json_text"])
    summary = json.loads(payload["summary_json_text"])
    readiness = json.loads(payload["readiness_json_text"])
    assert metrics["format_version"] == "survival_report_metrics_v2"
    assert metrics["advisory_gates"]["advisory_only"] is True
    assert summary["status"] in {"healthy", "watch", "warning"}
    assert readiness["format_version"] == "survival_readiness_v1"


def test_bundle_bh_writes_json_and_html_report_artifacts(tmp_path) -> None:
    result = write_survival_report_artifacts(tmp_path, _rows())

    assert result["ok"] is True
    assert result["survival_readiness"]["format_version"] == "survival_readiness_v1"
    json_path = tmp_path / SURVIVAL_METRICS_JSON_NAME
    html_path = tmp_path / SURVIVAL_METRICS_HTML_NAME
    summary_json_path = tmp_path / SURVIVAL_SUMMARY_JSON_NAME
    summary_html_path = tmp_path / SURVIVAL_SUMMARY_HTML_NAME
    readiness_json_path = tmp_path / SURVIVAL_READINESS_JSON_NAME
    readiness_html_path = tmp_path / SURVIVAL_READINESS_HTML_NAME
    assert json_path.exists()
    assert html_path.exists()
    assert summary_json_path.exists()
    assert summary_html_path.exists()
    assert readiness_json_path.exists()
    assert readiness_html_path.exists()
    metrics = json.loads(json_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_json_path.read_text(encoding="utf-8"))
    readiness = json.loads(readiness_json_path.read_text(encoding="utf-8"))
    assert metrics["summary"]["blocked_survival_action_count"] == 1
    assert metrics["format_version"] == "survival_report_metrics_v2"
    assert "advisory_gates" in metrics
    assert summary["format_version"] == "survival_report_polish_v1"
    assert readiness["format_version"] == "survival_readiness_v1"
    html = html_path.read_text(encoding="utf-8")
    summary_html = summary_html_path.read_text(encoding="utf-8")
    readiness_html = readiness_html_path.read_text(encoding="utf-8")
    assert "no_water_available" in html
    assert "Advisory Survival Gates" in html
    assert "Survival Summary" in summary_html
    assert "Survival Readiness" in readiness_html


def test_bundle_bh_appends_survival_artifacts_to_zip(tmp_path) -> None:
    zip_path = tmp_path / "autoplay-campaign-results.zip"

    result = append_survival_report_artifacts_to_zip(zip_path, _rows(), prefix="reports")

    assert result["ok"] is True
    assert result["survival_readiness"]["format_version"] == "survival_readiness_v1"
    assert result["zip_members"] == [
        f"reports/{SURVIVAL_METRICS_JSON_NAME}",
        f"reports/{SURVIVAL_METRICS_HTML_NAME}",
        f"reports/{SURVIVAL_SUMMARY_JSON_NAME}",
        f"reports/{SURVIVAL_SUMMARY_HTML_NAME}",
        f"reports/{SURVIVAL_READINESS_JSON_NAME}",
        f"reports/{SURVIVAL_READINESS_HTML_NAME}",
    ]
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = set(zf.namelist())
        assert f"reports/{SURVIVAL_METRICS_JSON_NAME}" in names
        assert f"reports/{SURVIVAL_METRICS_HTML_NAME}" in names
        assert f"reports/{SURVIVAL_SUMMARY_JSON_NAME}" in names
        assert f"reports/{SURVIVAL_SUMMARY_HTML_NAME}" in names
        assert f"reports/{SURVIVAL_READINESS_JSON_NAME}" in names
        assert f"reports/{SURVIVAL_READINESS_HTML_NAME}" in names
        metrics = json.loads(zf.read(f"reports/{SURVIVAL_METRICS_JSON_NAME}").decode("utf-8"))
        summary = json.loads(zf.read(f"reports/{SURVIVAL_SUMMARY_JSON_NAME}").decode("utf-8"))
        readiness = json.loads(zf.read(f"reports/{SURVIVAL_READINESS_JSON_NAME}").decode("utf-8"))
    assert metrics["summary"]["passive_tick_count"] == 1
    assert metrics["format_version"] == "survival_report_metrics_v2"
    assert summary["format_version"] == "survival_report_polish_v1"
    assert readiness["format_version"] == "survival_readiness_v1"


def test_bundle_bh_attaches_survival_artifact_manifest() -> None:
    artifact_result = {
        "json_path": "out/survival-report-metrics.json",
        "html_path": "out/survival-report-metrics.html",
        "summary_json_path": "out/survival-summary.json",
        "summary_html_path": "out/survival-summary.html",
        "readiness_json_path": "out/survival-readiness.json",
        "readiness_html_path": "out/survival-readiness.html",
        "zip_path": "out/results.zip",
        "zip_members": [
            "reports/survival-report-metrics.json",
            "reports/survival-summary.json",
            "reports/survival-readiness.json",
        ],
        "metrics": {"summary": {"turns_observed": 2}},
        "compact_summary": {"status": "watch"},
        "survival_readiness": {"status": "watch", "format_version": "survival_readiness_v1"},
    }

    manifest = attach_survival_artifact_manifest({"artifacts": []}, artifact_result)

    assert manifest["survival_report_metrics"] == {"summary": {"turns_observed": 2}}
    assert manifest["survival_summary"] == {"status": "watch"}
    assert manifest["survival_readiness"] == {"status": "watch", "format_version": "survival_readiness_v1"}
    assert [item["kind"] for item in manifest["artifacts"]] == [
        "survival_metrics_json",
        "survival_metrics_html",
        "survival_summary_json",
        "survival_summary_html",
        "survival_readiness_json",
        "survival_readiness_html",
        "survival_metrics_zip_member",
        "survival_summary_zip_member",
        "survival_readiness_zip_member",
    ]


def test_bundle_bh_autoplay_wrapper_exports_writer(tmp_path) -> None:
    result = autoplay_write_survival_report_artifacts(tmp_path, _rows())

    assert result["ok"] is True
    assert result["survival_readiness"]["format_version"] == "survival_readiness_v1"
    assert (tmp_path / SURVIVAL_METRICS_JSON_NAME).exists()
    assert (tmp_path / SURVIVAL_METRICS_HTML_NAME).exists()
    assert (tmp_path / SURVIVAL_SUMMARY_JSON_NAME).exists()
    assert (tmp_path / SURVIVAL_SUMMARY_HTML_NAME).exists()
    assert (tmp_path / SURVIVAL_READINESS_JSON_NAME).exists()
    assert (tmp_path / SURVIVAL_READINESS_HTML_NAME).exists()
