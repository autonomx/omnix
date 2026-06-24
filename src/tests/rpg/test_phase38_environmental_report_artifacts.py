from __future__ import annotations

import json
import zipfile

from app.rpg.environmental_report_artifacts import (
    ENVIRONMENTAL_PANEL_HTML_NAME,
    ENVIRONMENTAL_PANEL_JSON_NAME,
    append_environmental_report_artifacts_to_zip,
    environmental_panel_artifact_payload,
    write_environmental_report_artifacts,
)


def _row():
    return {
        "turn_index": 2,
        "report_surface": {
            "sections": {
                "environmental_panel": {
                    "ready": True,
                    "badges": ("high", "changed"),
                    "triggers": ("weather_changed",),
                    "changed_fields": ("weather",),
                    "perceptual_fields": ("sights",),
                    "visible_activity": [{"kind": "npc", "text": "Bran: argues with a courier"}],
                    "opportunities": ("conversation_or_rumor",),
                    "panel_cues": ("Changed: weather",),
                }
            }
        },
    }


def test_phase38_environmental_panel_payload_contains_html_and_json() -> None:
    payload = environmental_panel_artifact_payload([_row()])

    assert payload["ok"] is True
    assert payload["summary"]["changed_field_counts"] == {"weather": 1}
    assert ENVIRONMENTAL_PANEL_JSON_NAME in payload["json_filename"]
    assert "Environmental Panel" in payload["html_text"]
    assert "Bran: argues with a courier" in payload["html_text"]


def test_phase38_writes_environmental_artifacts(tmp_path) -> None:
    result = write_environmental_report_artifacts(tmp_path, [_row()])

    assert result["ok"] is True
    payload = json.loads((tmp_path / ENVIRONMENTAL_PANEL_JSON_NAME).read_text(encoding="utf-8"))
    assert payload["summary"]["opportunity_counts"] == {"conversation_or_rumor": 1}
    assert "Changed: weather" in (tmp_path / ENVIRONMENTAL_PANEL_HTML_NAME).read_text(encoding="utf-8")


def test_phase38_appends_environmental_artifacts_to_zip(tmp_path) -> None:
    zip_path = tmp_path / "autoplay-campaign-results.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("summary.json", "{}")

    result = append_environmental_report_artifacts_to_zip(zip_path, [_row()])

    assert result["ok"] is True
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = set(zf.namelist())
    assert "environment/environmental-panel.json" in names
    assert "environment/environmental-panel.html" in names
