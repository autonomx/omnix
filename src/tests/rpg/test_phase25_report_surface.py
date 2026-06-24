from __future__ import annotations

from app.rpg.report_surface_runtime import attach_report_surface_to_summary


def test_phase25_report_surface_smoke() -> None:
    result = attach_report_surface_to_summary({"transcript_rows": [{"turn_result": {}}]})

    assert result["report_surface"]["source"] == "phase25_report_surface_runtime_v1"
    assert result["report_surface"]["turn_count"] == 1
    row_surface = result["transcript_rows"][0]["report_surface"]
    assert "world" in row_surface["sections"]
    assert "quest" in row_surface["sections"]
