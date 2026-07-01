from __future__ import annotations

from typing import Any

from .field_check import check_fields
from .result_display import ResultDisplay, result_display_payload


def validated_result_display(payload: dict[str, Any]) -> ResultDisplay:
    checked = check_fields(payload)
    if checked["ok"]:
        return result_display_payload(payload)
    return result_display_payload(
        {
            "ok": False,
            "item_id": str(payload.get("item_id") or ""),
            "summary": "Missing required result fields.",
            "review": True,
        }
    )
