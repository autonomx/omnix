from __future__ import annotations

from app.assist_core.result_display import result_display_payload


def test_result_display_fields() -> None:
    payload = result_display_payload({"ok": True})

    assert payload["ok"] is True
    assert payload["review"] is True
