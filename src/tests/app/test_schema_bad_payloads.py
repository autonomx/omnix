from __future__ import annotations

from app.assist_core.field_check import check_fields
from app.assist_core.result_display import result_display_payload


def test_bad_payload_reports_missing_fields() -> None:
    payload = check_fields({})

    assert payload["ok"] is False
    assert "ok" in payload["missing"]
    assert "summary" in payload["missing"]


def test_display_handles_empty_payload() -> None:
    payload = result_display_payload({})

    assert payload["ok"] is False
    assert payload["item_id"] == ""
    assert payload["summary"] == ""
    assert payload["review"] is True
