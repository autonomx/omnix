import json
from pathlib import Path

from app.rpg.autoplay_report_size_guard import REPORT_JSON_NAME, cap_oversized_autoplay_reports


def test_phase13_26_post_run_summary_preserves_materialization_events(tmp_path: Path):
    summary_path = tmp_path / "autoplay-report-size-guard-summary.json"
    existing = {
        "ok": True,
        "source": "autoplay_report_size_guard_v1",
        "materialization_guard_source": "autoplay_report_materialization_guard_v3",
        "file_result": {
            "ok": True,
            "source": "autoplay_report_size_guard_v1",
            "capped_files": [
                {
                    "path": str(tmp_path / REPORT_JSON_NAME),
                    "original_size_bytes": 64_708_125,
                    "new_size_bytes": 467,
                    "limit_bytes": 26_214_400,
                    "source": "autoplay_report_materialization_guard_v3",
                    "guarded_api": "open.write",
                }
            ],
        },
        "zip_results": [],
    }
    summary_path.write_text(json.dumps(existing), encoding="utf-8")

    report_path = tmp_path / REPORT_JSON_NAME
    report_path.write_text('{"ok": true}', encoding="utf-8")
    result = cap_oversized_autoplay_reports(tmp_path)

    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert result["ok"] is True
    assert payload["materialization_guard_source"] == "autoplay_report_materialization_guard_v3"
    capped = payload["file_result"]["capped_files"]
    assert capped
    assert capped[0]["guarded_api"] == "open.write"
    assert capped[0]["original_size_bytes"] == 64_708_125
