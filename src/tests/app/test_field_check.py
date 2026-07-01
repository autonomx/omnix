from __future__ import annotations

from app.assist_core.field_check import check_fields


def test_check_fields_reports_missing() -> None:
    assert check_fields({"ok": True}) == {"ok": False, "missing": ["item_id", "summary", "review"]}


def test_check_fields_accepts_complete_payload() -> None:
    assert check_fields({"ok": True, "item_id": "p1", "summary": "s", "review": True}) == {"ok": True, "missing": []}
